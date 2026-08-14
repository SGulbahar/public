"""
Servis Haritasi JS fonksiyonunu frontend'e ekler.
Calistirma: python3 patch_servis_haritasi.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

JS = """
async function servisHaritasiYukle() {
  var el = document.getElementById('pg-servis-haritasi');
  if (!el) return;
  el.innerHTML =
    '<div class="pgh"><div>' +
    '<div class="pgey">Analitik</div>' +
    '<div class="pgt">Servis Haritas\\u0131</div>' +
    '<div class="pgs">Servis ili\\u015fkileri ve alarm durumu \\u2014 Leiden cluster algoritmas\\u0131</div>' +
    '</div>' +
    '<div><button class="btn btn-gh btn-sm" onclick="servisHaritasiYukle()">Yenile</button></div>' +
    '</div>' +
    '<div id="sh-icerik">' + ldg() + '</div>';

  try {
    var response = await fetch('/api/v1/service-map', {
      headers: {'Authorization': 'Bearer ' + _tok}
    });
    var ok = response.status >= 200 && response.status < 300;
    if (!ok) throw new Error('HTTP ' + response.status);
    var html = await response.text();
    var iframe = document.createElement('iframe');
    iframe.style.cssText = 'width:100%;height:calc(100vh - 160px);border:none;border-radius:8px';
    iframe.srcdoc = html;
    document.getElementById('sh-icerik').innerHTML = '';
    document.getElementById('sh-icerik').appendChild(iframe);
  } catch(e) {
    document.getElementById('sh-icerik').innerHTML = htaHtml(e.message);
  }
}

"""

old = 'async function ayarlarYukle()'
if old in c:
    c = c.replace(old, JS + '\nasync function ayarlarYukle()', 1)
    print("OK: servisHaritasiYukle eklendi")
else:
    print("WARN: ayarlarYukle bulunamadi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("servisHaritasiYukle:", "servisHaritasiYukle" in c)
print("girisYap:", "girisYap" in c)
