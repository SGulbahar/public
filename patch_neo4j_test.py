"""
Neo4j baglanti testini entegrasyon test endpoint'ine ekler.
Calistirma: python3 patch_neo4j_test.py
"""

with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

old = '''        except Exception as e:
        test_sonuc = {"status": "error", "message": str(e)}

        # Sonucu DB'ye kaydet'''

new = '''        elif key == "neo4j":
                url = config.get("url", "")
                database = config.get("database", "neo4j")
                password = secrets.get("password", "")
                if not url or not password:
                    test_sonuc = {"status": "error", "message": "URL veya sifre eksik"}
                else:
                    from base64 import b64encode as _b64
                    auth = _b64(f"neo4j:{password}".encode()).decode()
                    async with httpx.AsyncClient(verify=False, timeout=10) as client:
                        r = await client.post(
                            f"{url}/db/{database}/tx/commit",
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Basic {auth}"
                            },
                            json={"statements": [{"statement": "MATCH (h:Host) RETURN count(h) as sayi"}]}
                        )
                        if r.status_code == 200:
                            data = r.json()
                            if data.get("errors"):
                                test_sonuc = {"status": "error", "message": str(data["errors"][0])}
                            else:
                                sayi = data["results"][0]["data"][0]["row"][0] if data["results"][0]["data"] else 0
                                test_sonuc = {"status": "ok", "message": f"Neo4j baglanti basarili — {sayi} Host node"}
                        else:
                            test_sonuc = {"status": "error", "message": f"HTTP {r.status_code}"}

        except Exception as e:
        test_sonuc = {"status": "error", "message": str(e)}

        # Sonucu DB'ye kaydet'''

if old in c:
    c = c.replace(old, new)
    print("OK: Neo4j test eklendi")
else:
    print("WARN: blok bulunamadi")

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/app/api/routes.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
