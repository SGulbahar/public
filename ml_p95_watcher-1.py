"""
ML P95 Response Time Anomali Watcher
=====================================
Harici CatBoost modelinin uerettigi rt_anomaly_result.json dosyasini
periyodik okur, yeni alarm varsa anomaly_events tablosuna ekler ve
engine'e RCA/Zabbix/Cascade tetikleme istegi gonderir.

Dosya: ML_P95_RESULT_PATH (varsayilan /app/ML_Inference/anomalies/rt_anomaly_result.json)
Model 15 dakikada bir calisir, dosyayi her seferinde uzerine yazar.

Calisma mantigi:
- run_at alanina bakarak yeni bir calisma olup olmadigini anlar
- alarms[] listesindeki her kaydi (service, channel, window_15m) bazinda
  dedup ederek anomaly_events tablosuna ekler (SQLAlchemy AsyncSession ile)
- anomaly_type = 'ml_p95' olarak isaretlenir
- WARNING/CRITICAL -> sistemin kendi severity etiketlerine map edilir
- Kayit basariyla eklenince engine'in /rca-trigger endpoint'ine HTTP istegi
  gonderilir (LLM RCA + Zabbix + Cascade icin)
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import select

from app.database import AsyncSessionLocal, AnomalyEvent
from app.settings import settings

logger = logging.getLogger(__name__)

# ── Konfigurasyon ─────────────────────────────────────────
ML_RESULT_PATH = os.environ.get(
    "ML_P95_RESULT_PATH",
    "/app/ML_Inference/anomalies/rt_anomaly_result.json"
)
POLL_SECONDS = int(os.environ.get("ML_P95_POLL_SECONDS", "60"))
ENGINE_URL = os.environ.get("ENGINE_URL", getattr(settings, "engine_url", "http://engine:8001"))

STATUS_MAP = {"CRITICAL": "DISASTER", "WARNING": "WARNING"}

_son_run_at: Optional[str] = None
_watcher_aktif = False
_watcher_task: Optional[asyncio.Task] = None


def watcher_durum() -> dict:
    return {
        "aktif": _watcher_aktif,
        "son_run_at": _son_run_at,
        "dosya_yolu": ML_RESULT_PATH,
        "dosya_var": os.path.exists(ML_RESULT_PATH),
        "poll_seconds": POLL_SECONDS,
    }


def _dosya_oku() -> Optional[dict]:
    """rt_anomaly_result.json dosyasini okur (senkron - kucuk dosya)."""
    if not os.path.exists(ML_RESULT_PATH):
        return None
    try:
        with open(ML_RESULT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"ML p95 dosya okuma hatasi: {e}")
        return None


def _anomali_donustur(alarm: dict) -> dict:
    """ML alarm kaydini Lumen anomali formatina cevirir."""
    status = alarm.get("anomaly_status", "WARNING")
    severity = STATUS_MAP.get(status, "WARNING")

    service = alarm.get("servicename", "UNKNOWN")
    channel = str(alarm.get("channel", "unknown"))
    channel_name = alarm.get("channelname", channel)

    actual = float(alarm.get("actual_p95_response_time", 0) or 0)
    predicted = float(alarm.get("predicted_p95_response_time", 0) or 0)
    residual = float(alarm.get("residual", 0) or 0)
    rel_residual = float(alarm.get("relative_positive_residual", 0) or 0)
    tx_count = int(alarm.get("transaction_count", 0) or 0)
    window = alarm.get("window_15m")

    summary = (
        f"{service} [{channel_name}] - ML P95 Response Time Anomalisi: "
        f"Gercek {actual:.0f}ms, Tahmini {predicted:.0f}ms "
        f"(Fark: +{residual:.0f}ms, {rel_residual:.1f}x)"
    )

    return {
        "service": service,
        "channel_code": channel,
        "anomaly_type": "ml_p95",
        "severity": severity,
        "summary": summary,
        "error_rate": 0.0,
        "elapsed_mean": actual,
        "tx_count": tx_count,
        "score": rel_residual,
        "window_15m": window,
    }


async def _zaten_var_mi(anomali: dict) -> bool:
    """Ayni servis/kanal/window_15m icin son 20dk'da kayit var mi kontrol eder."""
    window = str(anomali.get("window_15m") or "")
    async with AsyncSessionLocal() as session:
        stmt = (
            select(AnomalyEvent.id)
            .where(AnomalyEvent.service == anomali["service"])
            .where(AnomalyEvent.channel_code == anomali["channel_code"])
            .where(AnomalyEvent.anomaly_type == "ml_p95")
            .where(AnomalyEvent.detected_at >= datetime.utcnow() - timedelta(minutes=20))
        )
        if window:
            stmt = stmt.where(AnomalyEvent.summary.like(f"%{window}%"))
        result = await session.execute(stmt)
        return result.first() is not None


async def _anomali_kaydet(anomali: dict) -> Optional[int]:
    """anomaly_events tablosuna ekler. Basariliysa id dondurur."""
    try:
        if await _zaten_var_mi(anomali):
            return None

        async with AsyncSessionLocal() as session:
            kayit = AnomalyEvent(
                detected_at=datetime.utcnow(),
                anomaly_type=anomali["anomaly_type"],
                channel_code=anomali["channel_code"],
                service=anomali["service"],
                severity=anomali["severity"],
                summary=anomali["summary"],
                error_rate=anomali["error_rate"],
                elapsed_mean=anomali["elapsed_mean"],
                tx_count=anomali["tx_count"],
                score=anomali["score"],
            )
            session.add(kayit)
            await session.commit()
            await session.refresh(kayit)
            return kayit.id
    except Exception as e:
        logger.error(f"ML p95 anomali kaydetme hatasi: {e}")
        return None


async def _engine_tetikle(anomali: dict, anomali_id: int):
    """Engine'e RCA/Zabbix/Cascade tetiklemesi icin istek gonderir."""
    try:
        payload = {k: v for k, v in anomali.items() if k != "window_15m"}
        payload["id"] = anomali_id
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"{ENGINE_URL}/rca-trigger", json=payload)
    except Exception as e:
        logger.error(f"Engine rca-trigger istegi basarisiz: {e}")


async def _watcher_loop():
    """Periyodik olarak ML p95 dosyasini kontrol eder."""
    global _son_run_at, _watcher_aktif
    _watcher_aktif = True
    logger.info(f"ML P95 watcher baslatildi: {ML_RESULT_PATH} ({POLL_SECONDS}sn)")

    while True:
        try:
            data = await asyncio.get_event_loop().run_in_executor(None, _dosya_oku)
            if data:
                run_at = data.get("run_at")
                if run_at and run_at != _son_run_at:
                    _son_run_at = run_at
                    alarms = data.get("alarms", [])
                    if alarms:
                        logger.info(f"ML P95: yeni calisma {run_at}, {len(alarms)} alarm")
                    for alarm in alarms:
                        anomali = _anomali_donustur(alarm)
                        anomali_id = await _anomali_kaydet(anomali)
                        if anomali_id:
                            logger.info(
                                f"ML P95 anomali eklendi: id={anomali_id} "
                                f"{anomali['service']}[{anomali['channel_code']}] "
                                f"{anomali['severity']}"
                            )
                            asyncio.create_task(_engine_tetikle(anomali, anomali_id))
        except Exception as e:
            logger.error(f"ML P95 watcher loop hatasi: {e}")

        await asyncio.sleep(POLL_SECONDS)


def watcher_baslat() -> asyncio.Task:
    """Watcher task'ini olusturur ve global referansta tutar."""
    global _watcher_task
    _watcher_task = asyncio.create_task(_watcher_loop())
    return _watcher_task


async def watcher_durdur():
    """Watcher task'ini durdurur (shutdown icin)."""
    global _watcher_task, _watcher_aktif
    _watcher_aktif = False
    if _watcher_task:
        _watcher_task.cancel()
        try:
            await _watcher_task
        except asyncio.CancelledError:
            pass
