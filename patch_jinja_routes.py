"""
routes.py'e eklenecek Jinja2 route'ları.

1. main.py'e şunu ekle:
   from fastapi.templating import Jinja2Templates
   from fastapi.staticfiles import StaticFiles

   templates = Jinja2Templates(directory="/app/templates")
   app.mount("/static", StaticFiles(directory="/app/static"), name="static")

2. Aşağıdaki route'ları routes.py'e ekle.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timedelta

router = APIRouter()
templates = Jinja2Templates(directory="/app/templates")


# ── ORTAK CONTEXT ──
async def get_base_context(request: Request, db: AsyncSession) -> dict:
    """Her sayfada ortak olan context değerleri."""

    # Sidebar badge counts
    anomaly_count = await db.scalar(
        text("SELECT COUNT(*) FROM anomaly_events WHERE detected_at > now() - interval '24 hours'")
    )
    zabbix_count = await db.scalar(
        text("SELECT COUNT(*) FROM zabbix_events WHERE resolved_at IS NULL")
    )
    incident_count = await db.scalar(
        text("SELECT COUNT(*) FROM incidents WHERE status = 'open'")
    )

    return {
        "request":            request,
        "anomaly_count":      anomaly_count or 0,
        "zabbix_alarm_count": zabbix_count or 0,
        "incident_count":     incident_count or 0,
        "engine_online":      True,   # Engine health check'ten gelebilir
        "neo4j_online":       True,   # Neo4j health check'ten gelebilir
        "zabbix_online":      True,   # Zabbix health check'ten gelebilir
        "current_user":       "Admin",
        "time_filter":        "Son 24 Saat",
    }


# ── DASHBOARD ──
@router.get("/", response_class=HTMLResponse, name="dashboard")
@router.get("/dashboard", response_class=HTMLResponse, name="dashboard_alt")
async def dashboard(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx["active_page"] = "dashboard"
    ctx["page_title"]  = "Dashboard"
    ctx["breadcrumb"]  = ["Dashboard"]

    # Stats
    since_24h = datetime.utcnow() - timedelta(hours=24)
    since_1h  = datetime.utcnow() - timedelta(hours=1)

    anomaly_24h = await db.scalar(
        text("SELECT COUNT(*) FROM anomaly_events WHERE detected_at > :since"),
        {"since": since_24h}
    )
    anomaly_1h = await db.scalar(
        text("SELECT COUNT(*) FROM anomaly_events WHERE detected_at > :since"),
        {"since": since_1h}
    )

    ctx["stats"] = {
        "anomaly_count":  anomaly_24h or 0,
        "anomaly_delta":  anomaly_1h or 0,
        "incident_count": ctx["incident_count"],
        "incident_status": "Aktif",
        "zabbix_count":   ctx["zabbix_alarm_count"],
        "zabbix_delta":   2,
        "health_pct":     94,
        "health_delta":   2.1,
    }

    # Timeline (son 24 saat anomalileri, yüzde konumu hesaplanmış)
    timeline_rows = await db.execute(
        text("""
            SELECT service, severity, detected_at
            FROM anomaly_events
            WHERE detected_at > now() - interval '24 hours'
            ORDER BY detected_at ASC
            LIMIT 50
        """)
    )
    now = datetime.utcnow()
    start = now - timedelta(hours=24)
    total_secs = 24 * 3600
    timeline = []
    for row in timeline_rows.fetchall():
        pct = max(2, min(97, int((row.detected_at - start).total_seconds() / total_secs * 100)))
        timeline.append({
            "service":  row.service,
            "severity": row.severity,
            "time":     row.detected_at.strftime("%H:%M"),
            "pct":      pct,
        })
    ctx["timeline"] = timeline

    # Top services
    top_svc_rows = await db.execute(
        text("""
            SELECT service, COUNT(*) as cnt
            FROM anomaly_events
            WHERE detected_at > now() - interval '24 hours'
            GROUP BY service
            ORDER BY cnt DESC
            LIMIT 6
        """)
    )
    top_svcs = top_svc_rows.fetchall()
    max_cnt = top_svcs[0].cnt if top_svcs else 1
    color_map = {0: "red", 1: "orange", 2: "orange", 3: "blue", 4: "blue", 5: "teal"}
    ctx["top_services"] = [
        {
            "name":  s.service,
            "count": s.cnt,
            "pct":   int(s.cnt / max_cnt * 100),
            "color": color_map.get(i, "blue"),
        }
        for i, s in enumerate(top_svcs)
    ]

    # Recent incidents
    inc_rows = await db.execute(
        text("""
            SELECT id, summary, severity, affected_count, source, created_at
            FROM incidents
            WHERE status = 'open'
            ORDER BY created_at DESC
            LIMIT 4
        """)
    )
    severity_color = {"DISASTER": "red", "HIGH": "orange", "WARNING": "amber"}
    ctx["recent_incidents"] = [
        {
            "id":             f"INC-{r.id}",
            "title":          r.summary or "—",
            "severity":       r.severity,
            "severity_color": severity_color.get(r.severity, "gray"),
            "affected":       r.affected_count or 0,
            "source":         r.source or "log",
            "elapsed":        _elapsed(r.created_at),
        }
        for r in inc_rows.fetchall()
    ]

    # Recent Zabbix alarms
    zbx_rows = await db.execute(
        text("""
            SELECT z.name, z.host_name, z.clock, b.business_services
            FROM zabbix_events z
            LEFT JOIN bmc_hosts b ON LOWER(z.host_name) = LOWER(b.host_name)
            WHERE z.resolved_at IS NULL
            ORDER BY z.clock DESC
            LIMIT 4
        """)
    )
    ctx["recent_zabbix"] = [
        {
            "name":        r.name,
            "host":        r.host_name,
            "bmc_service": (r.business_services or [None])[0],
            "elapsed":     _elapsed(datetime.utcfromtimestamp(r.clock)) if r.clock else "—",
        }
        for r in zbx_rows.fetchall()
    ]

    # Live stream (son 5 anomali)
    stream_rows = await db.execute(
        text("""
            SELECT service, severity, detection_type, error_rate, elapsed_mean, detected_at
            FROM anomaly_events
            ORDER BY detected_at DESC
            LIMIT 5
        """)
    )
    color_sev = {"DISASTER": "red", "HIGH": "orange", "WARNING": "amber"}
    ctx["live_stream"] = [
        {
            "time":       r.detected_at.strftime("%H:%M:%S"),
            "service":    r.service,
            "severity":   r.severity,
            "color":      color_sev.get(r.severity, "txt2"),
            "type":       r.detection_type or "rule",
            "error_rate": round(r.error_rate or 0, 1),
            "elapsed":    int(r.elapsed_mean or 0),
        }
        for r in stream_rows.fetchall()
    ]

    ctx["tl_start"] = (now - timedelta(hours=24)).strftime("%H:%M")
    return templates.TemplateResponse("pages/dashboard.html", ctx)


# ── ANOMALİLER ──
@router.get("/anomaliler", response_class=HTMLResponse, name="anomaliler")
async def anomaliler(
    request: Request,
    page: int = 1,
    severity: str = "",
    type: str = "",
    db: AsyncSession = Depends(get_session)
):
    ctx = await get_base_context(request, db)
    ctx["active_page"]     = "anomaliler"
    ctx["page_title"]      = "Anomaliler"
    ctx["breadcrumb"]      = ["Anomaliler"]
    ctx["severity_filter"] = severity
    ctx["type_filter"]     = type

    per_page = 50
    offset   = (page - 1) * per_page

    where = ["detected_at > now() - interval '24 hours'"]
    params = {}
    if severity:
        where.append("severity = :severity")
        params["severity"] = severity
    if type:
        where.append("detection_type = :dtype")
        params["dtype"] = type

    where_sql = " AND ".join(where)

    total = await db.scalar(
        text(f"SELECT COUNT(*) FROM anomaly_events WHERE {where_sql}"), params
    )
    rows = await db.execute(
        text(f"""
            SELECT id, service, channel_code, severity, detection_type,
                   error_rate, elapsed_mean, tx_count, detected_at,
                   COALESCE(
                     SPLIT_PART(rca_text, E'\n', 1),
                     detection_type || ': ' || ROUND(error_rate::numeric, 1) || '% hata'
                   ) as summary
            FROM anomaly_events
            WHERE {where_sql}
            ORDER BY detected_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": per_page, "offset": offset}
    )

    ctx["anomalies"]    = rows.fetchall()
    ctx["total_count"]  = total or 0
    ctx["total_pages"]  = max(1, ((total or 0) + per_page - 1) // per_page)
    ctx["current_page"] = page

    return templates.TemplateResponse("pages/anomaliler.html", ctx)


# ── ZABBİX ALARMLARI ──
@router.get("/zabbix-alarmlar", response_class=HTMLResponse, name="zabbix_alarmlar")
async def zabbix_alarmlar(
    request: Request,
    filter: str = "active",
    db: AsyncSession = Depends(get_session)
):
    ctx = await get_base_context(request, db)
    ctx["active_page"]  = "zabbix"
    ctx["page_title"]   = "Zabbix Alarmları"
    ctx["breadcrumb"]   = ["Zabbix Alarmları"]
    ctx["alarm_filter"] = filter

    where = "z.severity = 5"
    if filter == "active":
        where += " AND z.resolved_at IS NULL"

    rows = await db.execute(text(f"""
        SELECT z.id, z.zabbix_event_id, z.name, z.host_name,
               z.clock, z.resolved_at, z.synced_at,
               b.business_services, b.environment
        FROM zabbix_events z
        LEFT JOIN bmc_hosts b ON LOWER(z.host_name) = LOWER(b.host_name)
        WHERE {where}
        ORDER BY z.clock DESC
        LIMIT 100
    """))
    alarms = rows.fetchall()

    # Counts
    active_count   = await db.scalar(text("SELECT COUNT(*) FROM zabbix_events WHERE severity=5 AND resolved_at IS NULL"))
    resolved_count = await db.scalar(text("SELECT COUNT(*) FROM zabbix_events WHERE severity=5 AND resolved_at IS NOT NULL AND synced_at > now()-interval '24h'"))
    bmc_count      = await db.scalar(text("""
        SELECT COUNT(DISTINCT z.id) FROM zabbix_events z
        JOIN bmc_hosts b ON LOWER(z.host_name) = LOWER(b.host_name)
        WHERE z.severity=5 AND z.resolved_at IS NULL
    """))

    ctx["alarms"]         = alarms
    ctx["active_count"]   = active_count or 0
    ctx["resolved_count"] = resolved_count or 0
    ctx["bmc_count"]      = bmc_count or 0
    ctx["no_bmc_count"]   = (active_count or 0) - (bmc_count or 0)

    return templates.TemplateResponse("pages/zabbix_alarmlar.html", ctx)


# ── INCİDENT MERKEZİ ──
@router.get("/incident-merkezi", response_class=HTMLResponse, name="incident_merkezi")
async def incident_merkezi(
    request: Request,
    status: str = "open",
    db: AsyncSession = Depends(get_session)
):
    ctx = await get_base_context(request, db)
    ctx["active_page"] = "incidents"
    ctx["page_title"]  = "Incident Merkezi"
    ctx["breadcrumb"]  = ["Incident Merkezi"]
    ctx["inc_filter"]  = status

    rows = await db.execute(text(f"""
        SELECT id, summary, severity, source, affected_count,
               infrastructure_root, status, created_at, resolved_at
        FROM incidents
        WHERE (:status = 'all' OR status = :status)
        ORDER BY created_at DESC
        LIMIT 50
    """), {"status": status})

    severity_color = {"DISASTER": "red", "HIGH": "orange", "WARNING": "amber"}
    source_color   = {"log": "blue", "zabbix": "orange", "both": "orange"}
    incidents = []
    for r in rows.fetchall():
        incidents.append({
            "id":             f"INC-{r.id}",
            "raw_id":         r.id,
            "title":          r.summary or "—",
            "severity":       r.severity,
            "sev_color":      severity_color.get(r.severity, "gray"),
            "source":         r.source,
            "src_color":      source_color.get(r.source, "gray"),
            "affected":       r.affected_count or 0,
            "root":           r.infrastructure_root or "—",
            "status":         r.status,
            "elapsed":        _elapsed(r.created_at),
        })

    ctx["incidents"]      = incidents
    ctx["open_count"]     = sum(1 for i in incidents if i["status"] == "open")
    ctx["resolved_count"] = sum(1 for i in incidents if i["status"] == "resolved")

    return templates.TemplateResponse("pages/incident_merkezi.html", ctx)


# ── SERVİS SAĞLIĞI ──
@router.get("/servis-sagligi", response_class=HTMLResponse, name="servis_sagligi")
async def servis_sagligi(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx["active_page"] = "servishealth"
    ctx["page_title"]  = "Servis Sağlığı"
    ctx["breadcrumb"]  = ["Servis Sağlığı"]

    rows = await db.execute(text("""
        SELECT id, service, channel_code, status, started_at, resolved_at,
               anomali_count, max_severity, avg_error_rate, avg_elapsed,
               tags, notes, root_cause_hint
        FROM service_health
        ORDER BY
          CASE WHEN status = 'active' THEN 0 ELSE 1 END,
          started_at DESC
        LIMIT 100
    """))

    severity_color = {"DISASTER": "red", "HIGH": "orange", "WARNING": "amber"}
    health_list = []
    for r in rows.fetchall():
        health_list.append({
            "id":          r.id,
            "service":     r.service,
            "channel":     r.channel_code,
            "status":      r.status,
            "severity":    r.max_severity,
            "sev_color":   severity_color.get(r.max_severity, "gray"),
            "anomali":     r.anomali_count or 0,
            "error_rate":  round(r.avg_error_rate or 0, 1),
            "elapsed":     int(r.avg_elapsed or 0),
            "started_at":  r.started_at,
            "resolved_at": r.resolved_at,
            "elapsed_str": _elapsed(r.started_at),
            "tags":        r.tags or [],
            "notes":       r.notes or "",
            "hint":        r.root_cause_hint or "",
        })

    ctx["health_list"]  = health_list
    ctx["active_count"] = sum(1 for h in health_list if h["status"] == "active")
    return templates.TemplateResponse("pages/servis_sagligi.html", ctx)


# ── VM ANALİZ ──
@router.get("/vm-analiz", response_class=HTMLResponse, name="vm_analiz")
async def vm_analiz(request: Request, host: str = "", db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx["active_page"]   = "vmradar"
    ctx["page_title"]    = "VM Analiz"
    ctx["breadcrumb"]    = ["VM Analiz"]
    ctx["selected_host"] = host

    return templates.TemplateResponse("pages/vm_analiz.html", ctx)


# ── DİĞER SAYFALAR (stub) ──
@router.get("/servis-topolojisi", response_class=HTMLResponse, name="servis_topolojisi")
async def servis_topolojisi(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "topoloji", "page_title": "Servis Topolojisi", "breadcrumb": ["Topoloji"]})
    return templates.TemplateResponse("pages/servis_topolojisi.html", ctx)

@router.get("/servis-haritasi", response_class=HTMLResponse, name="servis_haritasi")
async def servis_haritasi(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "servismap", "page_title": "Servis Haritası", "breadcrumb": ["Servis Haritası"]})
    return templates.TemplateResponse("pages/servis_haritasi.html", ctx)

@router.get("/hata-kodlari", response_class=HTMLResponse, name="hata_kodlari")
async def hata_kodlari(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "hatakodlari", "page_title": "Hata Kodları", "breadcrumb": ["Hata Kodları"]})
    return templates.TemplateResponse("pages/hata_kodlari.html", ctx)

@router.get("/entegrasyonlar", response_class=HTMLResponse, name="entegrasyonlar")
async def entegrasyonlar(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "entegrasyonlar", "page_title": "Entegrasyonlar", "breadcrumb": ["Yönetim", "Entegrasyonlar"]})
    return templates.TemplateResponse("pages/entegrasyonlar.html", ctx)

@router.get("/kullanici-yonetimi", response_class=HTMLResponse, name="kullanici_yonetimi")
async def kullanici_yonetimi(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "kullanicilar", "page_title": "Kullanıcı Yönetimi", "breadcrumb": ["Yönetim", "Kullanıcılar"]})
    return templates.TemplateResponse("pages/kullanici_yonetimi.html", ctx)

@router.get("/servis-katalogu", response_class=HTMLResponse, name="servis_katalogu")
async def servis_katalogu(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "katalog", "page_title": "Servis Kataloğu", "breadcrumb": ["Yönetim", "Katalog"]})
    return templates.TemplateResponse("pages/servis_katalogu.html", ctx)

@router.get("/denetim", response_class=HTMLResponse, name="denetim")
async def denetim(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "denetim", "page_title": "Denetim", "breadcrumb": ["Yönetim", "Denetim"]})
    return templates.TemplateResponse("pages/denetim.html", ctx)

@router.get("/aksiyon-merkezi", response_class=HTMLResponse, name="aksiyon_merkezi")
async def aksiyon_merkezi(request: Request, db: AsyncSession = Depends(get_session)):
    ctx = await get_base_context(request, db)
    ctx.update({"active_page": "aksiyon", "page_title": "Aksiyon Merkezi", "breadcrumb": ["SRE Ajanı", "Aksiyon Merkezi"]})
    return templates.TemplateResponse("pages/aksiyon_merkezi.html", ctx)


# ── HELPERS ──
def _elapsed(dt) -> str:
    """datetime → '14 dk', '2 sa', '3 gün' formatı"""
    if not dt:
        return "—"
    diff = datetime.utcnow() - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return f"{secs} sn"
    elif secs < 3600:
        return f"{secs // 60} dk"
    elif secs < 86400:
        return f"{secs // 3600} sa {(secs % 3600) // 60} dk"
    else:
        return f"{secs // 86400} gün"
