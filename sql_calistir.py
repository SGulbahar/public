"""
Bir SQL dosyasini, calistirirken girilen baglanti bilgileriyle tek transaction icinde calistirir.

Kullanim:
  docker cp sql_calistir.py   lumen-app:/tmp/
  docker cp agent_tables.sql  lumen-app:/tmp/
  docker exec -it lumen-app python3 /tmp/sql_calistir.py /tmp/agent_tables.sql

Baglanti bilgileri ortam degiskenlerinden (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, PGSSLMODE)
alinir, yoksa sorulur. Sifre ekranda gorunmez.
"""
import asyncio
import getpass
import os
import sys

import asyncpg


def sor(etiket, env, varsayilan="", gizli=False):
    deger = os.environ.get(env)
    if deger:
        print(f"{etiket}: {'*****' if gizli else deger}  (ortam degiskeni {env})")
        return deger
    ipucu = f" [{varsayilan}]" if varsayilan else ""
    deger = getpass.getpass(f"{etiket}: ") if gizli else input(f"{etiket}{ipucu}: ").strip()
    return deger or varsayilan


async def main():
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        sys.exit("Kullanim: python3 sql_calistir.py /yol/dosya.sql")
    yol = sys.argv[1]
    sql = open(yol, encoding="utf-8").read()

    print(f"=== {os.path.basename(yol)} calistirilacak ===\n")
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
        sys.exit(f"\nBaglanti kurulamadi: {e}")

    try:
        print(f"\nBaglandi: {await conn.fetchval('SELECT current_user')}@{host}:{port}/"
              f"{await conn.fetchval('SELECT current_database()')}")
        print("\n--- SQL ---")
        print(sql.strip())
        print("-----------")
        if input("\nBu SQL calistirilsin mi? (evet/hayir): ").strip().lower() != "evet":
            sys.exit("Iptal edildi.")
        async with conn.transaction():
            await conn.execute(sql)
        print("Tamamlandi.")
    except Exception as e:
        sys.exit(f"\nHata (hicbir degisiklik uygulanmadi): {e}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
