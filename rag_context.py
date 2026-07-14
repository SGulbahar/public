"""
RAG Context Builder
PostgreSQL'den gecmis anomali verilerini cezip LLM prompt'una ekler.
Embedding veya vektor DB gerektirmez — SQL bazli semantik zenginlestirme.
"""
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RAGContextBuilder:

    async def _zabbix_problemleri_al(self, anomali_zamani) -> str:
        """Anomali zamani etrafindaki Zabbix kritik alarmlarini ceker."""
        try:
            import aiohttp as _aiohttp
            from cryptography.fernet import Fernet as _Fernet
            import os as _os
            from datetime import datetime as _dt, timedelta as _td

            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='zabbix'"
                )
                if not row or not row["enabled"]:
                    return ""
                config = dict(row["config"]) if row["config"] else {}
                secrets_raw = dict(row["secrets"]) if row["secrets"] else {}

            secret_key = _os.environ.get("LUMEN_SECRET_KEY", "")
            secrets = {}
            if secret_key:
                f = _Fernet(secret_key.encode())
                for k, v in secrets_raw.items():
                    try:
                        secrets[k] = f.decrypt(v.encode()).decode()
                    except Exception:
                        secrets[k] = v
            else:
                secrets = secrets_raw

            url = config.get("url", "").rstrip("/")
            user = config.get("user", "Admin")
            password = secrets.get("password", "")
            if not url or not password:
                return ""

            try:
                if isinstance(anomali_zamani, str):
                    dt = _dt.fromisoformat(anomali_zamani.replace("Z", ""))
                else:
                    dt = _dt.utcnow()
            except Exception:
                dt = _dt.utcnow()

            time_from = int((dt - _td(minutes=30)).timestamp())
            time_till = int((dt + _td(minutes=30)).timestamp())

            async with _aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    json={"jsonrpc": "2.0", "method": "user.login",
                          "params": {"username": user, "password": password}, "id": 1},
                    ssl=False, timeout=_aiohttp.ClientTimeout(total=10)
                ) as r:
                    data = await r.json()
                    token = data.get("result")
                    if not token:
                        return ""

                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"jsonrpc": "2.0", "method": "event.get", "params": {
                        "output": ["eventid", "name", "severity", "clock"],
                        "severities": [4, 5],
                        "value": 1,
                        "time_from": time_from,
                        "time_till": time_till,
                        "selectHosts": ["name"],
                        "limit": 10
                    }, "id": 1},
                    ssl=False, timeout=_aiohttp.ClientTimeout(total=10)
                ) as r:
                    data = await r.json()
                    events = data.get("result", [])

            if not events:
                return ""

            SEV_MAP = {"4": "Yuksek", "5": "Kritik"}
            lines = []
            for e in events:
                host_adi = e["hosts"][0]["name"] if e.get("hosts") else "Bilinmiyor"
                sev = SEV_MAP.get(str(e.get("severity", "")), "?")
                lines.append(f"  - [{sev}] {e['name']} | Host: {host_adi}")

            return "Anomali Zamani Zabbix Alarmlari (+-30 dakika, " + str(len(events)) + " alarm):\n" + "\n".join(lines)


        except Exception as ex:
            logger.debug(f"Zabbix problem cekme hatasi: {ex}")
            return ""

    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn
        self._pool = None

    async def baglanti_ac(self):
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(self.db_dsn, min_size=1, max_size=3)
            logger.info("RAG DB baglantisi hazir")
        except Exception as e:
            logger.error(f"RAG DB baglanti hatasi: {e}")

    async def baglanti_kapat(self):
        if self._pool:
            await self._pool.close()

    async def context_olustur(self, anomali: dict) -> Optional[str]:
        """
        Anomali icin gecmis veri context'i olusturur.
        LLM prompt'una eklenmek uzere Turkce metin dondurur.
        """
        if not self._pool:
            return None

        service = anomali.get("service", "")
        channel = anomali.get("channel_code", "")
        result_code = anomali.get("result_code", 0)
        detected_at = anomali.get("detected_at") or datetime.utcnow().isoformat()

        try:
            async with self._pool.acquire() as conn:
                parts = []

                # 1. Son 30 gunde bu servisten kac anomali uretildi
                gecmis = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as toplam,
                        SUM(CASE WHEN severity='DISASTER' THEN 1 ELSE 0 END) as kritik,
                        SUM(CASE WHEN severity='HIGH' THEN 1 ELSE 0 END) as yuksek,
                        SUM(CASE WHEN is_false_positive=true THEN 1 ELSE 0 END) as yanlis_tespit,
                        MIN(detected_at) as ilk_gorulme
                    FROM anomaly_events
                    WHERE service = $1
                      AND detected_at >= NOW() - INTERVAL '30 days'
                      AND id != COALESCE($2, -1)
                """, service, anomali.get("id"))

                if gecmis and gecmis["toplam"] > 0:
                    parts.append(
                        f"Son 30 Gün Gecmisi ({service}):\n"
                        f"  Toplam anomali: {gecmis['toplam']} adet "
                        f"({gecmis['kritik']} kritik, {gecmis['yuksek']} yuksek)\n"
                        f"  Yanlis tespit: {gecmis['yanlis_tespit']} adet\n"
                        f"  Ilk gorulme: {gecmis['ilk_gorulme'].strftime('%d.%m.%Y %H:%M') if gecmis['ilk_gorulme'] else '-'}"
                    )
                else:
                    parts.append(f"Son 30 Gün Gecmisi ({service}): Daha once anomali uretmemis.")

                # 2. Son 3 anomalinin ozeti
                son_anomaliler = await conn.fetch("""
                    SELECT detected_at, severity, summary, anomaly_type,
                           error_rate, elapsed_mean, acknowledged, is_false_positive
                    FROM anomaly_events
                    WHERE service = $1
                      AND detected_at >= NOW() - INTERVAL '30 days'
                      AND id != COALESCE($2, -1)
                    ORDER BY detected_at DESC
                    LIMIT 3
                """, service, anomali.get("id"))

                if son_anomaliler:
                    onceki = []
                    for a in son_anomaliler:
                        durum = "Yanlis Tespit" if a["is_false_positive"] else ("Onaylandi" if a["acknowledged"] else "Degerlendirilmedi")
                        onceki.append(
                            f"  • {a['detected_at'].strftime('%d.%m %H:%M')} | "
                            f"{a['severity']} | {a['anomaly_type'].upper()} | "
                            f"Hata:%{(a['error_rate'] or 0)*100:.0f} | "
                            f"Elapsed:{int(a['elapsed_mean'] or 0)}ms | {durum}"
                        )
                    parts.append("Onceki Anomaliler:\n" + "\n".join(onceki))

                # 3. Baseline karsilastirmasi
                baseline = await conn.fetchrow("""
                    SELECT
                        AVG(mean_error) as ort_hata,
                        AVG(std_error) as std_hata,
                        AVG(mean_elapsed) as ort_elapsed,
                        AVG(std_elapsed) as std_elapsed,
                        SUM(sample_count) as toplam_ornek,
                        EXTRACT(DOW FROM NOW()) as bugun,
                        EXTRACT(HOUR FROM NOW()) as saat
                    FROM baseline_stats
                    WHERE service = $1
                      AND channel_code = $2
                      AND weekday = EXTRACT(DOW FROM NOW())::int
                      AND hour_bucket = EXTRACT(HOUR FROM NOW())::int
                """, service, channel)

                if baseline and baseline["toplam_ornek"] and baseline["toplam_ornek"] > 0:
                    baz_hata = (baseline["ort_hata"] or 0) * 100
                    sim_hata = (anomali.get("error_rate", 0) or 0) * 100
                    baz_elapsed = int(baseline["ort_elapsed"] or 0)
                    sim_elapsed = int(anomali.get("elapsed_mean", 0) or 0)

                    sapma_hata = ""
                    if baseline["std_hata"] and baseline["std_hata"] > 0:
                        z = (anomali.get("error_rate", 0) - (baseline["ort_hata"] or 0)) / baseline["std_hata"]
                        sapma_hata = f" (Z-score: {z:.1f}σ)"

                    parts.append(
                        f"Baseline Karsilastirma (Bu gun/saat icin {int(baseline['toplam_ornek'])} ornekten):\n"
                        f"  Normal hata orani: %{baz_hata:.1f} → Simdi: %{sim_hata:.1f}{sapma_hata}\n"
                        f"  Normal elapsed: {baz_elapsed}ms → Simdi: {sim_elapsed}ms"
                    )

                # 4. Ayni zaman diliminde baska etkilenen servisler
                ayni_donem = await conn.fetch("""
                    SELECT service, severity, summary
                    FROM anomaly_events
                    WHERE detected_at BETWEEN $1::timestamp - INTERVAL '10 minutes'
                                          AND $1::timestamp + INTERVAL '10 minutes'
                      AND service != $2
                      AND is_false_positive = false
                    ORDER BY detected_at DESC
                    LIMIT 5
                """, detected_at, service)

                if ayni_donem:
                    etkilenen = [f"  • {a['service']} ({a['severity']})" for a in ayni_donem]
                    parts.append(
                        f"Ayni Zaman Diliminde Etkilenen Diger Servisler ({len(ayni_donem)} adet):\n"
                        + "\n".join(etkilenen)
                    )

                # 5. En sik hata kodu analizi (son 7 gun)
                if result_code and result_code != 0:
                    kod_gecmis = await conn.fetchrow("""
                        SELECT COUNT(*) as gorulme_sayisi,
                               MAX(detected_at) as son_gorulme
                        FROM anomaly_events
                        WHERE summary LIKE $1
                          AND detected_at >= NOW() - INTERVAL '7 days'
                          AND id != COALESCE($2, -1)
                    """, f"%{result_code}%", anomali.get("id"))

                    if kod_gecmis and kod_gecmis["gorulme_sayisi"] > 0:
                        parts.append(
                            f"Hata Kodu {result_code} Gecmisi (Son 7 gun):\n"
                            f"  {kod_gecmis['gorulme_sayisi']} farkli anomalide goruldu\n"
                            f"  Son gorulme: {kod_gecmis['son_gorulme'].strftime('%d.%m.%Y %H:%M') if kod_gecmis['son_gorulme'] else '-'}"
                        )

                # 6. Hata kodu aciklamasi (error_codes tablosundan)
                if result_code and result_code != 0:
                    kod_aciklama = await conn.fetchrow("""
                        SELECT description, category
                        FROM error_codes
                        WHERE result_code = $1
                        LIMIT 1
                    """, result_code)

                    if kod_aciklama:
                        kategori = "Sistem Hatası" if kod_aciklama["category"] == "SYS" else "İş Hatası"
                        parts.append(
                            "Hata Kodu Tanimi (%s) [Referans amacli — servis baglamiyla celiSiyorsa ozeti esas al]:\n  Kategori: %s\n  Genel Aciklama: %s" %
                            (result_code, kategori, kod_aciklama["description"])
                        )

                # 7. Son 1 saatteki trend (artiyor mu azaliyor mu)
                trend = await conn.fetch("""
                    SELECT
                        DATE_TRUNC('minute', detected_at) - 
                        (EXTRACT(MINUTE FROM detected_at)::int % 10) * INTERVAL '1 minute' as dilim,
                        COUNT(*) as adet,
                        AVG(CASE WHEN severity='DISASTER' THEN 3 WHEN severity='HIGH' THEN 2 ELSE 1 END) as agirlik
                    FROM anomaly_events
                    WHERE service = $1
                      AND detected_at >= NOW() - INTERVAL '1 hour'
                      AND is_false_positive = false
                    GROUP BY dilim
                    ORDER BY dilim DESC
                    LIMIT 6
                """, service)

                if trend and len(trend) >= 2:
                    sayilar = [int(t["adet"]) for t in trend]
                    if sayilar[0] > sayilar[-1]:
                        trend_yon = "ARTIYOR"
                    elif sayilar[0] < sayilar[-1]:
                        trend_yon = "AZALIYOR"
                    else:
                        trend_yon = "SABIT"
                    parts.append(
                        f"Son 1 Saat Trend: {trend_yon} "
                        f"(son 10dk: {sayilar[0]} anomali, 60dk once: {sayilar[-1]} anomali)"
                    )

                # 8. Servisin haftalik anomali pattern analizi
                haftalik = await conn.fetch("""
                    SELECT
                        TRIM(TO_CHAR(detected_at AT TIME ZONE 'Europe/Istanbul', 'Day')) as gun,
                        EXTRACT(HOUR FROM detected_at AT TIME ZONE 'Europe/Istanbul') as saat,
                        COUNT(*) as adet
                    FROM anomaly_events
                    WHERE service = $1
                      AND detected_at >= NOW() - INTERVAL '30 days'
                      AND is_false_positive = false
                    GROUP BY gun, saat
                    ORDER BY adet DESC
                    LIMIT 3
                """, service)

                if haftalik and len(haftalik) >= 2:
                    pattern = [f"  • {h['gun']} {int(h['saat']):02d}:00 → {h['adet']} anomali" for h in haftalik]
                    parts.append("Anomali Pattern (En yogun zamanlar):\n" + "\n".join(pattern))

                # Zabbix kritik alarmlar
                try:
                    zabbix_ctx = await self._zabbix_problemleri_al(detected_at)
                    if zabbix_ctx:
                        parts.append(zabbix_ctx)
                except Exception as zb_e:
                    logger.debug(f"Zabbix RAG hatasi: {zb_e}")

                if not parts:
                    return None

                context = "\n\n".join(parts)
                logger.info(f"RAG context olusturuldu: {service} ({len(context)} karakter)")
                return context

        except Exception as e:
            logger.error(f"RAG context hatasi: {e}")
            return None


# Singleton
_rag_instance = None


def rag_baslat(db_dsn: str) -> RAGContextBuilder:
    global _rag_instance
    _rag_instance = RAGContextBuilder(db_dsn)
    return _rag_instance


def rag_al() -> Optional[RAGContextBuilder]:
    return _rag_instance
