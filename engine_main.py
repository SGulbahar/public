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
import asyncpg
from engine.settings import engine_settings
from engine.models.rule_engine import RuleEngine, whitelist_yukle
from engine.models.zscore import ZScoreEngine
from engine.models.isolation_forest import if_engine
from engine.models.voting import voting_engine
from engine.baseline.manager import baseline_manager
from engine.baseline.trainer import model_trainer
from engine.baseline.trainer import model_trainer
from engine.store.model_store import model_store
from engine.notification import notification_service, _notification_cooldown
from engine.llm_rca import llm_rca_service
from engine.rag_context import rag_baslat, rag_al
from engine.cascade_detector import cascade_detector_baslat, cascade_detector_al
from engine.zabbix_integration import zabbix_baslat, zabbix_al
import engine.models.rule_engine as rule_engine_module

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
ZSCORE_ENABLED = False
IF_ENABLED = False

_stats = {
    "total_batches": 0,
    "total_logs": 0,
    "total_anomalies": 0,
    "last_batch_at": None,
    "loop_running": False,
    "zscore_enabled": ZSCORE_ENABLED,
    "if_enabled": IF_ENABLED,
    "last_settings_reload": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Lumen Engine baslatiliyor...")
    if_engine.load_models()
    baselines = await baseline_manager.load_all_seasonal()
    zscore_engine.load_seasonal_baseline(baselines)
    logger.info(f"Seasonal baseline: {len(baselines)} kayit")
    await reload_settings_from_db()
    await reload_whitelist_from_db()
    logger.info(f"Aktif modeller: Kural=True, ZScore={ZSCORE_ENABLED}, IF={IF_ENABLED}")
    try:
        r = aioredis.from_url(engine_settings.redis_url, decode_responses=True)
        await r.ping()
        await r.aclose()
        logger.info("Redis OK")
    except Exception as e:
        logger.error(f"Redis hatasi: {e}")
    # RAG context builder
    rag = rag_baslat(settings.database_url)
    await rag.baglanti_ac()
    logger.info('RAG context builder hazir')
    cascade = cascade_detector_baslat(engine_settings.database_url.replace("postgresql+asyncpg://", "postgresql://"), llm_rca_service)
    await cascade.baglanti_ac()
    logger.info('Cascade Detector hazir')
    zabbix = zabbix_baslat(engine_settings.database_url.replace("postgresql+asyncpg://","postgresql://"))
    logger.info('Zabbix entegrasyonu hazir')
    task1 = asyncio.create_task(processing_loop('engine-1'))
    task_trainer = asyncio.create_task(nightly_scheduler())
    logger.info('Processing loop x1 baslatildi')
    yield
    task1.cancel()
    task_trainer.cancel()
    for t in [task1, task_trainer]:
        try:
            await t
        except asyncio.CancelledError:
            pass
    logger.info("Lumen Engine durduruldu")


app = FastAPI(title="Lumen ML Engine", version="1.0.0", lifespan=lifespan)


async def get_db_conn():
    db_url = engine_settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(db_url)


async def reload_settings_from_db():
    global ZSCORE_ENABLED, IF_ENABLED
    try:
        conn = await get_db_conn()
        rows = await conn.fetch("SELECT key, value FROM system_settings")
        await conn.close()
        settings_dict = {row['key']: row['value'] for row in rows}

        for key, value in settings_dict.items():
            if key == 'rule_elapsed_disaster':
                engine_settings.rule_elapsed_disaster = int(value)
            elif key == 'rule_elapsed_high':
                engine_settings.rule_elapsed_high = int(value)
            elif key == 'rule_elapsed_p99_disaster':
                rule_engine_module.ELAPSED_P99_DISASTER = int(value)
            elif key == 'rule_elapsed_p95_high':
                rule_engine_module.ELAPSED_P95_HIGH = int(value)
            elif key == 'rule_error_rate_disaster':
                engine_settings.rule_error_rate_disaster = float(value)
            elif key == 'rule_error_rate_high':
                engine_settings.rule_error_rate_high = float(value)
            elif key == 'zscore_enabled':
                ZSCORE_ENABLED = (value == 'true')
                _stats["zscore_enabled"] = ZSCORE_ENABLED
            elif key == 'if_enabled':
                IF_ENABLED = (value == 'true')
                _stats["if_enabled"] = IF_ENABLED
            elif key == 'sys_error_code_threshold':
                rule_engine_module.SYS_ERROR_CODE_THRESHOLD = int(value)
            elif key == 'biz_error_code_threshold':
                rule_engine_module.BIZ_ERROR_CODE_THRESHOLD = int(value)
            elif key == 'min_tx_count':
                rule_engine_module.MIN_TX_COUNT = int(value)
            elif key == 'min_slow_tx_count':
                rule_engine_module.MIN_SLOW_TX_COUNT = int(value)
            elif key == 'cooldown_seconds':
                rule_engine_module.COOLDOWN_SECONDS = int(value)
            elif key == 'sliding_window_seconds':
                rule_engine_module.SLIDING_WINDOW_SECONDS = int(value)
            elif key == 'zscore_threshold_warning':
                engine_settings.zscore_threshold_warning = float(value)
            elif key == 'zscore_threshold_high':
                engine_settings.zscore_threshold_high = float(value)
            elif key == 'zscore_rolling_minutes':
                engine_settings.zscore_rolling_minutes = int(value)

        notification_service.ayarlari_yukle(settings_dict)
        llm_rca_service.ayarlari_yukle(settings_dict)
        _stats["last_settings_reload"] = datetime.utcnow().isoformat()
        logger.info(
            f"Ayarlar yuklendi: ZScore={ZSCORE_ENABLED}(w={engine_settings.zscore_threshold_warning}, "
            f"h={engine_settings.zscore_threshold_high}, win={engine_settings.zscore_rolling_minutes}dk), "
            f"IF={IF_ENABLED}, p99={rule_engine_module.ELAPSED_P99_DISASTER}, "
            f"p95={rule_engine_module.ELAPSED_P95_HIGH}, bildirim={notification_service.enabled}"
        )
    except Exception as e:
        logger.error(f"Ayar yukleme hatasi: {e}")


async def reload_whitelist_from_db():
    try:
        conn = await get_db_conn()
        rows = await conn.fetch(
            "SELECT service_name, channel_code, rule_name, reason FROM service_whitelist"
        )
        await conn.close()
        kayitlar = [dict(r) for r in rows]
        whitelist_yukle(kayitlar)
        logger.info(f"Whitelist yuklendi: {len(kayitlar)} kural")
    except Exception as e:
        logger.error(f"Whitelist yukleme hatasi: {e}")


async def save_detection_run(started_at, logs_processed, anomalies_found, zabbix_sent, status, error=None):
    try:
        conn = await get_db_conn()
        await conn.execute("""
            INSERT INTO detection_runs
              (started_at, finished_at, logs_processed, anomalies_found, zabbix_sent, status, error)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, started_at, datetime.utcnow(), logs_processed, anomalies_found, zabbix_sent, status, error)
        await conn.close()
    except Exception as e:
        logger.error(f"Detection run kayit hatasi: {e}")


async def processing_loop(consumer_name: str = "engine-1"):
    logger.info(f"Processing loop baslatildi: {consumer_name}")
    _stats["loop_running"] = True
    redis_client = None
    while True:
        started_at = datetime.utcnow()
        batch_logs = 0
        batch_anomalies = 0
        try:
            last_reload = _stats.get("last_settings_reload")
            if last_reload:
                elapsed = (datetime.utcnow() - datetime.fromisoformat(last_reload)).total_seconds()
                if elapsed >= 60:
                    await reload_settings_from_db()
                    await reload_whitelist_from_db()
            else:
                await reload_settings_from_db()
                await reload_whitelist_from_db()

            if redis_client is None:
                redis_client = aioredis.from_url(
                    engine_settings.redis_url, encoding="utf-8", decode_responses=True,
                )
                try:
                    await redis_client.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
                    logger.info("Consumer group olusturuldu")
                except aioredis.ResponseError as e:
                    if "BUSYGROUP" not in str(e):
                        logger.error(f"Consumer group hatasi: {e}")

            messages = await redis_client.xreadgroup(
                groupname=CONSUMER_GROUP, consumername=consumer_name,
                streams={STREAM_KEY: ">"}, count=2000, block=5000,
            )
            if not messages:
                continue

            logs, ids = [], []
            for stream, msgs in messages:
                for msg_id, data in msgs:
                    try:
                        logs.append(json.loads(data["data"]))
                        ids.append(msg_id)
                    except Exception as e:
                        logger.error(f"Parse hatasi: {e}")

            if not logs:
                continue

            await redis_client.xack(STREAM_KEY, CONSUMER_GROUP, *ids)
            anomalies = await process_batch(logs)

            batch_logs = len(logs)
            batch_anomalies = len(anomalies)
            _stats["total_batches"] += 1
            _stats["total_logs"] += batch_logs
            _stats["total_anomalies"] += batch_anomalies
            _stats["last_batch_at"] = datetime.utcnow().isoformat()

            if anomalies:
                logger.info(f"Batch: {batch_logs} log, {batch_anomalies} anomali")
                await send_anomalies(anomalies)
                # Cascade failure kontrolu
                try:
                    cascade = cascade_detector_al()
                    if cascade:
                        asyncio.create_task(cascade.kontrol_et(anomalies))
                except Exception as cas_e:
                    logger.error(f"Cascade kontrol hatasi: {cas_e}")
                for anomali in anomalies:
                    try:
                        await notification_service.anomali_bildir(anomali)
                    except Exception as e:
                        logger.error(f"Bildirim hatasi: {e}")

            if _stats["total_batches"] % 10 == 0:
                await save_detection_run(started_at, batch_logs, batch_anomalies, 0, "ok")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Loop hatasi: {e}")
            await save_detection_run(started_at, batch_logs, batch_anomalies, 0, "error", str(e))
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
        k = svc + ":" + ch
        if k not in groups:
            groups[k] = []
        groups[k].append(log)

    all_anomalies = []
    logger.info(f"Batch services: {list(groups.keys())[:5]}")
    # Tum batch loglarini sliding window icin onceden isle
    for _log in logs:
        _rc = _log.get("result", 0)
        if _rc != 0:
            _svc = _log.get("service", "unknown")
            _ch = _log.get("channel_code", "unknown")
            rule_engine.pre_update_window(_svc, _ch, {_rc: 1})
    for key, group_logs in groups.items():
        parts = key.split(":", 1)
        service = parts[0]
        channel = parts[1] if len(parts) > 1 else "unknown"
        features = calculate_features(service, channel, group_logs)

        if "IBMB" in service and features.get("result_codes"): logger.info("IBMB rc=%s tx=%s" % (str(features["result_codes"])[:80], features["tx_count"]))
        rule_anomalies = rule_engine.detect(features)
        zscore_anomalies = zscore_engine.detect(features) if ZSCORE_ENABLED else []
        if_anomaly = if_engine.detect(features) if IF_ENABLED else None

        finals = voting_engine.decide(
            features=features,
            rule_anomalies=rule_anomalies,
            zscore_anomalies=zscore_anomalies,
            if_anomaly=if_anomaly,
        )

        if _stats["total_batches"] % 10 == 0:
            try:
                await baseline_manager.update(
                    service=service, channel_code=channel,
                    error_rate=features["error_rate"],
                    elapsed_mean=features["elapsed_mean"],
                )
            except Exception as e:
                logger.error(f"Baseline hatasi: {e}")

        for f in finals:
            anomali_dict = {
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
                "result_distribution": {str(k): v for k, v in features["result_codes"].items()},
            }
            # LLM RCA arka planda - loop'u bloklama
            asyncio.create_task(_llm_rca_gonder(anomali_dict))
            # Zabbix gonder
            try:
                zabbix = zabbix_al()
                if zabbix:
                    asyncio.create_task(zabbix.anomali_gonder(anomali_dict))
            except Exception as zb_e:
                logger.error(f"Zabbix gonderme hatasi: {zb_e}")
            all_anomalies.append(anomali_dict)
        return all_anomalies


def calculate_features(service, channel, logs):
    tx_count = len(logs)
    if tx_count == 0:
        return {
            "service": service, "channel_code": channel,
            "tx_count": 0, "error_count": 0,
            "error_rate": 0.0, "elapsed_mean": 0.0,
            "elapsed_max": 0.0, "elapsed_p95": 0.0, "elapsed_p99": 0.0,
            "slow_count_disaster": 0, "slow_count_high": 0,
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
    n = len(elapsed_sorted)
    elapsed_p95 = elapsed_sorted[min(int(n * 0.95), n-1)] if elapsed_sorted else 0
    elapsed_p99 = elapsed_sorted[min(int(n * 0.99), n-1)] if elapsed_sorted else 0
    slow_count_disaster = sum(1 for e in elapsed_values if e >= rule_engine_module.ELAPSED_P99_DISASTER)
    slow_count_high = sum(1 for e in elapsed_values if e >= rule_engine_module.ELAPSED_P95_HIGH)

    # Tum result kodlari ve sayilari (0 dahil)
    result_codes = {}
    for log in logs:
        rc = log.get("result", 0)
        if rc != 0:  # Basarili islemleri result_codes'a ekleme
            result_codes[rc] = result_codes.get(rc, 0) + 1

    return {
        "service": service, "channel_code": channel,
        "tx_count": tx_count, "error_count": error_count,
        "error_rate": error_count / tx_count,
        "elapsed_mean": elapsed_mean, "elapsed_max": elapsed_max,
        "elapsed_p95": elapsed_p95, "elapsed_p99": elapsed_p99,
        "slow_count_disaster": slow_count_disaster, "slow_count_high": slow_count_high,
        "sys_error_count": sys_errors, "biz_error_count": biz_errors,
        "sys_error_rate": sys_errors / tx_count,
        "biz_error_rate": biz_errors / tx_count,
        "result_codes": result_codes, "window_seconds": 60,
    }


async def nightly_scheduler():
    """Her gece 02:00'de model yeniden egitimi yapar."""
    import datetime as dt
    while True:
        try:
            now = dt.datetime.utcnow() + dt.timedelta(hours=3)  # TR saati
            # Bugun veya yarin 02:00'e kac saniye kaldi
            hedef = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if now >= hedef:
                hedef += dt.timedelta(days=1)
            bekle = (hedef - now).total_seconds()
            logger.info(f"Gece egitimi icin bekleniyor: {int(bekle/3600)}s {int((bekle%3600)/60)}dk")
            await asyncio.sleep(bekle)
            await model_trainer.nightly_retrain()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Gece scheduler hatasi: {e}")
            await asyncio.sleep(3600)  # Hata durumunda 1 saat bekle


async def _llm_rca_gonder(anomali_dict: dict):
    """LLM RCA analizini arka planda calistirir - loop'u bloklamaz."""
    try:
        # Ingest tamamlansin diye bekle
        await asyncio.sleep(5)

        # Once DB'den anomali ID'sini bul
        conn = await get_db_conn()
        row = await conn.fetchrow(
            """SELECT id FROM anomaly_events
               WHERE service = $1
                 AND channel_code = $2
                 AND ai_analysis IS NULL
               ORDER BY detected_at DESC
               LIMIT 1""",
            anomali_dict.get("service"),
            anomali_dict.get("channel_code"),
        )
        await conn.close()

        if not row:
            logger.warning(f"LLM RCA: Anomali bulunamadi: {anomali_dict.get('service')}")
            return

        anomaly_id = row["id"]

        # RAG context olustur
        rag_context = None
        try:
            rag = rag_al()
            if rag:
                rag_context = await rag.context_olustur(anomali_dict)
        except Exception as rag_e:
            logger.warning(f"RAG context hatasi (devam edildi): {rag_e}")

        # LLM analizi yap
        ai_analysis = await llm_rca_service.rca_analiz(anomali_dict, rag_context=rag_context)
        if not ai_analysis:
            return

        # ID ile UPDATE at
        conn = await get_db_conn()
        await conn.execute(
            "UPDATE anomaly_events SET ai_analysis = $1 WHERE id = $2",
            ai_analysis, anomaly_id
        )
        await conn.close()
        logger.info(f"LLM RCA DB'ye yazildi: {anomali_dict.get('service')} (id={anomaly_id})")

    except Exception as e:
        logger.error(f"LLM RCA arka plan hatasi: {e}")


async def send_anomalies(anomalies):
    if not anomalies:
        return
    try:
        data = json.dumps(anomalies)
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", engine_settings.app_url + "/api/v1/anomalies/ingest",
             "-H", "Content-Type: application/json", "-d", data],
            capture_output=True, text=True, timeout=10,
        )
        logger.info(f"{len(anomalies)} anomali gonderildi: {result.stdout[:100]}")
    except Exception as e:
        logger.error(f"Anomali gonderim hatasi: {e}")


def _test_anomali():
    return {
        "service": "TEST_SERVICE",
        "channel_code": "000",
        "anomaly_type": "test",
        "severity": notification_service.min_severity or "HIGH",
        "score": 99.9,
        "error_rate": 0.75,
        "elapsed_mean": 5000,
        "tx_count": 100,
        "summary": "Bu bir test bildirimidir - Lumen AIOps",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "Lumen Engine",
        "stats": _stats,
        "notification": {
            "enabled": notification_service.enabled,
            "min_severity": notification_service.min_severity,
            "teams": bool(notification_service.teams_webhook_url),
            "email": bool(notification_service.smtp_host and notification_service.smtp_to),
        }
    }


@app.get("/stats")
async def stats():
    return {
        **_stats,
        "rule_engine_settings": {
            "min_tx_count": rule_engine_module.MIN_TX_COUNT,
            "min_slow_tx_count": rule_engine_module.MIN_SLOW_TX_COUNT,
            "cooldown_seconds": rule_engine_module.COOLDOWN_SECONDS,
            "elapsed_p95_high": rule_engine_module.ELAPSED_P95_HIGH,
            "elapsed_p99_disaster": rule_engine_module.ELAPSED_P99_DISASTER,
            "sys_error_code_threshold": rule_engine_module.SYS_ERROR_CODE_THRESHOLD,
            "biz_error_code_threshold": rule_engine_module.BIZ_ERROR_CODE_THRESHOLD,
            "whitelist_count": len(rule_engine_module._WHITELIST),
        },
        "zscore_settings": {
            "enabled": ZSCORE_ENABLED,
            "threshold_warning": engine_settings.zscore_threshold_warning,
            "threshold_high": engine_settings.zscore_threshold_high,
            "rolling_minutes": engine_settings.zscore_rolling_minutes,
        }
    }


@app.post("/reload-settings")
async def trigger_reload():
    await reload_settings_from_db()
    await reload_whitelist_from_db()
    return {
        "status": "ok",
        "zscore_enabled": ZSCORE_ENABLED,
        "if_enabled": IF_ENABLED,
        "zscore_threshold_warning": engine_settings.zscore_threshold_warning,
        "zscore_threshold_high": engine_settings.zscore_threshold_high,
        "whitelist_count": len(rule_engine_module._WHITELIST),
        "notification_enabled": notification_service.enabled,
    }


@app.post("/test-notification")
async def test_notification(kanal: str = "hepsi"):
    anomali = _test_anomali()
    _notification_cooldown.clear()
    try:
        if kanal == "teams":
            if not notification_service.teams_webhook_url:
                return {"status": "error", "message": "Teams webhook URL tanimli degil"}
            await notification_service._teams_gonder(anomali)
            return {"status": "ok", "kanal": "teams"}
        elif kanal == "email":
            if not notification_service.smtp_host:
                return {"status": "error", "message": "SMTP sunucusu tanimli degil"}
            if not notification_service.smtp_to:
                return {"status": "error", "message": "Alici e-posta adresi tanimli degil"}
            await notification_service._email_gonder(anomali)
            return {"status": "ok", "kanal": "email", "alicilar": notification_service.smtp_to}
        else:
            await notification_service.anomali_bildir(anomali)
            return {"status": "ok", "kanal": "hepsi"}
    except Exception as e:
        logger.error(f"Test bildirimi hatasi: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/llm/test")
async def test_llm():
    result = await llm_rca_service.baglanti_test()
    return result


if __name__ == "__main__":
    uvicorn.run("engine.main:app", host="0.0.0.0", port=engine_settings.engine_port, reload=False, log_config=None)
