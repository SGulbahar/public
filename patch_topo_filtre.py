"""
Topoloji servis listesinde varsayilan olarak sadece alarmli servisleri gosterir.
Arama yapilinca tum servisler gorunur.
Calistirma: python3 patch_topo_filtre.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

degisiklik = 0

# 1. topoServisleriYukle - chip'e data-alarm ekle ve varsayilan gizle
old1 = "    html += '<div class=\"topo-svc-chip\" data-svc=\"' + s.name + '\" onclick=\"topoYukle(this.dataset.svc)\" style=\"' + alarmCss + ';padding:4px 10px;border-radius:20px;cursor:pointer;font-size:10px;font-family:JetBrains Mono,monospace\" onmouseover=\"this.style.opacity=0.7\" onmouseout=\"this.style.opacity=1\">' +"
new1 = "    var alarmliMi = s.alarm_count > 0;\n    html += '<div class=\"topo-svc-chip\" data-svc=\"' + s.name + '\" data-alarm=\"' + (alarmliMi ? '1' : '0') + '\" onclick=\"topoYukle(this.dataset.svc)\" style=\"' + alarmCss + ';padding:4px 10px;border-radius:20px;cursor:pointer;font-size:10px;font-family:JetBrains Mono,monospace;display:' + (alarmliMi ? 'inline-block' : 'none') + '\" onmouseover=\"this.style.opacity=0.7\" onmouseout=\"this.style.opacity=1\">' +"

if old1 in c:
    c = c.replace(old1, new1)
    degisiklik += 1
    print("OK: chip data-alarm eklendi")
else:
    print("WARN: chip satiri bulunamadi")

# 2. topoFiltrele - bos arama -> sadece alarmlilar, dolu -> hepsi
old2 = """function topoFiltrele(ara) {
  var chips = document.querySelectorAll('.topo-svc-chip');
  chips.forEach(function(chip) {
    chip.style.display = chip.dataset.svc.toLowerCase().indexOf(ara.toLowerCase()) !== -1 ? '' : 'none';
  });
}"""

new2 = """function topoFiltrele(ara) {
  var chips = document.querySelectorAll('.topo-svc-chip');
  chips.forEach(function(chip) {
    var eslesiyor = chip.dataset.svc.toLowerCase().indexOf(ara.toLowerCase()) !== -1;
    var alarmli = chip.dataset.alarm === '1';
    if (ara === '') {
      chip.style.display = alarmli ? 'inline-block' : 'none';
    } else {
      chip.style.display = eslesiyor ? 'inline-block' : 'none';
    }
  });
}"""

if old2 in c:
    c = c.replace(old2, new2)
    degisiklik += 1
    print("OK: topoFiltrele guncellendi")
else:
    print("WARN: topoFiltrele bulunamadi")

# 3. Input placeholder guncelle - kullaniciya ipucu ver
old3 = 'placeholder="Servis ad\\u0131 yaz..."'
new3 = 'placeholder="Arama yaparak t\\u00fcm servisleri g\\u00f6r\\u00fcn..."'
if old3 in c:
    c = c.replace(old3, new3)
    degisiklik += 1
    print("OK: placeholder guncellendi")
else:
    print("WARN: placeholder bulunamadi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print(f"\nToplam degisiklik: {degisiklik}/3")
print("girisYap:", "girisYap" in c)
