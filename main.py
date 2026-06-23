"""
Lumen AIOps — Ana uygulama giriş noktası
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.settings import settings
from app.database import init_db
from app.enrichment.error_codes import error_code_service
from app.queue.redis_stream import redis_queue
from app.zabbix.client import zabbix_client
from app.auth.routes import router as auth_router
from app.api.routes import router as api_router
from app.ingest.receiver import router as ingest_router
from app.api.password import router as password_router
from app.ml_p95_watcher import watcher_baslat, watcher_durdur, watcher_durum

# Logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/app/logs/lumen.log"),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────
    logger.info(f"{settings.app_name} başlatılıyor…")

    # DB tablolarını oluştur
    await init_db()
    logger.info("Veritabanı hazır.")

    # Hata kodlarını yükle
    count = await error_code_service.load()
    logger.info(f"Hata kodları yüklendi: {count} kayıt")

    # Redis Stream bağlantısı
    await redis_queue.connect()
    logger.info("Redis Stream hazır.")

    # Zabbix bağlantısı
    if settings.zabbix_url:
        try:
            await zabbix_client._ensure_host()
            logger.info("Zabbix bağlantısı hazır.")
        except Exception as e:
            logger.warning(f"Zabbix bağlantısı kurulamadı: {e}")

    # ML P95 Response Time anomali watcher
    try:
        watcher_baslat()
        logger.info(f"ML P95 watcher hazır: {watcher_durum()}")
    except Exception as e:
        logger.warning(f"ML P95 watcher başlatılamadı: {e}")

    logger.info(f"{settings.app_name} hazır ✓")

    yield

    # ── Shutdown ─────────────────────────────────────
    logger.info(f"{settings.app_name} durduruluyor…")
    await watcher_durdur()
    await redis_queue.disconnect()
    await zabbix_client.close()
    logger.info(f"{settings.app_name} durduruldu.")


# FastAPI
app = FastAPI(
    title=f"{settings.app_name} AIOps",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router'lar
app.include_router(auth_router)
app.include_router(api_router)
app.include_router(ingest_router)
app.include_router(password_router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=False,
        log_config=None,
    )
