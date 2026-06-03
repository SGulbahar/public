"""
Cascade Failure Detection
=========================
Ayni zaman penceresinde birden fazla servis anomali urettiginde
bunlari tek bir Incident olarak gruplar.

Calisma mantigi:
- Her batch sonunda son N dakikadaki anomalilere bakar
- MIN_AFFECTED_SERVICES esigini gecerse incident olusturur
- Ilk anomali ureten servis -> root_cause
- Diger servisler -> affected
- LLM'e tum anomalileri birlikte gonderir
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Konfigürasyon ─────────────────────────────────────────
WINDOW_SECONDS = 300        # 5 dakikalik pencere
MIN_AFFECTED_SERVICES = 3   # En az 3 farkli servis
COOLDOWN_SECONDS = 1800     # Ayni incident 30 dk tekrar olusturulmasin
SEV_ORDER = {"WARNING": 1, "HIGH": 2, "DISASTER": 3}


class CascadeDetector:
    def __init__(self, db_dsn: str, llm_service=None):
        self.db_dsn = db_dsn
        self.llm_service = llm_service
        self._pool = None
        self._son_incident_zamani: dict = {}  # servis_seti -> datetime
        logger.info("Cascade Detector baslatildi")

    async def baglanti_ac(self):
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self.db_dsn.replace("postgresql+asyncpg://", "postgresql://"),
                min_size=1, max_size=3
            )
            logger.info("Cascade Detector DB baglantisi hazir")
        except Exception as e:
            logger.error(f"Cascade Detector DB baglanti hatasi: {e}")

    async def baglanti_kapat(self):
        if self._pool:
            await self._pool.close()

    async def kontrol_et(self, yeni_anomaliler: list) -> list:
        """
        Yeni anomalileri kontrol eder, cascade varsa incident olusturur.
        Donus: Olusturulan incident listesi
        """
        if not self._pool or not yeni_anomaliler:
            return []

        try:
            async with self._pool.acquire() as conn:
                # Son WINDOW_SECONDS icerisindeki tum anomalileri cek
                pencere_baslangic = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS)
                son_anomaliler = await conn.fetch("""
                    SELECT id, service, channel_code, severity, detected_at,
                           anomaly_type, summary, error_rate, elapsed_mean, tx_count
                    FROM anomaly_events
                    WHERE detected_at >= $1
                      AND is_false_positive = false
                    ORDER BY detected_at ASC
                """, pencere_baslangic)

                if len(son_anomaliler) < MIN_AFFECTED_SERVICES:
                    return []

                # Benzersiz servisler
                servisler = list(set(a["service"] for a in son_anomaliler))
                if len(servisler) < MIN_AFFECTED_SERVICES:
                    return []

                # Bu servis seti icin daha once incident olusturulmus mu
                servis_anahtar = frozenset(servisler)
                son_zaman = self._son_incident_zamani.get(servis_anahtar)
                if son_zaman and (datetime.utcnow() - son_zaman).total_seconds() < COOLDOWN_SECONDS:
                    return []

                # Mevcut acik incident var mi
                mevcut = await conn.fetchrow("""
                    SELECT id FROM incidents
                    WHERE status = 'open'
                      AND detected_at >= $1
                    LIMIT 1
                """, pencere_baslangic)

                if mevcut:
                    # Mevcut incidente yeni anomalileri ekle
                    await self._incidente_anomali_ekle(conn, mevcut["id"], yeni_anomaliler)
                    return []

                # Yeni incident olustur
                incident = await self._incident_olustur(conn, son_anomaliler)
                if incident:
                    self._son_incident_zamani[servis_anahtar] = datetime.utcnow()
                    logger.info(
                        f"CASCADE INCIDENT olusturuldu: ID={incident['id']} "
                        f"Etkilenen={len(servisler)} servis "
                        f"Kok={incident['root_cause_svc']}"
                    )
                    # LLM analizi arka planda
                    if self.llm_service:
                        asyncio.create_task(
                            self._llm_analiz(incident["id"], son_anomaliler)
                        )
                    return [incident]

        except Exception as e:
            logger.error(f"Cascade detection hatasi: {e}")

        return []

    async def _incident_olustur(self, conn, anomaliler: list) -> Optional[dict]:
        """Incident kaydini olusturur."""
        # En yuksek severity'ye sahip ilk anomali -> root cause
        sorted_anoms = sorted(
            anomaliler,
            key=lambda a: (SEV_ORDER.get(a["severity"], 0), a["detected_at"])
        )
        root = sorted_anoms[-1]  # En yuksek severity

        # En erken anomali -> zaman
        ilk_anomali = min(anomaliler, key=lambda a: a["detected_at"])

        servisler = list(set(a["service"] for a in anomaliler))
        max_sev = max(anomaliler, key=lambda a: SEV_ORDER.get(a["severity"], 0))

        # Ozet olustur
        summary = (
            f"Cascade Failure: {len(servisler)} servis etkilendi. "
            f"Ilk anomali: {ilk_anomali['service']} ({ilk_anomali['severity']}). "
            f"Muhtemel kok neden: {root['service']}."
        )

        try:
            row = await conn.fetchrow("""
                INSERT INTO incidents
                    (detected_at, severity, root_cause_svc, root_cause_channel,
                     affected_count, window_seconds, summary, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'open')
                RETURNING id, detected_at, severity, root_cause_svc, affected_count, summary
            """,
                ilk_anomali["detected_at"],
                max_sev["severity"],
                root["service"],
                root["channel_code"],
                len(servisler),
                WINDOW_SECONDS,
                summary
            )

            # Anomalileri incidente bagla
            for a in anomaliler:
                role = "root_cause" if a["service"] == root["service"] else "affected"
                await conn.execute("""
                    INSERT INTO incident_anomalies (incident_id, anomaly_id, role)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                """, row["id"], a["id"], role)

            return dict(row)

        except Exception as e:
            logger.error(f"Incident olusturma hatasi: {e}")
            return None

    async def _incidente_anomali_ekle(self, conn, incident_id: int, anomaliler: list):
        """Mevcut incidente yeni anomalileri ekler."""
        for a in anomaliler:
            try:
                await conn.execute("""
                    INSERT INTO incident_anomalies (incident_id, anomaly_id, role)
                    VALUES ($1, $2, 'affected')
                    ON CONFLICT DO NOTHING
                """, incident_id, a.get("id"))
            except Exception:
                pass
        # affected_count guncelle
        await conn.execute("""
            UPDATE incidents SET
                affected_count = (
                    SELECT COUNT(DISTINCT ae.service)
                    FROM incident_anomalies ia
                    JOIN anomaly_events ae ON ia.anomaly_id = ae.id
                    WHERE ia.incident_id = $1
                )
            WHERE id = $1
        """, incident_id)

    async def _llm_analiz(self, incident_id: int, anomaliler: list):
        """LLM ile cascade failure analizi yapar."""
        if not self.llm_service or not self._pool:
            return
        try:
            servisler = list(set(a["service"] for a in anomaliler))
            ozet_listesi = [
                f"- {a['service']} [{a['channel_code']}]: {a['severity']} - {a['summary'] or 'anomali'}"
                for a in anomaliler
            ]

            prompt = f"""Bankacılık sisteminde cascade failure tespit edildi.
{len(servisler)} farklı servis kısa sürede anomali üretti.

Etkilenen Servisler:
{chr(10).join(ozet_listesi)}

Lütfen:
1. Bu cascade failure'ın muhtemel ortak kök nedeni nedir? (1-2 cümle)
2. Hangi altyapı bileşeni (DB, network, middleware) en olası tetikleyicidir?
3. İlk müdahale için önerilen aksiyon (2 madde)

Yanıt Türkçe ve kısa olsun."""

            # LLM'e gönder
            analiz = await self.llm_service.rca_analiz(
                {
                    "service": "CASCADE_FAILURE",
                    "channel_code": "N/A",
                    "severity": "DISASTER",
                    "summary": f"{len(servisler)} servis etkilendi",
                    "error_rate": 0,
                    "elapsed_mean": 0,
                    "tx_count": len(anomaliler),
                },
                rag_context="\n".join(ozet_listesi)
            )

            if analiz and self._pool:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE incidents SET ai_analysis = $1 WHERE id = $2",
                        analiz, incident_id
                    )
                logger.info(f"Cascade LLM analizi kaydedildi: incident_id={incident_id}")

        except Exception as e:
            logger.error(f"Cascade LLM analiz hatasi: {e}")

    async def acik_incidentler(self) -> list:
        """Acik incidentleri dondurur."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT i.*,
                           array_agg(DISTINCT ae.service) as affected_services
                    FROM incidents i
                    LEFT JOIN incident_anomalies ia ON ia.incident_id = i.id
                    LEFT JOIN anomaly_events ae ON ia.anomaly_id = ae.id
                    WHERE i.status = 'open'
                    GROUP BY i.id
                    ORDER BY i.detected_at DESC
                    LIMIT 20
                """)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Incident listesi hatasi: {e}")
            return []


# Singleton
_cascade_detector = None


def cascade_detector_baslat(db_dsn: str, llm_service=None) -> CascadeDetector:
    global _cascade_detector
    _cascade_detector = CascadeDetector(db_dsn, llm_service)
    return _cascade_detector


def cascade_detector_al() -> Optional[CascadeDetector]:
    return _cascade_detector
