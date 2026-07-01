"""
VM Radar kart gorunumunu duzelten patch.
Calistirma: python3 patch_vm_radar_cards.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

# vmRadarMetrikKart ve vmRadarSonucGoster fonksiyonlarini yeniden yaz
import re

# vmRadarMetrikKart fonksiyonunu bul ve degistir
old_kart = """function vmRadarMetrikKart(baslik, deger, css) {
  return '<div class="card"><div class="cb" style="text-align:center;padding:8px">' +
    '<div style="font-size:18px;font-weight:800" class="' + css + '">' + deger + '</div>' +
    '<div style="font-size:9px;color:var(--txt3);margin-top:2px">' + baslik + '</div>' +
    '</div></div>';
}"""

new_kart = """function vmRadarProgressBar(baslik, yuzde, renk, aciklama) {
  var bar_w = Math.min(100, Math.max(0, yuzde));
  return '<div style="margin-bottom:10px">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">' +
    '<span style="font-size:10px;color:var(--txt3);font-family:JetBrains Mono,monospace;font-weight:600">' + baslik + '</span>' +
    '<div style="display:flex;align-items:center;gap:8px">' +
    (aciklama ? '<span style="font-size:9px;color:var(--txt3)">' + aciklama + '</span>' : '') +
    '<span style="font-size:13px;font-weight:800;color:' + renk + ';font-family:JetBrains Mono,monospace;min-width:50px;text-align:right">' + yuzde + '%</span>' +
    '</div></div>' +
    '<div style="height:6px;background:var(--bg4);border-radius:3px;overflow:hidden">' +
    '<div style="height:100%;width:' + bar_w + '%;background:' + renk + ';border-radius:3px;transition:width .4s"></div>' +
    '</div></div>';
}

function vmRadarRenk(yuzde, esik_yuksek, esik_orta) {
  if (yuzde >= esik_yuksek) return 'var(--red)';
  if (yuzde >= esik_orta) return 'var(--orange)';
  return 'var(--green)';
}"""

if old_kart in c:
    c = c.replace(old_kart, new_kart)
    print("OK: vmRadarMetrikKart yeniden yazildi")
else:
    print("WARN: vmRadarMetrikKart bulunamadi")
    # Sona ekle
    c = c.replace('async function vmRadarLlmAnalizEt', new_kart + '\nasync function vmRadarLlmAnalizEt')

# vmRadarSonucGoster fonksiyonunu yeniden yaz
start_idx = c.find('function vmRadarSonucGoster(s, el, gun) {')
if start_idx == -1:
    print("WARN: vmRadarSonucGoster bulunamadi")
else:
    # Fonksiyon sonunu bul
    depth = 0
    i = c.find('{', start_idx)
    while i < len(c):
        if c[i] == '{': depth += 1
        elif c[i] == '}':
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
        i += 1

    NEW_SONUC_GOSTER = """function vmRadarSonucGoster(s, el, gun) {
  var riskCss = s.risk === 'LOW' ? 'c-g' : s.risk === 'HIGH' ? 'c-r' : 'c-a';
  var riskTr = s.risk === 'LOW' ? 'D\\u00fc\\u015f\\u00fck \\u2014 Optimize Edilebilir' :
               s.risk === 'HIGH' ? 'Y\\u00fcksek \\u2014 Kaynak Arttirilmali' : 'Orta \\u2014 \\u0130zlenmeli';

  var html = '<div class="card">';
  html += '<div class="ch">';
  html += '<span class="cht" style="font-family:JetBrains Mono,monospace;color:var(--acc)">' + s.host_name + '</span>';
  html += '<span class="chip ' + riskCss + '">' + riskTr + '</span>';
  html += '</div><div class="cb">';

  // CPU bolumu
  html += '<div style="background:var(--bg3);border-radius:10px;padding:14px 16px;margin-bottom:12px">';
  html += '<div style="font-size:10px;font-weight:700;color:var(--txt3);margin-bottom:12px;font-family:JetBrains Mono,monospace;letter-spacing:.05em">CPU KULLANIMI \\u2014 Son ' + gun + ' G\\u00fcn</div>';
  html += vmRadarProgressBar('P95 (Normal Y\\u00fck)', s.cpu.p95, vmRadarRenk(s.cpu.p95, 70, 40), '');
  html += vmRadarProgressBar('Maksimum', s.cpu.max, vmRadarRenk(s.cpu.max, 80, 60),
    s.cpu.spike_saat > 0 ? '\\u26a0\\ufe0f ' + s.cpu.spike_saat + ' saat %80+' : '');
  html += vmRadarProgressBar('Ortalama', s.cpu.avg, vmRadarRenk(s.cpu.avg, 60, 30), '');
  html += '</div>';

  // RAM bolumu
  html += '<div style="background:var(--bg3);border-radius:10px;padding:14px 16px;margin-bottom:12px">';
  html += '<div style="font-size:10px;font-weight:700;color:var(--txt3);margin-bottom:12px;font-family:JetBrains Mono,monospace;letter-spacing:.05em">RAM KULLANIMI \\u2014 Toplam ' + s.ram.total_gb + ' GB</div>';
  html += vmRadarProgressBar('P95 (Normal Y\\u00fck)', s.ram.kullanim_p95, vmRadarRenk(s.ram.kullanim_p95, 80, 60), '');
  html += vmRadarProgressBar('Maksimum', s.ram.kullanim_max, vmRadarRenk(s.ram.kullanim_max, 90, 70), '');
  html += vmRadarProgressBar('Ortalama', s.ram.kullanim_avg, vmRadarRenk(s.ram.kullanim_avg, 70, 50), '');
  html += '</div>';

  // Oneri bolumu
  if (s.oneri && s.oneri.length) {
    html += '<div style="background:var(--acc-dim);border:1px solid var(--acc-mid);border-radius:8px;padding:10px 14px;margin-bottom:12px">';
    html += '<div style="font-size:10px;font-weight:700;color:var(--acc);margin-bottom:6px;font-family:JetBrains Mono,monospace">\\u00d6NER\\u0130LER</div>';
    s.oneri.forEach(function(o) {
      html += '<div style="font-size:11px;color:var(--txt);padding:2px 0">\\u2022 ' + o + '</div>';
    });
    html += '</div>';
  }

  // LLM butonu
  html += '<button class="btn btn-ok" data-hid="' + s.host_id + '" onclick="vmRadarLlmAnalizEt(this.dataset.hid)" style="width:100%;margin-top:4px">\\u{1F916} LLM Detay Analizi</button>';
  html += '<div id="vr-llm-' + s.host_id + '" style="margin-top:12px"></div>';
  html += '</div></div>';

  el.innerHTML = html;
}"""

    c = c[:start_idx] + NEW_SONUC_GOSTER + c[end_idx:]
    print("OK: vmRadarSonucGoster yeniden yazildi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("vmRadarProgressBar:", "vmRadarProgressBar" in c)
print("vmRadarSonucGoster:", "function vmRadarSonucGoster" in c)
print("girisYap:", "function girisYap" in c)
