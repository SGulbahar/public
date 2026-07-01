"""
VM Radar fonksiyonlarini yeniden yazar:
- Arama kutusu ile host filtreleme
- Host'a tiklayinca analiz
- Checkbox ve toplu analiz kaldirildi
Calistirma: python3 patch_vm_radar_ux.py
"""
import re

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

# Eski VM Radar JS blogunu bul ve sil
start_marker = '/* ─────────────────────────────────────────\n   VM RADAR'
end_marker = 'async function ayarlarYukle()'

start_idx = c.find(start_marker)
end_idx = c.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"WARN: start={start_idx} end={end_idx}")
else:
    print(f"OK: VM Radar blogu bulundu ({start_idx}-{end_idx})")

NEW_VM_RADAR_JS = """/* ─────────────────────────────────────────
   VM RADAR
───────────────────────────────────────── */
var _vmRadarHosts = [];
var _vmRadarSonuclar = {};
var VM_RADAR_GROUP_ID = '193';

async function vmRadarYukle() {
  var el = document.getElementById('pg-vmradar');
  if (!el) return;

  el.innerHTML =
    '<div class="pgh"><div>' +
    '<div class="pgey">Altyap\\u0131</div>' +
    '<div class="pgt">VM Analiz</div>' +
    '<div class="pgs">Sunucu CPU ve bellek kullan\\u0131m analizi \\u2014 kapasite optimizasyonu</div>' +
    '</div></div>' +
    '<div class="card" style="margin-bottom:14px"><div class="cb">' +
    '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">' +
    '<div style="flex:1;min-width:200px">' +
    '<label class="form-lbl">Host Ara</label>' +
    '<input class="form-input" id="vr-ara" placeholder="Sunucu ad\\u0131 yaz..." oninput="vmRadarFiltrele(this.value)" />' +
    '</div>' +
    '<div>' +
    '<label class="form-lbl">Analiz S\\u00fcresi</label>' +
    '<select id="vr-gun" class="form-select">' +
    '<option value="30">Son 30 G\\u00fcn</option>' +
    '<option value="60" selected>Son 60 G\\u00fcn</option>' +
    '</select>' +
    '</div>' +
    '<div style="align-self:flex-end">' +
    '<button class="btn btn-gh" onclick="vmRadarHostYukle()">Yenile</button>' +
    '</div>' +
    '</div>' +
    '</div></div>' +
    '<div style="display:flex;gap:14px;align-items:flex-start">' +
    '<div style="width:280px;flex-shrink:0">' +
    '<div class="card"><div class="ch"><span class="cht">Sunucular</span><span id="vr-host-sayi" style="font-size:10px;color:var(--txt3)">-</span></div>' +
    '<div class="cb" id="vr-host-liste" style="max-height:600px;overflow-y:auto;padding:4px">' + ldg() + '</div>' +
    '</div></div>' +
    '<div style="flex:1" id="vr-sonuc-alan"></div>' +
    '</div>';

  await vmRadarHostYukle();
}

async function vmRadarHostYukle() {
  var el = document.getElementById('vr-host-liste');
  if (el) el.innerHTML = ldg();
  try {
    var hosts = await apiFetch('/api/v1/vm-radar/hosts?group_id=' + VM_RADAR_GROUP_ID) || [];
    _vmRadarHosts = hosts;
    vmRadarListeGoster(hosts);
  } catch(e) {
    if (el) el.innerHTML = '<div style="font-size:11px;color:var(--red);padding:8px">' + e.message + '</div>';
  }
}

function vmRadarListeGoster(hosts) {
  var el = document.getElementById('vr-host-liste');
  var sayiEl = document.getElementById('vr-host-sayi');
  if (!el) return;
  if (sayiEl) sayiEl.textContent = hosts.length + ' sunucu';

  if (!hosts.length) {
    el.innerHTML = '<div style="font-size:11px;color:var(--txt3);padding:8px;text-align:center">Sunucu bulunamad\\u0131</div>';
    return;
  }

  var html = '';
  hosts.forEach(function(h) {
    var sonuc = _vmRadarSonuclar[h.id];
    var riskBadge = '';
    if (sonuc) {
      var riskCss = sonuc.risk === 'LOW' ? 'c-g' : sonuc.risk === 'HIGH' ? 'c-r' : 'c-a';
      var riskTr = sonuc.risk === 'LOW' ? 'D\\u00fc\\u015f\\u00fck' : sonuc.risk === 'HIGH' ? 'Y\\u00fcksek' : 'Orta';
      riskBadge = '<span class="chip ' + riskCss + '" style="font-size:8px;padding:1px 5px">' + riskTr + '</span>';
    }
    html += '<div class="vr-host-item" data-hid="' + h.id + '" data-hname="' + h.name + '" onclick="vmRadarHostAnalizEt(this.dataset.hid, this.dataset.hname)" style="display:flex;align-items:center;justify-content:space-between;padding:7px 8px;border-radius:6px;cursor:pointer;border:1px solid transparent;margin-bottom:3px;transition:background .15s" onmouseover="this.style.background=\'var(--bg3)\'" onmouseout="this.style.background=\'\'">';
    html += '<span style="font-size:11px;font-family:JetBrains Mono,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">' + h.name + '</span>';
    html += riskBadge;
    html += '</div>';
  });

  el.innerHTML = html;
}

function vmRadarFiltrele(ara) {
  var araLower = ara.toLowerCase();
  var filtered = _vmRadarHosts.filter(function(h) {
    return h.name.toLowerCase().indexOf(araLower) !== -1;
  });
  vmRadarListeGoster(filtered);
}

async function vmRadarHostAnalizEt(hostId, hostName) {
  // Aktif item'i vurgula
  document.querySelectorAll('.vr-host-item').forEach(function(el) {
    el.style.background = '';
    el.style.borderColor = 'transparent';
  });
  var aktif = document.querySelector('.vr-host-item[data-hid="' + hostId + '"]');
  if (aktif) {
    aktif.style.background = 'var(--acc-dim)';
    aktif.style.borderColor = 'var(--acc)';
  }

  var sonucAlan = document.getElementById('vr-sonuc-alan');
  if (!sonucAlan) return;
  sonucAlan.innerHTML = '<div class="card"><div class="cb">' + ldg() + '<div style="text-align:center;font-size:11px;color:var(--txt3);margin-top:8px">' + hostName + ' analiz ediliyor...</div></div></div>';

  var gun = document.getElementById('vr-gun') ? document.getElementById('vr-gun').value : '60';

  try {
    var data = await apiFetch('/api/v1/vm-radar/analyze', {
      method: 'POST',
      body: JSON.stringify({host_ids: [hostId], gun: parseInt(gun)})
    });

    var sonuclar = data.sonuclar || [];
    if (!sonuclar.length || sonuclar[0].hata) {
      sonucAlan.innerHTML = htaHtml(sonuclar[0] ? sonuclar[0].hata : 'Veri alinamadi');
      return;
    }

    var s = sonuclar[0];
    _vmRadarSonuclar[hostId] = s;

    // Host listesini guncelle (risk badge icin)
    var araEl = document.getElementById('vr-ara');
    vmRadarFiltrele(araEl ? araEl.value : '');

    vmRadarSonucGoster(s, sonucAlan, gun);
  } catch(e) {
    sonucAlan.innerHTML = htaHtml(e.message);
  }
}

function vmRadarSonucGoster(s, el, gun) {
  var riskCss = s.risk === 'LOW' ? 'c-g' : s.risk === 'HIGH' ? 'c-r' : 'c-a';
  var riskTr = s.risk === 'LOW' ? 'D\\u00fc\\u015f\\u00fck \\u2014 Optimize Edilebilir' : s.risk === 'HIGH' ? 'Y\\u00fcksek \\u2014 Kaynak Arttirilmali' : 'Orta \\u2014 \\u0130zlenmeli';

  var html = '<div class="card">';
  html += '<div class="ch"><span class="cht" style="font-family:JetBrains Mono,monospace;color:var(--acc)">' + s.host_name + '</span>';
  html += '<span class="chip ' + riskCss + '">' + (s.risk_tr || riskTr) + '</span></div>';
  html += '<div class="cb">';

  // CPU karti
  html += '<div style="margin-bottom:14px">';
  html += '<div style="font-size:10px;font-weight:700;color:var(--txt3);margin-bottom:8px;font-family:JetBrains Mono,monospace">CPU KULLANIMI (' + gun + ' G\\u00dcN)</div>';
  html += '<div class="gw">';
  html += vmRadarMetrikKart('P95', s.cpu.p95 + '%', s.cpu.p95 > 70 ? 'c-r' : s.cpu.p95 > 40 ? 'c-a' : 'c-g');
  html += vmRadarMetrikKart('Max', s.cpu.max + '%', s.cpu.max > 80 ? 'c-r' : s.cpu.max > 60 ? 'c-a' : 'c-g');
  html += vmRadarMetrikKart('Ort', s.cpu.avg + '%', 'c-gr');
  html += vmRadarMetrikKart('Spike', s.cpu.spike_saat + ' saat', s.cpu.spike_saat > 10 ? 'c-r' : s.cpu.spike_saat > 0 ? 'c-a' : 'c-g');
  html += '</div></div>';

  // RAM karti
  html += '<div style="margin-bottom:14px">';
  html += '<div style="font-size:10px;font-weight:700;color:var(--txt3);margin-bottom:8px;font-family:JetBrains Mono,monospace">RAM KULLANIMI (' + gun + ' G\\u00dcN) \\u2014 Toplam: ' + s.ram.total_gb + ' GB</div>';
  html += '<div class="gw">';
  html += vmRadarMetrikKart('P95', s.ram.kullanim_p95 + '%', s.ram.kullanim_p95 > 80 ? 'c-r' : s.ram.kullanim_p95 > 60 ? 'c-a' : 'c-g');
  html += vmRadarMetrikKart('Max', s.ram.kullanim_max + '%', s.ram.kullanim_max > 90 ? 'c-r' : s.ram.kullanim_max > 70 ? 'c-a' : 'c-g');
  html += vmRadarMetrikKart('Ort', s.ram.kullanim_avg + '%', 'c-gr');
  html += '</div></div>';

  // Oneri
  if (s.oneri && s.oneri.length) {
    html += '<div style="background:var(--bg3);border-radius:8px;padding:10px 14px;margin-bottom:14px">';
    html += '<div style="font-size:10px;font-weight:700;color:var(--acc);margin-bottom:6px">\\u00d6NER\\u0130LER</div>';
    s.oneri.forEach(function(o) {
      html += '<div style="font-size:11px;color:var(--txt2);padding:2px 0">\\u2022 ' + o + '</div>';
    });
    html += '</div>';
  }

  // LLM analiz butonu
  html += '<button class="btn btn-ok" onclick="vmRadarLlmAnalizEt(\'' + s.host_id + '\')" style="width:100%">\\u{1F916} LLM Detay Analizi</button>';
  html += '<div id="vr-llm-' + s.host_id + '" style="margin-top:10px"></div>';
  html += '</div></div>';

  el.innerHTML = html;
}

function vmRadarMetrikKart(baslik, deger, css) {
  return '<div class="card"><div class="cb" style="text-align:center;padding:8px">' +
    '<div style="font-size:18px;font-weight:800" class="' + css + '">' + deger + '</div>' +
    '<div style="font-size:9px;color:var(--txt3);margin-top:2px">' + baslik + '</div>' +
    '</div></div>';
}

async function vmRadarLlmAnalizEt(hostId) {
  var sunucu = _vmRadarSonuclar[hostId];
  if (!sunucu) return;

  var el = document.getElementById('vr-llm-' + hostId);
  if (!el) return;
  el.innerHTML = ldg();

  try {
    var data = await apiFetch('/api/v1/vm-radar/llm-analyze', {
      method: 'POST',
      body: JSON.stringify({sunucu: sunucu})
    });

    var analiz = (data.analiz || '').replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
    el.innerHTML = '<div style="background:var(--bg3);border-radius:8px;padding:12px 16px;font-size:12px;line-height:1.8;margin-top:8px">' + analiz + '</div>';
  } catch(e) {
    el.innerHTML = htaHtml(e.message);
  }
}

"""

if start_idx != -1 and end_idx != -1:
    c = c[:start_idx] + NEW_VM_RADAR_JS + '\n' + c[end_idx:]
    print("OK: VM Radar JS yeniden yazildi")
else:
    # ayarlarYukle'den once ekle
    old = 'async function ayarlarYukle()'
    if old in c:
        c = c.replace(old, NEW_VM_RADAR_JS + '\nasync function ayarlarYukle()', 1)
        print("OK: VM Radar JS eklendi (alternatif)")
    else:
        print("WARN: ekleme noktasi bulunamadi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("vmRadarYukle:", "async function vmRadarYukle" in c)
print("vmRadarFiltrele:", "function vmRadarFiltrele" in c)
print("vmRadarHostAnalizEt:", "function vmRadarHostAnalizEt" in c)
print("girisYap:", "function girisYap" in c)
