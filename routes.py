"""
REST API endpoint'leri
"""
import logging
import traceback
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
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

# Kanal mapping cache
_channel_cache: dict = {}
_channel_cache_ts = None


async def get_channel_name(channel_code: str, db: AsyncSession) -> str:
    global _channel_cache, _channel_cache_ts
    now = datetime.utcnow()
    if not _channel_cache_ts or (now - _channel_cache_ts).total_seconds() > 300:
        result = await db.execute(text("SELECT channel_code, channel_name FROM channel_mappings"))
        rows = result.fetchall()
        _channel_cache = {r.channel_code: r.channel_name for r in rows}
        _channel_cache_ts = now
    return _channel_cache.get(channel_code, channel_code)


class FalsePositiveRequest(BaseModel):
    reason: Optional[str] = None


class ChannelMappingRequest(BaseModel):
    channel_code: str
    channel_name: str
    description: Optional[str] = None


@router.get("/status")
async def api_status():
    return {
        "status": "running",
        "app": "Lumen AIOps",
        "time": datetime.utcnow().isoformat(),
        "error_codes_loaded": error_code_service.cache_size(),
    }


@router.get(
    "/anomalies",
    dependencies=[require_permission("log.anomalies.view")]
)
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

    # Kanal isimlerini ekle
    result = await db.execute(text("SELECT channel_code, channel_name FROM channel_mappings"))
    ch_map = {r.channel_code: r.channel_name for r in result.fetchall()}

    return [_anomaly_to_dict(a, ch_map) for a in rows]


@router.get(
    "/anomalies/{anomaly_id}",
    dependencies=[require_permission("log.anomalies.view")]
)
async def get_anomaly(
    anomaly_id: int,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id)
    )
    anomaly = result.scalars().first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomali bulunamadi")
    ch_result = await db.execute(text("SELECT channel_code, channel_name FROM channel_mappings"))
    ch_map = {r.channel_code: r.channel_name for r in ch_result.fetchall()}
    return _anomaly_to_dict(anomaly, ch_map)


@router.post(
    "/anomalies/{anomaly_id}/acknowledge",
    dependencies=[require_permission("log.anomalies.ack")]
)
async def acknowledge_anomaly(
    anomaly_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id)
    )
    anomaly = result.scalars().first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomali bulunamadi")
    if anomaly.acknowledged:
        raise HTTPException(status_code=400, detail="Anomali zaten onaylandi")
    anomaly.acknowledged = True
    anomaly.acknowledged_by = user.get("sub")
    anomaly.acknowledged_at = datetime.utcnow()
    await db.commit()
    return {"message": "Anomali onaylandi", "anomaly_id": anomaly_id}


@router.post(
    "/anomalies/{anomaly_id}/false-positive",
    dependencies=[require_permission("log.anomalies.ack")]
)
async def mark_false_positive(
    anomaly_id: int,
    body: FalsePositiveRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id)
    )
    anomaly = result.scalars().first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomali bulunamadi")
    if anomaly.is_false_positive:
        raise HTTPException(status_code=400, detail="Anomali zaten FP olarak isaretlendi")
    anomaly.is_false_positive = True
    anomaly.false_positive_by = user.get("sub")
    anomaly.false_positive_at = datetime.utcnow()
    anomaly.false_positive_reason = body.reason
    if not anomaly.acknowledged:
        anomaly.acknowledged = True
        anomaly.acknowledged_by = user.get("sub")
        anomaly.acknowledged_at = datetime.utcnow()
    await db.commit()
    return {"message": "False positive olarak isaretlendi", "anomaly_id": anomaly_id}


@router.post("/anomalies/ingest")
async def ingest_anomalies(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    try:
        anomalies = await request.json()
        if isinstance(anomalies, dict):
            anomalies = [anomalies]
        logger.info(f"Ingest: {len(anomalies)} anomali geldi")

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
        logger.info(f"{saved} anomali kaydedildi")
        return {"saved": saved}

    except Exception as e:
        err = traceback.format_exc()
        logger.error(f"Ingest hatasi:\n{err}")
        return JSONResponse(
            status_code=500,
            content={"detail": str(e), "traceback": err}
        )


@router.get("/runs")
async def list_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_session),
):
    rows = (await db.execute(
        select(DetectionRun)
        .order_by(desc(DetectionRun.id))
        .limit(limit)
    )).scalars().all()
    return [
        {
            "id": r.id,
            "started_at": r.started_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.started_at else None,
            "finished_at": r.finished_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.finished_at else None,
            "logs_processed": r.logs_processed,
            "anomalies_found": r.anomalies_found,
            "zabbix_sent": r.zabbix_sent,
            "status": r.status,
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/error-codes")
async def list_error_codes(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    q = select(ErrorCode).order_by(ErrorCode.result_code)
    if category:
        q = q.where(ErrorCode.category == category.upper())
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "result_code": r.result_code,
            "description": r.description,
            "category": r.category,
        }
        for r in rows
    ]


@router.post(
    "/error-codes/reload",
    dependencies=[require_permission("admin.settings.edit")]
)
async def reload_error_codes():
    count = await error_code_service.reload()
    return {"reloaded": count}


# KANAL MAPPING
@router.get("/channel-mappings")
async def list_channel_mappings(db: AsyncSession = Depends(get_session)):
    result = await db.execute(text("SELECT channel_code, channel_name, description, updated_at FROM channel_mappings ORDER BY channel_code"))
    rows = result.fetchall()
    return [
        {
            "channel_code": r.channel_code,
            "channel_name": r.channel_name,
            "description": r.description,
            "updated_at": r.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.updated_at else None,
        }
        for r in rows
    ]


@router.post(
    "/channel-mappings",
    dependencies=[require_permission("admin.settings.edit")]
)
async def upsert_channel_mapping(
    body: ChannelMappingRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    await db.execute(text("""
        INSERT INTO channel_mappings (channel_code, channel_name, description, updated_at)
        VALUES (:code, :name, :desc, NOW())
        ON CONFLICT (channel_code) DO UPDATE
        SET channel_name = EXCLUDED.channel_name,
            description = EXCLUDED.description,
            updated_at = NOW()
    """), {"code": body.channel_code, "name": body.channel_name, "desc": body.description})
    await db.commit()
    global _channel_cache, _channel_cache_ts
    _channel_cache = {}
    _channel_cache_ts = None
    return {"message": "Kanal tanimi kaydedildi", "channel_code": body.channel_code}


@router.delete(
    "/channel-mappings/{channel_code}",
    dependencies=[require_permission("admin.settings.edit")]
)
async def delete_channel_mapping(
    channel_code: str,
    db: AsyncSession = Depends(get_session),
):
    await db.execute(text("DELETE FROM channel_mappings WHERE channel_code = :code"), {"code": channel_code})
    await db.commit()
    global _channel_cache, _channel_cache_ts
    _channel_cache = {}
    _channel_cache_ts = None
    return {"message": "Kanal tanimi silindi"}


@router.get(
    "/sre/actions",
    dependencies=[require_permission("sre.actions.view")]
)
async def list_sre_actions(
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    q = select(SREAction).order_by(desc(SREAction.created_at)).limit(limit)
    if status:
        q = q.where(SREAction.status == status)
    rows = (await db.execute(q)).scalars().all()
    return [_sre_action_to_dict(a) for a in rows]


@router.post(
    "/sre/actions/{action_id}/approve",
    dependencies=[require_permission("sre.actions.approve")]
)
async def approve_action(
    action_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
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
    await db.commit()
    return {"message": "Aksiyon onaylandi", "action_id": action_id}


@router.post(
    "/sre/actions/{action_id}/reject",
    dependencies=[require_permission("sre.actions.approve")]
)
async def reject_action(
    action_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
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
    await db.commit()
    return {"message": "Aksiyon reddedildi", "action_id": action_id}


@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_session)):
    total_anomalies = (await db.execute(select(func.count(AnomalyEvent.id)))).scalar()
    active_anomalies = (await db.execute(select(func.count(AnomalyEvent.id)).where(AnomalyEvent.zabbix_sent == False))).scalar()
    pending_actions = (await db.execute(select(func.count(SREAction.id)).where(SREAction.status == "pending"))).scalar()
    fp_count = (await db.execute(select(func.count(AnomalyEvent.id)).where(AnomalyEvent.is_false_positive == True))).scalar()
    last_run = (await db.execute(select(DetectionRun).order_by(desc(DetectionRun.id)).limit(1))).scalars().first()
    return {
        "total_anomalies": total_anomalies,
        "active_anomalies": active_anomalies,
        "pending_actions": pending_actions,
        "false_positive_count": fp_count,
        "last_run": {
            "status": last_run.status if last_run else None,
            "finished_at": last_run.finished_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if last_run and last_run.finished_at else None,
            "logs_processed": last_run.logs_processed if last_run else 0,
        }
    }


@router.get("/settings", dependencies=[require_permission("admin.settings.edit")])
async def get_settings(db: AsyncSession = Depends(get_session)):
    result = await db.execute(text("SELECT key, value, description, updated_at, updated_by FROM system_settings ORDER BY key"))
    rows = result.fetchall()
    return [
        {
            "key": r.key,
            "value": r.value,
            "description": r.description,
            "updated_at": r.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.updated_at else None,
            "updated_by": r.updated_by,
        }
        for r in rows
    ]


@router.post("/settings", dependencies=[require_permission("admin.settings.edit")])
async def update_settings(
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    try:
        body = await request.json()
        username = user.get("sub", "unknown")
        updated = []
        for key, value in body.items():
            result = await db.execute(text("SELECT key FROM system_settings WHERE key = :key"), {"key": key})
            if result.fetchone():
                await db.execute(
                    text("UPDATE system_settings SET value = :value, updated_at = NOW(), updated_by = :user WHERE key = :key"),
                    {"key": key, "value": str(value), "user": username}
                )
                updated.append(key)
        await db.commit()

        # Engine'e reload bildir
        try:
            from app.settings import settings
            import httpx
            async with httpx.AsyncClient(timeout=3) as client:
                await client.post(f"{settings.engine_url}/reload-settings")
        except Exception:
            pass

        logger.info(f"Ayarlar guncellendi: {updated} by {username}")
        return {"updated": updated, "count": len(updated)}
    except Exception as e:
        err = traceback.format_exc()
        logger.error(f"Settings hatasi:\n{err}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


def _anomaly_to_dict(a: AnomalyEvent, ch_map: dict = None) -> dict:
    ch_map = ch_map or {}
    ch_code = a.channel_code or '-'
    ch_name = ch_map.get(ch_code, ch_code)
    return {
        "id": a.id,
        "detected_at": a.detected_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if a.detected_at else None,
        "anomaly_type": a.anomaly_type,
        "channel_code": ch_code,
        "channel_name": ch_name,
        "service": a.service,
        "result_code": a.result_code,
        "result_desc": a.result_desc,
        "result_category": a.result_category,
        "score": a.score,
        "elapsed_mean": a.elapsed_mean,
        "error_rate": a.error_rate,
        "tx_count": a.tx_count,
        "severity": a.severity,
        "summary": a.summary,
        "ai_analysis": a.ai_analysis,
        "zabbix_sent": a.zabbix_sent,
        "zabbix_id": a.zabbix_id,
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
        "anomaly_id": a.anomaly_id,
        "action_type": a.action_type,
        "target": a.target,
        "auto": a.auto,
        "status": a.status,
        "approved_by": a.approved_by,
        "approved_at": a.approved_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if a.approved_at else None,
        "result": a.result,
        "ai_reasoning": a.ai_reasoning,
    }
