"""
BMC ve Zabbix verilerini Neo4j'ye yukler.
Graph modeli:
  (:Host)-[:HAS_SERVICE]->(:BusinessService)
  (:Host)-[:HAS_ALARM]->(:ZabbixEvent)

Calistirma: python3 load_neo4j.py
Gereksinimler: pip install asyncpg requests
"""
import asyncio
import json
import logging
import os
from base64 import b64encode

import asyncpg
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Konfigurasyon ─────────────────────────────────────────
PG_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://logwatch_user:SIFRE@VM3_IP:5432/logwatch"
)
NEO4J_URL = os.environ.get("NEO4J_URL", "http://localhost:7474")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASS", "YENI_SIFRE")


def neo4j_sorgu(cypher: str, params: dict = None) -> dict:
    """Neo4j HTTP API ile Cypher sorgusu calistirir."""
    auth = b64encode(f"{NEO4J_USER}:{NEO4J_PASS}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth}"
    }
    body = {"statements": [{"statement": cypher, "parameters": params or {}}]}
    r = requests.post(
        f"{NEO4J_URL}/db/neo4j/tx/commit",
        headers=headers,
        json=body,
        verify=False,
        timeout=30
    )
    data = r.json()
    if data.get("errors"):
        logger.error(f"Neo4j hata: {data['errors']}")
    return data


def indeksler_olustur():
    """Performans icin index'ler olusturur."""
    logger.info("Index'ler olusturuluyor...")
    sorgular = [
        "CREATE INDEX host_name IF NOT EXISTS FOR (h:Host) ON (h.name)",
        "CREATE INDEX service_name IF NOT EXISTS FOR (s:BusinessService) ON (s.name)",
        "CREATE INDEX alarm_id IF NOT EXISTS FOR (a:ZabbixEvent) ON (a.event_id)",
    ]
    for s in sorgular:
        neo4j_sorgu(s)
    logger.info("Index'ler hazir")


async def bmc_yukle(conn):
    """BMC host ve business service verilerini Neo4j'ye yukler."""
    logger.info("BMC verisi yukleniyor...")

    rows = await conn.fetch("""
        SELECT host_name, os, environment, application, role,
               scanned_via, business_services
        FROM bmc_hosts
        WHERE array_length(business_services, 1) > 0
    """)

    logger.info(f"{len(rows)} BMC host bulundu")

    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        hosts_data = []
        for r in batch:
            services = list(r["business_services"]) if r["business_services"] else []
            hosts_data.append({
                "name": r["host_name"],
                "os": r["os"] or "",
                "environment": r["environment"] or "",
                "application": r["application"] or "",
                "role": r["role"] or "",
                "services": services
            })

        # Host node'larini ve iliskilerini olustur
        cypher = """
        UNWIND $hosts AS h
        MERGE (host:Host {name: h.name})
        SET host.os = h.os,
            host.environment = h.environment,
            host.application = h.application,
            host.role = h.role,
            host.source = 'BMC'
        WITH host, h
        UNWIND h.services AS svc
        MERGE (bs:BusinessService {name: svc})
        MERGE (host)-[:HAS_SERVICE]->(bs)
        """
        neo4j_sorgu(cypher, {"hosts": hosts_data})
        logger.info(f"BMC: {min(i + batch_size, len(rows))}/{len(rows)} host yuklendi")


async def zabbix_yukle(conn):
    """Zabbix DISASTER alarmlarini Neo4j'ye yukler."""
    logger.info("Zabbix alarmlari yukleniyor...")

    rows = await conn.fetch("""
        SELECT ze.id, ze.zabbix_event_id, ze.name, ze.severity,
               ze.host_name, ze.clock, ze.resolved_at,
               bh.environment, bh.application
        FROM zabbix_events ze
        LEFT JOIN bmc_hosts bh ON LOWER(bh.host_name) = LOWER(ze.host_name)
        ORDER BY ze.clock DESC
    """)

    logger.info(f"{len(rows)} Zabbix alarm bulundu")

    alarms_data = []
    for r in rows:
        alarms_data.append({
            "event_id": r["zabbix_event_id"],
            "name": r["name"] or "",
            "severity": r["severity"] or 5,
            "host_name": r["host_name"] or "",
            "clock": r["clock"].isoformat() if r["clock"] else "",
            "resolved": r["resolved_at"] is not None,
            "aktif": r["resolved_at"] is None
        })

    if alarms_data:
        cypher = """
        UNWIND $alarms AS a
        MERGE (alarm:ZabbixEvent {event_id: a.event_id})
        SET alarm.name = a.name,
            alarm.severity = a.severity,
            alarm.clock = a.clock,
            alarm.resolved = a.resolved,
            alarm.aktif = a.aktif
        WITH alarm, a
        WHERE a.host_name <> ''
        MERGE (host:Host {name: a.host_name})
        MERGE (host)-[:HAS_ALARM]->(alarm)
        """
        neo4j_sorgu(cypher, {"alarms": alarms_data})
        logger.info(f"{len(alarms_data)} Zabbix alarm yuklendi")


async def istatistik_goster():
    """Yuklenen veri istatistiklerini gosterir."""
    sorgular = [
        ("Host sayisi", "MATCH (h:Host) RETURN count(h) as sayi"),
        ("BusinessService sayisi", "MATCH (s:BusinessService) RETURN count(s) as sayi"),
        ("ZabbixEvent sayisi", "MATCH (a:ZabbixEvent) RETURN count(a) as sayi"),
        ("HAS_SERVICE iliski", "MATCH ()-[:HAS_SERVICE]->() RETURN count(*) as sayi"),
        ("HAS_ALARM iliski", "MATCH ()-[:HAS_ALARM]->() RETURN count(*) as sayi"),
        ("Aktif alarm", "MATCH (a:ZabbixEvent {aktif: true}) RETURN count(a) as sayi"),
        ("BMC eslesen alarm", "MATCH (h:Host)-[:HAS_ALARM]->(a:ZabbixEvent) WHERE h.source='BMC' RETURN count(a) as sayi"),
    ]
    logger.info("\n=== NEO4J ISTATISTIK ===")
    for baslik, cypher in sorgular:
        result = neo4j_sorgu(cypher)
        sayi = result["results"][0]["data"][0]["row"][0] if result.get("results") else "?"
        logger.info(f"  {baslik}: {sayi}")


async def main():
    logger.info(f"Neo4j baglantisi test ediliyor: {NEO4J_URL}")
    test = neo4j_sorgu("RETURN 1 as test")
    if test.get("errors"):
        logger.error("Neo4j baglantisi basarisiz!")
        return

    logger.info("Neo4j baglantisi OK")
    logger.info(f"PostgreSQL baglantisi: {PG_DSN[:30]}...")

    conn = await asyncpg.connect(PG_DSN)
    try:
        indeksler_olustur()
        await bmc_yukle(conn)
        await zabbix_yukle(conn)
        await istatistik_goster()
        logger.info("\n✓ Yukleme tamamlandi!")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
