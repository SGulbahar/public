"""
Logstash HTTP Push Receiver
- Gelen JSON batch'leri normalize edip Redis Stream'e yazar
- 22:55'te yeni gunluk log dosyasi acilir (yarinin tarihi ile)
- Her dosya 26 saat aktif kalir (22:55 - 00:55 ertesi gun)
- 22:55 - 00:55 arasi iki dosyaya ayni anda yazilir
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Request, HTTPException, status

from app.queue.redis_stream import redis_queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# ── Log ayarlari ──────────────────────────────────────────
LOG_DIR = os.environ.get("INGEST_LOG_DIR", "/app/logs/ingest")

# Aktif log handler'lari: {tarih_str: file_handle}
_aktif_handlerlar: dict = {}
# Dosya acilis zamanlari: {tarih_str: datetime}
_acilis_zamanlari: dict = {}
_log_aktif: bool = False

# ── Stats ─────────────────────────────────────────────────
_stats = {
    "total_received": 0,
    "total_batches": 0,
    "last_received_at": None,
    "errors": 0,
    "normalize_failed": 0,
    "log_enabled": False,
    "aktif_dosyalar": [],
}


def _yarin_tarih_str() -> str:
    """Yarin tarihini DD-MM-YY formatinda dondurur."""
    yarin = datetime.now() + timedelta(days=1)
    return yarin.strftime("%d-%m-%y")


def _bugun_tarih_str() -> str:
    """Bugunku tarihi DD-MM-YY formatinda dondurur."""
    return datetime.now().strftime("%d-%m-%y")


def _log_dosyasi_ac(tarih_str: str) -> Optional[object]:
    """Verilen tarih icin log dosyasi acar."""
    global _aktif_handlerlar
    if tarih_str in _aktif_handlerlar:
        return _aktif_handlerlar[tarih_str]
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        dosya_adi = os.path.join(LOG_DIR, f"ingest_{tarih_str}.jsonl")
        f = open(dosya_adi, "a", encoding="utf-8", buffering=1)
        _aktif_handlerlar[tarih_str] = f
        _acilis_zamanlari[tarih_str] = datetime.now()
        logger.info(f"Log dosyasi acildi: {dosya_adi}")
        return f
    except Exception as e:
        logger.error(f"Log dosyasi acma hatasi: {e}")
        return None


def _log_dosyasi_kapat(tarih_str: str):
    """Verilen tarih icin log dosyasini kapatir."""
    global _aktif_handlerlar
    if tarih_str in _aktif_handlerlar:
        try:
            _aktif_handlerlar[tarih_str].close()
            del _aktif_handlerlar[tarih_str]
            _acilis_zamanlari.pop(tarih_str, None)
            logger.info(f"Log dosyasi kapatildi: ingest_{tarih_str}.jsonl")
        except Exception as e:
            logger.error(f"Log dosyasi kapatma hatasi: {e}")


def _aktif_dosyalari_guncelle():
    """
    Her log yaziminda cagrilir.
    - Acik dosyalarin 26 saatlik suresi dolmussa kapatir.
    - Yeni dosya acma islemi enable endpoint'i tarafindan yapilir.
    
    Kural:
    - Her dosya enable aninda yarin tarihi ile acilir
    - Dosya acilma zamanindan 26 saat sonra otomatik kapanir
    - 22:55 - 00:55 arasi iki dosya ayni anda aktif olabilir
    """
    global _aktif_handlerlar, _acilis_zamanlari

    simdi = datetime.now()
    # 26 saat gecmis dosyalari kapat
    kapatilacaklar = []
    for tarih, acilis in list(_acilis_zamanlari.items()):
        gecen_saat = (simdi - acilis).total_seconds() / 3600
        if gecen_saat >= 25.166:
            kapatilacaklar.append(tarih)
            logger.info(f"26 saat doldu, kapatiliyor: ingest_{tarih}.jsonl ({gecen_saat:.1f} saat (25.1h)")

    for tarih in kapatilacaklar:
        _log_dosyasi_kapat(tarih)
        _acilis_zamanlari.pop(tarih, None)


def _log_yaz(satir: str):
    """Aktif tum log dosyalarina yazar."""
    global _aktif_handlerlar
    for tarih, f in list(_aktif_handlerlar.items()):
        try:
            f.write(satir + "\n")
        except Exception as e:
            logger.error(f"Log yazma hatasi ({tarih}): {e}")
            try:
                del _aktif_handlerlar[tarih]
            except Exception:
                pass


def _aktif_dosya_listesi() -> List[str]:
    """Aktif log dosyalarinin isimlerini dondurur."""
    return [f"ingest_{t}.jsonl" for t in _aktif_handlerlar.keys()]


# ── Endpoints ─────────────────────────────────────────────

@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_logs(request: Request):
    global _log_aktif
    try:
        body = await request.json()
    except Exception as e:
        _stats["errors"] += 1
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz JSON: {e}"
        )

    if isinstance(body, dict):
        batch = [body]
    elif isinstance(body, list):
        batch = body
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gecersiz format"
        )

    if not batch:
        return {"accepted": 0}

    normalized = []
    for log in batch:
        # Ham log kaydi
        if _log_aktif:
            try:
                _aktif_dosyalari_guncelle()
                _log_yaz(json.dumps(log, ensure_ascii=False))
            except Exception as e:
                logger.warning(f"Ham log yazma hatasi: {e}")

        n = _normalize(log)
        if n:
            normalized.append(n)
        else:
            _stats["normalize_failed"] += 1

    written = 0
    if normalized:
        written = await redis_queue.publish(normalized)

    _stats["total_received"] += written
    _stats["total_batches"] += 1
    _stats["last_received_at"] = datetime.utcnow().isoformat()
    _stats["aktif_dosyalar"] = _aktif_dosya_listesi()

    logger.debug(f"Batch: {len(batch)} gelen, {written} yazildi")

    return {
        "accepted": written,
        "total_received": _stats["total_received"],
    }


@router.post("/log/enable", status_code=status.HTTP_200_OK)
async def log_enable():
    """
    Ham log kaydini aktif et.
    Enable aninda YARIN tarihli dosya acilir.
    Ornek: Bugun 22-05-26 ise ingest_23-05-26.jsonl acilir.
    """
    global _log_aktif
    _log_aktif = True
    # Her zaman yarinki tarihle yeni dosya ac
    yarin = _yarin_tarih_str()
    _log_dosyasi_ac(yarin)
    dosyalar = _aktif_dosya_listesi()
    _stats["log_enabled"] = True
    _stats["aktif_dosyalar"] = dosyalar
    logger.info(f"Ham log kaydi AKTIF: {dosyalar}")
    return {"status": "ok", "log_enabled": True, "aktif_dosyalar": dosyalar, "log_dir": LOG_DIR, "yeni_dosya": f"ingest_{yarin}.jsonl"}


@router.post("/log/disable", status_code=status.HTTP_200_OK)
async def log_disable():
    """Ham log kaydini devre disi birak ve tum dosyalari kapat."""
    global _log_aktif, _aktif_handlerlar
    _log_aktif = False
    for tarih in list(_aktif_handlerlar.keys()):
        _log_dosyasi_kapat(tarih)
    _stats["log_enabled"] = False
    _stats["aktif_dosyalar"] = []
    logger.info("Ham log kaydi DEVRE DISI birakildi")
    return {"status": "ok", "log_enabled": False}


@router.post("/log/kapat/{tarih}", status_code=status.HTTP_200_OK)
async def log_dosya_kapat(tarih: str):
    """
    Belirli bir tarihin log dosyasini kapat.
    tarih formati: DD-MM-YY (ornek: 23-05-26)
    """
    if tarih in _aktif_handlerlar:
        _log_dosyasi_kapat(tarih)
        return {"status": "ok", "kapatildi": f"ingest_{tarih}.jsonl"}
    return {"status": "not_found", "mesaj": f"ingest_{tarih}.jsonl aktif degil"}


@router.get("/stats")
async def ingest_stats():
    stream_info = await redis_queue.stream_info()
    return {
        **_stats,
        "stream_length": stream_info.get("length", 0),
        "stream_pending": stream_info.get("pending", 0),
    }


def _normalize(raw: dict) -> Optional[dict]:
    """
    Logstash formatini normalize eder.
    """
    try:
        jm = raw.get("json_message", {})
        if not isinstance(jm, dict):
            return None

        channel_code = jm.get("channelCode")
        elapsed_time = jm.get("elapsedTime")
        result = jm.get("result")
        service = jm.get("service")
        logtime = jm.get("logtime") or raw.get("@timestamp")

        if not service:
            return None

        return {
            "channel_code": str(channel_code) if channel_code is not None else "unknown",
            "elapsed_time": int(elapsed_time) if elapsed_time is not None else 0,
            "result": int(result) if result is not None else 0,
            "service": str(service),
            "logtime": str(logtime) if logtime else datetime.utcnow().isoformat(),
            "user": str(jm.get("user", "")),
            "trace_id": str(jm.get("traceId", "")),
            "session_id": str(jm.get("sessionID", "")),
        }

    except Exception as e:
        logger.error(f"Normalize hatasi: {e} — raw keys: {list(raw.keys())}")
        return None
