"""
REST API endpoint'leri
"""
import logging
import traceback
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    get_session, AnomalyEvent, DetectionRun,
    ErrorCode, SREAction
)
from app.rbac.decorators import require_permission, get_current_user
from app.enrichment.error_codes import error_code_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["api"])


class FalsePositiveRequest(BaseModel):
    reason: Optional[str] = None


class ChannelMappingRequest(BaseModel):
    channel_code: str
    channel_name: str
    description: Optional[str] = None


class WhitelistRequest(BaseModel):
    service_name: str
    channel_code: str = "*"
    rule_name: str = "*"
    reason: Optional[str] = None


async def write_audit(db, user, action, target, detail="", result="success", ip_address=""):
    try:
        await db.execute(text("""
            INSERT INTO audit_logs (created_at, "user", action, target, detail, ip_address, result)
            VALUES (NOW(), :user, :action, :target, :detail, :ip, :result)
        """), {"user": user, "action": action, "target": target,
               "detail": detail, "ip": ip_address, "result": result})
    except Exception as e:
        logger.error(f"Audit log hatasi: {e}")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/status")
async def api_status():
    return {
        "status": "running",
        "app": "Lumen AIOps",
        "time": datetime.utcnow().isoformat(),
        "error_codes_loaded": error_code_service.cache_size(),
    }


@router.get("/anomalies", dependencies=[require_permission("log.anomalies.view")])
async def list_anomalies(
    limit: int = 50,
    severity: Optional[str] = None,
    service: Optional[str] = None,
    channel_code: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    q = select(AnomalyEvent).order_by(desc(AnomalyEvent.detected_at)).limit(limit)
    if severity:
        q = q.where(AnomalyEvent.severity == severity.upper())
    if service:
        q = q.where(AnomalyEvent.service == service)
    if channel_code:
        q = q.where(AnomalyEvent.channel_code == channel_code)
    if category:
        q = q.where(AnomalyEvent.result_category == category.upper())
    rows = (await db.execute(q)).scalars().all()
    ch_result = await db.execute(text("SELECT channel_code, channel_name FROM channel_mappings"))
    ch_map = {r.channel_code: r.channel_name for r in ch_result.fetchall()}
    return [_anomaly_to_dict(a, ch_map) for a in rows]


@router.get("/anomalies/{anomaly_id}", dependencies=[require_permission("log.anomalies.view")])
async def get_anomaly(anomaly_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
    anomaly = result.scalars().first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomali bulunamadi")
    ch_result = await db.execute(text("SELECT channel_code, channel_name FROM channel_mappings"))
    ch_map = {r.channel_code: r.channel_name for r in ch_result.fetchall()}
    return _anomaly_to_dict(anomaly, ch_map)


@router.post("/anomalies/{anomaly_id}/acknowledge", dependencies=[require_permission("log.anomalies.ack")])
async def acknowledge_anomaly(
    anomaly_id: int, request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
    anomaly = result.scalars().first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomali bulunamadi")
    if anomaly.acknowledged:
        raise HTTPException(status_code=400, detail="Zaten onaylandi")
    anomaly.acknowledged = True
    anomaly.acknowledged_by = user.get("sub")
    anomaly.acknowledged_at = datetime.utcnow()
    await write_audit(db, user.get("sub"), "anomaly.acknowledge",
        f"anomaly_events/{anomaly_id}",
        f"service={anomaly.service} channel={anomaly.channel_code} severity={anomaly.severity}",
        ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Anomali onaylandi", "anomaly_id": anomaly_id}


@router.post("/anomalies/{anomaly_id}/false-positive", dependencies=[require_permission("log.anomalies.ack")])
async def mark_false_positive(
    anomaly_id: int, body: FalsePositiveRequest, request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
    anomaly = result.scalars().first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomali bulunamadi")
    if anomaly.is_false_positive:
        raise HTTPException(status_code=400, detail="Zaten FP isaretlendi")
    anomaly.is_false_positive = True
    anomaly.false_positive_by = user.get("sub")
    anomaly.false_positive_at = datetime.utcnow()
    anomaly.false_positive_reason = body.reason
    if not anomaly.acknowledged:
        anomaly.acknowledged = True
        anomaly.acknowledged_by = user.get("sub")
        anomaly.acknowledged_at = datetime.utcnow()
    await write_audit(db, user.get("sub"), "anomaly.false_positive",
        f"anomaly_events/{anomaly_id}",
        f"service={anomaly.service} reason={body.reason}",
        ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "False positive isaretlendi", "anomaly_id": anomaly_id}


@router.post("/anomalies/ingest")
async def ingest_anomalies(request: Request, db: AsyncSession = Depends(get_session)):
    try:
        anomalies = await request.json()
        if isinstance(anomalies, dict):
            anomalies = [anomalies]
        from app.zabbix.client import zabbix_client
        saved = 0
        for a in anomalies:
            rc = a.get("result_code", 0)
            if rc is None:
                rc = 0
            rc = int(rc)
            if rc == 0:
                result_desc = "Basarili islem - Elapsed/Hata Orani anomalisi"
                result_category = "PERFORMANCE"
            elif rc < 7500:
                result_desc = error_code_service.describe(rc)
                result_category = "SYS"
            else:
                result_desc = error_code_service.describe(rc)
                result_category = "BIZ"
            event = AnomalyEvent(
                anomaly_type=a.get("anomaly_type"),
                channel_code=a.get("channel_code"),
                service=a.get("service"),
                result_code=rc,
                result_desc=result_desc,
                result_category=result_category,
                score=float(a.get("score", 0) or 0),
                elapsed_mean=float(a.get("elapsed_mean", 0) or 0),
                error_rate=float(a.get("error_rate", 0) or 0),
                tx_count=int(a.get("tx_count", 0) or 0),
                severity=a.get("severity"),
                summary=a.get("summary"),
            )
            db.add(event)
            await db.flush()
            try:
                zabbix_id = await zabbix_client.send_anomaly(a)
                if zabbix_id:
                    event.zabbix_sent = True
                    event.zabbix_id = str(zabbix_id)
            except Exception as ze:
                logger.error(f"Zabbix hatasi: {ze}")
            saved += 1
        await db.commit()
        return {"saved": saved}
    except Exception as e:
        err = traceback.format_exc()
        logger.error(f"Ingest hatasi:\n{err}")
        return JSONResponse(status_code=500, content={"detail": str(e), "traceback": err})


@router.get("/runs")
async def list_runs(limit: int = 20, db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(DetectionRun).order_by(desc(DetectionRun.id)).limit(limit))).scalars().all()
    return [{"id": r.id,
             "started_at": r.started_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.started_at else None,
             "finished_at": r.finished_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.finished_at else None,
             "logs_processed": r.logs_processed, "anomalies_found": r.anomalies_found,
             "zabbix_sent": r.zabbix_sent, "status": r.status, "error": r.error} for r in rows]


@router.get("/error-codes")
async def list_error_codes(category: Optional[str] = None, db: AsyncSession = Depends(get_session)):
    q = select(ErrorCode).order_by(ErrorCode.result_code)
    if category:
        q = q.where(ErrorCode.category == category.upper())
    rows = (await db.execute(q)).scalars().all()
    return [{"result_code": r.result_code, "description": r.description, "category": r.category} for r in rows]


@router.post("/error-codes/reload", dependencies=[require_permission("admin.settings.edit")])
async def reload_error_codes(
    request: Request, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session)
):
    count = await error_code_service.reload()
    await write_audit(db, user.get("sub"), "error_codes.reload", "error_codes",
        f"reloaded={count}", ip_address=get_client_ip(request))
    await db.commit()
    return {"reloaded": count}


@router.get("/channel-mappings")
async def list_channel_mappings(db: AsyncSession = Depends(get_session)):
    result = await db.execute(text(
        "SELECT channel_code, channel_name, description, updated_at FROM channel_mappings ORDER BY channel_code"
    ))
    rows = result.fetchall()
    return [{"channel_code": r.channel_code, "channel_name": r.channel_name,
             "description": r.description,
             "updated_at": r.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.updated_at else None}
            for r in rows]


@router.post("/channel-mappings", dependencies=[require_permission("admin.settings.edit")])
async def upsert_channel_mapping(
    body: ChannelMappingRequest, request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    await db.execute(text("""
        INSERT INTO channel_mappings (channel_code, channel_name, description, updated_at)
        VALUES (:code, :name, :desc, NOW())
        ON CONFLICT (channel_code) DO UPDATE
        SET channel_name = EXCLUDED.channel_name, description = EXCLUDED.description, updated_at = NOW()
    """), {"code": body.channel_code, "name": body.channel_name, "desc": body.description})
    await write_audit(db, user.get("sub"), "channel_mapping.upsert",
        f"channel_mappings/{body.channel_code}",
        f"channel_name={body.channel_name}", ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Kanal tanimi kaydedildi", "channel_code": body.channel_code}


@router.delete("/channel-mappings/{channel_code}", dependencies=[require_permission("admin.settings.edit")])
async def delete_channel_mapping(
    channel_code: str, request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    await db.execute(text("DELETE FROM channel_mappings WHERE channel_code = :code"), {"code": channel_code})
    await write_audit(db, user.get("sub"), "channel_mapping.delete",
        f"channel_mappings/{channel_code}", ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Kanal tanimi silindi"}


@router.get("/sre/actions", dependencies=[require_permission("sre.actions.view")])
async def list_sre_actions(limit: int = 50, status: Optional[str] = None, db: AsyncSession = Depends(get_session)):
    q = select(SREAction).order_by(desc(SREAction.created_at)).limit(limit)
    if status:
        q = q.where(SREAction.status == status)
    rows = (await db.execute(q)).scalars().all()
    return [_sre_action_to_dict(a) for a in rows]


@router.post("/sre/actions/{action_id}/approve", dependencies=[require_permission("sre.actions.approve")])
async def approve_action(
    action_id: int, request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(SREAction).where(SREAction.id == action_id))
    action = result.scalars().first()
    if not action:
        raise HTTPException(status_code=404, detail="Aksiyon bulunamadi")
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Aksiyon zaten {action.status}")
    action.status = "approved"
    action.approved_by = user.get("sub")
    action.approved_at = datetime.utcnow()
    await write_audit(db, user.get("sub"), "sre_action.approve",
        f"sre_actions/{action_id}", f"action_type={action.action_type}",
        ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Aksiyon onaylandi", "action_id": action_id}


@router.post("/sre/actions/{action_id}/reject", dependencies=[require_permission("sre.actions.approve")])
async def reject_action(
    action_id: int, request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(SREAction).where(SREAction.id == action_id))
    action = result.scalars().first()
    if not action:
        raise HTTPException(status_code=404, detail="Aksiyon bulunamadi")
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Aksiyon zaten {action.status}")
    action.status = "rejected"
    action.approved_by = user.get("sub")
    action.approved_at = datetime.utcnow()
    await write_audit(db, user.get("sub"), "sre_action.reject",
        f"sre_actions/{action_id}", f"action_type={action.action_type}",
        ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Aksiyon reddedildi", "action_id": action_id}


@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_session)):
    total_anomalies = (await db.execute(select(func.count(AnomalyEvent.id)))).scalar()
    active_anomalies = (await db.execute(
        select(func.count(AnomalyEvent.id)).where(AnomalyEvent.zabbix_sent == False)
    )).scalar()
    pending_actions = (await db.execute(
        select(func.count(SREAction.id)).where(SREAction.status == "pending")
    )).scalar()
    fp_count = (await db.execute(
        select(func.count(AnomalyEvent.id)).where(AnomalyEvent.is_false_positive == True)
    )).scalar()
    last_run = (await db.execute(
        select(DetectionRun).order_by(desc(DetectionRun.id)).limit(1)
    )).scalars().first()

    svc_result = await db.execute(text("""
        SELECT service, COUNT(*) as cnt,
               SUM(CASE WHEN severity='DISASTER' THEN 1 ELSE 0 END) as disaster,
               SUM(CASE WHEN severity='HIGH' THEN 1 ELSE 0 END) as high
        FROM anomaly_events
        WHERE detected_at >= NOW() - INTERVAL '24 hours'
        GROUP BY service ORDER BY cnt DESC LIMIT 10
    """))
    by_service = [{"service": r.service, "count": int(r.cnt),
                   "disaster": int(r.disaster), "high": int(r.high)}
                  for r in svc_result.fetchall()]

    ch_result = await db.execute(text("""
        SELECT a.channel_code, COALESCE(c.channel_name, a.channel_code) as channel_name,
               COUNT(*) as cnt
        FROM anomaly_events a
        LEFT JOIN channel_mappings c ON a.channel_code = c.channel_code
        WHERE a.detected_at >= NOW() - INTERVAL '24 hours'
        GROUP BY a.channel_code, c.channel_name ORDER BY cnt DESC LIMIT 10
    """))
    by_channel = [{"channel_code": r.channel_code, "channel_name": r.channel_name,
                   "count": int(r.cnt)} for r in ch_result.fetchall()]

    trend_result = await db.execute(text("""
        SELECT DATE_TRUNC('hour', detected_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul') as hour,
               COUNT(*) as cnt
        FROM anomaly_events
        WHERE detected_at >= NOW() - INTERVAL '24 hours'
        GROUP BY hour ORDER BY hour
    """))
    trend = [{"hour": r.hour.strftime("%H:00"), "count": int(r.cnt)}
             for r in trend_result.fetchall()]

    return {
        "total_anomalies": total_anomalies,
        "active_anomalies": active_anomalies,
        "pending_actions": pending_actions,
        "false_positive_count": fp_count,
        "by_service": by_service,
        "by_channel": by_channel,
        "trend_24h": trend,
        "last_run": {
            "status": last_run.status if last_run else None,
            "finished_at": last_run.finished_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if last_run and last_run.finished_at else None,
            "logs_processed": last_run.logs_processed if last_run else 0,
        }
    }


@router.get("/settings", dependencies=[require_permission("admin.settings.edit")])
async def get_settings(db: AsyncSession = Depends(get_session)):
    result = await db.execute(text(
        "SELECT key, value, description, updated_at, updated_by FROM system_settings ORDER BY key"
    ))
    rows = result.fetchall()
    return [{"key": r.key, "value": r.value, "description": r.description,
             "updated_at": r.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.updated_at else None,
             "updated_by": r.updated_by} for r in rows]


@router.post("/settings", dependencies=[require_permission("admin.settings.edit")])
async def update_settings(
    request: Request, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    try:
        body = await request.json()
        username = user.get("sub", "unknown")
        updated, changes = [], []
        for key, value in body.items():
            result = await db.execute(
                text("SELECT key, value FROM system_settings WHERE key = :key"), {"key": key}
            )
            row = result.fetchone()
            if row:
                old_value = row.value
                await db.execute(
                    text("UPDATE system_settings SET value = :value, updated_at = NOW(), updated_by = :user WHERE key = :key"),
                    {"key": key, "value": str(value), "user": username}
                )
                updated.append(key)
                if old_value != str(value):
                    changes.append(f"{key}: {old_value} -> {value}")
        await write_audit(db, username, "settings.update", "system_settings",
            "; ".join(changes) if changes else "degisiklik yok",
            ip_address=get_client_ip(request))
        await db.commit()
        try:
            from app.settings import settings
            import httpx
            async with httpx.AsyncClient(timeout=3) as client:
                await client.post(f"{settings.engine_url}/reload-settings")
        except Exception:
            pass
        return {"updated": updated, "count": len(updated)}
    except Exception as e:
        err = traceback.format_exc()
        logger.error(f"Settings hatasi:\n{err}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.get("/audit-logs", dependencies=[require_permission("admin.settings.edit")])
async def list_audit_logs(
    limit: int = 100,
    user_filter: Optional[str] = None,
    action_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    query = 'SELECT id, created_at, "user", action, target, detail, ip_address, result FROM audit_logs'
    conditions, params = [], {}
    if user_filter:
        conditions.append('"user" = :user')
        params["user"] = user_filter
    if action_filter:
        conditions.append("action LIKE :action")
        params["action"] = f"%{action_filter}%"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit
    result = await db.execute(text(query), params)
    rows = result.fetchall()
    return [{"id": r.id,
             "created_at": r.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.created_at else None,
             "user": r.user, "action": r.action, "target": r.target,
             "detail": r.detail, "ip_address": r.ip_address, "result": r.result}
            for r in rows]


# --- WHITELIST ---

@router.get("/whitelist", dependencies=[require_permission("admin.settings.edit")])
async def list_whitelist(db: AsyncSession = Depends(get_session)):
    result = await db.execute(text(
        "SELECT service_name, channel_code, rule_name, reason, created_by, created_at "
        "FROM service_whitelist ORDER BY service_name, channel_code, rule_name"
    ))
    rows = result.fetchall()
    return [{"service_name": r.service_name, "channel_code": r.channel_code,
             "rule_name": r.rule_name, "reason": r.reason, "created_by": r.created_by,
             "created_at": r.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.created_at else None}
            for r in rows]


@router.post("/whitelist", dependencies=[require_permission("admin.settings.edit")])
async def add_whitelist(
    body: WhitelistRequest, request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    await db.execute(text("""
        INSERT INTO service_whitelist (service_name, channel_code, rule_name, reason, created_by)
        VALUES (:svc, :ch, :rule, :reason, :user)
        ON CONFLICT (service_name, channel_code, rule_name) DO UPDATE
        SET reason = EXCLUDED.reason, created_by = EXCLUDED.created_by, created_at = NOW()
    """), {"svc": body.service_name, "ch": body.channel_code, "rule": body.rule_name,
           "reason": body.reason, "user": user.get("sub")})
    await write_audit(db, user.get("sub"), "whitelist.add",
        f"service_whitelist/{body.service_name}/{body.channel_code}/{body.rule_name}",
        f"reason={body.reason}", ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Whitelist kurali eklendi"}


@router.delete(
    "/whitelist/{service_name}/{channel_code}/{rule_name}",
    dependencies=[require_permission("admin.settings.edit")]
)
async def delete_whitelist(
    service_name: str, channel_code: str, rule_name: str,
    request: Request,
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_session),
):
    await db.execute(text(
        "DELETE FROM service_whitelist WHERE service_name=:svc AND channel_code=:ch AND rule_name=:rule"
    ), {"svc": service_name, "ch": channel_code, "rule": rule_name})
    await write_audit(db, user.get("sub"), "whitelist.delete",
        f"service_whitelist/{service_name}/{channel_code}/{rule_name}",
        ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Whitelist kurali silindi"}


# --- BILDIRIM TEST PROXY ---

@router.post("/notification/test", dependencies=[require_permission("admin.settings.edit")])
async def test_notification_proxy(request: Request):
    """
    Browser'dan engine'e direkt erisim olmadigi icin
    bu endpoint VM-1 uzerinden VM-2 engine'e proxy olarak istek gonderir.
    """
    try:
        body = await request.json()
        kanal = body.get("kanal", "hepsi")
        from app.settings import settings
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            yanit = await client.post(
                f"{settings.engine_url}/test-notification?kanal={kanal}"
            )
            return yanit.json()
    except Exception as e:
        logger.error(f"Bildirim test proxy hatasi: {e}")
        return {"status": "error", "message": str(e)}


def _anomaly_to_dict(a: AnomalyEvent, ch_map: dict = None) -> dict:
    ch_map = ch_map or {}
    ch_code = a.channel_code or '-'
    ch_name = ch_map.get(ch_code, ch_code)
    return {
        "id": a.id,
        "detected_at": a.detected_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if a.detected_at else None,
        "anomaly_type": a.anomaly_type,
        "channel_code": ch_code, "channel_name": ch_name,
        "service": a.service,
        "result_code": a.result_code, "result_desc": a.result_desc,
        "result_category": a.result_category,
        "score": a.score, "elapsed_mean": a.elapsed_mean,
        "error_rate": a.error_rate, "tx_count": a.tx_count,
        "severity": a.severity, "summary": a.summary,
        "ai_analysis": a.ai_analysis,
        "zabbix_sent": a.zabbix_sent, "zabbix_id": a.zabbix_id,
        "itsm_ticket_id": a.itsm_ticket_id,
        "acknowledged": a.acknowledged,
        "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": a.acknowledged_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if a.acknowledged_at else None,
        "is_false_positive": a.is_false_positive,
        "false_positive_by": a.false_positive_by,
        "false_positive_at": a.false_positive_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if a.false_positive_at else None,
        "false_positive_reason": a.false_positive_reason,
    }


def _sre_action_to_dict(a: SREAction) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if a.created_at else None,
        "anomaly_id": a.anomaly_id, "action_type": a.action_type,
        "target": a.target, "auto": a.auto, "status": a.status,
        "approved_by": a.approved_by,
        "approved_at": a.approved_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if a.approved_at else None,
        "result": a.result, "ai_reasoning": a.ai_reasoning,
    }
