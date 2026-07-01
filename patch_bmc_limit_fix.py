"""
BMC limit duzeltmesi: DML icindeki 'limit N' kaldirilir,
URL'e ayri query parametresi olarak &offset=0&limit=N eklenir.
Calistirma: python3 patch_bmc_limit_fix.py
"""
with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

degisiklik_sayisi = 0

old1 = 'test_query = _up.quote("search BusinessService show name limit 1")'
new1 = 'test_query = _up.quote("search BusinessService show name")'
if old1 in c:
    c = c.replace(old1, new1)
    degisiklik_sayisi += 1
    print("OK: test_query DML duzeltildi")
else:
    print("WARN: test_query satiri bulunamadi (eslesmedi)")

old2 = 'f"{url}/api/v1.14/data/search?query={test_query}"'
new2 = 'f"{url}/api/v1.14/data/search?query={test_query}&offset=0&limit=1"'
if old2 in c:
    c = c.replace(old2, new2)
    degisiklik_sayisi += 1
    print("OK: test URL duzeltildi")
else:
    print("WARN: test URL satiri bulunamadi (eslesmedi)")

old3 = 'f"{url}/api/v1.14/data/search?query={encoded_query}"'
new3 = 'f"{url}/api/v1.14/data/search?query={encoded_query}&offset=0&limit=5000"'
if old3 in c:
    c = c.replace(old3, new3)
    degisiklik_sayisi += 1
    print("OK: sync URL duzeltildi")
else:
    print("WARN: sync URL satiri bulunamadi (eslesmedi)")

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

print(f"Toplam degisiklik: {degisiklik_sayisi}/3")
