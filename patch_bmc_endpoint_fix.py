"""
BMC endpoint duzeltmesi: POST /api/v1.14/search (body) -> GET /api/v1.14/data/search?query=...
Calistirma: python3 patch_bmc_endpoint_fix.py
"""
with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

degisiklik_sayisi = 0

# 1) bmc_sync icindeki cagri
old1 = '''    try:
        async with httpx.AsyncClient(verify=False, timeout=60) as client:
            r = await client.post(
                f"{url}/api/v1.14/search",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"query": dml_query}
            )
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"BMC API hatasi: HTTP {r.status_code}")
            sonuc = r.json()'''

new1 = '''    try:
        import urllib.parse as _up
        encoded_query = _up.quote(dml_query)
        async with httpx.AsyncClient(verify=False, timeout=60) as client:
            r = await client.get(
                f"{url}/api/v1.14/data/search?query={encoded_query}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"BMC API hatasi: HTTP {r.status_code} - {r.text[:200]}")
            sonuc = r.json()'''

if old1 in c:
    c = c.replace(old1, new1)
    degisiklik_sayisi += 1
    print("OK: bmc_sync cagrisi duzeltildi")
else:
    print("WARN: bmc_sync bloğu bulunamadi (eslesmedi)")

# 2) integrations/{key}/test icindeki BMC test bloğu
old2 = '''            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                    r = await client.post(f"{url}/api/v1.14/search",
                        headers={"Authorization": f"Bearer {token}",
                                 "Content-Type": "application/json"},
                        json={"query": "search BusinessService limit 1"})
                    if r.status_code == 200:
                        test_sonuc = {"status": "ok", "message": "BMC Discovery baglanti basarili"}
                    else:
                        test_sonuc = {"status": "error", "message": f"HTTP {r.status_code}"}'''

new2 = '''            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                    import urllib.parse as _up
                    test_query = _up.quote("search BusinessService limit 1")
                    r = await client.get(f"{url}/api/v1.14/data/search?query={test_query}",
                        headers={"Authorization": f"Bearer {token}"})
                    if r.status_code == 200:
                        test_sonuc = {"status": "ok", "message": "BMC Discovery baglanti basarili"}
                    else:
                        test_sonuc = {"status": "error", "message": f"HTTP {r.status_code} - {r.text[:150]}"}'''

if old2 in c:
    c = c.replace(old2, new2)
    degisiklik_sayisi += 1
    print("OK: integrations test bloğu duzeltildi")
else:
    print("WARN: integrations test bloğu bulunamadi (eslesmedi) - indentation farkli olabilir")

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

print(f"Toplam degisiklik: {degisiklik_sayisi}/2")
