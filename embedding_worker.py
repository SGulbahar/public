"""
Embedding Worker
================
Her EMBED_POLL_SECONDS saniyede bir:
  - knowledge_embeddings'te karsiligi olmayan anomaly_events kayitlarini,
  - embedding'i uretildikten sonra onaylanan / yanlis alarm isaretlenen kayitlari
metne cevirir, maskeler, embedding servisine gonderir ve knowledge_embeddings'e yazar.

Embedding ayarlari integrations tablosundaki key='embedding' kaydindan her turda okunur
(Ayarlar ekranindan degisirse restart gerekmez).
Ic CA: EMBED_CA_FILE veya SSL_CERT_FILE ortam degiskeni.

Ortam degiskenleri:
  EMBED_POLL_SECONDS   (varsayilan 120)
  EMBED_BATCH          (varsayilan 16)
  EMBED_MAX_PER_CYCLE  (varsayilan 500)
  EMBED_CA_FILE / SSL_CERT_FILE
"""
import asyncio
import json
import logging
import os
import re
import ssl
from typing import Optional

logger = logging.getLogger(__name__)

POLL_SECONDS = int(os.environ.get("EMBED_POLL_SECONDS", "120"))
BATCH = int(os.environ.get("EMBED_BATCH", "16"))
MAX_PER_CYCLE = int(os.environ.get("EMBED_MAX_PER_CYCLE", "500"))
DIM = 4096
AI_ANALIZ_MAX = 1500
SUMMARY_MAX = 1000


# --------------------------------------------------------------------------- #
#  Metin uretimi ve maskeleme (backfill script'i ile ayni)                      #
# --------------------------------------------------------------------------- #

_IBAN = re.compile(r"\bTR\d{2}[ ]?(?:\d{4}[ ]?){5}\d{2}\b", re.I)
_KART = re.compile(r"\b\d(?:[ -]?\d){14,15}\b")
_TCKN = re.compile(r"\b[1-9]\d{10}\b")


def maskele(metin: str) -> str:
    if not metin:
        return ""
    metin = _IBAN.sub("[IBAN]", metin)
    metin = _KART.sub("[KART]", metin)
    return _TCKN.sub("[TCKN]", metin)


def _kisalt(metin, n):
    metin = " ".join((metin or "").split())
    return metin if len(metin) <= n else metin[:n].rstrip() + "…"


def _sayi(v, fmt="{:.2f}"):
    return "-" if v is None else fmt.format(v)


def anomali_metni(r, kanal_adi: str) -> str:
    p = [
        f"{r['service'] or 'Bilinmeyen servis'} servisinde ({kanal_adi} kanalı) "
        f"{r['anomaly_type']} tipi {r['severity'] or ''} anomali.".replace("  ", " "),
        f"Zaman: {r['detected_at']:%Y-%m-%d %H:%M}." if r["detected_at"] else "",
    ]
    if r["result_code"] is not None or r["result_desc"]:
        p.append(
            f"Sonuç kodu {r['result_code'] if r['result_code'] is not None else '-'}"
            f"{' (' + r['result_category'] + ')' if r['result_category'] else ''}: "
            f"{_kisalt(r['result_desc'], 300)}."
        )
    er = r["error_rate"]
    p.append(
        f"İşlem sayısı {r['tx_count'] if r['tx_count'] is not None else '-'}, "
        f"hata oranı {_sayi(er * 100 if er is not None and er <= 1 else er, '{:.1f}')}%, "
        f"ortalama süre {_sayi(r['elapsed_mean'], '{:.0f}')} ms, skor {_sayi(r['score'])}."
    )
    if r["summary"]:
        p.append(f"Özet: {_kisalt(r['summary'], SUMMARY_MAX)}")
    if r["ai_analysis"]:
        p.append(f"Analiz: {_kisalt(r['ai_analysis'], AI_ANALIZ_MAX)}")
    if r["is_false_positive"]:
        p.append(
            "Operatör tarafından YANLIŞ ALARM olarak işaretlendi"
            f"{': ' + _kisalt(r['false_positive_reason'], 300) if r['false_positive_reason'] else ''}."
        )
    elif r["acknowledged"]:
        p.append(f"Operatör tarafından onaylandı ({r['acknowledged_by'] or '-'}).")
    if r["itsm_ticket_id"]:
        p.append(f"ITSM kaydı: {r['itsm_ticket_id']}.")
    return maskele(" ".join(x for x in p if x))


def anomali_metadata(r, kanal_adi: str) -> dict:
    return {
        "service": r["service"],
        "channel_code": r["channel_code"],
        "channel_name": kanal_adi,
        "anomaly_type": r["anomaly_type"],
        "severity": r["severity"],
        "result_code": r["result_code"],
        "result_category": r["result_category"],
        "detected_at": r["detected_at"].isoformat() if r["detected_at"] else None,
        "is_false_positive": bool(r["is_false_positive"]),
        "itsm_ticket_id": r["itsm_ticket_id"],
    }


def _vec(v):
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


# --------------------------------------------------------------------------- #
#  SQL                                                                          #
# --------------------------------------------------------------------------- #

SECIM_SQL = """
SELECT a.*, COALESCE(c.channel_name, a.channel_code, '-') AS kanal_adi
FROM anomaly_events a
LEFT JOIN channel_mappings c ON c.channel_code = a.channel_code
LEFT JOIN knowledge_embeddings k
       ON k.source_type = 'anomaly' AND k.source_id = a.id::text
WHERE k.id IS NULL
   OR a.false_positive_at > k.created_at
   OR a.acknowledged_at   > k.created_at
ORDER BY a.id DESC
LIMIT $1
"""

YAZ_SQL = """
INSERT INTO knowledge_embeddings (source_type, source_id, content, metadata, embedding, model)
VALUES ('anomaly', $1, $2, $3::jsonb, $4::vector, $5)
ON CONFLICT (source_type, source_id) DO UPDATE
   SET content = EXCLUDED.content,
       metadata = EXCLUDED.metadata,
       embedding = EXCLUDED.embedding,
       model = EXCLUDED.model,
       created_at = now()
"""


# --------------------------------------------------------------------------- #
#  Worker                                                                       #
# --------------------------------------------------------------------------- #

class EmbeddingWorker:
    def __init__(self, db_dsn: str):
        self._db_dsn = db_dsn
        self._pool = None
        self._aktif = False
        self._task: Optional[asyncio.Task] = None
        self._ssl = self._ssl_ctx()
        logger.info(f"Embedding Worker hazir (poll={POLL_SECONDS}sn, batch={BATCH})")

    @staticmethod
    def _ssl_ctx():
        ca = os.environ.get("EMBED_CA_FILE") or os.environ.get("SSL_CERT_FILE")
        if ca and os.path.exists(ca):
            ctx = ssl.create_default_context()
            ctx.load_verify_locations(cafile=ca)
            return ctx
        if ca:
            logger.warning(f"Embedding CA dosyasi bulunamadi: {ca}")
        return None

    async def baglanti_ac(self):
        import asyncpg
        self._pool = await asyncpg.create_pool(self._db_dsn, min_size=1, max_size=2)

    async def baglanti_kapat(self):
        if self._pool:
            await self._pool.close()

    async def _ayarlar(self):
        """(url, model, api_key) veya entegrasyon kapaliysa None."""
        from cryptography.fernet import Fernet
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config, secrets, enabled FROM integrations WHERE key='embedding'")
        if not row or not row["enabled"]:
            return None
        cfg = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"] or "{}")
        sec = row["secrets"] if isinstance(row["secrets"], dict) else json.loads(row["secrets"] or "{}")
        key = sec.get("api_key", "")
        sk = os.environ.get("LUMEN_SECRET_KEY", "")
        if key and sk:
            try:
                key = Fernet(sk.encode()).decrypt(key.encode()).decode()
            except Exception:
                pass
        url = (cfg.get("url") or "").rstrip("/")
        if not url or not key:
            return None
        return url, cfg.get("model", "llama-embed-nemotron-8b"), key

    async def _embed(self, session, url, model, key, metinler):
        import aiohttp
        async with session.post(
            f"{url}/embeddings",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "input": metinler},
            ssl=self._ssl,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:300]}")
            data = sorted((await r.json())["data"], key=lambda d: d["index"])
        vektorler = [d["embedding"] for d in data]
        if len(vektorler) != len(metinler) or any(len(v) != DIM for v in vektorler):
            raise RuntimeError(f"Beklenmeyen embedding cevabi (adet={len(vektorler)}, "
                               f"boyut={len(vektorler[0]) if vektorler else 0})")
        return vektorler

    async def bir_tur(self) -> int:
        """Bir tur calistirir, islenen kayit sayisini dondurur."""
        import aiohttp
        ayar = await self._ayarlar()
        if not ayar:
            logger.debug("Embedding entegrasyonu yok veya kapali")
            return 0
        url, model, key = ayar

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(SECIM_SQL, MAX_PER_CYCLE)
        if not rows:
            return 0

        islenen = 0
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(rows), BATCH):
                parca = rows[i:i + BATCH]
                metinler = [anomali_metni(r, r["kanal_adi"]) for r in parca]
                vektorler = await self._embed(session, url, model, key, metinler)
                async with self._pool.acquire() as conn:
                    await conn.executemany(YAZ_SQL, [
                        (str(r["id"]), m,
                         json.dumps(anomali_metadata(r, r["kanal_adi"]), ensure_ascii=False),
                         _vec(v), model)
                        for r, m, v in zip(parca, metinler, vektorler)
                    ])
                islenen += len(parca)
        return islenen

    async def _calistir(self):
        self._aktif = True
        logger.info("Embedding Worker basladi")
        hata_sayisi = 0
        while self._aktif:
            try:
                n = await self.bir_tur()
                if n:
                    logger.info(f"Embedding: {n} anomali islendi")
                hata_sayisi = 0
            except Exception as e:
                hata_sayisi += 1
                # ayni hatayi her turda yigmamak icin ilk ve her 10. hatada logla
                if hata_sayisi == 1 or hata_sayisi % 10 == 0:
                    logger.error(f"Embedding Worker hatasi ({hata_sayisi}. kez): {e}")
            await asyncio.sleep(POLL_SECONDS)

    def baslat(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._calistir())
        return self._task

    async def durdur(self):
        self._aktif = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.baglanti_kapat()


# Singleton
_worker: Optional[EmbeddingWorker] = None


def embedding_worker_baslat(db_dsn: str) -> EmbeddingWorker:
    global _worker
    _worker = EmbeddingWorker(db_dsn)
    return _worker


def embedding_worker_al() -> Optional[EmbeddingWorker]:
    return _worker
