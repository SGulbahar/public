"""
Service Health history listesini timeline ile degistirir.
Calistirma: python3 patch_sh_timeline.py
"""
import re

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

# shDetayGoster fonksiyonunu bul
start_idx = c.find('async function shDetayGoster(id) {')
if start_idx == -1:
    print("WARN: shDetayGoster bulunamadi")
    exit()

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

NEW_DETAY = """async function shDetayGoster(id) {
  _shSeciliId = id;
  var detayEl = document.getElementById('sh-detay');
  if (!detayEl) return;
  detayEl.innerHTML = '<div class="card"><div class="cb">' + ldg() + '</div></div>';

  document.querySelectorAll('.sh-item').forEach(function(el) {
    el.style.borderColor = el.dataset.id == id ? 'var(--acc)' : '';
  });

  try {
    var data = await apiFetch('/api/v1/service-health/' + id + '/history');
    if (!data) return;

    var html = '<div class="card"><div class="ch">';
    html += '<span class="cht" style="font-family:JetBrains Mono,monospace;color:var(--acc);font-size:12px">' + data.service + '</span>';
    html += '<span style="font-size:10px;color:var(--txt3)">' + data.channel_code + '</span>';
    html += '</div><div class="cb">';

    // Tag ekleme
    html += '<div style="margin-bottom:14px">';
    html += '<label class="form-lbl">Etiketler</label>';
    html += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px" id="sh-tags-' + id + '">';
    var ilkKayit = data.history[0] || {};
    (ilkKayit.tags || []).forEach(function(t) {
      html += '<span class="chip c-v" style="font-size:9px;cursor:pointer" onclick="this.remove()">' + t + ' \\u00d7</span>';
    });
    html += '</div>';
    html += '<div style="display:flex;gap:6px">';
    html += '<input class="form-input" id="sh-tag-input-' + id + '" placeholder="Tag ekle..." style="height:28px;font-size:11px" data-sid="' + id + '" onkeydown="if(event.keyCode===13) shTagEkle(this.dataset.sid)"/>';
    html += '<button class="btn btn-gh btn-sm" data-sid="' + id + '" onclick="shTagEkle(this.dataset.sid)">Ekle</button>';
    html += '</div></div>';

    // Not
    html += '<div style="margin-bottom:16px">';
    html += '<label class="form-lbl">Not</label>';
    html += '<textarea class="form-input" id="sh-not-' + id + '" style="height:50px;font-size:11px;resize:vertical">' + (ilkKayit.notes || '') + '</textarea>';
    html += '<button class="btn btn-ok btn-sm" style="margin-top:4px;width:100%" onclick="shKaydet(' + id + ')">Kaydet</button>';
    html += '</div>';

    // TIMELINE
    if (data.history.length > 0) {
      html += '<div style="font-size:10px;font-weight:700;color:var(--txt3);margin-bottom:10px;font-family:JetBrains Mono,monospace">ANOMAL\\u0130 T\\u0130MEL\\u0130NE (' + data.history.length + ' periyot)</div>';

      // Zaman araligini hesapla
      var now = Date.now();
      var enErken = data.history.reduce(function(min, h) {
        var t = h.started_at ? new Date(h.started_at).getTime() : now;
        return t < min ? t : min;
      }, now);
      var enGec = now;
      var toplamMs = enGec - enErken;
      if (toplamMs < 3600000) toplamMs = 3600000; // En az 1 saat goster

      html += '<div style="position:relative;height:48px;background:var(--bg3);border-radius:6px;margin-bottom:6px;overflow:visible" id="sh-tl-' + id + '">';

      data.history.forEach(function(h, idx) {
        var basMs = h.started_at ? new Date(h.started_at).getTime() : now;
        var bitMs = h.resolved_at ? new Date(h.resolved_at).getTime() : now;
        var leftPct = Math.max(0, Math.min(98, ((basMs - enErken) / toplamMs) * 100));
        var widthPct = Math.max(1, Math.min(98 - leftPct, ((bitMs - basMs) / toplamMs) * 100));

        var renk = h.max_severity === 'DISASTER' ? 'var(--red)' :
                   h.max_severity === 'HIGH' ? 'var(--orange)' : 'var(--amber)';
        var aktif = h.status === 'active';
        var sure = h.sure_dk < 60 ? h.sure_dk + ' dk' : Math.round(h.sure_dk/60) + ' sa ' + Math.round(h.sure_dk%60) + ' dk';
        var basTr = h.started_at ? new Date(h.started_at).toLocaleString('tr-TR') : '-';
        var bitTr = h.resolved_at ? new Date(h.resolved_at).toLocaleString('tr-TR') : 'Devam ediyor';
        var tooltip = h.max_severity + ' | ' + h.anomali_count + ' anomali | ' + sure + '\n' + basTr + ' -> ' + bitTr;

        html += '<div title="' + tooltip + '" style="position:absolute;top:8px;height:32px;left:' + leftPct + '%;width:' + widthPct + '%;background:' + renk + ';border-radius:4px;opacity:0.85;cursor:pointer;min-width:4px;box-sizing:border-box;' + (aktif ? 'outline:2px solid white;' : '') + '"';
        html += ' onmouseover="shTimelineHover(this, ' + JSON.stringify({
          severity: h.max_severity,
          count: h.anomali_count,
          sure: sure,
          bas: basTr,
          bit: bitTr,
          aktif: aktif
        }).replace(/"/g, '&quot;') + ')"';
        html += ' onmouseout="shTimelineHoverKapat()">';
        if (aktif) {
          html += '<div style="width:100%;height:100%;border-radius:4px;animation:pulse 2s infinite;background:' + renk + '"></div>';
        }
        html += '</div>';
      });

      html += '</div>';

      // Zaman etiketleri
      html += '<div style="display:flex;justify-content:space-between;font-size:8px;color:var(--txt3);font-family:JetBrains Mono,monospace;margin-bottom:14px">';
      html += '<span>' + new Date(enErken).toLocaleDateString('tr-TR') + '</span>';
      html += '<span>' + new Date(enGec).toLocaleDateString('tr-TR') + '</span>';
      html += '</div>';

      // Hover tooltip div
      html += '<div id="sh-tl-tooltip" style="display:none;position:fixed;background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;font-size:11px;z-index:9999;pointer-events:none;max-width:250px;box-shadow:0 4px 20px rgba(0,0,0,.3)"></div>';

      // Legend
      html += '<div style="display:flex;gap:10px;margin-bottom:12px">';
      [['var(--red)', 'DISASTER'], ['var(--orange)', 'HIGH'], ['var(--amber)', 'WARNING']].forEach(function(item) {
        html += '<div style="display:flex;align-items:center;gap:4px">';
        html += '<div style="width:10px;height:10px;border-radius:2px;background:' + item[0] + '"></div>';
        html += '<span style="font-size:9px;color:var(--txt3)">' + item[1] + '</span>';
        html += '</div>';
      });
      html += '<div style="display:flex;align-items:center;gap:4px">';
      html += '<div style="width:10px;height:10px;border-radius:2px;background:var(--acc);outline:2px solid white"></div>';
      html += '<span style="font-size:9px;color:var(--txt3)">Aktif</span>';
      html += '</div></div>';
    }

    html += '</div></div>';
    detayEl.innerHTML = html;

  } catch(e) {
    detayEl.innerHTML = htaHtml(e.message);
  }
}

function shTimelineHover(el, data) {
  var tip = document.getElementById('sh-tl-tooltip');
  if (!tip) return;
  var rect = el.getBoundingClientRect();
  tip.style.display = 'block';
  tip.style.left = (rect.left + rect.width/2 - 125) + 'px';
  tip.style.top = (rect.top - 120) + 'px';
  var sevCss = data.severity === 'DISASTER' ? 'color:var(--red)' : data.severity === 'HIGH' ? 'color:var(--orange)' : 'color:var(--amber)';
  tip.innerHTML =
    '<div style="' + sevCss + ';font-weight:700;margin-bottom:6px">' + (data.aktif ? '\\u26a0 AKTIF - ' : '') + data.severity + '</div>' +
    '<div style="color:var(--txt2)">' + data.count + ' anomali | ' + data.sure + '</div>' +
    '<div style="color:var(--txt3);font-size:10px;margin-top:4px">' + data.bas + '</div>' +
    '<div style="color:var(--txt3);font-size:10px">\\u2192 ' + data.bit + '</div>';
}

function shTimelineHoverKapat() {
  var tip = document.getElementById('sh-tl-tooltip');
  if (tip) tip.style.display = 'none';
}"""

c = c[:start_idx] + NEW_DETAY + c[end_idx:]
print("OK: shDetayGoster yeniden yazildi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("girisYap:", "girisYap" in c)
print("shTimelineHover:", "shTimelineHover" in c)
