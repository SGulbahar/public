"""
REST API endpoint'leri
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    get_session, AnomalyEvent, DetectionRun,
    ErrorCode, SREAction
)
from app.rbac.decorators import require_permission, get_current_user
from app.enrichment.error_codes import error_code_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["api"])


# STATUS
@router.get("/status")
async def api_status():
    return {
        "status": "running",
        "app": "Lumen AIOps",
        "time": datetime.utcnow().isoformat(),
        "error_codes_loaded": error_code_service.cache_size(),
    }


# ANOMALILER
@router.get(
    "/anomalies",
    dependencies=[require_permission("log.anomalies.view")]
)
async def list_anomalies(
    limit: int = 50,
    severity: Optional[str] = None,
    service: Optional[str] = None,
    channel_code: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    q = select(AnomalyEvent).order_by(desc(AnomalyEvent.detected_at)).limit(limit)
    if severity:
        q = q.where(AnomalyEvent.severity == severity.upper())
    if service:
        q = q.where(AnomalyEvent.service == service)
    if channel_code:
        q = q.where(AnomalyEvent.channel_code == channel_code)
    rows = (await db.execute(q)).scalars().all()
    return [_anomaly_to_dict(a) for a in rows]


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
    return _anomaly_to_dict(anomaly)


# ENGINE'DEN GELEN ANOMALILER
@router.post("/anomalies/ingest")
async def ingest_anomalies(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    try:
        anomalies = await request.json()
        if isinstance(anomalies, dict):
            anomalies = [anomalies]

        from app.zabbix.client import zabbix_client

        saved = 0
        for a in anomalies:
            rc = a.get("result_code", 0)
            event = AnomalyEvent(
                anomaly_type=a.get("anomaly_type"),
                channel_code=a.get("channel_code"),
                service=a.get("service"),
                result_code=rc,
                result_desc=error_code_service.describe(rc),
                result_category=error_code_service.category(rc),
                score=a.get("score"),
                elapsed_mean=a.get("elapsed_mean"),
                error_rate=a.get("error_rate"),
                tx_count=a.get("tx_count"),
                severity=a.get("severity"),
                summary=a.get("summary"),
            )
            db.add(event)
            await db.flush()

            zabbix_id = await zabbix_client.send_anomaly(a)
            if zabbix_id:
                event.zabbix_sent = True
                event.zabbix_id = str(zabbix_id)

            saved += 1

        await db.commit()
        logger.info(f"{saved} anomali kaydedildi")
        return {"saved": saved}
    except Exception as e:
        logger.error(f"Anomali ingest hatasi: {e}")
        import traceback
        traceback.print_exc()
        raise


# DETECTION RUNS
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
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "logs_processed": r.logs_processed,
            "anomalies_found": r.anomalies_found,
            "zabbix_sent": r.zabbix_sent,
            "status": r.status,
            "error": r.error,
        }
        for r in rows
    ]


# HATA KODLARI
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


# SRE AKSIYONLARI
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
    result = await db.execute(
        select(SREAction).where(SREAction.id == action_id)
    )
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
    result = await db.execute(
        select(SREAction).where(SREAction.id == action_id)
    )
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


# DASHBOARD STATS
@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_session)):
    total_anomalies = (await db.execute(
        select(func.count(AnomalyEvent.id))
    )).scalar()

    active_anomalies = (await db.execute(
        select(func.count(AnomalyEvent.id))
        .where(AnomalyEvent.zabbix_sent == False)
    )).scalar()

    pending_actions = (await db.execute(
        select(func.count(SREAction.id))
        .where(SREAction.status == "pending")
    )).scalar()

    last_run = (await db.execute(
        select(DetectionRun)
        .order_by(desc(DetectionRun.id))
        .limit(1)
    )).scalars().first()

    return {
        "total_anomalies": total_anomalies,
        "active_anomalies": active_anomalies,
        "pending_actions": pending_actions,
        "last_run": {
            "status": last_run.status if last_run else None,
            "finished_at": last_run.finished_at.isoformat() if last_run and last_run.finished_at else None,
            "logs_processed": last_run.logs_processed if last_run else 0,
        }
    }


# YARDIMCI FONKSIYONLAR
def _anomaly_to_dict(a: AnomalyEvent) -> dict:
    return {
        "id": a.id,
        "detected_at": a.detected_at.isoformat() if a.detected_at else None,
        "anomaly_type": a.anomaly_type,
        "channel_code": a.channel_code,
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
    }


def _sre_action_to_dict(a: SREAction) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "anomaly_id": a.anomaly_id,
        "action_type": a.action_type,
        "target": a.target,
        "auto": a.auto,
        "status": a.status,
        "approved_by": a.approved_by,
        "approved_at": a.approved_at.isoformat() if a.approved_at else None,
        "result": a.result,
        "ai_reasoning": a.ai_reasoning,
    }
