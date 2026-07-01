"""
BMC yanit formati duzeltmesi:
BMC, dict yerine list-of-lists + headings donduruyor.
Bunu headings kullanarak dict'e ceviriyoruz.
Calistirma: python3 patch_bmc_parse_fix.py
"""
with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

old = '''    import logging as _log
    _log.getLogger(__name__).info(f"BMC ham yanit (ilk 500 karakter): {str(sonuc)[:500]}")
    rows = sonuc if isinstance(sonuc, list) else sonuc.get("results", sonuc.get("data", []))
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="BMC yanit formati beklenmedik")

    yazilan = 0
    for r in rows:
        host_name = r.get("name") or r.get("Name")
        if not host_name:
            continue
        biz_raw = r.get("Name")
        if isinstance(biz_raw, list):
            biz_services = biz_raw
        elif biz_raw and biz_raw != host_name:
            biz_services = [biz_raw]
        else:
            biz_services = []'''

new = '''    # BMC yanit formati: [{kind, count, offset, headings: [...], results: [[...], [...]]}]
    # headings kullanarak list-of-lists -> list-of-dicts cevirimi yapiyoruz
    rows = []
    try:
        if isinstance(sonuc, list) and len(sonuc) > 0:
            blok = sonuc[0]
            headings = blok.get("headings", [])
            raw_results = blok.get("results", [])
            for satir in raw_results:
                rows.append(dict(zip(headings, satir)))
        elif isinstance(sonuc, dict):
            headings = sonuc.get("headings", [])
            raw_results = sonuc.get("results", [])
            for satir in raw_results:
                rows.append(dict(zip(headings, satir)))
    except Exception as parse_e:
        raise HTTPException(status_code=502, detail=f"BMC yanit parse hatasi: {parse_e}")

    if not rows:
        return {"status": "ok", "host_count": 0, "yazilan": 0, "mesaj": "BMC'den kayit gelmedi"}

    yazilan = 0
    for r in rows:
        host_name = r.get("name") or r.get("Name")
        if not host_name:
            continue
        biz_raw = r.get("Name")
        if isinstance(biz_raw, list):
            biz_services = [b for b in biz_raw if b]
        elif biz_raw:
            biz_services = [biz_raw]
        else:
            biz_services = []'''

if old in c:
    c = c.replace(old, new)
    print("OK: BMC parse blogu duzeltildi")
else:
    print("WARN: blok bulunamadi (eslesmedi)")

# host_count da gercek kayit sayisina donusturelim
old2 = '    return {"status": "ok", "host_count": len(rows), "yazilan": yazilan}'
new2 = '    return {"status": "ok", "host_count": len(rows), "yazilan": yazilan, "toplam_bmc_kayit": len(rows)}'
if old2 in c:
    c = c.replace(old2, new2)
    print("OK: return guncellendi")

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)
