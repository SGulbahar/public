"""
Zabbix Event Collector
======================
Her POLL_SECONDS saniyede bir Zabbix'ten aktif DISASTER
problemlerini ceker, DB'ye yazar, kapananlari isaretler,
Neo4j'yi senkronize eder.
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

POLL_SECONDS = int(os.environ.get("ZABBIX_COLLECTOR_POLL", "60"))


class ZabbixEventCollector:
    def __init__(self, db_dsn: str):
        self._db_dsn = db_dsn
        self._pool = None
        self._aktif = False
        self._task: Optional[asyncio.Task] = None
        logger.info(f"Zabbix Event Collector hazir (poll={POLL_SECONDS}sn)")

    async def baglanti_ac(self):
        import asyncpg
        self._pool = await asyncpg.create_pool(self._db_dsn, min_size=1, max_size=3)

    async def baglanti_kapat(self):
        if self._pool:
            await self._pool.close()

    # ------------------------------------------------------------------ #
    #  Zabbix                                                              #
    # ------------------------------------------------------------------ #

    async def _zabbix_config_al(self):
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

    async def _aktif_problemleri_cek(self, url: str, token: str) -> Optional[list]:
        """
        Zabbix'ten suan acik DISASTER problemlerini ceker.
        None = API hatasi (bu turda hicbir sey yapma)
        []   = Hic aktif problem yok
        [...] = Aktif problemler
        """
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"jsonrpc": "2.0", "method": "problem.get", "params": {
                        "output": ["eventid", "objectid", "name", "severity", "clock", "acknowledged"],
                        "severities": [5],
                        "hosts": ["hostid", "name"],
                        "limit": 1000,
                        "sortfield": "eventid",
                        "sortorder": "DESC"
                    }, "id": 1},
                    ssl=False, timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    data = await r.json()
                    result = data.get("result")
                    if result is None:
                        logger.error(f"Zabbix problem.get hata: {data.get('error')}")
                        return None
                    return result
        except Exception as e:
            logger.error(f"Zabbix problem cekme hatasi: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Neo4j                                                               #
    # ------------------------------------------------------------------ #

    async def _neo4j_config_al(self):
        """Neo4j baglanti bilgilerini DB'den ceker. (url, password, database) dondurur."""
        import json
        from cryptography.fernet import Fernet
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='neo4j'"
                )
            if not row or not row["enabled"]:
                return None, None, None
            config = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"] or "{}")
            secrets_raw = row["secrets"] if isinstance(row["secrets"], dict) else json.loads(row["secrets"] or "{}")
            secret_key = os.environ.get("LUMEN_SECRET_KEY", "")
            password = ""
            if secret_key and secrets_raw.get("password"):
                try:
                    password = Fernet(secret_key.encode()).decrypt(secrets_raw["password"].encode()).decode()
                except Exception:
                    password = secrets_raw.get("password", "")
            else:
                password = secrets_raw.get("password", "")
            url = config.get("url", "").rstrip("/")
            database = config.get("database", "neo4j")
            if not url or not password:
                return None, None, None
            return url, password, database
        except Exception as e:
            logger.debug(f"Neo4j config hatasi: {e}")
            return None, None, None

    def _neo4j_headers(self, password: str) -> dict:
        from base64 import b64encode
        auth = b64encode(f"neo4j:{password}".encode()).decode()
        return {"Content-Type": "application/json", "Authorization": f"Basic {auth}"}

    async def _neo4j_alarm_ac(self, problem: dict):
        """Yeni alarmi Neo4j'ye ekler."""
        import requests
        try:
            url, password, database = await self._neo4j_config_al()
            if not url:
                return
            host_info = problem.get("hosts", [{}])
            host_name = host_info[0].get("name", "") if host_info else ""
            event_id = str(problem.get("eventid", ""))
            clock = datetime.utcfromtimestamp(int(problem.get("clock", 0))).isoformat()
            cypher = (
                "MERGE (a:ZabbixEvent {event_id: $event_id}) "
                "SET a.name = $name, a.severity = 5, a.clock = $clock, a.aktif = true "
                "WITH a "
                "MATCH (h:Host) WHERE toLower(h.name) = toLower($host_name) "
                "MERGE (h)-[:HAS_ALARM]->(a)"
            )
            requests.post(
                f"{url}/db/{database}/tx/commit",
                headers=self._neo4j_headers(password),
                json={"statements": [{"statement": cypher, "parameters": {
                    "event_id": event_id,
                    "name": problem.get("name", ""),
                    "clock": clock,
                    "host_name": host_name,
                }}]},
                verify=False, timeout=10
            )
            logger.debug(f"Neo4j: alarm eklendi {event_id} -> {host_name}")
        except Exception as e:
            logger.debug(f"Neo4j alarm ekleme hatasi: {e}")

    async def _neo4j_alarm_kapat(self, kapanan_idler: list):
        """Kapanan alarmlari Neo4j'de gunceller."""
        if not kapanan_idler:
            return
        import requests
        try:
            url, password, database = await self._neo4j_config_al()
            if not url:
                return
            requests.post(
                f"{url}/db/{database}/tx/commit",
                headers=self._neo4j_headers(password),
                json={"statements": [{"statement":
                    "MATCH (a:ZabbixEvent) WHERE a.event_id IN $ids SET a.aktif = false",
                    "parameters": {"ids": kapanan_idler}
                }]},
                verify=False, timeout=10
            )
            logger.debug(f"Neo4j: {len(kapanan_idler)} alarm kapandi")
        except Exception as e:
            logger.debug(f"Neo4j alarm kapatma hatasi: {e}")

    # ------------------------------------------------------------------ #
    #  DB                                                                  #
    # ------------------------------------------------------------------ #

    async def _event_kaydet(self, conn, problem: dict) -> bool:
        """Problemi DB'ye kaydeder. Yeni kayit ise True dondurur."""
        event_id = str(problem.get("eventid", ""))
        if not event_id:
            return False
        host_info = problem.get("hosts", [{}])
        host_name = host_info[0].get("name", "Bilinmiyor") if host_info else "Bilinmiyor"
        host_id = host_info[0].get("hostid", "") if host_info else ""
        try:
            clock = datetime.utcfromtimestamp(int(problem.get("clock", 0)))
        except Exception:
            clock = datetime.utcnow()
        try:
            result = await conn.fetchrow("""
                INSERT INTO zabbix_events
                    (zabbix_event_id, name, severity, host_name, host_id, clock, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (zabbix_event_id) DO UPDATE SET
                    synced_at = NOW(),
                    resolved_at = NULL
                RETURNING id, (xmax = 0) as yeni
            """, event_id, problem.get("name", ""), 5, host_name, host_id, clock)
            return result["yeni"] if result else False
        except Exception as e:
            logger.error(f"Event kaydetme hatasi ({event_id}): {e}")
            return False

    # ------------------------------------------------------------------ #
    #  Ana dongu                                                           #
    # ------------------------------------------------------------------ #

    async def _calistir(self):
        self._aktif = True
        logger.info("Zabbix Event Collector basladi")

        while self._aktif:
            try:
                url, user, password = await self._zabbix_config_al()
                if not url or not password:
                    logger.debug("Zabbix config yok veya devre disi")
                    await asyncio.sleep(POLL_SECONDS)
                    continue

                token = await self._zabbix_login(url, user, password)
                if not token:
                    logger.warning("Zabbix login basarisiz")
                    await asyncio.sleep(POLL_SECONDS)
                    continue

                problemler = await self._aktif_problemleri_cek(url, token)

                if problemler is None:
                    logger.warning("Zabbix API yanit vermedi, bu tur atlaniyor")
                    await asyncio.sleep(POLL_SECONDS)
                    continue

                aktif_idler = [str(p.get("eventid", "")) for p in problemler if p.get("eventid")]
                logger.info(f"Zabbix'te {len(aktif_idler)} aktif DISASTER problem")

                async with self._pool.acquire() as conn:
                    # Yeni alarmlari kaydet
                    for problem in problemler:
                        yeni = await self._event_kaydet(conn, problem)
                        if yeni:
                            asyncio.create_task(self._neo4j_alarm_ac(problem))

                    # Kapananlari bul ve isaretle
                    if aktif_idler:
                        kapananlar = await conn.fetch("""
                            SELECT zabbix_event_id FROM zabbix_events
                            WHERE resolved_at IS NULL
                            AND zabbix_event_id != ALL($1::text[])
                        """, aktif_idler)
                    else:
                        kapananlar = await conn.fetch("""
                            SELECT zabbix_event_id FROM zabbix_events
                            WHERE resolved_at IS NULL
                        """)

                    kapanan_idler = [r["zabbix_event_id"] for r in kapananlar]

                    if kapanan_idler:
                        await conn.execute("""
                            UPDATE zabbix_events
                            SET resolved_at = NOW()
                            WHERE zabbix_event_id = ANY($1::text[])
                        """, kapanan_idler)
                        logger.info(f"{len(kapanan_idler)} alarm kapandi olarak isaretlendi")
                        asyncio.create_task(self._neo4j_alarm_kapat(kapanan_idler))

            except Exception as e:
                logger.error(f"Zabbix Collector dongu hatasi: {e}", exc_info=True)

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
