"""
Zabbix Entegrasyonu
===================
Lumen anomalilerini Zabbix'e trapper item olarak gönderir.

Calisma mantigi:
- Her anomali icin Zabbix'te dinamik trapper item olusturur
- Item key: lumen.anomaly[SERVIS_ADI,KANAL_KODU]
- Severity: WARNING olarak gönderilir (ayarlanabilir)
- DRY_RUN=true iken gönderme yapmaz, sadece loglar
- Trigger otomatik olusturulur

Item formati:
  Key:   lumen.anomaly[MMS_GET_CUSTOMER,708]
  Value: 1 (anomali var) / 0 (normal)
  Type:  Trapper
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Konfigurasyon ─────────────────────────────────────────
ZABBIX_URL = os.environ.get("ZABBIX_URL", "")
ZABBIX_USER = os.environ.get("ZABBIX_USER", "Admin")
ZABBIX_PASSWORD = os.environ.get("ZABBIX_PASSWORD", "")
ZABBIX_HOST_ID = os.environ.get("ZABBIX_HOST_ID", "23401")
ZABBIX_DRY_RUN = os.environ.get("ZABBIX_DRY_RUN", "true").lower() == "true"

# Zabbix'e gonderilecek severity - simdilik WARNING
ZABBIX_SEVERITY = int(os.environ.get("ZABBIX_SEVERITY", "2"))  # 0=Not, 1=Info, 2=Warning, 3=Average, 4=High, 5=Disaster
ZABBIX_SEVERITY_MAP = {0: "Not classified", 1: "Information", 2: "Warning", 3: "Average", 4: "High", 5: "Disaster"}

# Lumen severity -> Zabbix severity
LUMEN_TO_ZABBIX_SEV = {
    "WARNING": 2,   # Warning
    "HIGH": 3,      # Average
    "DISASTER": 4,  # High (simdilik High, Disaster degil)
}


class ZabbixIntegration:
    def __init__(self, db_dsn: str = None):
        self._token: Optional[str] = None
        self._token_zaman: Optional[datetime] = None
        self._olusturulan_itemlar: set = set()
        self._session = None
        self._db_dsn = db_dsn
        # Config - DB'den veya env'den
        self._url = ZABBIX_URL
        self._user = ZABBIX_USER
        self._password = ""
        self._host_id = ZABBIX_HOST_ID
        self._dry_run = ZABBIX_DRY_RUN
        self._severity = ZABBIX_SEVERITY
        logger.info(
            f"Zabbix entegrasyon baslatildi | "
            f"Host: {self._host_id} | "
            f"DRY_RUN: {self._dry_run}"
        )

    async def _config_yukle(self):
        """DB'den Zabbix konfigurasyonunu yukler."""
        if not self._db_dsn:
            return
        try:
            import asyncpg
            from cryptography.fernet import Fernet
            import os as _os
            conn = await asyncpg.connect(
                self._db_dsn.replace("postgresql+asyncpg://", "postgresql://")
            )
            try:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='zabbix'"
                )
                if not row or not row["enabled"]:
                    return
                config = dict(row["config"]) if row["config"] else {}
                secrets = dict(row["secrets"]) if row["secrets"] else {}

                # Secret coz
                secret_key = _os.environ.get("LUMEN_SECRET_KEY", "")
                if secret_key:
                    f = Fernet(secret_key.encode())
                    for k, v in secrets.items():
                        try:
                            secrets[k] = f.decrypt(v.encode()).decode()
                        except Exception:
                            pass

                self._url = config.get("url", self._url)
                self._user = config.get("user", self._user)
                self._host_id = str(config.get("host_id", self._host_id))
                self._password = secrets.get("password", "")
                dry = config.get("dry_run", True)
                self._dry_run = dry if isinstance(dry, bool) else str(dry).lower() == "true"
                sev = config.get("severity", self._severity)
                self._severity = int(sev) if sev else self._severity
                logger.info(f"Zabbix config DB'den yuklendi: {self._url} host={self._host_id} dry={self._dry_run}")
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Zabbix config yukleme hatasi: {e}")

    async def _session_al(self):
        """aiohttp session dondurur."""
        if self._session is None or self._session.closed:
            try:
                import aiohttp
                self._session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp yuklu degil: pip install aiohttp")
                return None
        return self._session

    async def _api(self, method: str, params: dict) -> Optional[dict]:
        """Zabbix API cagrisi yapar."""
        if not ZABBIX_URL:
            return None

        session = await self._session_al()
        if not session:
            return None

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }

        try:
            async with session.post(
                f"{self._url}/api_jsonrpc.php",
                json=body,
                headers=headers,
                ssl=False,
                timeout=10
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    logger.error(f"Zabbix API hatasi ({method}): {data['error']}")
                    return None
                return data.get("result")
        except Exception as e:
            logger.error(f"Zabbix API baglanti hatasi: {e}")
            return None

    async def login(self) -> bool:
        """Zabbix'e giris yapar, token alir."""
        await self._config_yukle()

        if not self._url or not self._password:
            logger.warning("Zabbix URL veya sifre eksik")
            return False

        # Token 8 saatte bir yenile
        if self._token and self._token_zaman:
            gecen = (datetime.utcnow() - self._token_zaman).total_seconds()
            if gecen < 28800:
                return True

        result = await self._api("user.login", {
            "username": self._user,
            "password": self._password
        })

        if result:
            self._token = result
            self._token_zaman = datetime.utcnow()
            logger.info("Zabbix login basarili")
            return True

        logger.error("Zabbix login basarisiz")
        return False

    def _item_key(self, service: str, channel: str) -> str:
        """Zabbix item key olusturur."""
        # Zabbix key kurallari: bosluk yok, ozel karakter yok
        svc = service.replace(" ", "_").replace("/", "_")[:50]
        ch = str(channel).replace(" ", "_")[:10]
        return f"lumen.anomaly[{svc},{ch}]"

    async def _item_olustur_veya_al(self, service: str, channel: str) -> Optional[str]:
        """Item varsa ID'sini dondurur, yoksa olusturur."""
        key = self._item_key(service, channel)

        if key in self._olusturulan_itemlar:
            # Onceden olusturuldu, ID'yi al
            result = await self._api("item.get", {
                "output": ["itemid"],
                "hostids": [ZABBIX_HOST_ID],
                "filter": {"key_": key}
            })
            if result and len(result) > 0:
                return result[0]["itemid"]

        # Item mevcut mu kontrol et
        result = await self._api("item.get", {
            "output": ["itemid"],
            "hostids": [ZABBIX_HOST_ID],
            "filter": {"key_": key}
        })

        if result and len(result) > 0:
            self._olusturulan_itemlar.add(key)
            return result[0]["itemid"]

        # Item yok, olustur
        item_name = f"Lumen Anomali: {service} [{channel}]"
        result = await self._api("item.create", {
            "name": item_name,
            "key_": key,
            "hostid": ZABBIX_HOST_ID,
            "type": 2,          # Trapper
            "value_type": 3,    # Unsigned int
            "delay": "0",
            "description": f"Lumen AIOps anomali tespiti - {service} kanali {channel}",
            "tags": [
                {"tag": "source", "value": "lumen-aiops"},
                {"tag": "service", "value": service[:50]},
                {"tag": "channel", "value": str(channel)}
            ]
        })

        if result and "itemids" in result:
            item_id = result["itemids"][0]
            self._olusturulan_itemlar.add(key)
            logger.info(f"Zabbix item olusturuldu: {key} (id={item_id})")

            # Trigger olustur
            await self._trigger_olustur(item_id, key, service, channel)
            return item_id

        logger.error(f"Zabbix item olusturulamadi: {key}")
        return None

    async def _trigger_olustur(self, item_id: str, key: str, service: str, channel: str):
        """Item icin trigger olusturur."""
        # Mevcut trigger var mi
        mevcut = await self._api("trigger.get", {
            "output": ["triggerid"],
            "hostids": [ZABBIX_HOST_ID],
            "filter": {"description": f"Lumen Anomali: {service} [{channel}]"}
        })
        if mevcut and len(mevcut) > 0:
            return

        await self._api("trigger.create", {
            "description": f"Lumen Anomali: {service} [{channel}]",
            "expression": f"last(/{ZABBIX_HOST_ID}/{key})=1",  # Simplified
            "priority": ZABBIX_SEVERITY,
            "manual_close": 1,
            "tags": [
                {"tag": "source", "value": "lumen-aiops"},
                {"tag": "service", "value": service[:50]}
            ]
        })

    async def anomali_gonder(self, anomali: dict) -> bool:
        """
        Anomaliyi Zabbix'e gönderir.
        DRY_RUN=true ise sadece loglar.
        """
        service = anomali.get("service", "")
        channel = anomali.get("channel_code", "unknown")
        severity = anomali.get("severity", "WARNING")

        if not service:
            return False

        zabbix_sev = LUMEN_TO_ZABBIX_SEV.get(severity, 2)
        sev_str = ZABBIX_SEVERITY_MAP.get(zabbix_sev, "Warning")

        if self._dry_run:
            logger.info(
                f"[DRY_RUN] Zabbix'e gönderilecekti: "
                f"{service}[{channel}] | {severity} → {sev_str}"
            )
            return True

        if not await self.login():
            return False

        try:
            import aiohttp

            key = self._item_key(service, channel)

            # Item olustur veya al
            await self._item_olustur_veya_al(service, channel)

            # zabbix_sender ile deger gonder (HTTP trapper)
            sender_data = {
                "request": "sender data",
                "data": [{
                    "host": "lumen-aiops",
                    "key": key,
                    "value": "1",
                    "clock": int(datetime.utcnow().timestamp())
                }]
            }

            session = await self._session_al()
            if not session:
                return False

            # Trapper port 10051
            zabbix_ip = ZABBIX_URL.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0]
            async with session.post(
                f"http://{zabbix_ip}:10051",
                json=sender_data,
                timeout=5
            ) as resp:
                logger.info(f"Zabbix sender: {service}[{channel}] gönderildi")
                return True

        except Exception as e:
            logger.error(f"Zabbix anomali gönderme hatasi: {e}")
            return False

    async def anomali_temizle(self, service: str, channel: str) -> bool:
        """
        Anomali çözüldüğünde Zabbix item'ini 0'a çeker.
        """
        if self._dry_run:
            logger.info(f"[DRY_RUN] Zabbix temizlenecekti: {service}[{channel}]")
            return True

        if not await self.login():
            return False

        try:
            key = self._item_key(service, channel)
            zabbix_ip = ZABBIX_URL.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0]

            sender_data = {
                "request": "sender data",
                "data": [{
                    "host": "lumen-aiops",
                    "key": key,
                    "value": "0",
                    "clock": int(datetime.utcnow().timestamp())
                }]
            }

            session = await self._session_al()
            if session:
                async with session.post(
                    f"http://{zabbix_ip}:10051",
                    json=sender_data,
                    timeout=5
                ) as resp:
                    return True
        except Exception as e:
            logger.error(f"Zabbix temizleme hatasi: {e}")
        return False

    async def baglanti_test(self) -> dict:
        """Zabbix baglantisini test eder."""
        if not ZABBIX_URL:
            return {"status": "error", "message": "ZABBIX_URL tanimlanmamis"}

        ok = await self.login()
        if not ok:
            return {"status": "error", "message": "Login basarisiz"}

        # Host kontrol
        result = await self._api("host.get", {
            "output": ["hostid", "host", "name", "status"],
            "hostids": [ZABBIX_HOST_ID]
        })

        if not result:
            return {"status": "error", "message": f"Host {ZABBIX_HOST_ID} bulunamadi"}

        host = result[0]
        return {
            "status": "ok",
            "dry_run": ZABBIX_DRY_RUN,
            "host_id": ZABBIX_HOST_ID,
            "host_name": host.get("name"),
            "host_status": "Aktif" if host.get("status") == "0" else "Pasif",
            "severity": sev_str if 'sev_str' in dir() else ZABBIX_SEVERITY_MAP.get(ZABBIX_SEVERITY)
        }

    async def kapat(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton
_zabbix = None


def zabbix_baslat(db_dsn: str = None) -> ZabbixIntegration:
    global _zabbix
    _zabbix = ZabbixIntegration(db_dsn)
    return _zabbix


def zabbix_al() -> Optional[ZabbixIntegration]:
    return _zabbix
