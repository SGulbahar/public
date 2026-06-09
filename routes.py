import json
import hashlib
import os
"""
REST API endpoint'leri
"""
import logging
import json as _json
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

            # result_distribution: batch'teki tum result kodlari ve sayilari
            rd = a.get("result_distribution")
            result_distribution = _json.dumps(rd) if rd else None

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
                result_distribution=result_distribution,
                ai_analysis=a.get("ai_analysis"),
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

    hk_result = await db.execute(text("""
        SELECT result_code, result_category,
               COALESCE(result_desc, result_code::text) as result_desc,
               COUNT(*) as cnt
        FROM anomaly_events
        WHERE detected_at >= NOW() - INTERVAL '24 hours'
          AND result_code > 0
        GROUP BY result_code, result_category, result_desc
        ORDER BY cnt DESC LIMIT 10
    """))
    by_error_code = [{"result_code": r.result_code, "result_category": r.result_category,
                      "result_desc": r.result_desc, "count": int(r.cnt)}
                     for r in hk_result.fetchall()]

    # Top 10 servis - son 7 gun
    top_svc_result = await db.execute(text("""
        SELECT service, COUNT(*) as cnt,
               SUM(CASE WHEN severity='DISASTER' THEN 1 ELSE 0 END) as disaster,
               SUM(CASE WHEN severity='HIGH' THEN 1 ELSE 0 END) as high
        FROM anomaly_events
        WHERE detected_at >= NOW() - INTERVAL '7 days'
        GROUP BY service ORDER BY cnt DESC LIMIT 10
    """))
    top_services = [{"service": r.service, "count": int(r.cnt),
                     "disaster": int(r.disaster), "high": int(r.high)}
                    for r in top_svc_result.fetchall()]

    # Top 10 kanal - son 7 gun
    top_ch_result = await db.execute(text("""
        SELECT a.channel_code, COALESCE(c.channel_name, a.channel_code) as channel_name,
               COUNT(*) as cnt
        FROM anomaly_events a
        LEFT JOIN channel_mappings c ON a.channel_code = c.channel_code
        WHERE a.detected_at >= NOW() - INTERVAL '7 days'
        GROUP BY a.channel_code, c.channel_name ORDER BY cnt DESC LIMIT 10
    """))
    top_channels = [{"channel_code": r.channel_code, "channel_name": r.channel_name,
                     "count": int(r.cnt)}
                    for r in top_ch_result.fetchall()]

    # Top 10 baseline olgun servis
    top_baseline_result = await db.execute(text("""
        SELECT service, channel_code, SUM(sample_count) as toplam
        FROM baseline_stats
        GROUP BY service, channel_code
        ORDER BY toplam DESC LIMIT 10
    """))
    top_baselines = [{"service": r.service, "channel_code": r.channel_code,
                      "sample_count": int(r.toplam)}
                     for r in top_baseline_result.fetchall()]

    return {
        "total_anomalies": total_anomalies,
        "active_anomalies": active_anomalies,
        "pending_actions": pending_actions,
        "false_positive_count": fp_count,
        "by_service": by_service,
        "by_channel": by_channel,
        "trend_24h": trend,
        "by_error_code": by_error_code,
        "top_services": top_services,
        "top_channels": top_channels,
        "top_baselines": top_baselines,
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


@router.post("/llm/test", dependencies=[require_permission("admin.settings.edit")])
async def test_llm_proxy(request: Request):
    """LLM baglanti testini engine uzerinden proxy olarak gonder."""
    try:
        from app.settings import settings
        import httpx
        async with httpx.AsyncClient(timeout=20) as client:
            yanit = await client.post(f"{settings.engine_url}/llm/test")
            return yanit.json()
    except Exception as e:
        logger.error(f"LLM test proxy hatasi: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/notification/test", dependencies=[require_permission("admin.settings.edit")])
async def test_notification_proxy(request: Request):
    try:
        body = await request.json()
        kanal = body.get("kanal", "hepsi")
        from app.settings import settings
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            yanit = await client.post(f"{settings.engine_url}/test-notification?kanal={kanal}")
            return yanit.json()
    except Exception as e:
        logger.error(f"Bildirim test proxy hatasi: {e}")
        return {"status": "error", "message": str(e)}


def _anomaly_to_dict(a: AnomalyEvent, ch_map: dict = None) -> dict:
    ch_map = ch_map or {}
    ch_code = a.channel_code or '-'
    ch_name = ch_map.get(ch_code, ch_code)

    # result_distribution: JSON string ise parse et
    rd = None
    if hasattr(a, 'result_distribution') and a.result_distribution:
        try:
            rd = _json.loads(a.result_distribution) if isinstance(a.result_distribution, str) else a.result_distribution
        except Exception:
            rd = None

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
        "result_distribution": rd,
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


# ═══════════════════════════════════════════════════════════
# SERVİS KATALOĞU
# ═══════════════════════════════════════════════════════════

@router.get("/catalog/services")
async def katalog_servis_listesi(
    request: Request,
    sadece_kataloglanmamis: bool = False,
    sadece_anomali_uretenler: bool = True,
    db: AsyncSession = Depends(get_session)
):
    """Servis listesini döndürür. Anomali üreten servisler önce gelir."""
    # Anomali üreten benzersiz servisler
    anomali_servisler = await db.execute(text("""
        SELECT DISTINCT service,
               COUNT(*) as anomali_sayisi,
               MAX(detected_at) as son_anomali
        FROM anomaly_events
        WHERE detected_at >= NOW() - INTERVAL '30 days'
        GROUP BY service
        ORDER BY anomali_sayisi DESC
    """))
    anomali_dict = {r.service: {"anomali_sayisi": r.anomali_sayisi, "son_anomali": r.son_anomali.isoformat() if r.son_anomali else None}
                   for r in anomali_servisler.fetchall()}

    # Katalog kayitlari
    katalog = await db.execute(text("SELECT * FROM service_catalog ORDER BY service_name"))
    katalog_dict = {r.service_name: dict(r._mapping) for r in katalog.fetchall()}

    # Birlestir
    sonuc = []
    if sadece_anomali_uretenler:
        servisler = list(anomali_dict.keys())
    else:
        tum = await db.execute(text("SELECT DISTINCT service FROM anomaly_events ORDER BY service"))
        servisler = [r.service for r in tum.fetchall()]

    for svc in servisler:
        katalog_bilgi = katalog_dict.get(svc, {})
        if sadece_kataloglanmamis and katalog_bilgi:
            continue
        sonuc.append({
            "service_name": svc,
            "kataloglanmis": bool(katalog_bilgi),
            "display_name": katalog_bilgi.get("display_name"),
            "system_name": katalog_bilgi.get("system_name"),
            "team": katalog_bilgi.get("team"),
            "criticality": katalog_bilgi.get("criticality", "MEDIUM"),
            "bmc_ci_name": katalog_bilgi.get("bmc_ci_name"),
            "tags": katalog_bilgi.get("tags") or [],
            "notes": katalog_bilgi.get("notes"),
            "updated_by": katalog_bilgi.get("updated_by"),
            "updated_at": katalog_bilgi.get("updated_at").isoformat() if katalog_bilgi.get("updated_at") else None,
            **anomali_dict.get(svc, {"anomali_sayisi": 0, "son_anomali": None}),
        })

    # Kataloglanmamislar once
    sonuc.sort(key=lambda x: (x["kataloglanmis"], -x["anomali_sayisi"]))
    return sonuc


@router.post("/catalog/services/{service_name}")
async def katalog_servis_kaydet(
    request: Request,
    service_name: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Servis katalog bilgisini kaydet veya güncelle."""
    body = await request.json()
    await db.execute(text("""
        INSERT INTO service_catalog
            (service_name, display_name, system_name, team, criticality,
             bmc_ci_name, tags, notes, updated_by, updated_at)
        VALUES
            (:service_name, :display_name, :system_name, :team, :criticality,
             :bmc_ci_name, :tags, :notes, :updated_by, NOW())
        ON CONFLICT (service_name) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            system_name  = EXCLUDED.system_name,
            team         = EXCLUDED.team,
            criticality  = EXCLUDED.criticality,
            bmc_ci_name  = EXCLUDED.bmc_ci_name,
            tags         = EXCLUDED.tags,
            notes        = EXCLUDED.notes,
            updated_by   = EXCLUDED.updated_by,
            updated_at   = NOW()
    """), {
        "service_name": service_name,
        "display_name": body.get("display_name"),
        "system_name": body.get("system_name"),
        "team": body.get("team"),
        "criticality": body.get("criticality", "MEDIUM"),
        "bmc_ci_name": body.get("bmc_ci_name"),
        "tags": body.get("tags", []),
        "notes": body.get("notes"),
        "updated_by": user.get("sub", "unknown"),
    })
    await db.commit()
    await write_audit(db, user.get("sub", "unknown"), "catalog.service.upsert", service_name,
                    f"Katalog guncellendi", request)
    return {"status": "ok", "service_name": service_name}


@router.delete("/catalog/services/{service_name}")
async def katalog_servis_sil(
    request: Request,
    service_name: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Servis katalog kaydını sil."""
    await db.execute(text("DELETE FROM service_catalog WHERE service_name = :sn"),
                     {"sn": service_name})
    await db.commit()
    await write_audit(db, user.get("sub", "unknown"), "catalog.service.delete", service_name,
                    "Katalog silindi", request)
    return {"status": "ok"}


@router.post("/catalog/services/import/csv", dependencies=[require_permission("admin.settings.edit")])
async def katalog_csv_import(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """
    CSV formatında toplu import.
    Format: service_name,display_name,system_name,team,criticality,bmc_ci_name,tags,notes
    """
    body = await request.json()
    csv_icerik = body.get("csv", "")
    satirlar = csv_icerik.strip().split("\n")
    basari = 0
    hata = 0
    for satir in satirlar[1:]:  # Header atla
        parcalar = satir.split(",")
        if len(parcalar) < 2:
            continue
        try:
            tags = [t.strip() for t in parcalar[6].split("|")] if len(parcalar) > 6 and parcalar[6] else []
            await db.execute(text("""
                INSERT INTO service_catalog
                    (service_name, display_name, system_name, team, criticality,
                     bmc_ci_name, tags, notes, updated_by, updated_at)
                VALUES (:sn, :dn, :sys, :team, :crit, :bmc, :tags, :notes, :user, NOW())
                ON CONFLICT (service_name) DO UPDATE SET
                    display_name=EXCLUDED.display_name, system_name=EXCLUDED.system_name,
                    team=EXCLUDED.team, criticality=EXCLUDED.criticality,
                    bmc_ci_name=EXCLUDED.bmc_ci_name, tags=EXCLUDED.tags,
                    notes=EXCLUDED.notes, updated_by=EXCLUDED.updated_by, updated_at=NOW()
            """), {
                "sn": parcalar[0].strip(),
                "dn": parcalar[1].strip() if len(parcalar) > 1 else None,
                "sys": parcalar[2].strip() if len(parcalar) > 2 else None,
                "team": parcalar[3].strip() if len(parcalar) > 3 else None,
                "crit": parcalar[4].strip() if len(parcalar) > 4 else "MEDIUM",
                "bmc": parcalar[5].strip() if len(parcalar) > 5 else None,
                "tags": tags,
                "notes": parcalar[7].strip() if len(parcalar) > 7 else None,
                "user": user.get("sub", "unknown"),
            })
            basari += 1
        except Exception:
            hata += 1
    await db.commit()
    return {"status": "ok", "basari": basari, "hata": hata}


# ── TAG YÖNETİMİ ──────────────────────────────────────────

@router.get("/catalog/tags")
async def tag_listesi(db: AsyncSession = Depends(get_session)):
    """Tüm tagları döndürür."""
    result = await db.execute(text("SELECT * FROM catalog_tags ORDER BY tag_name"))
    return [dict(r._mapping) for r in result.fetchall()]


@router.post("/catalog/tags", dependencies=[require_permission("admin.settings.edit")])
async def tag_ekle(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Yeni tag ekle veya güncelle."""
    body = await request.json()
    tag_name = body.get("tag_name", "").strip().lower().replace(" ", "-")
    if not tag_name:
        raise HTTPException(status_code=400, detail="Tag adı zorunludur")
    await db.execute(text("""
        INSERT INTO catalog_tags (tag_name, tag_color, description)
        VALUES (:name, :color, :desc)
        ON CONFLICT (tag_name) DO UPDATE SET
            tag_color=EXCLUDED.tag_color, description=EXCLUDED.description
    """), {"name": tag_name, "color": body.get("tag_color", "#6B7280"), "desc": body.get("description")})
    await db.commit()
    return {"status": "ok", "tag_name": tag_name}


@router.delete("/catalog/tags/{tag_name}", dependencies=[require_permission("admin.settings.edit")])
async def tag_sil(
    request: Request,
    tag_name: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Tag sil. Servislerdeki bu tag referansları da temizlenir."""
    # Servislerdeki tag referansini temizle
    await db.execute(text("""
        UPDATE service_catalog
        SET tags = array_remove(tags, :tag)
        WHERE :tag = ANY(tags)
    """), {"tag": tag_name})
    await db.execute(text("DELETE FROM catalog_tags WHERE tag_name = :tag"), {"tag": tag_name})
    await db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# INCİDENT YÖNETİMİ
# ═══════════════════════════════════════════════════════════

@router.get("/incidents", dependencies=[require_permission("log.anomalies.view")])
async def incident_listesi(
    request: Request,
    status: str = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_session)
):
    """Incident listesini döndürür."""
    where = "WHERE 1=1"
    params = {}
    if status:
        where += " AND i.status = :status"
        params["status"] = status

    result = await db.execute(text(f"""
        SELECT i.*,
               array_agg(DISTINCT ae.service) FILTER (WHERE ia.role = 'affected') as affected_services,
               array_agg(DISTINCT ae.service) FILTER (WHERE ia.role = 'root_cause') as root_cause_services,
               COUNT(DISTINCT ia.anomaly_id) as anomaly_count
        FROM incidents i
        LEFT JOIN incident_anomalies ia ON ia.incident_id = i.id
        LEFT JOIN anomaly_events ae ON ia.anomaly_id = ae.id
        {where}
        GROUP BY i.id
        ORDER BY i.detected_at DESC
        LIMIT :limit
    """), {**params, "limit": limit})

    rows = result.fetchall()
    return [{
        "id": r.id,
        "detected_at": r.detected_at.isoformat() if r.detected_at else None,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "severity": r.severity,
        "status": r.status,
        "root_cause_svc": r.root_cause_svc,
        "root_cause_channel": r.root_cause_channel,
        "affected_count": r.affected_count,
        "anomaly_count": int(r.anomaly_count or 0),
        "summary": r.summary,
        "ai_analysis": r.ai_analysis,
        "acknowledged": r.acknowledged,
        "acknowledged_by": r.acknowledged_by,
        "affected_services": [s for s in (r.affected_services or []) if s],
        "root_cause_services": [s for s in (r.root_cause_services or []) if s],
    } for r in rows]


@router.get("/incidents/{incident_id}", dependencies=[require_permission("log.anomalies.view")])
async def incident_detay(
    request: Request,
    incident_id: int,
    db: AsyncSession = Depends(get_session)
):
    """Incident detayını döndürür."""
    result = await db.execute(text("""
        SELECT i.*,
               json_agg(json_build_object(
                   'id', ae.id,
                   'service', ae.service,
                   'channel_code', ae.channel_code,
                   'severity', ae.severity,
                   'anomaly_type', ae.anomaly_type,
                   'summary', ae.summary,
                   'error_rate', ae.error_rate,
                   'elapsed_mean', ae.elapsed_mean,
                   'detected_at', ae.detected_at,
                   'role', ia.role
               ) ORDER BY ae.detected_at) as anomalies
        FROM incidents i
        LEFT JOIN incident_anomalies ia ON ia.incident_id = i.id
        LEFT JOIN anomaly_events ae ON ia.anomaly_id = ae.id
        WHERE i.id = :id
        GROUP BY i.id
    """), {"id": incident_id})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incident bulunamadi")

    return {
        "id": row.id,
        "detected_at": row.detected_at.isoformat() if row.detected_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "severity": row.severity,
        "status": row.status,
        "root_cause_svc": row.root_cause_svc,
        "affected_count": row.affected_count,
        "summary": row.summary,
        "ai_analysis": row.ai_analysis,
        "acknowledged": row.acknowledged,
        "acknowledged_by": row.acknowledged_by,
        "anomalies": row.anomalies or [],
    }


@router.post("/incidents/{incident_id}/resolve", dependencies=[require_permission("log.anomalies.ack")])
async def incident_coz(
    request: Request,
    incident_id: int,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Incident'i çözümlendi olarak işaretle."""
    await db.execute(text("""
        UPDATE incidents SET
            status = 'resolved',
            resolved_at = NOW(),
            acknowledged = true,
            acknowledged_by = :user,
            acknowledged_at = NOW()
        WHERE id = :id
    """), {"id": incident_id, "user": user.get("sub", "unknown")})
    await db.commit()
    await write_audit(db, user.get("sub", "unknown"), "incident.resolve",
                      str(incident_id), "Incident cozumlendi", request)
    return {"status": "ok"}


@router.post("/incidents/{incident_id}/acknowledge", dependencies=[require_permission("log.anomalies.ack")])
async def incident_onayla(
    request: Request,
    incident_id: int,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Incident'i onayla."""
    await db.execute(text("""
        UPDATE incidents SET
            acknowledged = true,
            acknowledged_by = :user,
            acknowledged_at = NOW()
        WHERE id = :id
    """), {"id": incident_id, "user": user.get("sub", "unknown")})
    await db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# KULLANICI YÖNETİMİ
# ═══════════════════════════════════════════════════════════

@router.get("/users", dependencies=[require_permission("admin.settings.edit")])
async def kullanici_listesi(db: AsyncSession = Depends(get_session)):
    """Tüm kullanıcıları döndürür."""
    result = await db.execute(text("""
        SELECT u.id, u.username, u.email, u.auth_source, u.is_active,
               u.created_at, u.last_login,
               array_agg(r.name) FILTER (WHERE r.name IS NOT NULL) as roles
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.id
        LEFT JOIN roles r ON r.id = ur.role_id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """))
    rows = result.fetchall()
    return [{
        "id": r.id,
        "username": r.username,
        "email": r.email,
        "auth_source": r.auth_source,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "last_login": r.last_login.isoformat() if r.last_login else None,
        "roles": r.roles or [],
    } for r in rows]


@router.post("/users", dependencies=[require_permission("admin.settings.edit")])
async def kullanici_ekle(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Yeni kullanıcı ekle."""
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    email = body.get("email", "").strip()
    roles = body.get("roles", [])

    if not username or not password:
        raise HTTPException(status_code=400, detail="Kullanıcı adı ve şifre zorunludur")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Şifre en az 8 karakter olmalıdır")

    # Sifre hash
    hashed = hashlib.sha256(password.encode()).hexdigest()

    try:
        result = await db.execute(text("""
            INSERT INTO users (username, email, hashed_password, auth_source, is_active, created_at)
            VALUES (:username, :email, :hashed, 'local', true, NOW())
            RETURNING id
        """), {"username": username, "email": email or None, "hashed": hashed})
        user_id = result.fetchone().id

        # Rolleri ata
        for role_name in roles:
            await db.execute(text("""
                INSERT INTO user_roles (user_id, role_id)
                SELECT :user_id, id FROM roles WHERE name = :role_name
                ON CONFLICT DO NOTHING
            """), {"user_id": user_id, "role_name": role_name})

        await db.commit()
        await write_audit(db, user.get("sub", "unknown"), "user.create", username,
                         f"Roller: {roles}", request)
        return {"status": "ok", "user_id": user_id}
    except Exception as e:
        await db.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Bu kullanıcı adı zaten kullanılıyor")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}", dependencies=[require_permission("admin.settings.edit")])
async def kullanici_guncelle(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Kullanıcı bilgilerini güncelle."""
    body = await request.json()
    roles = body.get("roles", [])

    # Email ve aktiflik guncelle
    await db.execute(text("""
        UPDATE users SET
            email = :email,
            is_active = :is_active
        WHERE id = :id
    """), {
        "id": user_id,
        "email": body.get("email") or None,
        "is_active": body.get("is_active", True),
    })

    # Sifre degistirme
    if body.get("password"):
        if len(body["password"]) < 8:
            raise HTTPException(status_code=400, detail="Şifre en az 8 karakter olmalıdır")
        hashed = hashlib.sha256(body["password"].encode()).hexdigest()
        await db.execute(text("UPDATE users SET hashed_password = :h WHERE id = :id"),
                        {"h": hashed, "id": user_id})

    # Rolleri guncelle
    await db.execute(text("DELETE FROM user_roles WHERE user_id = :id"), {"id": user_id})
    for role_name in roles:
        await db.execute(text("""
            INSERT INTO user_roles (user_id, role_id)
            SELECT :user_id, id FROM roles WHERE name = :role_name
            ON CONFLICT DO NOTHING
        """), {"user_id": user_id, "role_name": role_name})

    await db.commit()
    await write_audit(db, user.get("sub", "unknown"), "user.update", str(user_id),
                     f"Roller: {roles}", request)
    return {"status": "ok"}


@router.delete("/users/{user_id}", dependencies=[require_permission("admin.settings.edit")])
async def kullanici_sil(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Kullanıcı sil. Kendini silemez."""
    # Mevcut kullanicinin id'sini bul
    me = await db.execute(text("SELECT id FROM users WHERE username = :u"),
                         {"u": user.get("sub", "")})
    me_row = me.fetchone()
    if me_row and me_row.id == user_id:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")

    await db.execute(text("DELETE FROM user_roles WHERE user_id = :id"), {"id": user_id})
    result = await db.execute(text("DELETE FROM users WHERE id = :id RETURNING username"),
                              {"id": user_id})
    deleted = result.fetchone()
    if not deleted:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    await db.commit()
    await write_audit(db, user.get("sub", "unknown"), "user.delete", deleted.username,
                     "Kullanıcı silindi", request)
    return {"status": "ok"}


@router.get("/roles", dependencies=[require_permission("admin.settings.edit")])
async def rol_listesi(db: AsyncSession = Depends(get_session)):
    """Tüm rolleri döndürür."""
    result = await db.execute(text("SELECT * FROM roles ORDER BY id"))
    return [dict(r._mapping) for r in result.fetchall()]


@router.get("/zabbix/test", dependencies=[require_permission("admin.settings.edit")])
async def zabbix_test(request: Request):
    """Zabbix baglantisini test eder."""
    import httpx
    zabbix_url = os.environ.get("ZABBIX_URL", "")
    zabbix_user = os.environ.get("ZABBIX_USER", "Admin")
    zabbix_password = os.environ.get("ZABBIX_PASSWORD", "")
    zabbix_host_id = os.environ.get("ZABBIX_HOST_ID", "23401")
    dry_run = os.environ.get("ZABBIX_DRY_RUN", "true").lower() == "true"

    if not zabbix_url:
        raise HTTPException(status_code=400, detail="ZABBIX_URL tanimlanmamis")

    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            r = await client.post(f"{zabbix_url}/api_jsonrpc.php",
                json={"jsonrpc":"2.0","method":"user.login",
                      "params":{"username":zabbix_user,"password":zabbix_password},"id":1})
            data = r.json()
            if "error" in data:
                raise HTTPException(status_code=400, detail=f"Login hatasi: {data['error']}")
            token = data["result"]

            r2 = await client.post(f"{zabbix_url}/api_jsonrpc.php",
                headers={"Authorization": f"Bearer {token}"},
                json={"jsonrpc":"2.0","method":"host.get",
                      "params":{"output":["hostid","host","name","status"],"hostids":[zabbix_host_id]},"id":1})
            hosts = r2.json().get("result", [])
            if not hosts:
                raise HTTPException(status_code=404, detail=f"Host {zabbix_host_id} bulunamadi")

            host = hosts[0]
            return {
                "status": "ok",
                "dry_run": dry_run,
                "host_id": zabbix_host_id,
                "host_name": host.get("name"),
                "host_status": "Aktif" if host.get("status") == "0" else "Pasif",
                "zabbix_url": zabbix_url
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# ENTEGRASYONLAR
# ═══════════════════════════════════════════════════════════

def _secret_manager():
    try:
        from app.security.secrets import secret_manager
        return secret_manager
    except Exception:
        return None


@router.get("/integrations", dependencies=[require_permission("admin.settings.edit")])
async def entegrasyon_listesi(db: AsyncSession = Depends(get_session)):
    """Tum entegrasyonlari dondurur. Sifreli alanlari gizler."""
    result = await db.execute(text("""
        SELECT key, name, enabled, config, status, last_test, test_result, updated_by, updated_at
        FROM integrations ORDER BY key
    """))
    rows = result.fetchall()
    return [{
        "key": r.key,
        "name": r.name,
        "enabled": r.enabled,
        "config": dict(r.config) if r.config else {},
        "status": r.status,
        "last_test": r.last_test.isoformat() if r.last_test else None,
        "test_result": r.test_result,
        "updated_by": r.updated_by,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]


@router.get("/integrations/{key}", dependencies=[require_permission("admin.settings.edit")])
async def entegrasyon_detay(key: str, db: AsyncSession = Depends(get_session)):
    """Entegrasyon detayini dondurur. Sifreli alanlari maskeler."""
    result = await db.execute(text(
        "SELECT * FROM integrations WHERE key = :key"
    ), {"key": key})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entegrasyon bulunamadi")

    # Secrets - dolu mu bos mu goster, degeri gosterme
    secrets = dict(row.secrets) if row.secrets else {}
    masked_secrets = {k: "***" if v else "" for k, v in secrets.items()}

    return {
        "key": row.key,
        "name": row.name,
        "enabled": row.enabled,
        "config": dict(row.config) if row.config else {},
        "secrets": masked_secrets,
        "status": row.status,
        "last_test": row.last_test.isoformat() if row.last_test else None,
        "test_result": row.test_result,
    }


@router.post("/integrations/{key}", dependencies=[require_permission("admin.settings.edit")])
async def entegrasyon_kaydet(
    request: Request,
    key: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Entegrasyon ayarlarini kaydet."""
    body = await request.json()
    config = body.get("config", {})
    secrets_raw = body.get("secrets", {})
    enabled = body.get("enabled", False)

    # Bos secrets gelmisse mevcut secrets'i koru
    result = await db.execute(text(
        "SELECT secrets FROM integrations WHERE key = :key"
    ), {"key": key})
    row = result.fetchone()
    mevcut_secrets = dict(row.secrets) if row and row.secrets else {}

    # Sifreli alanlari guncelle - *** ise dokunma
    sm = _secret_manager()
    yeni_secrets = dict(mevcut_secrets)
    for k, v in secrets_raw.items():
        if v and v != "***":
            yeni_secrets[k] = sm.sifrele(str(v)) if sm else str(v)

    await db.execute(text("""
        UPDATE integrations SET
            config = :config,
            secrets = :secrets,
            enabled = :enabled,
            updated_by = :user,
            updated_at = NOW()
        WHERE key = :key
    """), {
        "key": key,
        "config": json.dumps(config),
        "secrets": json.dumps(yeni_secrets),
        "enabled": enabled,
        "user": user.get("sub", "unknown")
    })
    await db.commit()
    await write_audit(db, user.get("sub", "unknown"), "integration.update", key,
                     f"Entegrasyon guncellendi", request)
    return {"status": "ok"}


@router.post("/integrations/{key}/test", dependencies=[require_permission("admin.settings.edit")])
async def entegrasyon_test(
    key: str,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """Entegrasyon baglantisini test eder."""
    result = await db.execute(text(
        "SELECT * FROM integrations WHERE key = :key"
    ), {"key": key})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entegrasyon bulunamadi")

    config = dict(row.config) if row.config else {}
    secrets_enc = dict(row.secrets) if row.secrets else {}

    sm = _secret_manager()
    secrets = {k: sm.coz(v) if sm else v for k, v in secrets_enc.items()}

    test_sonuc = {"status": "error", "message": "Test implemente edilmedi"}

    try:
        import httpx
        if key == "zabbix":
            url = config.get("url", "")
            zabbix_user = config.get("user", "Admin")
            password = secrets.get("password", "")
            host_id = config.get("host_id", "")
            if not url or not password:
                test_sonuc = {"status": "error", "message": "URL veya sifre eksik"}
            else:
                async with httpx.AsyncClient(verify=False, timeout=10) as client:
                    r = await client.post(f"{url}/api_jsonrpc.php",
                        json={"jsonrpc":"2.0","method":"user.login",
                              "params":{"username":zabbix_user,"password":password},"id":1})
                    data = r.json()
                    if "error" in data:
                        test_sonuc = {"status": "error", "message": str(data["error"])}
                    else:
                        token = data["result"]
                        r2 = await client.post(f"{url}/api_jsonrpc.php",
                            headers={"Authorization": f"Bearer {token}"},
                            json={"jsonrpc":"2.0","method":"host.get",
                                  "params":{"output":["hostid","name","status"],"hostids":[host_id]},"id":1})
                        hosts = r2.json().get("result", [])
                        if hosts:
                            test_sonuc = {"status": "ok", "message": f"Baglanti basarili — Host: {hosts[0].get('name')}"}
                        else:
                            test_sonuc = {"status": "error", "message": f"Host {host_id} bulunamadi"}

        elif key == "llm":
            base_url = config.get("base_url", "")
            api_key = secrets.get("api_key", "")
            model = config.get("model", "")
            if not base_url:
                test_sonuc = {"status": "error", "message": "Base URL eksik"}
            else:
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                async with httpx.AsyncClient(verify=False, timeout=15) as client:
                    r = await client.post(f"{base_url}/chat/completions",
                        headers=headers,
                        json={"model": model, "messages": [{"role":"user","content":"ping"}], "max_tokens": 5})
                    if r.status_code == 200:
                        test_sonuc = {"status": "ok", "message": f"LLM baglanti basarili — Model: {model}"}
                    else:
                        test_sonuc = {"status": "error", "message": f"HTTP {r.status_code}"}

        elif key == "smtp":
            import smtplib, ssl
            host = config.get("host", "")
            port = int(config.get("port", 587))
            smtp_user = config.get("user", "")
            password = secrets.get("password", "")
            if not host:
                test_sonuc = {"status": "error", "message": "SMTP host eksik"}
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with smtplib.SMTP(host, port, timeout=10) as s:
                    s.starttls(context=ctx)
                    if smtp_user and password:
                        s.login(smtp_user, password)
                    test_sonuc = {"status": "ok", "message": f"SMTP baglanti basarili — {host}:{port}"}

        elif key == "teams":
            webhook = secrets.get("webhook_url", "")
            if not webhook:
                test_sonuc = {"status": "error", "message": "Webhook URL eksik"}
            else:
                async with httpx.AsyncClient(verify=False, timeout=10) as client:
                    r = await client.post(webhook,
                        json={"text": "Lumen AIOps — Teams baglanti testi ✓"})
                    if r.status_code in (200, 202):
                        test_sonuc = {"status": "ok", "message": "Teams mesaji gonderildi"}
                    else:
                        test_sonuc = {"status": "error", "message": f"HTTP {r.status_code}"}

        elif key == "bmc":
            url = config.get("url", "")
            token = secrets.get("token", "")
            if not url or not token:
                test_sonuc = {"status": "error", "message": "URL veya token eksik"}
            else:
                async with httpx.AsyncClient(verify=False, timeout=10) as client:
                    r = await client.post(f"{url}/api/v1/search",
                        headers={"Authorization": f"Bearer {token}",
                                 "Content-Type": "application/json"},
                        json={"query": "search BusinessService limit 1"})
                    if r.status_code == 200:
                        test_sonuc = {"status": "ok", "message": "BMC Discovery baglanti basarili"}
                    else:
                        test_sonuc = {"status": "error", "message": f"HTTP {r.status_code}"}

    except Exception as e:
        test_sonuc = {"status": "error", "message": str(e)}

    # Sonucu DB'ye kaydet
    await db.execute(text("""
        UPDATE integrations SET
            status = :status,
            last_test = NOW(),
            test_result = :result
        WHERE key = :key
    """), {
        "key": key,
        "status": test_sonuc["status"],
        "result": test_sonuc["message"]
    })
    await db.commit()
    return test_sonuc
