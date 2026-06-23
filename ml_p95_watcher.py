"""
ML P95 Response Time Anomali Watcher
=====================================
Harici CatBoost modelinin uerettigi rt_anomaly_result.json dosyasini
periyodik okur, yeni alarm varsa anomaly_events tablosuna ekler ve
engine'e RCA/Zabbix/Cascade tetikleme istegi gonderir.

Dosya: /data/lumen/ML_Inference/anomalies/rt_anomaly_result.json
Model 15 dakikada bir calisir, dosyayi her seferinde uzerine yazar.

Calisma mantigi:
- run_at alanina bakarak yeni bir calisma olup olmadigini anlar
- alarms[] listesindeki her kaydi (service, channel, window_15m) bazinda
  dedup ederek anomaly_events'e ekler
- anomaly_type = 'ml_p95' olarak isaretlenir
- WARNING/CRITICAL -> sistemin kendi severity etiketlerine map edilir
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Konfigurasyon ─────────────────────────────────────────
ML_RESULT_PATH = os.environ.get(
    "ML_P95_RESULT_PATH",
    "/app/ML_Inference/anomalies/rt_anomaly_result.json"
)
POLL_SECONDS = int(os.environ.get("ML_P95_POLL_SECONDS", "60"))
ENGINE_URL = os.environ.get("ENGINE_URL", "http://engine:8001")

# ML anomali_status -> Lumen severity
STATUS_MAP = {
    "CRITICAL": "DISASTER",
    "WARNING": "WARNING",
}

_son_run_at: Optional[str] = None
_watcher_aktif = False


def _watcher_durum() -> dict:
    return {
        "aktif": _watcher_aktif,
        "son_run_at": _son_run_at,
        "dosya_yolu": ML_RESULT_PATH,
        "poll_seconds": POLL_SECONDS,
    }


async def _dosya_oku() -> Optional[dict]:
    """rt_anomaly_result.json dosyasini okur."""
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

    actual = alarm.get("actual_p95_response_time", 0)
    predicted = alarm.get("predicted_p95_response_time", 0)
    residual = alarm.get("residual", 0)
    rel_residual = alarm.get("relative_positive_residual", 0)
    tx_count = alarm.get("transaction_count", 0)

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
        "tx_count": int(tx_count),
        "score": rel_residual,
        "result_distribution": {},
        # Ek ML context - DB'de result_distribution yerine ayri tutulabilir
        "ml_context": {
            "actual_p95_ms": actual,
            "predicted_p95_ms": predicted,
            "residual_ms": residual,
            "relative_residual": rel_residual,
            "window_15m": alarm.get("window_15m"),
            "threshold_source": alarm.get("threshold_source"),
        }
    }


async def _anomali_kaydet(db_pool, anomali: dict) -> Optional[int]:
    """anomaly_events tablosuna ekler, dedup kontrolu yapar."""
    window = anomali["ml_context"].get("window_15m")
    try:
        async with db_pool.acquire() as conn:
            # Dedup - ayni servis/kanal/window_15m icin zaten kayit var mi
            mevcut = await conn.fetchrow("""
                SELECT id FROM anomaly_events
                WHERE service = $1 AND channel_code = $2
                  AND anomaly_type = 'ml_p95'
                  AND summary LIKE '%' || $3 || '%'
                  AND detected_at >= NOW() - INTERVAL '20 minutes'
            """, anomali["service"], anomali["channel_code"], str(window or ""))

            if mevcut:
                return None  # zaten eklenmis

            row = await conn.fetchrow("""
                INSERT INTO anomaly_events
                    (service, channel_code, severity, anomaly_type, summary,
                     error_rate, elapsed_mean, tx_count, score, detected_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                RETURNING id
            """,
                anomali["service"], anomali["channel_code"], anomali["severity"],
                anomali["anomaly_type"], anomali["summary"], anomali["error_rate"],
                anomali["elapsed_mean"], anomali["tx_count"], anomali["score"]
            )
            return row["id"] if row else None
    except Exception as e:
        logger.error(f"ML p95 anomali kaydetme hatasi: {e}")
        return None


async def _engine_tetikle(anomali: dict, anomali_id: int):
    """Engine'e RCA/Zabbix/Cascade tetiklemesi icin istek gonderir."""
    try:
        payload = dict(anomali)
        payload["id"] = anomali_id
        payload.pop("ml_context", None)
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"{ENGINE_URL}/rca-trigger", json=payload)
    except Exception as e:
        logger.error(f"Engine rca-trigger istegi basarisiz: {e}")


async def _watcher_loop(db_pool):
    """Periyodik olarak ML p95 dosyasini kontrol eder."""
    global _son_run_at, _watcher_aktif
    _watcher_aktif = True
    logger.info(f"ML P95 watcher baslatildi: {ML_RESULT_PATH} ({POLL_SECONDS}sn)")

    while True:
        try:
            data = await _dosya_oku()
            if data:
                run_at = data.get("run_at")
                if run_at and run_at != _son_run_at:
                    _son_run_at = run_at
                    alarms = data.get("alarms", [])
                    if alarms:
                        logger.info(f"ML P95: yeni calisma {run_at}, {len(alarms)} alarm")
                    for alarm in alarms:
                        anomali = _anomali_donustur(alarm)
                        anomali_id = await _anomali_kaydet(db_pool, anomali)
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


def watcher_baslat(db_pool):
    """Watcher task'ini olusturur. Cagiran taraf task'i saklamalidir."""
    return asyncio.create_task(_watcher_loop(db_pool))
