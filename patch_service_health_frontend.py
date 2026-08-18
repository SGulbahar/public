"""
Servis Sagligi sayfasini frontend'e ekler.
Calistirma: python3 patch_service_health_frontend.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

degisiklik = 0

# 1. Sidebar - servis-haritasi'ndan sonra ekle
old1 = "h+=ni('servis-haritasi',"
new1 = "h+=ni('servis-sagligi','<path d=\"M12 2a10 10 0 100 20A10 10 0 0012 2zm0 6v4l3 3\"/>','Servis Sa\\u011fl\\u0131\\u011f\\u0131');\n    h+=ni('servis-haritasi',"
if old1 in c:
    c = c.replace(old1, new1)
    degisiklik += 1
    print("OK: sidebar eklendi")
else:
    print("WARN: sidebar")

# 2. pg ekle
old2 = "'<div class=\"page\" id=\"pg-servis-haritasi\"></div>'"
new2 = "'<div class=\"page\" id=\"pg-servis-sagligi\"></div>'+\n    '<div class=\"page\" id=\"pg-servis-haritasi\"></div>'"
if old2 in c:
    c = c.replace(old2, new2)
    degisiklik += 1
    print("OK: pg eklendi")
else:
    print("WARN: pg")

# 3. SAYFA_ADLARI
old3 = "'servis-haritasi':'servis-haritasi'"
new3 = "'servis-sagligi':'servis-sagligi','servis-haritasi':'servis-haritasi'"
if old3 in c:
    c = c.replace(old3, new3)
    degisiklik += 1
    print("OK: SAYFA_ADLARI")
else:
    print("WARN: SAYFA_ADLARI")

# 4. YUKLE
old4 = "'servis-haritasi':servisHaritasiYukle"
new4 = "'servis-sagligi':servisSagligiYukle,'servis-haritasi':servisHaritasiYukle"
if old4 in c:
    c = c.replace(old4, new4)
    degisiklik += 1
    print("OK: YUKLE")
else:
    print("WARN: YUKLE")

# 5. JS fonksiyonu ekle
SH_JS = """
/* ─────────────────────────────────────────
   SERVİS SAĞLIĞI
───────────────────────────────────────── */
var _shSeciliId = null;

async function servisSagligiYukle() {
  var el = document.getElementById('pg-servis-sagligi');
  if (!el) return;

  el.innerHTML =
    '<div class="pgh"><div>' +
    '<div class="pgey">Analitik</div>' +
    '<div class="pgt">Servis Sa\\u011fl\\u0131\\u011f\\u0131</div>' +
    '<div class="pgs">Servis bazl\\u0131 anomali ge\\u00e7mi\\u015fi ve aktif sorunlar</div>' +
    '</div></div>' +
    '<div class="card" style="margin-bottom:14px"><div class="cb" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
    '<div style="display:flex;gap:6px">' +
    '<button class="btn btn-gh" id="sh-btn-aktif" onclick="shFiltrele(\'active\')" style="border-color:var(--acc)">Aktif</button>' +
    '<button class="btn btn-gh" id="sh-btn-hepsi" onclick="shFiltrele(null)">T\\u00fcm\\u00fc</button>' +
    '</div>' +
    '<div style="flex:1;min-width:150px">' +
    '<input class="form-input" id="sh-ara" placeholder="Servis ara..." oninput="shAra(this.value)" style="height:32px"/>' +
    '</div>' +
    '</div></div>' +
    '<div style="display:flex;gap:14px">' +
    '<div style="flex:1" id="sh-liste">' + ldg() + '</div>' +
    '<div style="width:360px;flex-shrink:0" id="sh-detay"></div>' +
    '</div>';

  await shListeYukle('active');
}

async function shListeYukle(status) {
  var el = document.getElementById('sh-liste');
  if (el) el.innerHTML = ldg();

  try {
    var url = '/api/v1/service-health' + (status ? '?status=' + status : '?limit=100');
    var data = await apiFetch(url) || [];

    if (!data.length) {
      el.innerHTML = '<div class="card"><div class="cb" style="text-align:center;color:var(--txt3);padding:20px">' +
        (status === 'active' ? '\\u2713 Aktif servis sorunu yok' : 'Kay\\u0131t bulunamad\\u0131') + '</div></div>';
      return;
    }

    var html = '<div style="display:flex;flex-direction:column;gap:6px">';
    data.forEach(function(s) {
      var sevCss = s.max_severity === 'DISASTER' ? 'd' : s.max_severity === 'HIGH' ? 'h' : 'w';
      var statusCss = s.status === 'active' ? 'c-r' : 'c-g';
      var statusTr = s.status === 'active' ? 'Aktif' : 'C\\u00f6z\\u00fcld\\u00fc';
      var sure = s.sure_dk < 60 ? s.sure_dk + ' dk' : Math.round(s.sure_dk/60) + ' sa';

      html += '<div class="card sh-item" data-id="' + s.id + '" onclick="shDetayGoster(this.dataset.id)" style="cursor:pointer;transition:border-color .15s" onmouseover="this.style.borderColor=\'var(--acc)\'" onmouseout="this.style.borderColor=\'\'">';
      html += '<div class="cb" style="padding:10px 14px">';
      html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">';
      html += '<span class="sbg ' + sevCss + '" style="font-size:8px;padding:2px 6px">' + (s.max_severity || '-') + '</span>';
      html += '<span class="chip ' + statusCss + '" style="font-size:8px">' + statusTr + '</span>';
      if (s.tags && s.tags.length) {
        s.tags.forEach(function(t) {
          html += '<span class="chip c-v" style="font-size:8px">' + t + '</span>';
        });
      }
      html += '<span style="font-size:9px;color:var(--txt3);margin-left:auto">' + sure + '</span>';
      html += '</div>';
      html += '<div style="font-size:12px;font-weight:700;font-family:JetBrains Mono,monospace;margin-bottom:2px">' + s.service + '</div>';
      html += '<div style="display:flex;gap:12px;font-size:10px;color:var(--txt3)">';
      html += '<span>' + s.anomali_count + ' anomali</span>';
      html += '<span>Ort. Hata: %' + s.avg_error_rate + '</span>';
      html += '<span>Ort. S\\u00fcre: ' + s.avg_elapsed + 'ms</span>';
      html += '</div>';
      html += '</div></div>';
    });
    html += '</div>';
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = htaHtml(e.message);
  }
}

function shFiltrele(status) {
  document.getElementById('sh-btn-aktif').style.borderColor = status === 'active' ? 'var(--acc)' : '';
  document.getElementById('sh-btn-hepsi').style.borderColor = !status ? 'var(--acc)' : '';
  shListeYukle(status);
}

async function shAra(ara) {
  var items = document.querySelectorAll('.sh-item');
  items.forEach(function(item) {
    var svc = item.querySelector('[style*="font-weight:700"]');
    if (!svc) return;
    item.style.display = svc.textContent.toLowerCase().indexOf(ara.toLowerCase()) !== -1 ? '' : 'none';
  });
}

async function shDetayGoster(id) {
  _shSeciliId = id;
  var detayEl = document.getElementById('sh-detay');
  if (!detayEl) return;
  detayEl.innerHTML = '<div class="card"><div class="cb">' + ldg() + '</div></div>';

  // Aktif item vurgula
  document.querySelectorAll('.sh-item').forEach(function(el) {
    el.style.borderColor = el.dataset.id == id ? 'var(--acc)' : '';
  });

  try {
    var data = await apiFetch('/api/v1/service-health/' + id + '/history');
    if (!data) return;

    var html = '<div class="card"><div class="ch">';
    html += '<span class="cht" style="font-family:JetBrains Mono,monospace;color:var(--acc);font-size:12px">' + data.service + '</span>';
    html += '</div><div class="cb">';

    // Tag ekleme
    html += '<div style="margin-bottom:12px">';
    html += '<label class="form-lbl">Etiketler</label>';
    html += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px" id="sh-tags-' + id + '">';
    var ilkKayit = data.history[0] || {};
    (ilkKayit.tags || []).forEach(function(t) {
      html += '<span class="chip c-v" style="font-size:9px;cursor:pointer" onclick="shTagSil(this, ' + id + ')">' + t + ' \\u00d7</span>';
    });
    html += '</div>';
    html += '<div style="display:flex;gap:6px">';
    html += '<input class="form-input" id="sh-tag-input-' + id + '" placeholder="Tag ekle..." style="height:28px;font-size:11px" onkeydown="if(event.key===\'Enter\') shTagEkle(' + id + ')"/>';
    html += '<button class="btn btn-gh btn-sm" onclick="shTagEkle(' + id + ')">Ekle</button>';
    html += '</div></div>';

    // Not
    html += '<div style="margin-bottom:12px">';
    html += '<label class="form-lbl">Not</label>';
    html += '<textarea class="form-input" id="sh-not-' + id + '" style="height:60px;font-size:11px;resize:vertical">' + (ilkKayit.notes || '') + '</textarea>';
    html += '<button class="btn btn-ok btn-sm" style="margin-top:4px;width:100%" onclick="shKaydet(' + id + ')">Kaydet</button>';
    html += '</div>';

    // Gecmis
    html += '<div style="font-size:10px;font-weight:700;color:var(--txt3);margin-bottom:8px;font-family:JetBrains Mono,monospace">GE\\u00c7M\\u0130\\u015e (' + data.history.length + ')</div>';
    data.history.forEach(function(h) {
      var sevCss = h.max_severity === 'DISASTER' ? 'd' : h.max_severity === 'HIGH' ? 'h' : 'w';
      var baslangic = h.started_at ? new Date(h.started_at).toLocaleString('tr-TR', {timeZone:'Europe/Istanbul'}) : '-';
      var bitis = h.resolved_at ? new Date(h.resolved_at).toLocaleString('tr-TR', {timeZone:'Europe/Istanbul'}) : 'Devam ediyor';
      var sure = h.sure_dk < 60 ? h.sure_dk + ' dk' : Math.round(h.sure_dk/60) + ' sa';

      html += '<div style="border-left:3px solid ' + (h.status === 'active' ? 'var(--red)' : 'var(--green)') + ';padding:8px 10px;margin-bottom:8px;background:var(--bg3);border-radius:0 6px 6px 0">';
      html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">';
      html += '<span class="sbg ' + sevCss + '" style="font-size:8px;padding:2px 5px">' + (h.max_severity || '-') + '</span>';
      html += '<span style="font-size:10px;font-weight:700">' + h.anomali_count + ' anomali</span>';
      html += '<span style="font-size:9px;color:var(--txt3);margin-left:auto">' + sure + '</span>';
      html += '</div>';
      html += '<div style="font-size:9px;color:var(--txt3)">' + baslangic + ' \\u2192 ' + bitis + '</div>';
      if (h.root_cause_hint) {
        html += '<div style="font-size:10px;color:var(--txt2);margin-top:4px">' + h.root_cause_hint + '</div>';
      }
      html += '</div>';
    });

    html += '</div></div>';
    detayEl.innerHTML = html;
  } catch(e) {
    detayEl.innerHTML = htaHtml(e.message);
  }
}

var _shTaglar = {};
function shTagEkle(id) {
  var input = document.getElementById('sh-tag-input-' + id);
  if (!input || !input.value.trim()) return;
  var tag = input.value.trim();
  var container = document.getElementById('sh-tags-' + id);
  if (!container) return;
  var span = document.createElement('span');
  span.className = 'chip c-v';
  span.style.cssText = 'font-size:9px;cursor:pointer';
  span.textContent = tag + ' x';
  span.onclick = function() { shTagSil(span, id); };
  container.appendChild(span);
  input.value = '';
}

function shTagSil(el, id) {
  el.remove();
}

async function shKaydet(id) {
  var container = document.getElementById('sh-tags-' + id);
  var notEl = document.getElementById('sh-not-' + id);
  var tags = [];
  if (container) {
    container.querySelectorAll('.chip').forEach(function(chip) {
      var t = chip.textContent.replace(' x', '').trim();
      if (t) tags.push(t);
    });
  }
  try {
    await apiFetch('/api/v1/service-health/' + id + '/tag', {
      method: 'PATCH',
      body: JSON.stringify({tags: tags, notes: notEl ? notEl.value : ''})
    });
    bildirim('Kaydedildi', 'ok');
    shListeYukle(document.getElementById('sh-btn-aktif').style.borderColor ? 'active' : null);
  } catch(e) { bildirim(e.message, 'err'); }
}

"""

old5 = 'async function ayarlarYukle()'
if old5 in c:
    c = c.replace(old5, SH_JS + '\nasync function ayarlarYukle()', 1)
    degisiklik += 1
    print("OK: JS eklendi")
else:
    print("WARN: ayarlarYukle")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print(f"\nToplam degisiklik: {degisiklik}/5")
print("girisYap:", "girisYap" in c)
print("servisSagligiYukle:", "servisSagligiYukle" in c)
