"""
VM Radar sayfasini frontend index.html ye ekler.
Calistirma: python3 patch_vm_radar_frontend.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

degisiklik = 0

# 1. Sidebar - incidents'tan sonra vmradar ekle
old1 = "h+=ni('incidents','<path d=\"M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z\"/><line x1=\"12\" y1=\"9\" x2=\"12\" y2=\"13\"/><line x1=\"12\" y1=\"17\" x2=\"12.01\" y2=\"17\"/>','Incident Merkezi','<span class=\"nbadge nb-r\" id=\"nb-incidents\">-</span>');"
new1 = old1 + "\n    h+=ni('vmradar','<circle cx=\"9\" cy=\"9\" r=\"3\"/><path d=\"M9 1v2M9 15v2M1 9h2M15 9h2M3.3 3.3l1.5 1.5M13.2 13.2l1.5 1.5M3.3 14.7l1.5-1.5M13.2 4.8l1.5-1.5\"/>','VM Analiz');"

if old1 in c:
    c = c.replace(old1, new1)
    degisiklik += 1
    print("OK: sidebar eklendi")
else:
    print("WARN: sidebar - incidents satiri bulunamadi")

# 2. pg div ekle
old2 = "'<div class=\"page\" id=\"pg-incidents\"></div>'"
new2 = "'<div class=\"page\" id=\"pg-incidents\"></div>'+\n    '<div class=\"page\" id=\"pg-vmradar\"></div>'"

if old2 in c:
    c = c.replace(old2, new2)
    degisiklik += 1
    print("OK: pg-vmradar eklendi")
else:
    print("WARN: pg-incidents div bulunamadi")

# 3. SAYFA_ADLARI
old3 = "incidents:'incident-merkezi'"
new3 = "incidents:'incident-merkezi',vmradar:'vm-analiz'"

if old3 in c:
    c = c.replace(old3, new3)
    degisiklik += 1
    print("OK: SAYFA_ADLARI guncellendi")
else:
    print("WARN: SAYFA_ADLARI - incidents bulunamadi")

# 4. YUKLE
old4 = "incidents:incidentYukle"
new4 = "incidents:incidentYukle,vmradar:vmRadarYukle"

if old4 in c:
    c = c.replace(old4, new4)
    degisiklik += 1
    print("OK: YUKLE guncellendi")
else:
    print("WARN: YUKLE - incidents bulunamadi")

# 5. vmRadarYukle JS fonksiyonu ekle - ayarlarYukle'den once
VM_RADAR_JS = """
/* ─────────────────────────────────────────
   VM RADAR
───────────────────────────────────────── */
var _vmRadarHosts = [];
var _vmRadarSonuclar = [];
var VM_RADAR_GROUP_ID = '193';

async function vmRadarYukle() {
  var el = document.getElementById('pg-vmradar');
  if (!el) return;

  el.innerHTML =
    '<div class="pgh"><div>' +
    '<div class="pgey">Altyapi</div>' +
    '<div class="pgt">VM Analiz</div>' +
    '<div class="pgs">Sunucu CPU ve bellek kullanim analizi — kapasite optimizasyonu</div>' +
    '</div></div>' +
    '<div class="card" style="margin-bottom:14px">' +
    '<div class="cb" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">' +
    '<div>' +
    '<label class="form-lbl">Analiz Suresi</label>' +
    '<select id="vr-gun" class="form-select" style="width:140px">' +
    '<option value="30">Son 30 Gun</option>' +
    '<option value="60" selected>Son 60 Gun</option>' +
    '</select>' +
    '</div>' +
    '<div style="flex:1">' +
    '<label class="form-lbl">Secili Host Sayisi</label>' +
    '<div id="vr-host-sayi" style="font-size:13px;font-weight:700;font-family:JetBrains Mono,monospace;color:var(--acc)">-</div>' +
    '</div>' +
    '<div style="display:flex;gap:8px;align-items:flex-end">' +
    '<button class="btn btn-gh" onclick="vmRadarHostYukle()">Hostlari Yukle</button>' +
    '<button class="btn btn-ok" id="vr-analiz-btn" onclick="vmRadarAnalizEt()" style="display:none">Analiz Et</button>' +
    '</div>' +
    '</div></div>' +
    '<div id="vr-host-liste" style="margin-bottom:14px"></div>' +
    '<div id="vr-sonuc-liste"></div>';

  await vmRadarHostYukle();
}

async function vmRadarHostYukle() {
  var el = document.getElementById('vr-host-liste');
  if (el) el.innerHTML = ldg();
  try {
    var hosts = await apiFetch('/api/v1/vm-radar/hosts?group_id=' + VM_RADAR_GROUP_ID) || [];
    _vmRadarHosts = hosts;
    document.getElementById('vr-host-sayi').textContent = hosts.length + ' host';

    var html = '<div class="card"><div class="ch"><span class="cht">Hostlar</span>';
    html += '<div style="display:flex;gap:6px">';
    html += '<button class="btn btn-gh btn-sm" onclick="vmRadarTumunuSec(true)">Tumunu Sec</button>';
    html += '<button class="btn btn-gh btn-sm" onclick="vmRadarTumunuSec(false)">Temizle</button>';
    html += '</div></div>';
    html += '<div class="cb"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px">';

    hosts.forEach(function(h) {
      html += '<label style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:6px;border:1px solid var(--border);cursor:pointer;font-size:11px;font-family:JetBrains Mono,monospace">';
      html += '<input type="checkbox" data-hid="' + h.id + '" onchange="vmRadarSecimGuncelle()" style="cursor:pointer"/>';
      html += '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + h.name + '</span>';
      html += '</label>';
    });

    html += '</div></div></div>';
    if (el) el.innerHTML = html;
    document.getElementById('vr-analiz-btn').style.display = 'inline-flex';
  } catch(e) {
    if (el) el.innerHTML = htaHtml(e.message);
  }
}

function vmRadarTumunuSec(sec) {
  document.querySelectorAll('#vr-host-liste input[type=checkbox]').forEach(function(cb) {
    cb.checked = sec;
  });
  vmRadarSecimGuncelle();
}

function vmRadarSecimGuncelle() {
  var secili = document.querySelectorAll('#vr-host-liste input[type=checkbox]:checked').length;
  document.getElementById('vr-host-sayi').textContent = _vmRadarHosts.length + ' host (' + secili + ' secili)';
}

async function vmRadarAnalizEt() {
  var seciliIds = [];
  document.querySelectorAll('#vr-host-liste input[type=checkbox]:checked').forEach(function(cb) {
    seciliIds.push(cb.dataset.hid);
  });

  if (!seciliIds.length) {
    bildirim('Analiz icin en az 1 host secin', 'warn');
    return;
  }

  var gun = document.getElementById('vr-gun').value;
  var sonucEl = document.getElementById('vr-sonuc-liste');
  sonucEl.innerHTML = '<div class="card"><div class="cb">' + ldg() + '<div style="text-align:center;margin-top:8px;font-size:11px;color:var(--txt3)">' + seciliIds.length + ' host icin ' + gun + ' gunluk veri analiz ediliyor...</div></div></div>';

  try {
    var data = await apiFetch('/api/v1/vm-radar/analyze', {
      method: 'POST',
      body: JSON.stringify({host_ids: seciliIds, gun: parseInt(gun)})
    });

    _vmRadarSonuclar = data.sonuclar || [];
    vmRadarSonucGoster(_vmRadarSonuclar);
  } catch(e) {
    sonucEl.innerHTML = htaHtml(e.message);
  }
}

function vmRadarSonucGoster(sonuclar) {
  var el = document.getElementById('vr-sonuc-liste');
  if (!sonuclar.length) {
    el.innerHTML = '<div class="card"><div class="cb" style="text-align:center;color:var(--txt3)">Sonuc bulunamadi</div></div>';
    return;
  }

  var low = sonuclar.filter(function(s) { return s.risk === 'LOW'; });
  var med = sonuclar.filter(function(s) { return s.risk === 'MEDIUM'; });
  var high = sonuclar.filter(function(s) { return s.risk === 'HIGH'; });
  var unk = sonuclar.filter(function(s) { return s.risk === 'UNKNOWN'; });

  var html = '<div class="gw" style="margin-bottom:14px">';
  html += '<div class="card"><div class="cb" style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--green)">' + low.length + '</div><div style="font-size:10px;color:var(--txt3)">Optimize Edilebilir</div></div></div>';
  html += '<div class="card"><div class="cb" style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--amber)">' + med.length + '</div><div style="font-size:10px;color:var(--txt3)">Orta Risk</div></div></div>';
  html += '<div class="card"><div class="cb" style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--red)">' + high.length + '</div><div style="font-size:10px;color:var(--txt3)">Yuksek Kullanim</div></div></div>';
  html += '<div class="card"><div class="cb" style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--txt3)">' + sonuclar.length + '</div><div style="font-size:10px;color:var(--txt3)">Toplam Analiz</div></div></div>';
  html += '</div>';

  html += '<div class="card"><div class="ch"><span class="cht">Analiz Sonuclari</span></div><div class="cb">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:11px">';
  html += '<thead><tr style="border-bottom:1px solid var(--border)">';
  html += '<th style="text-align:left;padding:6px;color:var(--txt3);font-weight:600">Sunucu</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">CPU P95</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">CPU Max</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">RAM P95</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">RAM (GB)</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">Spike</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">Risk</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">Oneri</th>';
  html += '<th style="text-align:center;padding:6px;color:var(--txt3);font-weight:600">LLM</th>';
  html += '</tr></thead><tbody>';

  sonuclar.forEach(function(s, idx) {
    if (s.hata) {
      html += '<tr><td colspan="9" style="padding:6px;color:var(--red);font-family:JetBrains Mono,monospace">' + (s.host_id || '-') + ': ' + s.hata + '</td></tr>';
      return;
    }
    var riskCss = s.risk === 'LOW' ? 'c-g' : s.risk === 'HIGH' ? 'c-r' : 'c-a';
    var riskTr = s.risk === 'LOW' ? 'Dusuk' : s.risk === 'HIGH' ? 'Yuksek' : s.risk === 'MEDIUM' ? 'Orta' : '-';
    var oneriStr = (s.oneri || []).join(', ') || '-';

    html += '<tr style="border-bottom:1px solid var(--border2)">';
    html += '<td style="padding:6px;font-family:JetBrains Mono,monospace;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (s.host_name || s.host_id) + '</td>';
    html += '<td style="text-align:center;padding:6px">%' + (s.cpu ? s.cpu.p95 : '-') + '</td>';
    html += '<td style="text-align:center;padding:6px">%' + (s.cpu ? s.cpu.max : '-') + '</td>';
    html += '<td style="text-align:center;padding:6px">%' + (s.ram ? s.ram.kullanim_p95 : '-') + '</td>';
    html += '<td style="text-align:center;padding:6px">' + (s.ram ? s.ram.total_gb : '-') + '</td>';
    html += '<td style="text-align:center;padding:6px">' + (s.cpu ? s.cpu.spike_saat + 's' : '-') + '</td>';
    html += '<td style="text-align:center;padding:6px"><span class="chip ' + riskCss + '">' + riskTr + '</span></td>';
    html += '<td style="padding:6px;font-size:10px;color:var(--txt2)">' + oneriStr + '</td>';
    html += '<td style="text-align:center;padding:6px"><button class="btn btn-gh btn-sm" data-idx="' + idx + '" onclick="vmRadarLlmAnalizEt(this.dataset.idx)">Analiz</button></td>';
    html += '</tr>';
  });

  html += '</tbody></table></div></div>';
  html += '<div id="vr-llm-sonuc" style="margin-top:14px"></div>';
  el.innerHTML = html;
}

async function vmRadarLlmAnalizEt(idx) {
  var sunucu = _vmRadarSonuclar[parseInt(idx)];
  if (!sunucu) return;

  var el = document.getElementById('vr-llm-sonuc');
  el.innerHTML = '<div class="card"><div class="cb">' + ldg() + '<div style="text-align:center;font-size:11px;color:var(--txt3);margin-top:8px">' + sunucu.host_name + ' icin LLM analizi yapiliyor...</div></div></div>';
  el.scrollIntoView({behavior:'smooth'});

  try {
    var data = await apiFetch('/api/v1/vm-radar/llm-analyze', {
      method: 'POST',
      body: JSON.stringify({sunucu: sunucu})
    });

    var analiz = data.analiz || '';
    var html = '<div class="card"><div class="ch"><span class="cht" style="font-family:JetBrains Mono,monospace;color:var(--acc)">' + data.host_name + '</span><span style="font-size:10px;color:var(--txt3)">LLM Analizi</span></div>';
    html += '<div class="cb"><div style="font-size:12px;line-height:1.7;white-space:pre-wrap">' + analiz.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') + '</div></div></div>';
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = htaHtml(e.message);
  }
}

"""

old5 = 'async function ayarlarYukle()'
new5 = VM_RADAR_JS + 'async function ayarlarYukle()'

if old5 in c:
    c = c.replace(old5, new5, 1)
    degisiklik += 1
    print("OK: vmRadarYukle JS eklendi")
else:
    print("WARN: ayarlarYukle bulunamadi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print(f"\nToplam degisiklik: {degisiklik}/5")
print("vmRadarYukle:", "vmRadarYukle" in c)
print("pg-vmradar:", "pg-vmradar" in c)
print("girisYap:", "girisYap" in c)
