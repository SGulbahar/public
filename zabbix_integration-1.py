"""
Zabbix Entegrasyonu
===================
Anomalileri Zabbix'e trapper item olarak gönderir.
Config DB'deki integrations tablosundan okunur.
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

LUMEN_TO_ZABBIX_SEV = {"WARNING": 2, "HIGH": 3, "DISASTER": 4}


class ZabbixIntegration:
    def __init__(self, db_dsn: str = None):
        self._db_dsn = db_dsn
        self._token: Optional[str] = None
        self._token_zaman: Optional[datetime] = None
        self._olusturulan_itemlar: set = set()
        # Config - DB'den yuklenir
        self._url = ""
        self._user = "Admin"
        self._password = ""
        self._host_id = os.environ.get("ZABBIX_HOST_ID", "23401")
        self._dry_run = False
        self._enabled = False
        logger.info(f"Zabbix entegrasyon baslatildi | db_dsn={bool(db_dsn)}")

    async def _config_yukle(self):
        """DB'den Zabbix konfigurasyonunu yukler."""
        if not self._db_dsn:
            return
        try:
            import asyncpg
            from cryptography.fernet import Fernet

            conn = await asyncpg.connect(self._db_dsn)
            try:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='zabbix'"
                )
                if not row:
                    logger.warning("Zabbix entegrasyon kaydı bulunamadı")
                    return

                self._enabled = bool(row["enabled"])
                if not self._enabled:
                    logger.info("Zabbix entegrasyonu DB'de pasif")
                    return

                cfg = row["config"]
                sec = row["secrets"]
                config = cfg if isinstance(cfg, dict) else json.loads(cfg or "{}")
                secrets_raw = sec if isinstance(sec, dict) else json.loads(sec or "{}")

                # Secret coz
                secret_key = os.environ.get("LUMEN_SECRET_KEY", "")
                secrets = {}
                if secret_key:
                    f = Fernet(secret_key.encode())
                    for k, v in secrets_raw.items():
                        if v:
                            try:
                                secrets[k] = f.decrypt(v.encode()).decode()
                            except Exception:
                                secrets[k] = v
                else:
                    secrets = secrets_raw

                self._url = config.get("url", "").rstrip("/")
                self._user = config.get("user", "Admin")
                self._host_id = str(config.get("host_id", self._host_id))
                self._password = secrets.get("password", "")
                dry = config.get("dry_run", False)
                self._dry_run = dry if isinstance(dry, bool) else str(dry).lower() == "true"
                sev = config.get("severity", 2)
                self._default_severity = int(sev) if sev else 2

                logger.info(
                    f"Zabbix config yuklendi: url={self._url} "
                    f"host={self._host_id} dry={self._dry_run} "
                    f"pass={'*' * min(len(self._password), 3)}"
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Zabbix config yukleme hatasi: {e}")

    async def _login(self) -> bool:
        """Zabbix'e giris yapar."""
        await self._config_yukle()

        if not self._enabled:
            return False

        if not self._url or not self._password:
            logger.warning(f"Zabbix URL veya sifre eksik (url={bool(self._url)} pass={bool(self._password)})")
            return False

        # Token 8 saatte bir yenile
        if self._token and self._token_zaman:
            if (datetime.utcnow() - self._token_zaman).total_seconds() < 28800:
                return True

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._url}/api_jsonrpc.php",
                    json={
                        "jsonrpc": "2.0",
                        "method": "user.login",
                        "params": {"username": self._user, "password": self._password},
                        "id": 1
                    },
                    headers={"Content-Type": "application/json"},
                    ssl=False,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    text = await resp.text()
                    data = json.loads(text)
                    if "error" in data:
                        logger.error(f"Zabbix login hatasi: {data['error']}")
                        return False
                    result = data.get("result")
                    if result:
                        self._token = result
                        self._token_zaman = datetime.utcnow()
                        logger.info("Zabbix login basarili")
                        return True
                    logger.error(f"Zabbix login: result yok, response={text[:200]}")
                    return False
        except Exception as e:
            logger.error(f"Zabbix login exception: {e}")
            return False

    async def _api(self, method: str, params: dict) -> Optional[dict]:
        """Zabbix API cagrisi."""
        if not self._token:
            return None
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._url}/api_jsonrpc.php",
                    json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._token}"
                    },
                    ssl=False,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    text = await resp.text()
                    data = json.loads(text)
                    if "error" in data:
                        logger.error(f"Zabbix API hatasi ({method}): {data['error']}")
                        return None
                    return data.get("result")
        except Exception as e:
            logger.error(f"Zabbix API exception ({method}): {e}")
            return None

    def _item_key(self, service: str, channel: str) -> str:
        svc = service.replace(" ", "_").replace("/", "_")[:50]
        ch = str(channel).replace(" ", "_")[:10]
        return f"lumen.anomaly[{svc},{ch}]"

    async def _item_hazirla(self, service: str, channel: str):
        """Item yoksa olusturur."""
        key = self._item_key(service, channel)
        if key in self._olusturulan_itemlar:
            return key

        # Mevcut kontrol
        result = await self._api("item.get", {
            "output": ["itemid"],
            "hostids": [self._host_id],
            "filter": {"key_": key}
        })
        if result and len(result) > 0:
            self._olusturulan_itemlar.add(key)
            return key

        # Olustur
        result = await self._api("item.create", {
            "name": f"Lumen Anomali: {service} [{channel}]",
            "key_": key,
            "hostid": self._host_id,
            "type": 2,        # Trapper
            "value_type": 3,  # Unsigned int
            "delay": "0",
            "tags": [
                {"tag": "source", "value": "lumen-aiops"},
                {"tag": "service", "value": service[:50]}
            ]
        })
        if result and "itemids" in result:
            self._olusturulan_itemlar.add(key)
            logger.info(f"Zabbix item olusturuldu: {key}")

            # Trigger olustur
            await self._api("trigger.create", {
                "description": f"Lumen Anomali: {service} [{channel}]",
                "expression": f"last(/{self._host_id}/{key})=1",
                "priority": self._default_severity,
                "manual_close": 1,
                "tags": [{"tag": "source", "value": "lumen-aiops"}]
            })
        return key

    async def anomali_gonder(self, anomali: dict) -> bool:
        """Anomaliyi Zabbix'e gönderir."""
        service = anomali.get("service", "")
        channel = str(anomali.get("channel_code", "unknown"))
        severity = anomali.get("severity", "WARNING")

        if not service:
            return False

        if self._dry_run:
            logger.info(f"[DRY_RUN] Zabbix: {service}[{channel}] {severity}")
            return True

        if not await self._login():
            return False

        try:
            key = await self._item_hazirla(service, channel)

            # Zabbix sender protokolu ile gonder (port 10051)
            import aiohttp, struct
            zabbix_ip = self._url.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]

            sender_data = json.dumps({
                "request": "sender data",
                "data": [{
                    "host": "lumen-aiops",
                    "key": key,
                    "value": "1",
                    "clock": int(datetime.utcnow().timestamp())
                }]
            }).encode()

            # Zabbix sender protokolu header
            header = b"ZBXD\x01" + struct.pack("<Q", len(sender_data))

            import asyncio
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(zabbix_ip, 10051),
                timeout=5
            )
            writer.write(header + sender_data)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(1024), timeout=5)
            writer.close()
            await writer.wait_closed()

            logger.info(f"Zabbix alarm gonderildi: {service}[{channel}] {severity}")
            return True

        except Exception as e:
            logger.error(f"Zabbix anomali gonderme hatasi: {e}")
            return False

    async def baglanti_test(self) -> dict:
        """Baglanti testi."""
        ok = await self._login()
        if not ok:
            return {"status": "error", "message": "Login basarisiz"}

        result = await self._api("host.get", {
            "output": ["hostid", "name", "status"],
            "hostids": [self._host_id]
        })
        if not result:
            return {"status": "error", "message": f"Host {self._host_id} bulunamadi"}

        return {
            "status": "ok",
            "dry_run": self._dry_run,
            "host_name": result[0].get("name"),
            "message": f"Baglanti basarili - {result[0].get('name')}"
        }


_zabbix = None


def zabbix_baslat(db_dsn: str = None) -> "ZabbixIntegration":
    global _zabbix
    _zabbix = ZabbixIntegration(db_dsn)
    return _zabbix


def zabbix_al() -> Optional["ZabbixIntegration"]:
    return _zabbix
