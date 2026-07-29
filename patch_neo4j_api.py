"""
Neo4j topoloji API endpoint'ini routes.py'ye ekler.
Calistirma: python3 patch_neo4j_api.py
"""

with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

NEO4J_ENDPOINTS = '''

# ═══════════════════════════════════════════════════════════
# NEO4J TOPOLOJİ
# ═══════════════════════════════════════════════════════════

async def _neo4j_baglan(db: AsyncSession):
    """DB'den Neo4j config ve sifresini alir."""
    from base64 import b64encode as _b64
    result = await db.execute(text("SELECT config, secrets, enabled FROM integrations WHERE key='neo4j'"))
    row = result.fetchone()
    if not row or not row.enabled:
        raise HTTPException(status_code=400, detail="Neo4j entegrasyonu aktif degil")

    config = dict(row.config) if row.config else {}
    secrets_enc = dict(row.secrets) if row.secrets else {}
    sm = _secret_manager()
    secrets = {k: sm.coz(v) if sm else v for k, v in secrets_enc.items()}

    url = config.get("url", "").rstrip("/")
    database = config.get("database", "neo4j")
    password = secrets.get("password", "")

    if not url or not password:
        raise HTTPException(status_code=400, detail="Neo4j URL veya sifre eksik")

    auth = _b64(f"neo4j:{password}".encode()).decode()
    return url, database, auth


async def _neo4j_sorgu(url: str, database: str, auth: str, cypher: str, params: dict = None) -> list:
    """Neo4j Cypher sorgusu calistirir."""
    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        r = await client.post(
            f"{url}/db/{database}/tx/commit",
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
            json={"statements": [{"statement": cypher, "parameters": params or {}}]}
        )
        data = r.json()
        if data.get("errors"):
            raise HTTPException(status_code=502, detail=str(data["errors"][0]))
        results = data.get("results", [])
        if not results or not results[0].get("data"):
            return []
        columns = results[0]["columns"]
        return [dict(zip(columns, row["row"])) for row in results[0]["data"]]


@router.get("/topology/services")
async def topology_services(db: AsyncSession = Depends(get_session)):
    """BusinessService listesini dondurur — topoloji filtresi icin."""
    url, database, auth = await _neo4j_baglan(db)
    rows = await _neo4j_sorgu(url, database, auth, """
        MATCH (bs:BusinessService)<-[:HAS_SERVICE]-(h:Host)
        WITH bs, count(h) as host_count
        OPTIONAL MATCH (h2:Host)-[:HAS_SERVICE]->(bs)
        OPTIONAL MATCH (h2)-[:HAS_ALARM]->(a:ZabbixEvent {aktif: true})
        WITH bs, host_count, count(DISTINCT a) as alarm_count
        RETURN bs.name as name, host_count, alarm_count
        ORDER BY alarm_count DESC, host_count DESC
        LIMIT 100
    """)
    return rows


@router.get("/topology/graph")
async def topology_graph(
    service: str = None,
    db: AsyncSession = Depends(get_session)
):
    """
    BusinessService merkezli topoloji graph'ini dondurur.
    Nodes: BusinessService (mavi), Host (gri/kirmizi)
    Edges: HAS_SERVICE, HAS_ALARM
    """
    url, database, auth = await _neo4j_baglan(db)

    if service:
        # Belirli bir servis icin topoloji
        cypher = """
        MATCH (bs:BusinessService {name: $service})<-[:HAS_SERVICE]-(h:Host)
        OPTIONAL MATCH (h)-[:HAS_ALARM]->(a:ZabbixEvent {aktif: true})
        WITH bs, h, collect(DISTINCT {
            id: a.event_id,
            name: a.name,
            aktif: a.aktif
        }) as alarmlar
        RETURN
            bs.name as service_name,
            h.name as host_name,
            h.os as host_os,
            h.environment as host_env,
            h.application as host_application,
            size([al in alarmlar WHERE al.id IS NOT NULL]) as alarm_count,
            alarmlar
        ORDER BY alarm_count DESC
        """
        rows = await _neo4j_sorgu(url, database, auth, cypher, {"service": service})
    else:
        # Aktif alarmi olan servisler
        cypher = """
        MATCH (bs:BusinessService)<-[:HAS_SERVICE]-(h:Host)-[:HAS_ALARM]->(a:ZabbixEvent {aktif: true})
        WITH bs, h, collect(DISTINCT {
            id: a.event_id,
            name: a.name,
            aktif: a.aktif
        }) as alarmlar
        RETURN
            bs.name as service_name,
            h.name as host_name,
            h.os as host_os,
            h.environment as host_env,
            h.application as host_application,
            size(alarmlar) as alarm_count,
            alarmlar
        ORDER BY alarm_count DESC
        LIMIT 50
        """
        rows = await _neo4j_sorgu(url, database, auth, cypher)

    # Graph formati olustur
    nodes = {}
    edges = []

    for r in rows:
        svc = r["service_name"]
        host = r["host_name"]

        # BusinessService node
        if svc and svc not in nodes:
            nodes[svc] = {
                "id": f"bs_{svc}",
                "label": svc,
                "type": "service",
                "color": "#2563EB",
                "alarm_count": 0
            }

        # Host node
        if host and host not in nodes:
            alarm_count = r.get("alarm_count", 0) or 0
            nodes[host] = {
                "id": f"host_{host}",
                "label": host,
                "type": "host",
                "color": "#EF4444" if alarm_count > 0 else "#6B7280",
                "alarm_count": alarm_count,
                "os": r.get("host_os", ""),
                "environment": r.get("host_env", ""),
                "application": r.get("host_application", ""),
                "alarmlar": [a for a in (r.get("alarmlar") or []) if a.get("id")]
            }

        # HAS_SERVICE edge
        if svc and host:
            edges.append({
                "source": f"host_{host}",
                "target": f"bs_{svc}",
                "type": "HAS_SERVICE"
            })

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "service": service,
        "toplam_host": len([n for n in nodes.values() if n["type"] == "host"]),
        "alarm_host": len([n for n in nodes.values() if n["type"] == "host" and n["alarm_count"] > 0])
    }

'''

# Zabbix events endpoint'inden once ekle
marker = '# ═══════════════════════════════════════════════════════════\n# ZABBİX EVENTS'
if marker in c:
    c = c.replace(marker, NEO4J_ENDPOINTS + '\n' + marker)
    print("OK: Neo4j endpoint'leri eklendi")
else:
    print("WARN: marker bulunamadi, sona ekleniyor")
    c = c + NEO4J_ENDPOINTS

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/app/api/routes.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
