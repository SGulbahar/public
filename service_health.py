"""
Service Health Lifecycle Manager
=================================
Her anomali geldiginde service_health tablosunu gunceller.

Yasam dongusu:
  Anomali geldi:
    - Aktif kayit var mi? → guncelle (count++, severity, error_rate, elapsed)
    - Yoksa → yeni aktif kayit ac

  Periyodik kontrol (her 5dk):
    - Son 30dk icinde anomali gelmeyen aktif kayitlari resolved yap
    - root_cause_hint icin LLM ozeti ekle

Kullanim (engine/main.py):
    from engine.service_health import ServiceHealthManager
    sh = ServiceHealthManager(db_dsn)
    await sh.baglanti_ac()
    await sh.anomali_isle(anomali_dict)
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

RESOLVE_DAKIKA = 30  # Kac dakika anomali gelmezse resolved sayilir
KONTROL_ARALIK = 300  # Kac saniyede bir kontrol yapilir (5dk)

SEV_ORDER = {"WARNING": 1, "HIGH": 2, "DISASTER": 3}


class ServiceHealthManager:
    def __init__(self, db_dsn: str):
        self._db_dsn = db_dsn
        self._pool = None
        self._task: Optional[asyncio.Task] = None

    async def baglanti_ac(self):
        import asyncpg
        self._pool = await asyncpg.create_pool(
            self._db_dsn, min_size=1, max_size=3
        )
        logger.info("ServiceHealthManager hazir")

    async def baglanti_kapat(self):
        if self._pool:
            await self._pool.close()

    async def anomali_isle(self, anomali: dict):
        """Anomali geldiginde service_health tablosunu gunceller."""
        service = anomali.get("service", "")
        channel = anomali.get("channel_code", "unknown")
        severity = anomali.get("severity", "WARNING")
        error_rate = float(anomali.get("error_rate") or 0)
        elapsed = float(anomali.get("elapsed_mean") or 0)
        summary = anomali.get("summary", "")

        if not service:
            return

        try:
            async with self._pool.acquire() as conn:
                # Aktif kayit var mi?
                mevcut = await conn.fetchrow("""
                    SELECT id, anomali_count, max_severity, avg_error_rate, avg_elapsed
                    FROM service_health
                    WHERE service = $1 AND channel_code = $2 AND status = 'active'
                """, service, channel)

                if mevcut:
                    # Guncelle
                    yeni_count = mevcut["anomali_count"] + 1
                    yeni_severity = (
                        severity if SEV_ORDER.get(severity, 0) > SEV_ORDER.get(mevcut["max_severity"], 0)
                        else mevcut["max_severity"]
                    )
                    # Hareketli ortalama
                    yeni_error = (mevcut["avg_error_rate"] * mevcut["anomali_count"] + error_rate) / yeni_count
                    yeni_elapsed = (mevcut["avg_elapsed"] * mevcut["anomali_count"] + elapsed) / yeni_count

                    await conn.execute("""
                        UPDATE service_health SET
                            anomali_count = $1,
                            max_severity = $2,
                            avg_error_rate = $3,
                            avg_elapsed = $4
                        WHERE id = $5
                    """, yeni_count, yeni_severity, yeni_error, yeni_elapsed, mevcut["id"])
                else:
                    # Yeni aktif kayit ac
                    await conn.execute("""
                        INSERT INTO service_health
                            (service, channel_code, status, started_at, anomali_count,
                             max_severity, avg_error_rate, avg_elapsed, root_cause_hint)
                        VALUES ($1, $2, 'active', NOW(), 1, $3, $4, $5, $6)
                        ON CONFLICT (service, channel_code) WHERE status = 'active'
                        DO UPDATE SET
                            anomali_count = service_health.anomali_count + 1,
                            max_severity = CASE
                                WHEN EXCLUDED.max_severity > service_health.max_severity THEN EXCLUDED.max_severity
                                ELSE service_health.max_severity
                            END
                    """, service, channel, severity, error_rate, elapsed, summary[:200] if summary else "")

        except Exception as e:
            logger.error(f"ServiceHealth anomali_isle hatasi: {e}")

    async def _resolve_kontrol(self):
        """Son RESOLVE_DAKIKA dk anomali gelmeyen servisleri resolved yapar."""
        try:
            async with self._pool.acquire() as conn:
                # Son 30dk icinde anomali gelmeyen aktif kayitlari bul
                esik = datetime.utcnow() - timedelta(minutes=RESOLVE_DAKIKA)

                # Son anomali zamanini anomaly_events'ten kontrol et
                rows = await conn.fetch("""
                    SELECT sh.id, sh.service, sh.channel_code, sh.anomali_count,
                           sh.max_severity, sh.started_at
                    FROM service_health sh
                    WHERE sh.status = 'active'
                      AND NOT EXISTS (
                          SELECT 1 FROM anomaly_events ae
                          WHERE ae.service = sh.service
                            AND ae.channel_code = sh.channel_code
                            AND ae.detected_at >= $1
                            AND ae.is_false_positive = false
                      )
                """, esik)

                if rows:
                    for r in rows:
                        await conn.execute("""
                            UPDATE service_health SET
                                status = 'resolved',
                                resolved_at = NOW()
                            WHERE id = $1
                        """, r["id"])
                        logger.info(
                            f"ServiceHealth resolved: {r['service']}[{r['channel_code']}] "
                            f"({r['anomali_count']} anomali, {r['max_severity']})"
                        )

        except Exception as e:
            logger.error(f"ServiceHealth resolve_kontrol hatasi: {e}")

    async def _periyodik_kontrol(self):
        """Periyodik olarak resolve kontrolu yapar."""
        while True:
            await asyncio.sleep(KONTROL_ARALIK)
            await self._resolve_kontrol()

    def baslat(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._periyodik_kontrol())
        return self._task

    async def durdur(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.baglanti_kapat()


# Singleton
_sh_manager: Optional[ServiceHealthManager] = None


def sh_baslat(db_dsn: str) -> ServiceHealthManager:
    global _sh_manager
    _sh_manager = ServiceHealthManager(db_dsn)
    return _sh_manager


def sh_al() -> Optional[ServiceHealthManager]:
    return _sh_manager
