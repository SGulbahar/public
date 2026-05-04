#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# loadAnomalies fonksiyonunu guncelle - category parametresi ekle
old_func = "async function loadAnomalies(severity) {"
new_func = "async function loadAnomalies(severity, category) {"

if old_func in content:
    content = content.replace(old_func, new_func)
    print('OK: loadAnomalies parametresi eklendi')
else:
    print('WARN: loadAnomalies fonksiyonu bulunamadi')

# Filter butonlarini guncelle
old_btns = (
    "'<button class=\"btn ' + (severity==='all'?'p':'') + '\" onclick=\"loadAnomalies(\\'all\\')\">Tumu</button>' +\n"
    "    '<button class=\"btn ' + (severity==='DISASTER'?'p':'') + '\" onclick=\"loadAnomalies(\\'DISASTER\\')\">Kritik</button>' +\n"
    "    '<button class=\"btn ' + (severity==='HIGH'?'p':'') + '\" onclick=\"loadAnomalies(\\'HIGH\\')\">Yuksek</button>' +\n"
    "    '<button class=\"btn ' + (severity==='WARNING'?'p':'') + '\" onclick=\"loadAnomalies(\\'WARNING\\')\">Uyari</button>' +"
)

new_btns = (
    "'<div style=\"display:flex;gap:6px;flex-wrap:wrap\">' +\n"
    "    '<button class=\"btn ' + (severity==='all'&&!category?'p':'') + '\" onclick=\"loadAnomalies(\\'all\\')\">Tumu</button>' +\n"
    "    '<button class=\"btn ' + (severity==='DISASTER'?'p':'') + '\" onclick=\"loadAnomalies(\\'DISASTER\\')\">Kritik</button>' +\n"
    "    '<button class=\"btn ' + (severity==='HIGH'?'p':'') + '\" onclick=\"loadAnomalies(\\'HIGH\\')\">Yuksek</button>' +\n"
    "    '<button class=\"btn ' + (severity==='WARNING'?'p':'') + '\" onclick=\"loadAnomalies(\\'WARNING\\')\">Uyari</button>' +\n"
    "    '<div style=\"width:1px;background:rgba(180,200,240,.4);margin:0 4px\"></div>' +\n"
    "    '<button class=\"btn ' + (category==='SYS'?'p':'') + '\" style=\"border-color:var(--ora);color:' + (category==='SYS'?'var(--ora)':'var(--txt2)') + '\" onclick=\"loadAnomalies(\\'all\\',\\'SYS\\')\">SYS</button>' +\n"
    "    '<button class=\"btn ' + (category==='BIZ'?'p':'') + '\" style=\"border-color:var(--red);color:' + (category==='BIZ'?'var(--red)':'var(--txt2)') + '\" onclick=\"loadAnomalies(\\'all\\',\\'BIZ\\')\">BIZ</button>' +\n"
    "    '<button class=\"btn ' + (category==='PERFORMANCE'?'p':'') + '\" style=\"border-color:var(--acc);color:' + (category==='PERFORMANCE'?'var(--acc)':'var(--txt2)') + '\" onclick=\"loadAnomalies(\\'all\\',\\'PERFORMANCE\\')\">PERF</button>' +\n"
    "    '</div>' +"
)

if old_btns in content:
    content = content.replace(old_btns, new_btns)
    print('OK: Filtre butonlari guncellendi')
else:
    print('WARN: Filtre butonlari bulunamadi')

# URL olusturma satirini guncelle
old_url = "var url = severity==='all' ? '/api/v1/anomalies?limit=100' : '/api/v1/anomalies?limit=100&severity='+severity;"
new_url = (
    "var url = '/api/v1/anomalies?limit=100';\n"
    "  if (severity && severity !== 'all') url += '&severity=' + severity;\n"
    "  if (category) url += '&category=' + category;"
)

if old_url in content:
    content = content.replace(old_url, new_url)
    print('OK: URL guncellendi')
else:
    print('WARN: URL satiri bulunamadi')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
