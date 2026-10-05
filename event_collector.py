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
MIN_ANOMALI_ESIK = 3        # Korelasyon icin minimum log anomalisi sayisi


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

            config = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"] or "{}")
            secrets_raw = row["secrets"] if isinstance(row["secrets"], dict) else json.loads(row["secrets"] or "{}")

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

    async def _disaster_alarmları_cek(self, url: str, token: str) -> Optional[list]:
        """
        Aktif DISASTER seviyesindeki Zabbix alarmlarini ceker.
        Basarili ancak bos liste = aktif alarm yok.
        None = API/baglanti hatasi, bu turda kapatma yapilmamali.
        """
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"jsonrpc": "2.0", "method": "event.get", "params": {
                        "output": ["eventid", "name", "severity", "clock", "acknowledged"],
                        "severities": [5],   # Sadece DISASTER
                        "value": 1,          # Sadece aktif (cozulmemis)
                        # time_from YOK — value=1 zaten sadece acik alarmları getirir,
                        # zaman kisitlamasi uzun sureli alarmlarin yanlis kapanmasina yol aciyordu
                        "selectHosts": ["hostid", "name"],
                        "limit": 200,
                        "sortfield": "clock",
                        "sortorder": "DESC"
                    }, "id": 1},
                    ssl=False, timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    data = await r.json()
                    return data.get("result", [])
        except Exception as e:
            logger.error(f"Zabbix alarm cekme hatasi: {e}")
            return None  # None = hata, [] = bos (tum alarmlar kapandi)

    async def _neo4j_alarm_ekle(self, event: dict):
        """Yeni Zabbix alarmini Neo4j'ye ekler ve host ile iliskilendirir."""
        try:
            import requests as _req
            from base64 import b64encode as _b64
            import os as _os
            import json as _json
            from cryptography.fernet import Fernet as _Fernet

            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='neo4j'"
                )
                if not row or not row['enabled']:
                    return

                config = row['config'] if isinstance(row['config'], dict) else _json.loads(row['config'] or '{}')
                secrets_raw = row['secrets'] if isinstance(row['secrets'], dict) else _json.loads(row['secrets'] or '{}')

                secret_key = _os.environ.get('LUMEN_SECRET_KEY', '')
                password = ''
                if secret_key and secrets_raw.get('password'):
                    try:
                        password = _Fernet(secret_key.encode()).decrypt(secrets_raw['password'].encode()).decode()
                    except Exception:
                        password = secrets_raw.get('password', '')
                else:
                    password = secrets_raw.get('password', '')

                url = config.get('url', '').rstrip('/')
                database = config.get('database', 'neo4j')
                if not url or not password:
                    return

            auth = _b64(f'neo4j:{password}'.encode()).decode()
            headers = {'Content-Type': 'application/json', 'Authorization': f'Basic {auth}'}

            host_info = event.get('hosts', [{}])
            host_name = host_info[0].get('name', '') if host_info else ''
            event_id = str(event.get('eventid', ''))
            clock = datetime.utcfromtimestamp(int(event.get('clock', 0))).isoformat()

            cypher = (
                "MERGE (a:ZabbixEvent {event_id: $event_id}) "
                "SET a.name = $name, a.severity = 5, a.clock = $clock, a.aktif = true "
                "WITH a "
                "MATCH (h:Host) WHERE toLower(h.name) = toLower($host_name) "
                "MERGE (h)-[:HAS_ALARM]->(a) "
                "RETURN count(a)"
            )
            _req.post(
                f'{url}/db/{database}/tx/commit',
                headers=headers,
                json={'statements': [{'statement': cypher, 'parameters': {
                    'event_id': event_id,
                    'name': event.get('name', ''),
                    'clock': clock,
                    'host_name': host_name
                }}]},
                verify=False, timeout=10
            )
            logger.debug(f"Neo4j: yeni alarm eklendi {event_id} -> {host_name}")
        except Exception as e:
            logger.debug(f"Neo4j alarm ekleme hatasi: {e}")

    async def _neo4j_sync(self, kapanan_idler: list):
        """Kapanan alarmlari Neo4j'de gunceller."""
        if not kapanan_idler:
            return
        try:
            import requests as _req
            from base64 import b64encode as _b64
            import os as _os
            import json as _json
            from cryptography.fernet import Fernet as _Fernet

            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='neo4j'"
                )
                if not row or not row['enabled']:
                    return

                config = row['config'] if isinstance(row['config'], dict) else _json.loads(row['config'] or '{}')
                secrets_raw = row['secrets'] if isinstance(row['secrets'], dict) else _json.loads(row['secrets'] or '{}')

                secret_key = _os.environ.get('LUMEN_SECRET_KEY', '')
                password = ''
                if secret_key and secrets_raw.get('password'):
                    try:
                        password = _Fernet(secret_key.encode()).decrypt(secrets_raw['password'].encode()).decode()
                    except Exception:
                        password = secrets_raw.get('password', '')
                else:
                    password = secrets_raw.get('password', '')

                url = config.get('url', '').rstrip('/')
                database = config.get('database', 'neo4j')
                if not url or not password:
                    return

            auth = _b64(f'neo4j:{password}'.encode()).decode()
            headers = {'Content-Type': 'application/json', 'Authorization': f'Basic {auth}'}

            _req.post(
                f'{url}/db/{database}/tx/commit',
                headers=headers,
                json={'statements': [{'statement':
                    'MATCH (a:ZabbixEvent) WHERE a.event_id IN $ids SET a.aktif = false RETURN count(a)',
                    'parameters': {'ids': kapanan_idler}
                }]},
                verify=False, timeout=10
            )
            logger.debug(f"Neo4j sync: {len(kapanan_idler)} alarm guncellendi")
        except Exception as e:
            logger.debug(f"Neo4j sync hatasi: {e}")

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

        anomali_sayisi = await conn.fetchval("""
            SELECT COUNT(*) FROM anomaly_events
            WHERE detected_at BETWEEN $1 AND $2
            AND is_false_positive = false
        """, pencere_baslangic, pencere_bitis)

        if anomali_sayisi < MIN_ANOMALI_ESIK:
            return

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
            etkilenen_servisler = await conn.fetch("""
                SELECT service, channel_code, severity
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
                    host_name,
                    "ZABBIX",
                    int(anomali_sayisi),
                    KORELASYON_PENCERE_DK * 60,
                    summary
                )

                if incident_row:
                    incident_id = incident_row["id"]

                    await conn.execute("""
                        UPDATE zabbix_events SET correlated_incident_id = $1
                        WHERE zabbix_event_id = $2
                    """, incident_id, event_id)

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

                        if events is None:
                            # API/baglanti hatasi — bu turu atla, hicbir seyi kapatma
                            logger.warning("Zabbix API yanit vermedi, bu tur atlaniyor")
                        else:
                            # events = [] ise tum alarmlar kapandi, events = [...] ise aktifler bunlar
                            aktif_idler = [str(e.get('eventid', '')) for e in events]

                            if events:
                                logger.info(f"Zabbix'ten {len(events)} aktif DISASTER alarm alindi")

                            async with self._pool.acquire() as conn:
                                # Yeni alarmlari kaydet
                                for event in events:
                                    yeni = await self._event_kaydet(conn, event)
                                    if yeni:
                                        asyncio.create_task(self._neo4j_alarm_ekle(event))
                                        await self._korelasyon_yap(conn, event)

                                # Kapanan alarmlari isaretle:
                                # DB'de acik olan ama Zabbix'te artik aktif olmayan alarmlar
                                sentinel = aktif_idler if aktif_idler else ['__NONE__']
                                kapananlar = await conn.fetch("""
                                    SELECT zabbix_event_id FROM zabbix_events
                                    WHERE resolved_at IS NULL
                                    AND zabbix_event_id != ALL($1::text[])
                                    AND clock >= NOW() - INTERVAL '7 days'
                                """, sentinel)
                                kapanan_idler = [r['zabbix_event_id'] for r in kapananlar]

                                if kapanan_idler:
                                    await conn.execute("""
                                        UPDATE zabbix_events
                                        SET resolved_at = NOW()
                                        WHERE resolved_at IS NULL
                                        AND zabbix_event_id != ALL($1::text[])
                                        AND clock >= NOW() - INTERVAL '7 days'
                                    """, sentinel)
                                    logger.info(f"{len(kapanan_idler)} alarm kapandi olarak isaretlendi")
                                    asyncio.create_task(self._neo4j_sync(kapanan_idler))

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
