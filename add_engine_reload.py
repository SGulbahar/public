#!/usr/bin/env python3
import sys

ENGINE_URL = "http://VM2_IP:8001"  # Buraya VM2 gercek IP'sini yaz

path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = "toast('Ayarlar kaydedildi', 's');"
new = (
    "toast('Ayarlar kaydedildi', 's');\n"
    "    try { await fetch('" + ENGINE_URL + "/reload-settings', {method:'POST'}); toast('Engine guncellendi', 'i'); } catch(e) {}"
)

if old in content:
    content = content.replace(old, new)
    print('OK: Engine reload eklendi')
else:
    print('WARN: Satir bulunamadi')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
