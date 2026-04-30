import asyncio
import logging
import sys
import json
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
import uvicorn
from fastapi import FastAPI
import redis.asyncio as aioredis
from engine.settings import engine_settings
from engine.models.rule_engine import RuleEngine
from engine.models.zscore import ZScoreEngine
from engine.models.isolation_forest import if_engine
from engine.models.voting import voting_engine
from engine.baseline.manager import baseline_manager
from engine.baseline.trainer import model_trainer
from engine.store.model_store import model_store

logging.basicConfig(
    level=getattr(logging, engine_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/app/logs/engine.log"),
    ],
)
logger = logging.getLogger(__name__)

rule_engine = RuleEngine()
zscore_engine = ZScoreEngine()

STREAM_KEY = "lumen:logs"
CONSUMER_GROUP = "lumen:engine"
CONSUMER_NAME = "engine-1"

# Hangi modeller aktif
ZSCORE_ENABLED = False   # Ay 2'de True yapilacak
IF_ENABLED = False       # Ay 2'de True yapilacak

_stats = {
    "total_batches": 0,
    "total_logs": 0,
    "total_anomalies": 0,
    "last_batch_at": None,
    "loop_running": False,
    "zscore_enabled": ZSCORE_ENABLED,
    "if_enabled": IF_ENABLED,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Lumen Engine baslatiliyor...")
    if_engine.load_models()
    baselines = await baseline_manager.load_all_seasonal()
    zscore_engine.load_seasonal_baseline(baselines)
    logger.info(f"Seasonal baseline: {len(baselines)} kayit")
    logger.info(f"Aktif modeller: Kural Motoru=True, ZScore={ZSCORE_ENABLED}, IF={IF_ENABLED}")
    try:
        r = aioredis.from_url(engine_settings.redis_url, decode_responses=True)
        await r.ping()
        await r.aclose()
        logger.info("Redis OK")
    except Exception as e:
        logger.error(f"Redis hatasi: {e}")
    task = asyncio.create_task(processing_loop())
    logger.info("Processing loop baslatildi")
    logger.info("Lumen Engine hazir")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Lumen Engine durduruldu")


app = FastAPI(title="Lumen ML Engine", version="1.0.0", lifespan=lifespan)


async def processing_loop():
    logger.info("Processing loop calisiyor...")
    _stats["loop_running"] = True
    redis_client = None
    while True:
        try:
            if redis_client is None:
                redis_client = aioredis.from_url(
                    engine_settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                try:
                    await redis_client.xgroup_create(
                        STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True
                    )
                    logger.info("Consumer group olusturuldu")
                except aioredis.ResponseError as e:
                    if "BUSYGROUP" not in str(e):
                        logger.error(f"Consumer group hatasi: {e}")
            messages = await redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=500,
                block=5000,
            )
            if not messages:
                continue
            logs = []
            ids = []
            for stream, msgs in messages:
                for msg_id, data in msgs:
                    try:
                        log = json.loads(data["data"])
                        logs.append(log)
                        ids.append(msg_id)
                    except Exception as e:
                        logger.error(f"Parse hatasi: {e}")
            if not logs:
                continue
            await redis_client.xack(STREAM_KEY, CONSUMER_GROUP, *ids)
            anomalies = await process_batch(logs)
            _stats["total_batches"] += 1
            _stats["total_logs"] += len(logs)
            _stats["total_anomalies"] += len(anomalies)
            _stats["last_batch_at"] = datetime.utcnow().isoformat()
            if anomalies:
                logger.info(f"Batch: {len(logs)} log, {len(anomalies)} anomali")
                await send_anomalies(anomalies)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Loop hatasi: {e}")
            if redis_client:
                try:
                    await redis_client.aclose()
                except Exception:
                    pass
                redis_client = None
            await asyncio.sleep(5)
    _stats["loop_running"] = False
    if redis_client:
        await redis_client.aclose()


async def process_batch(logs):
    if not logs:
        return []
    groups = {}
    for log in logs:
        svc = log.get("service", "unknown")
        ch = log.get("channel_code", "unknown")
        key = svc + ":" + ch
        if key not in groups:
            groups[key] = []
        groups[key].append(log)
    all_anomalies = []
    for key, group_logs in groups.items():
        parts = key.split(":", 1)
        service = parts[0]
        channel = parts[1] if len(parts) > 1 else "unknown"
        features = calculate_features(service, channel, group_logs)

        # Sadece kural motoru aktif
        rule_anomalies = rule_engine.detect(features)

        # Z-Score - baseline olgunlasinca aktif edilecek
        if ZSCORE_ENABLED:
            zscore_anomalies = zscore_engine.detect(features)
        else:
            zscore_anomalies = []

        # Isolation Forest - yeterli veri birikince aktif edilecek
        if IF_ENABLED:
            if_anomaly = if_engine.detect(features)
        else:
            if_anomaly = None

        finals = voting_engine.decide(
            features=features,
            rule_anomalies=rule_anomalies,
            zscore_anomalies=zscore_anomalies,
            if_anomaly=if_anomaly,
        )

        try:
            await baseline_manager.update(
                service=service,
                channel_code=channel,
                error_rate=features["error_rate"],
                elapsed_mean=features["elapsed_mean"],
            )
        except Exception as e:
            logger.error(f"Baseline hatasi: {e}")

        for f in finals:
            all_anomalies.append({
                "anomaly_type": f.anomaly_type,
                "channel_code": f.channel_code,
                "service": f.service,
                "severity": f.severity,
                "score": f.score,
                "error_rate": f.error_rate,
                "elapsed_mean": f.elapsed_mean,
                "tx_count": f.tx_count,
                "result_code": f.result_code,
                "summary": f.summary,
                "details": f.details,
                "triggered_by": f.triggered_by,
            })
    return all_anomalies


def calculate_features(service, channel, logs):
    tx_count = len(logs)
    if tx_count == 0:
        return {
            "service": service, "channel_code": channel,
            "tx_count": 0, "error_count": 0,
            "error_rate": 0.0, "elapsed_mean": 0.0,
            "elapsed_max": 0.0, "elapsed_p99": 0.0,
            "sys_error_count": 0, "biz_error_count": 0,
            "sys_error_rate": 0.0, "biz_error_rate": 0.0,
            "result_codes": {}, "window_seconds": 60,
        }
    error_count = sum(1 for l in logs if l.get("result", 0) != 0)
    sys_errors = sum(1 for l in logs if 0 < l.get("result", 0) < 7500)
    biz_errors = sum(1 for l in logs if l.get("result", 0) >= 7500)
    elapsed_values = [l.get("elapsed_time", 0) for l in logs]
    elapsed_mean = sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0
    elapsed_max = max(elapsed_values) if elapsed_values else 0
    elapsed_sorted = sorted(elapsed_values)
    p99_idx = int(len(elapsed_sorted) * 0.99)
    elapsed_p99 = elapsed_sorted[p99_idx] if elapsed_sorted else 0
    result_codes = {}
    for log in logs:
        rc = log.get("result", 0)
        if rc != 0:
            result_codes[rc] = result_codes.get(rc, 0) + 1
    return {
        "service": service,
        "channel_code": channel,
        "tx_count": tx_count,
        "error_count": error_count,
        "error_rate": error_count / tx_count,
        "elapsed_mean": elapsed_mean,
        "elapsed_max": elapsed_max,
        "elapsed_p99": elapsed_p99,
        "sys_error_count": sys_errors,
        "biz_error_count": biz_errors,
        "sys_error_rate": sys_errors / tx_count,
        "biz_error_rate": biz_errors / tx_count,
        "result_codes": result_codes,
        "window_seconds": 60,
    }


async def send_anomalies(anomalies):
    if not anomalies:
        return
    app_url = engine_settings.app_url
    try:
        data = json.dumps(anomalies)
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                app_url + "/api/v1/anomalies/ingest",
                "-H", "Content-Type: application/json",
                "-d", data,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        logger.info(f"{len(anomalies)} anomali gonderildi: {result.stdout[:100]}")
    except Exception as e:
        logger.error(f"Anomali gonderim hatasi: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Lumen Engine", "stats": _stats}


@app.get("/stats")
async def stats():
    return {
        **_stats,
        "zscore_stats": zscore_engine.stats(),
        "if_stats": if_engine.stats(),
    }


@app.post("/retrain")
async def trigger_retrain():
    return await model_trainer.nightly_retrain()


if __name__ == "__main__":
    uvicorn.run(
        "engine.main:app",
        host="0.0.0.0",
        port=engine_settings.engine_port,
        reload=False,
        log_config=None,
    )
