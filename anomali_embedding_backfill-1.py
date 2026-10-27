"""
anomaly_events -> knowledge_embeddings backfill

- Embedding'i olmayan anomalileri isler.
- Sonradan "yanlis alarm" isaretlenen veya onaylanan anomalileri yeniden isler
  (false_positive_at / acknowledged_at, embedding tarihinden yeniyse).
- Yarida kesilirse tekrar calistirin, kaldigi yerden devam eder.

Baglanti bilgileri: ortam degiskenleri (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, PGSSLMODE)
yoksa calistirirken sorulur.
Embedding ayarlari: integrations tablosundaki key='embedding' kaydindan (LUMEN_SECRET_KEY ile cozulur),
yoksa calistirirken sorulur.

Kullanim:
  docker cp anomali_embedding_backfill.py lumen-app:/tmp/
  docker exec -it lumen-app python3 /tmp/anomali_embedding_backfill.py --dry-run --limit 5   # once ornek metinlere bakin
  docker exec -it lumen-app python3 /tmp/anomali_embedding_backfill.py --limit 50            # kucuk deneme
  docker exec -it lumen-app python3 /tmp/anomali_embedding_backfill.py                       # hepsi
"""
import argparse
import asyncio
import getpass
import json
import os
import re
import sys
import time

import aiohttp
import asyncpg

DIM = 4096
AI_ANALIZ_MAX = 1500
SUMMARY_MAX = 1000


# --------------------------------------------------------------------------- #
#  Yardimcilar                                                                  #
# --------------------------------------------------------------------------- #

def sor(etiket, env, varsayilan="", gizli=False):
    deger = os.environ.get(env)
    if deger:
        print(f"{etiket}: {'*****' if gizli else deger}  (ortam degiskeni {env})")
        return deger
    ipucu = f" [{varsayilan}]" if varsayilan else ""
    deger = getpass.getpass(f"{etiket}: ") if gizli else input(f"{etiket}{ipucu}: ").strip()
    return deger or varsayilan


_IBAN = re.compile(r"\bTR\d{2}[ ]?(?:\d{4}[ ]?){5}\d{2}\b", re.I)
_KART = re.compile(r"\b\d(?:[ -]?\d){14,15}\b")
_TCKN = re.compile(r"\b[1-9]\d{10}\b")


def maskele(metin: str) -> str:
    """LLM ve embedding'e gitmeden once kisisel veriyi maskeler."""
    if not metin:
        return ""
    metin = _IBAN.sub("[IBAN]", metin)
    metin = _KART.sub("[KART]", metin)
    metin = _TCKN.sub("[TCKN]", metin)
    return metin


def kisalt(metin, n):
    metin = " ".join((metin or "").split())
    return metin if len(metin) <= n else metin[:n].rstrip() + "…"


def sayi(v, fmt="{:.2f}"):
    return "-" if v is None else fmt.format(v)


def anomali_metni(r, kanal_adi: str) -> str:
    parcalar = [
        f"{r['service'] or 'Bilinmeyen servis'} servisinde ({kanal_adi} kanalı) "
        f"{r['anomaly_type']} tipi {r['severity'] or ''} anomali.".replace("  ", " "),
        f"Zaman: {r['detected_at']:%Y-%m-%d %H:%M}." if r["detected_at"] else "",
    ]
    if r["result_code"] is not None or r["result_desc"]:
        parcalar.append(
            f"Sonuç kodu {r['result_code'] if r['result_code'] is not None else '-'}"
            f"{' (' + r['result_category'] + ')' if r['result_category'] else ''}: "
            f"{kisalt(r['result_desc'], 300)}."
        )
    parcalar.append(
        f"İşlem sayısı {r['tx_count'] if r['tx_count'] is not None else '-'}, "
        f"hata oranı {sayi(r['error_rate'] * 100 if r['error_rate'] is not None and r['error_rate'] <= 1 else r['error_rate'], '{:.1f}')}%, "
        f"ortalama süre {sayi(r['elapsed_mean'], '{:.0f}')} ms, skor {sayi(r['score'])}."
    )
    if r["summary"]:
        parcalar.append(f"Özet: {kisalt(r['summary'], SUMMARY_MAX)}")
    if r["ai_analysis"]:
        parcalar.append(f"Analiz: {kisalt(r['ai_analysis'], AI_ANALIZ_MAX)}")
    if r["is_false_positive"]:
        parcalar.append(
            f"Operatör tarafından YANLIŞ ALARM olarak işaretlendi"
            f"{': ' + kisalt(r['false_positive_reason'], 300) if r['false_positive_reason'] else ''}."
        )
    elif r["acknowledged"]:
        parcalar.append(f"Operatör tarafından onaylandı ({r['acknowledged_by'] or '-'}).")
    if r["itsm_ticket_id"]:
        parcalar.append(f"ITSM kaydı: {r['itsm_ticket_id']}.")
    return maskele(" ".join(p for p in parcalar if p))


def metadata(r, kanal_adi):
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


# --------------------------------------------------------------------------- #
#  Embedding                                                                    #
# --------------------------------------------------------------------------- #

async def embedding_ayarlari(conn):
    row = await conn.fetchrow("SELECT config, secrets, enabled FROM integrations WHERE key='embedding'")
    if row:
        cfg = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"] or "{}")
        sec = row["secrets"] if isinstance(row["secrets"], dict) else json.loads(row["secrets"] or "{}")
        key = sec.get("api_key", "")
        sk = os.environ.get("LUMEN_SECRET_KEY")
        if key and sk:
            from cryptography.fernet import Fernet
            try:
                key = Fernet(sk.encode()).decrypt(key.encode()).decode()
            except Exception:
                pass
        if cfg.get("url") and key:
            print(f"Embedding: {cfg['url']}  model={cfg.get('model')}  (integrations tablosundan)")
            return cfg["url"].rstrip("/"), cfg.get("model", "llama-embed-nemotron-8b"), key
    print("integrations tablosunda 'embedding' kaydi yok, bilgileri girin:")
    url = sor("Embedding URL (ornek http://host:port/v1)", "EMBED_URL").rstrip("/")
    model = sor("Model", "EMBED_MODEL", "llama-embed-nemotron-8b")
    key = sor("API key", "EMBED_API_KEY", gizli=True)
    return url, model, key


def ssl_ayari(ca_file: str, insecure: bool):
    """Ic CA dosyasi verilirse onu kullanir; --insecure ile dogrulama kapatilir (sadece gecici test icin)."""
    import ssl
    if insecure:
        print("UYARI: SSL sertifika dogrulamasi KAPALI (--insecure). Sadece test icin kullanin.")
        return False
    ca_file = ca_file or os.environ.get("EMBED_CA_FILE") or os.environ.get("SSL_CERT_FILE")
    if ca_file:
        if not os.path.exists(ca_file):
            sys.exit(f"CA dosyasi bulunamadi: {ca_file}")
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cafile=ca_file)
        print(f"SSL: {ca_file} CA dosyasi kullaniliyor")
        return ctx
    return None


async def embed(session, url, model, key, metinler, deneme=3, ssl_ctx=None):
    for i in range(deneme):
        try:
            async with session.post(
                f"{url}/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "input": metinler},
                timeout=aiohttp.ClientTimeout(total=120),
                ssl=ssl_ctx,
            ) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:300]}")
                data = (await r.json())["data"]
                data.sort(key=lambda d: d["index"])
                vektorler = [d["embedding"] for d in data]
                if any(len(v) != DIM for v in vektorler):
                    raise RuntimeError(f"Beklenmeyen boyut: {len(vektorler[0])} (beklenen {DIM})")
                return vektorler
        except Exception as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                sys.exit(f"\nSSL dogrulama hatasi: {e}\n"
                         "Ic CA sertifikasini --ca-file /yol/ca.pem ile verin.")
            if i == deneme - 1:
                raise
            print(f"  embedding hatasi, tekrar deneniyor ({i + 1}): {e}")
            await asyncio.sleep(2 * (i + 1))


def vec_literal(v):
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


# --------------------------------------------------------------------------- #
#  Ana akis                                                                     #
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
ORDER BY a.id
{limit}
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


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="En fazla bu kadar kayit isle")
    ap.add_argument("--batch", type=int, default=16, help="Tek istekte gonderilecek metin sayisi")
    ap.add_argument("--dry-run", action="store_true", help="Embedding uretme, sadece ornek metinleri goster")
    ap.add_argument("--ca-file", default="", help="Ic CA sertifika dosyasi (PEM)")
    ap.add_argument("--insecure", action="store_true", help="SSL dogrulamasini kapat (sadece test)")
    args = ap.parse_args()
    ssl_ctx = ssl_ayari(args.ca_file, args.insecure)

    print("=== Anomali embedding backfill ===\n")
    host = sor("Host", "PGHOST")
    port = int(sor("Port", "PGPORT", "5432"))
    db = sor("Veritabani", "PGDATABASE")
    user = sor("Kullanici", "PGUSER")
    pwd = sor("Sifre", "PGPASSWORD", gizli=True)
    ssl = sor("SSL (disable/prefer/require)", "PGSSLMODE", "prefer")

    try:
        conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=pwd,
                                     ssl=None if ssl == "disable" else ssl, timeout=10)
    except Exception as e:
        sys.exit(f"Baglanti kurulamadi: {e}")

    try:
        print(f"\nBaglandi: {await conn.fetchval('SELECT current_user')}@{host}/{await conn.fetchval('SELECT current_database()')}")
        if not await conn.fetchval("SELECT to_regclass('public.knowledge_embeddings') IS NOT NULL"):
            sys.exit("knowledge_embeddings tablosu yok. Once embedding_tablo_kur.py calistirin.")

        rows = await conn.fetch(SECIM_SQL.format(limit=f"LIMIT {args.limit}" if args.limit else ""))
        toplam = len(rows)
        print(f"Islenecek anomali: {toplam}")
        if not toplam:
            return

        if args.dry_run:
            for r in rows[:args.limit or 5]:
                print(f"\n--- id={r['id']} ---")
                print(anomali_metni(r, r["kanal_adi"]))
                print("metadata:", json.dumps(metadata(r, r["kanal_adi"]), ensure_ascii=False))
            return

        url, model, key = await embedding_ayarlari(conn)
        if input(f"\n{toplam} kayit icin embedding uretilsin mi? (evet/hayir): ").strip().lower() != "evet":
            sys.exit("Iptal edildi.")

        bas = time.time()
        islenen = 0
        async with aiohttp.ClientSession() as session:
            for i in range(0, toplam, args.batch):
                parca = rows[i:i + args.batch]
                metinler = [anomali_metni(r, r["kanal_adi"]) for r in parca]
                vektorler = await embed(session, url, model, key, metinler, ssl_ctx=ssl_ctx)
                await conn.executemany(YAZ_SQL, [
                    (str(r["id"]), m, json.dumps(metadata(r, r["kanal_adi"]), ensure_ascii=False),
                     vec_literal(v), model)
                    for r, m, v in zip(parca, metinler, vektorler)
                ])
                islenen += len(parca)
                hiz = islenen / max(time.time() - bas, 0.001)
                kalan = (toplam - islenen) / hiz if hiz else 0
                print(f"  {islenen}/{toplam}  ({hiz:.1f} kayit/sn, kalan ~{kalan / 60:.1f} dk)")

        print(f"\nTamamlandi: {islenen} kayit, {time.time() - bas:.0f} sn")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
