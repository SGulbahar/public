"""
Logstash HTTP Push Receiver
- Gelen JSON batch'leri normalize edip Redis Stream'e yazar
- LOG_ENABLED=True iken gunluk rotating dosyaya ham log kaydeder
"""
import json
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status

from app.queue.redis_stream import redis_queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# ── Ham log kayit ayarlari ────────────────────────────────
LOG_ENABLED = os.environ.get("INGEST_LOG_ENABLED", "false").lower() == "true"
LOG_DIR = os.environ.get("INGEST_LOG_DIR", "/app/logs/ingest")
LOG_RETENTION_DAYS = int(os.environ.get("INGEST_LOG_RETENTION_DAYS", "1"))

_ham_log = None

def _ham_logger_al():
    global _ham_log
    if _ham_log is not None:
        return _ham_log
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _ham_log = logging.getLogger("lumen.ingest.ham")
        _ham_log.setLevel(logging.INFO)
        _ham_log.propagate = False
        handler = TimedRotatingFileHandler(
            filename=os.path.join(LOG_DIR, "ingest.jsonl"),
            when="midnight",
            interval=1,
            backupCount=LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        _ham_log.addHandler(handler)
        logger.info(f"Ham log aktif: {LOG_DIR} ({LOG_RETENTION_DAYS} gun saklanir)")
    except Exception as e:
        logger.error(f"Ham log baslatma hatasi: {e}")
        _ham_log = None
    return _ham_log

# ── Stats ─────────────────────────────────────────────────
_stats = {
    "total_received": 0,
    "total_batches": 0,
    "last_received_at": None,
    "errors": 0,
    "normalize_failed": 0,
    "log_enabled": LOG_ENABLED,
    "log_dir": LOG_DIR if LOG_ENABLED else None,
}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_logs(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        _stats["errors"] += 1
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz JSON: {e}"
        )

    if isinstance(body, dict):
        batch = [body]
    elif isinstance(body, list):
        batch = body
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gecersiz format"
        )

    if not batch:
        return {"accepted": 0}

    normalized = []
    for log in batch:
        # Ham log kaydi (LOG_ENABLED ise)
        if LOG_ENABLED:
            try:
                hl = _ham_logger_al()
                if hl:
                    hl.info(json.dumps(log, ensure_ascii=False))
            except Exception:
                pass

        n = _normalize(log)
        if n:
            normalized.append(n)
        else:
            _stats["normalize_failed"] += 1

    written = 0
    if normalized:
        written = await redis_queue.publish(normalized)

    _stats["total_received"] += written
    _stats["total_batches"] += 1
    _stats["last_received_at"] = datetime.utcnow().isoformat()

    logger.debug(f"Batch: {len(batch)} gelen, {written} yazildi")

    return {
        "accepted": written,
        "total_received": _stats["total_received"],
    }


@router.post("/log/enable", status_code=status.HTTP_200_OK)
async def log_enable():
    """Ham log kaydini aktif et."""
    global LOG_ENABLED, _ham_log
    LOG_ENABLED = True
    _ham_log = None  # Yeniden baslat
    _stats["log_enabled"] = True
    _stats["log_dir"] = LOG_DIR
    _ham_logger_al()
    logger.info("Ham log kaydi AKTIF edildi")
    return {"status": "ok", "log_enabled": True, "log_dir": LOG_DIR}


@router.post("/log/disable", status_code=status.HTTP_200_OK)
async def log_disable():
    """Ham log kaydini devre disi birak."""
    global LOG_ENABLED, _ham_log
    LOG_ENABLED = False
    _stats["log_enabled"] = False
    _stats["log_dir"] = None
    if _ham_log:
        for h in _ham_log.handlers[:]:
            h.close()
            _ham_log.removeHandler(h)
        _ham_log = None
    logger.info("Ham log kaydi DEVRE DISI birakildi")
    return {"status": "ok", "log_enabled": False}


@router.get("/stats")
async def ingest_stats():
    stream_info = await redis_queue.stream_info()
    return {
        **_stats,
        "stream_length": stream_info.get("length", 0),
        "stream_pending": stream_info.get("pending", 0),
    }


def _normalize(raw: dict) -> Optional[dict]:
    """
    Logstash formatini normalize eder.

    Beklenen format:
    {
        "@timestamp": "2026-04-24T23:59:59.322Z",
        "json_message": {
            "channelCode": "708",
            "elapsedTime": 362,
            "result": 0,
            "service": "CB_EXT_...",
            "logtime": "2026-04-25 02:59:59,322",
            "user": "T99002",
            "traceId": "...",
            "sessionID": "..."
        }
    }
    """
    try:
        jm = raw.get("json_message", {})

        if not isinstance(jm, dict):
            return None

        channel_code = jm.get("channelCode")
        elapsed_time = jm.get("elapsedTime")
        result = jm.get("result")
        service = jm.get("service")
        logtime = jm.get("logtime") or raw.get("@timestamp")

        if not service:
            return None

        return {
            "channel_code": str(channel_code) if channel_code is not None else "unknown",
            "elapsed_time": int(elapsed_time) if elapsed_time is not None else 0,
            "result": int(result) if result is not None else 0,
            "service": str(service),
            "logtime": str(logtime) if logtime else datetime.utcnow().isoformat(),
            "user": str(jm.get("user", "")),
            "trace_id": str(jm.get("traceId", "")),
            "session_id": str(jm.get("sessionID", "")),
        }

    except Exception as e:
        logger.error(f"Normalize hatasi: {e} — raw keys: {list(raw.keys())}")
        return None
