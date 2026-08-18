"""
Service Health endpoint'lerini routes.py'ye ekler.
Calistirma: python3 patch_service_health_api.py
"""

with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

SH_ENDPOINTS = '''

# ═══════════════════════════════════════════════════════════
# SERVİS SAĞLIK GEÇMİŞİ
# ═══════════════════════════════════════════════════════════

@router.get("/service-health")
async def service_health_listesi(
    status: str = None,
    service: str = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_session)
):
    """Servis saglik kayitlarini dondurur."""
    filtreler = []
    params = {"limit": limit}

    if status:
        filtreler.append("status = :status")
        params["status"] = status
    if service:
        filtreler.append("service ILIKE :service")
        params["service"] = f"%{service}%"

    where = "WHERE " + " AND ".join(filtreler) if filtreler else ""

    result = await db.execute(text(f"""
        SELECT
            id, service, channel_code, status,
            started_at, resolved_at, anomali_count,
            max_severity, avg_error_rate, avg_elapsed,
            tags, notes, root_cause_hint,
            EXTRACT(EPOCH FROM (COALESCE(resolved_at, NOW()) - started_at)) / 60 as sure_dk
        FROM service_health
        {where}
        ORDER BY started_at DESC
        LIMIT :limit
    """), params)

    rows = result.fetchall()
    return [{
        "id": r.id,
        "service": r.service,
        "channel_code": r.channel_code,
        "status": r.status,
        "started_at": (r.started_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.started_at else None,
        "resolved_at": (r.resolved_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.resolved_at else None,
        "anomali_count": r.anomali_count,
        "max_severity": r.max_severity,
        "avg_error_rate": round(float(r.avg_error_rate or 0) * 100, 1),
        "avg_elapsed": round(float(r.avg_elapsed or 0), 0),
        "tags": list(r.tags) if r.tags else [],
        "notes": r.notes,
        "root_cause_hint": r.root_cause_hint,
        "sure_dk": round(float(r.sure_dk or 0), 0)
    } for r in rows]


@router.get("/service-health/aktif")
async def service_health_aktif(db: AsyncSession = Depends(get_session)):
    """Aktif servis saglik sorunlarini dondurur."""
    result = await db.execute(text("""
        SELECT
            id, service, channel_code, status,
            started_at, anomali_count, max_severity,
            avg_error_rate, avg_elapsed, tags, root_cause_hint,
            EXTRACT(EPOCH FROM (NOW() - started_at)) / 60 as sure_dk
        FROM service_health
        WHERE status = 'active'
        ORDER BY
            CASE max_severity WHEN 'DISASTER' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END,
            started_at ASC
    """))
    rows = result.fetchall()
    return [{
        "id": r.id,
        "service": r.service,
        "channel_code": r.channel_code,
        "status": r.status,
        "started_at": (r.started_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.started_at else None,
        "anomali_count": r.anomali_count,
        "max_severity": r.max_severity,
        "avg_error_rate": round(float(r.avg_error_rate or 0) * 100, 1),
        "avg_elapsed": round(float(r.avg_elapsed or 0), 0),
        "tags": list(r.tags) if r.tags else [],
        "root_cause_hint": r.root_cause_hint,
        "sure_dk": round(float(r.sure_dk or 0), 0)
    } for r in rows]


@router.get("/service-health/{service_id}/history")
async def service_health_gecmis(
    service_id: int,
    db: AsyncSession = Depends(get_session)
):
    """Belirli bir servisin gecmis saglik kayitlarini dondurur."""
    result = await db.execute(text("""
        SELECT service, channel_code FROM service_health WHERE id = :id
    """), {"id": service_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    result2 = await db.execute(text("""
        SELECT
            id, status, started_at, resolved_at,
            anomali_count, max_severity, avg_error_rate, avg_elapsed,
            tags, notes, root_cause_hint,
            EXTRACT(EPOCH FROM (COALESCE(resolved_at, NOW()) - started_at)) / 60 as sure_dk
        FROM service_health
        WHERE service = :service AND channel_code = :channel
        ORDER BY started_at DESC
        LIMIT 20
    """), {"service": row.service, "channel": row.channel_code})

    rows = result2.fetchall()
    return {
        "service": row.service,
        "channel_code": row.channel_code,
        "history": [{
            "id": r.id,
            "status": r.status,
            "started_at": (r.started_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.started_at else None,
            "resolved_at": (r.resolved_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.resolved_at else None,
            "anomali_count": r.anomali_count,
            "max_severity": r.max_severity,
            "avg_error_rate": round(float(r.avg_error_rate or 0) * 100, 1),
            "avg_elapsed": round(float(r.avg_elapsed or 0), 0),
            "tags": list(r.tags) if r.tags else [],
            "notes": r.notes,
            "root_cause_hint": r.root_cause_hint,
            "sure_dk": round(float(r.sure_dk or 0), 0)
        } for r in rows]
    }


@router.patch("/service-health/{service_id}/tag")
async def service_health_tag_ekle(
    service_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Servis saglik kaydina tag ve not ekler."""
    body = await request.json()
    tags = body.get("tags", [])
    notes = body.get("notes", "")

    await db.execute(text("""
        UPDATE service_health SET
            tags = :tags,
            notes = :notes
        WHERE id = :id
    """), {"tags": tags, "notes": notes, "id": service_id})
    await db.commit()
    return {"status": "ok"}

'''

marker = '# ═══════════════════════════════════════════════════════════\n# NEO4J TOPOLOJİ'
if marker in c:
    c = c.replace(marker, SH_ENDPOINTS + '\n' + marker)
    print("OK: Service Health endpoint'leri eklendi")
else:
    print("WARN: marker bulunamadi, sona ekleniyor")
    c = c + SH_ENDPOINTS

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/app/api/routes.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
