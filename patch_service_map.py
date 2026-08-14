"""
Service map endpoint'ini routes.py'ye ekler.
Calistirma: python3 patch_service_map.py
"""

with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

SERVICE_MAP_ENDPOINT = '''

# ═══════════════════════════════════════════════════════════
# SERVİS HARİTASI
# ═══════════════════════════════════════════════════════════

@router.get("/service-map", response_class=None)
async def service_map():
    """
    Servis iliskilerini igraph + leidenalg + pyvis ile gorsellestirir.
    HTML olarak dondurur.
    """
    import sys
    import os
    sys.path.insert(0, '/app/app/modules/map')

    try:
        from service_map import create_service_map
        # CSV dosyalarinin konumuna gore calisma dizinini degistir
        original_dir = os.getcwd()
        os.chdir('/app/app/modules/map')
        try:
            html = create_service_map()
        finally:
            os.chdir(original_dir)

        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html)
    except Exception as e:
        import traceback
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            content=f"<pre>Hata: {e}\\n\\n{traceback.format_exc()}</pre>",
            status_code=500
        )

'''

# Zabbix feed'den once ekle
marker = '@router.get("/zabbix/feed")'
if marker in c:
    c = c.replace(marker, SERVICE_MAP_ENDPOINT + marker)
    print("OK: service-map endpoint eklendi")
else:
    print("WARN: marker bulunamadi, sona ekleniyor")
    c = c + SERVICE_MAP_ENDPOINT

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/app/api/routes.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
