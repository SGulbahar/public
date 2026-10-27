"""
knowledge_embeddings tablosunu kurar.

Baglanti bilgileri sirayla:
  1. Ortam degiskenlerinden (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD)
  2. Yoksa calistirirken sorulur (sifre ekranda gorunmez)

Calistirma:
  docker cp embedding_tablo_kur.py lumen-app:/tmp/
  docker exec -it lumen-app python3 /tmp/embedding_tablo_kur.py
"""
import asyncio
import getpass
import os
import sys

import asyncpg

DIM = 4096
MODEL = "llama-embed-nemotron-8b"

DDL = f"""
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id          bigserial PRIMARY KEY,
    source_type text         NOT NULL,
    source_id   text         NOT NULL,
    content     text         NOT NULL,
    metadata    jsonb        NOT NULL DEFAULT '{{}}',
    embedding   vector({DIM}) NOT NULL,
    model       text         NOT NULL DEFAULT '{MODEL}',
    created_at  timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (source_type, source_id)
);
CREATE INDEX IF NOT EXISTS ke_source_type_idx ON knowledge_embeddings (source_type);
CREATE INDEX IF NOT EXISTS ke_metadata_idx    ON knowledge_embeddings USING gin (metadata);
"""


def sor(etiket: str, env: str, varsayilan: str = "", gizli: bool = False) -> str:
    deger = os.environ.get(env)
    if deger:
        print(f"{etiket}: {'*****' if gizli else deger}  (ortam degiskeni {env})")
        return deger
    ipucu = f" [{varsayilan}]" if varsayilan else ""
    if gizli:
        deger = getpass.getpass(f"{etiket}: ")
    else:
        deger = input(f"{etiket}{ipucu}: ").strip()
    return deger or varsayilan


async def main():
    print("=== knowledge_embeddings kurulumu ===\n")
    host = sor("Host", "PGHOST")
    port = int(sor("Port", "PGPORT", "5432"))
    db = sor("Veritabani", "PGDATABASE")
    user = sor("Kullanici", "PGUSER")
    pwd = sor("Sifre", "PGPASSWORD", gizli=True)
    ssl = sor("SSL (disable/prefer/require)", "PGSSLMODE", "prefer")

    if not host or not db or not user:
        sys.exit("Host, veritabani ve kullanici bos olamaz.")

    try:
        conn = await asyncpg.connect(host=host, port=port, database=db, user=user,
                                     password=pwd, ssl=None if ssl == "disable" else ssl,
                                     timeout=10)
    except Exception as e:
        sys.exit(f"\nBaglanti kurulamadi: {e}")

    try:
        surum = await conn.fetchval("SHOW server_version")
        aktif_db = await conn.fetchval("SELECT current_database()")
        aktif_user = await conn.fetchval("SELECT current_user")
        print(f"\nBaglandi: {aktif_user}@{host}:{port}/{aktif_db}  (PostgreSQL {surum})")

        vec = await conn.fetchrow(
            "SELECT installed_version, default_version FROM pg_available_extensions WHERE name='vector'")
        if not vec:
            sys.exit("pgvector bu sunucuda kurulu degil (pg_available_extensions'da yok). DBA ile gorusun.")
        if not vec["installed_version"]:
            print(f"pgvector mevcut ama bu veritabaninda etkin degil (surum {vec['default_version']}).")
            if input("CREATE EXTENSION vector calistirilsin mi? (evet/hayir): ").strip().lower() != "evet":
                sys.exit("Iptal edildi.")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            print("pgvector etkinlestirildi.")
        else:
            print(f"pgvector etkin (surum {vec['installed_version']}).")

        var_mi = await conn.fetchval("SELECT to_regclass('public.knowledge_embeddings') IS NOT NULL")
        if var_mi:
            sayi = await conn.fetchval("SELECT count(*) FROM knowledge_embeddings")
            print(f"\nknowledge_embeddings zaten var ({sayi} kayit). Degisiklik yapilmadi.")
            return

        print(f"\nOlusturulacak: knowledge_embeddings (vector({DIM}), model={MODEL})")
        if input(f"'{aktif_db}' veritabaninda olusturulsun mu? (evet/hayir): ").strip().lower() != "evet":
            sys.exit("Iptal edildi.")

        async with conn.transaction():
            await conn.execute(DDL)
        print("Tablo ve indeksler olusturuldu.")

        kolonlar = await conn.fetch("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_name='knowledge_embeddings' ORDER BY ordinal_position""")
        for k in kolonlar:
            print(f"  {k['column_name']:<12} {k['data_type']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
