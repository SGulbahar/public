#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'async function ackAnomaly' in content:
    print('ackAnomaly zaten var')
else:
    func = (
        'async function ackAnomaly(id) {\n'
        '  try {\n'
        '    await apiFetch("/api/v1/anomalies/" + id + "/acknowledge", {method: "POST"});\n'
        '    toast("Anomali onaylandi", "s");\n'
        '    var ap = document.querySelector(".page.active");\n'
        '    if (ap && ap.id === "page-anomalies") loadAnomalies("all");\n'
        '    if (ap && ap.id === "page-dashboard") loadDashboard();\n'
        '  } catch(e) { toast("Hata: " + e.message, "e"); }\n'
        '}\n\n'
    )
    content = content.replace('function toast(msg, type) {', func + 'function toast(msg, type) {')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK: ackAnomaly eklendi')
