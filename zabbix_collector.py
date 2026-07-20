"""
Zabbix Event Collector
======================
Engine'de background task olarak calisir.
Her 60 saniyede bir Zabbix'ten DISASTER seviyesindeki
aktif alarmları ceker, DB'ye yazar ve log anomalileriyle
korelasyon yapar.

Korelasyon mantigi:
- Zabbix DISASTER alarm geldi
- Son 5 dakikada Lumen'de de anomali var mi?
- Varsa: ortak incident ac veya mevcuta bagla
- Yoksa: sadece zabbix_events tablosuna kaydet

Alarm gürültüsü azaltma:
- Ayni anda gelen cok sayida log anomalisi
  tek bir altyapi kaynakli incident'a baglanir
- NOC 50 alarm yerine 1 incident gorur
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

POLL_SECONDS = int(os.environ.get("ZABBIX_COLLECTOR_POLL", "60"))
KORELASYON_PENCERE_DK = 5  # Zabbix alarm + log anomalisi arasindaki max sure (dakika)
MIN_ANOMALI_ESIK = 3  # Korelasyon icin minimum log anomalisi sayisi


class ZabbixEventCollector:
    def __init__(self, db_dsn: str):
        self._db_dsn = db_dsn
        self._pool = None
        self._aktif = False
        self._task: Optional[asyncio.Task] = None
        logger.info(f"Zabbix Event Collector hazir (poll={POLL_SECONDS}sn)")

    async def baglanti_ac(self):
        import asyncpg
        self._pool = await asyncpg.create_pool(
            self._db_dsn, min_size=1, max_size=3
        )

    async def baglanti_kapat(self):
        if self._pool:
            await self._pool.close()

    async def _zabbix_config_al(self):
        """DB'den Zabbix config ve sifresini cozulmus olarak dondurur."""
        from cryptography.fernet import Fernet
        import json

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config, secrets, enabled FROM integrations WHERE key='zabbix'"
            )
            if not row or not row["enabled"]:
                return None, None, None

            config = dict(row["config"]) if row["config"] else {}
            secrets_raw = dict(row["secrets"]) if row["secrets"] else {}

        secret_key = os.environ.get("LUMEN_SECRET_KEY", "")
        secrets = {}
        if secret_key:
            f = Fernet(secret_key.encode())
            for k, v in secrets_raw.items():
                try:
                    secrets[k] = f.decrypt(v.encode()).decode()
                except Exception:
                    secrets[k] = v
        else:
            secrets = secrets_raw

        url = config.get("url", "").rstrip("/")
        user = config.get("user", "Admin")
        password = secrets.get("password", "")

        if not url or not password:
            return None, None, None

        return url, user, password

    async def _zabbix_login(self, url: str, user: str, password: str) -> Optional[str]:
        """Zabbix'e login olup token dondurur."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    json={"jsonrpc": "2.0", "method": "user.login",
                          "params": {"username": user, "password": password}, "id": 1},
                    ssl=False, timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    data = await r.json()
                    return data.get("result")
        except Exception as e:
            logger.error(f"Zabbix login hatasi: {e}")
            return None

    async def _disaster_alarmları_cek(self, url: str, token: str) -> list:
        """Aktif DISASTER seviyesindeki Zabbix alarmlarini ceker."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"jsonrpc": "2.0", "method": "event.get", "params": {
                        "output": ["eventid", "name", "severity", "clock", "acknowledged"],
                        "severities": [5],  # Sadece DISASTER
                        "value": 1,         # Sadece aktif (cozulmemis)
                        "time_from": int((datetime.utcnow() - timedelta(hours=2)).timestamp()),
                        "selectHosts": ["hostid", "name"],
                        "limit": 50,
                        "sortfield": "clock",
                        "sortorder": "DESC"
                    }, "id": 1},
                    ssl=False, timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    data = await r.json()
                    return data.get("result", [])
        except Exception as e:
            logger.error(f"Zabbix alarm cekme hatasi: {e}")
            return []

    async def _event_kaydet(self, conn, event: dict) -> bool:
        """Zabbix event'ini DB'ye kaydeder. Yeni kayit ise True dondurur."""
        event_id = str(event.get("eventid", ""))
        host_info = event.get("hosts", [{}])
        host_name = host_info[0].get("name", "Bilinmiyor") if host_info else "Bilinmiyor"
        host_id = host_info[0].get("hostid", "") if host_info else ""
        clock = datetime.utcfromtimestamp(int(event.get("clock", 0)))

        try:
            result = await conn.fetchrow("""
                INSERT INTO zabbix_events
                    (zabbix_event_id, name, severity, host_name, host_id, clock, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (zabbix_event_id) DO UPDATE SET
                    synced_at = NOW()
                RETURNING id, (xmax = 0) as yeni
            """, event_id, event.get("name", ""), 5, host_name, host_id, clock)

            return result["yeni"] if result else False
        except Exception as e:
            logger.error(f"Event kaydetme hatasi: {e}")
            return False

    async def _korelasyon_yap(self, conn, event: dict):
        """
        Zabbix DISASTER alarmi ile log anomalilerini korelasyon yapar.
        
        Mantik:
        - Son KORELASYON_PENCERE_DK dakikada log anomalisi var mi?
        - Varsa ve sayisi esigi geciyorsa: altyapi kaynakli incident ac
        """
        clock = datetime.utcfromtimestamp(int(event.get("clock", 0)))
        pencere_baslangic = clock - timedelta(minutes=KORELASYON_PENCERE_DK)
        pencere_bitis = clock + timedelta(minutes=KORELASYON_PENCERE_DK)

        # Bu pencerede kac log anomalisi var
        anomali_sayisi = await conn.fetchval("""
            SELECT COUNT(*) FROM anomaly_events
            WHERE detected_at BETWEEN $1 AND $2
              AND is_false_positive = false
        """, pencere_baslangic, pencere_bitis)

        if anomali_sayisi < MIN_ANOMALI_ESIK:
            return  # Yeterli anomali yok, korelasyon yapma

        # Bu pencerede zaten bir altyapi incident'i var mi
        mevcut_incident = await conn.fetchrow("""
            SELECT id FROM incidents
            WHERE source IN ('zabbix', 'both')
              AND detected_at BETWEEN $1 AND $2
              AND status = 'open'
            LIMIT 1
        """, pencere_baslangic, pencere_bitis)

        host_info = event.get("hosts", [{}])
        host_name = host_info[0].get("name", "Bilinmiyor") if host_info else "Bilinmiyor"
        event_id = str(event.get("eventid", ""))

        if mevcut_incident:
            # Mevcut incident'a Zabbix event'ini bagla
            incident_id = mevcut_incident["id"]
            await conn.execute("""
                UPDATE incidents SET
                    source = 'both',
                    zabbix_event_count = zabbix_event_count + 1,
                    infrastructure_root = true
                WHERE id = $1
            """, incident_id)
            await conn.execute("""
                UPDATE zabbix_events SET correlated_incident_id = $1
                WHERE zabbix_event_id = $2
            """, incident_id, event_id)
            logger.info(
                f"Zabbix alarm mevcut incident'a baglandi: "
                f"INC-{incident_id} <- {event.get('name', '')} ({host_name})"
            )
        else:
            # Yeni altyapi kaynakli incident ac
            etkilenen_servisler = await conn.fetch("""
                SELECT DISTINCT service, channel_code, severity
                FROM anomaly_events
                WHERE detected_at BETWEEN $1 AND $2
                  AND is_false_positive = false
                ORDER BY
                    CASE severity WHEN 'DISASTER' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END
                LIMIT 20
            """, pencere_baslangic, pencere_bitis)

            servis_listesi = ", ".join([r["service"] for r in etkilenen_servisler[:5]])
            summary = (
                f"Altyapi Kaynakli Incident: Zabbix DISASTER alarm - {event.get('name', '')} "
                f"| Host: {host_name} "
                f"| {anomali_sayisi} log anomalisi tespit edildi "
                f"| Etkilenen servisler: {servis_listesi}"
                + (" ve diger..." if len(etkilenen_servisler) > 5 else "")
            )

            # En yuksek severity'yi bul
            seviyeler = [r["severity"] for r in etkilenen_servisler]
            max_sev = "DISASTER" if "DISASTER" in seviyeler else "HIGH" if "HIGH" in seviyeler else "WARNING"

            try:
                incident_row = await conn.fetchrow("""
                    INSERT INTO incidents
                        (detected_at, severity, root_cause_svc, root_cause_channel,
                         affected_count, window_seconds, summary, status,
                         source, zabbix_event_count, infrastructure_root)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'open', 'zabbix', 1, true)
                    RETURNING id
                """,
                    clock, max_sev,
                    host_name,  # root cause: Zabbix host adı
                    "ZABBIX",
                    int(anomali_sayisi),
                    KORELASYON_PENCERE_DK * 60,
                    summary
                )

                if incident_row:
                    incident_id = incident_row["id"]

                    # Zabbix event'ini incident'a bagla
                    await conn.execute("""
                        UPDATE zabbix_events SET correlated_incident_id = $1
                        WHERE zabbix_event_id = $2
                    """, incident_id, event_id)

                    # Log anomalilerini incident'a bagla
                    anomali_idler = await conn.fetch("""
                        SELECT id FROM anomaly_events
                        WHERE detected_at BETWEEN $1 AND $2
                          AND is_false_positive = false
                        LIMIT 50
                    """, pencere_baslangic, pencere_bitis)

                    for a in anomali_idler:
                        await conn.execute("""
                            INSERT INTO incident_anomalies (incident_id, anomaly_id, role)
                            VALUES ($1, $2, 'affected')
                            ON CONFLICT DO NOTHING
                        """, incident_id, a["id"])

                    logger.info(
                        f"Altyapi kaynakli incident olusturuldu: INC-{incident_id} "
                        f"| {anomali_sayisi} anomali baglandi "
                        f"| Host: {host_name}"
                    )

            except Exception as e:
                logger.error(f"Incident olusturma hatasi: {e}")

    async def _calistir(self):
        """Ana polling dongusu."""
        self._aktif = True
        logger.info("Zabbix Event Collector basladi")

        while self._aktif:
            try:
                url, user, password = await self._zabbix_config_al()
                if url and password:
                    token = await self._zabbix_login(url, user, password)
                    if token:
                        events = await self._disaster_alarmları_cek(url, token)
                        if events:
                            logger.info(f"Zabbix'ten {len(events)} DISASTER alarm alindi")
                            async with self._pool.acquire() as conn:
                                for event in events:
                                    yeni = await self._event_kaydet(conn, event)
                                    if yeni:
                                        await self._korelasyon_yap(conn, event)
            except Exception as e:
                logger.error(f"Zabbix Collector dongu hatasi: {e}")

            await asyncio.sleep(POLL_SECONDS)

    def baslat(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._calistir())
        return self._task

    async def durdur(self):
        self._aktif = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.baglanti_kapat()


# Singleton
_collector: Optional[ZabbixEventCollector] = None


def collector_baslat(db_dsn: str) -> ZabbixEventCollector:
    global _collector
    _collector = ZabbixEventCollector(db_dsn)
    return _collector


def collector_al() -> Optional[ZabbixEventCollector]:
    return _collector
