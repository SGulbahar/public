#!/usr/bin/env python3
"""Frontend'deki syntax hatasini duzelt."""

path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Engine'e -> Engine ile (kesme isareti JS string'ini kiriyordu)
fixes = [
    ("Engine'e ula\u015f\u0131lamad\u0131", "Engine ile ba\u011flant\u0131 kurulamad\u0131"),
    ("Engine'e ula\u015filamadi", "Engine ile baglanti kurulamadi"),
    ("Engine'e", "Engine sunucusuna"),
]

duzeltildi = 0
for eski, yeni in fixes:
    if eski in content:
        content = content.replace(eski, yeni)
        print(f'OK: "{eski}" -> "{yeni}"')
        duzeltildi += 1

if duzeltildi == 0:
    print('WARN: Duzeltilecek metin bulunamadi, manuel kontrol gerekli')

# Eski bildirimTest fonksiyonunu da temizle (eski surum kalmis olabilir)
import re

# Eski tek parametreli versiyonu bul ve sil
eski_pattern = r'async function bildirimTest\(\) \{[^}]+\}'
if re.search(eski_pattern, content):
    content = re.sub(eski_pattern, '', content)
    print('OK: Eski bildirimTest fonksiyonu silindi')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi - nginx restart gerekli')
