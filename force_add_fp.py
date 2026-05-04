#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

fp_js = (
    'var _fpAnomalyId = null;\n'
    '\n'
    'function openFPModal(id) {\n'
    '  _fpAnomalyId = id;\n'
    '  document.getElementById("fp-reason").value = "";\n'
    '  document.getElementById("fp-overlay").classList.add("open");\n'
    '  closeModal();\n'
    '}\n'
    '\n'
    'function closeFPModal() {\n'
    '  document.getElementById("fp-overlay").classList.remove("open");\n'
    '  _fpAnomalyId = null;\n'
    '}\n'
    '\n'
    'async function submitFP() {\n'
    '  if (!_fpAnomalyId) return;\n'
    '  var reason = document.getElementById("fp-reason").value.trim();\n'
    '  try {\n'
    '    await apiFetch("/api/v1/anomalies/" + _fpAnomalyId + "/false-positive", {\n'
    '      method: "POST",\n'
    '      body: JSON.stringify({reason: reason || null})\n'
    '    });\n'
    '    closeFPModal();\n'
    '    toast("False positive olarak isaretlendi", "w");\n'
    '    var ap = document.querySelector(".page.active");\n'
    '    if (ap && ap.id === "page-anomalies") loadAnomalies("all");\n'
    '    if (ap && ap.id === "page-dashboard") loadDashboard();\n'
    '  } catch(e) { toast("Hata: " + e.message, "e"); }\n'
    '}\n'
    '\n'
)

if 'function openFPModal' not in content:
    content = content.replace('function toast(msg, type) {', fp_js + 'function toast(msg, type) {')
    print('OK: FP fonksiyonlari eklendi')
else:
    print('Zaten var')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
