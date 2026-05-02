"""
Baseline Manager
- RAM buffer'da biriktirir
- Her 5 dakikada bir PostgreSQL'e toplu yazar
- Engine hizini artirmak icin DB bekleme suresi kaldirildi
"""
import logging
from datetime import datetime
from collections import defaultdict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from engine.settings import engine_settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    engine_settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=2,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class BaselineManager:
    def __init__(self):
        self._cache: dict = {}
        self._buffer: dict = defaultdict(list)
        self._last_flush = datetime.utcnow()
        self._flush_interval = 300  # 5 dakika
        logger.info("Baseline Manager baslatildi (async buffer modu).")

    async def update(self, service: str, channel_code: str, error_rate: float, elapsed_mean: float):
        """
        Veriyi RAM buffer'a ekler.
        DB'ye yazmaz — flush() ile toplu yazilir.
        """
        key = f"{service}:{channel_code}"
        now = datetime.utcnow()
        self._buffer[key].append({
            "service": service,
            "channel_code": channel_code,
            "error_rate": error_rate,
            "elapsed_mean": elapsed_mean,
            "ts": now,
        })

        # 5 dakikada bir otomatik flush
        elapsed = (now - self._last_flush).total_seconds()
        if elapsed >= self._flush_interval:
            await self.flush()

    async def flush(self):
        """Buffer'daki tum veriyi PostgreSQL'e yazar."""
        if not self._buffer:
            return

        buffer_copy = dict(self._buffer)
        self._buffer.clear()
        self._last_flush = datetime.utcnow()

        try:
            async with AsyncSessionLocal() as db:
                for key, samples in buffer_copy.items():
                    if not samples:
                        continue

                    service = samples[0]["service"]
                    channel_code = samples[0]["channel_code"]
                    now = datetime.utcnow()
                    weekday = now.weekday()
                    hour_bucket = now.hour

                    # Ortalama hesapla
                    avg_error = sum(s["error_rate"] for s in samples) / len(samples)
                    avg_elapsed = sum(s["elapsed_mean"] for s in samples) / len(samples)

                    result = await db.execute(text("""
                        SELECT mean_error, std_error, mean_elapsed, std_elapsed, sample_count
                        FROM baseline_stats
                        WHERE service = :service
                        AND channel_code = :channel
                        AND weekday = :weekday
                        AND hour_bucket = :hour
                    """), {
                        "service": service,
                        "channel": channel_code,
                        "weekday": weekday,
                        "hour": hour_bucket,
                    })
                    row = result.fetchone()

                    if row:
                        n = row.sample_count + len(samples)
                        new_mean_err = row.mean_error + (avg_error - row.mean_error) / n
                        new_mean_ela = row.mean_elapsed + (avg_elapsed - row.mean_elapsed) / n
                        new_std_err = (row.std_error * (n - 1) + abs(avg_error - new_mean_err)) / n
                        new_std_ela = (row.std_elapsed * (n - 1) + abs(avg_elapsed - new_mean_ela)) / n

                        await db.execute(text("""
                            UPDATE baseline_stats
                            SET mean_error = :mean_error,
                                std_error = :std_error,
                                mean_elapsed = :mean_elapsed,
                                std_elapsed = :std_elapsed,
                                sample_count = :sample_count,
                                updated_at = NOW()
                            WHERE service = :service
                            AND channel_code = :channel
                            AND weekday = :weekday
                            AND hour_bucket = :hour
                        """), {
                            "mean_error": new_mean_err,
                            "std_error": new_std_err,
                            "mean_elapsed": new_mean_ela,
                            "std_elapsed": new_std_ela,
                            "sample_count": n,
                            "service": service,
                            "channel": channel_code,
                            "weekday": weekday,
                            "hour": hour_bucket,
                        })
                    else:
                        await db.execute(text("""
                            INSERT INTO baseline_stats (
                                service, channel_code, weekday, hour_bucket,
                                mean_error, std_error, mean_elapsed, std_elapsed, sample_count
                            ) VALUES (
                                :service, :channel, :weekday, :hour,
                                :mean_error, :std_error, :mean_elapsed, :std_elapsed, 1
                            )
                        """), {
                            "service": service,
                            "channel": channel_code,
                            "weekday": weekday,
                            "hour": hour_bucket,
                            "mean_error": avg_error,
                            "std_error": 0.0,
                            "mean_elapsed": avg_elapsed,
                            "std_elapsed": 0.0,
                        })

                await db.commit()
                logger.info(f"Baseline flush: {len(buffer_copy)} kombinasyon yazildi")

        except Exception as e:
            logger.error(f"Baseline flush hatasi: {e}")

    async def load_seasonal(self, service: str, channel_code: str, weekday: int, hour_bucket: int) -> dict:
        key = f"{service}:{channel_code}:{weekday}:{hour_bucket}"
        if key in self._cache:
            return self._cache[key]

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                SELECT mean_error, std_error, mean_elapsed, std_elapsed, sample_count
                FROM baseline_stats
                WHERE service = :service
                AND channel_code = :channel
                AND weekday = :weekday
                AND hour_bucket = :hour
            """), {
                "service": service,
                "channel": channel_code,
                "weekday": weekday,
                "hour": hour_bucket,
            })
            row = result.fetchone()

        if row and row.sample_count >= 10:
            data = {
                "mean_error": row.mean_error,
                "std_error": row.std_error,
                "mean_elapsed": row.mean_elapsed,
                "std_elapsed": row.std_elapsed,
                "sample_count": row.sample_count,
            }
            self._cache[key] = data
            return data
        return {}

    async def load_all_seasonal(self) -> list:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                SELECT service, channel_code, weekday, hour_bucket,
                       mean_error, std_error, mean_elapsed, std_elapsed, sample_count
                FROM baseline_stats
                WHERE sample_count >= 10
            """))
            rows = result.fetchall()
        return [
            {
                "service": r.service,
                "channel_code": r.channel_code,
                "weekday": r.weekday,
                "hour_bucket": r.hour_bucket,
                "mean_error": r.mean_error,
                "std_error": r.std_error,
                "mean_elapsed": r.mean_elapsed,
                "std_elapsed": r.std_elapsed,
                "sample_count": r.sample_count,
            }
            for r in rows
        ]

    def clear_cache(self):
        self._cache.clear()

    def buffer_size(self) -> int:
        return sum(len(v) for v in self._buffer.values())


baseline_manager = BaselineManager()
