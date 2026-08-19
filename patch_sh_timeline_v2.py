"""
Service Health timeline'ini anomali timeline gibi nokta/ucgen formatina ceviren patch.
Calistirma: python3 patch_sh_timeline_v2.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

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

    var ilkKayit = data.history[0] || {};

    var html = '<div class="card"><div class="ch">';
    html += '<span class="cht" style="font-family:JetBrains Mono,monospace;color:var(--acc);font-size:12px">' + data.service + '</span>';
    html += '<span style="font-size:10px;color:var(--txt3)">' + data.channel_code + '</span>';
    html += '</div><div class="cb">';

    // Tag ekleme
    html += '<div style="margin-bottom:12px">';
    html += '<label class="form-lbl">Etiketler</label>';
    html += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px" id="sh-tags-' + id + '">';
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

    // TIMELINE - nokta/ucgen format
    if (data.history.length > 0) {
      html += '<div style="font-size:10px;font-weight:700;color:var(--txt3);margin-bottom:12px;font-family:JetBrains Mono,monospace;letter-spacing:.05em">ANOMALi TiMELiNE (' + data.history.length + ' periyot)</div>';

      var now = Date.now();
      var enErken = data.history.reduce(function(min, h) {
        return Math.min(min, h.started_at ? new Date(h.started_at).getTime() : now);
      }, now);
      var toplamMs = Math.max(now - enErken, 3600000);

      // Timeline container
      html += '<div style="position:relative;height:60px;margin-bottom:4px">';

      // Yatay cizgi
      html += '<div style="position:absolute;top:24px;left:0;right:0;height:2px;background:var(--border)"></div>';

      data.history.forEach(function(h, idx) {
        var basMs = h.started_at ? new Date(h.started_at).getTime() : now;
        var leftPct = Math.max(1, Math.min(97, ((basMs - enErken) / toplamMs) * 100));
        var aktif = h.status === 'active';
        var renk = h.max_severity === 'DISASTER' ? 'var(--red)' :
                   h.max_severity === 'HIGH' ? 'var(--orange)' : 'var(--amber)';
        var sure = h.sure_dk < 60 ? h.sure_dk + ' dk' : Math.round(h.sure_dk/60) + ' sa';
        var basTr = h.started_at ? new Date(h.started_at).toLocaleString('tr-TR') : '-';
        var bitTr = h.resolved_at ? new Date(h.resolved_at).toLocaleString('tr-TR') : 'Aktif';
        var dataStr = 'data-sev="' + (h.max_severity||'') + '" data-count="' + h.anomali_count + '" data-sure="' + sure + '" data-bas="' + basTr + '" data-bit="' + bitTr + '" data-aktif="' + aktif + '"';

        if (aktif) {
          // Ucgen - aktif
          html += '<div ' + dataStr + ' onclick="shTlPopup(this)" style="position:absolute;left:calc(' + leftPct + '% - 8px);top:12px;width:0;height:0;border-left:8px solid transparent;border-right:8px solid transparent;border-bottom:16px solid ' + renk + ';cursor:pointer;filter:drop-shadow(0 0 4px ' + renk + ')" onmouseover="this.style.transform=\'scale(1.3)\'" onmouseout="this.style.transform=\'\'"></div>';
        } else {
          // Daire - resolved
          html += '<div ' + dataStr + ' onclick="shTlPopup(this)" style="position:absolute;left:calc(' + leftPct + '% - 6px);top:15px;width:12px;height:12px;border-radius:50%;background:' + renk + ';cursor:pointer;transition:transform .15s" onmouseover="this.style.transform=\'scale(1.4)\'" onmouseout="this.style.transform=\'\'"></div>';
        }
      });

      html += '</div>';

      // Zaman etiketleri
      html += '<div style="display:flex;justify-content:space-between;font-size:8px;color:var(--txt3);font-family:JetBrains Mono,monospace;margin-bottom:16px">';
      html += '<span>' + new Date(enErken).toLocaleDateString('tr-TR') + '</span>';
      html += '<span>Simdi</span>';
      html += '</div>';

      // Legend
      html += '<div style="display:flex;gap:12px;margin-bottom:4px">';
      html += '<div style="display:flex;align-items:center;gap:4px"><div style="width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-bottom:10px solid var(--red)"></div><span style="font-size:9px;color:var(--txt3)">Aktif</span></div>';
      html += '<div style="display:flex;align-items:center;gap:4px"><div style="width:10px;height:10px;border-radius:50%;background:var(--red)"></div><span style="font-size:9px;color:var(--txt3)">DISASTER</span></div>';
      html += '<div style="display:flex;align-items:center;gap:4px"><div style="width:10px;height:10px;border-radius:50%;background:var(--orange)"></div><span style="font-size:9px;color:var(--txt3)">HIGH</span></div>';
      html += '<div style="display:flex;align-items:center;gap:4px"><div style="width:10px;height:10px;border-radius:50%;background:var(--amber)"></div><span style="font-size:9px;color:var(--txt3)">WARNING</span></div>';
      html += '</div>';
    }

    html += '</div></div>';

    // Popup div
    html += '<div id="sh-tl-popup" style="display:none;position:fixed;z-index:9999;background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;min-width:220px;box-shadow:0 8px 32px rgba(0,0,0,.4);pointer-events:none"></div>';

    detayEl.innerHTML = html;
  } catch(e) {
    detayEl.innerHTML = htaHtml(e.message);
  }
}

function shTlPopup(el) {
  var popup = document.getElementById('sh-tl-popup');
  if (!popup) return;

  var sev = el.dataset.sev || '-';
  var count = el.dataset.count || '0';
  var sure = el.dataset.sure || '-';
  var bas = el.dataset.bas || '-';
  var bit = el.dataset.bit || '-';
  var aktif = el.dataset.aktif === 'true';

  var sevCss = sev === 'DISASTER' ? 'color:var(--red)' : sev === 'HIGH' ? 'color:var(--orange)' : 'color:var(--amber)';
  var renk = sev === 'DISASTER' ? 'var(--red)' : sev === 'HIGH' ? 'var(--orange)' : 'var(--amber)';

  popup.style.display = 'block';
  popup.style.pointerEvents = 'auto';
  popup.innerHTML =
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">' +
    '<span class="sbg ' + (sev === 'DISASTER' ? 'd' : sev === 'HIGH' ? 'h' : 'w') + '" style="font-size:9px">' + sev + '</span>' +
    (aktif ? '<span class="chip c-r" style="font-size:9px">Aktif</span>' : '<span class="chip c-g" style="font-size:9px">C\\u00f6z\\u00fcld\\u00fc</span>') +
    '</div>' +
    '<div style="font-size:13px;font-weight:800;color:' + renk + ';margin-bottom:8px">' + count + ' anomali</div>' +
    '<div style="font-size:11px;color:var(--txt2);margin-bottom:4px">\\u23f1 S\\u00fcre: ' + sure + '</div>' +
    '<div style="font-size:10px;color:var(--txt3)">Ba\\u015f: ' + bas + '</div>' +
    '<div style="font-size:10px;color:var(--txt3)">Biti\\u015f: ' + bit + '</div>' +
    '<button onclick="this.parentElement.style.display=\\'none\\'" style="margin-top:10px;width:100%;padding:4px;border-radius:6px;border:1px solid var(--border);background:var(--bg3);color:var(--txt2);cursor:pointer;font-size:10px">Kapat</button>';

  var rect = el.getBoundingClientRect();
  var left = Math.min(rect.left, window.innerWidth - 240);
  popup.style.left = left + 'px';
  popup.style.top = (rect.top - 160) + 'px';
}"""

c = c[:start_idx] + NEW_DETAY + c[end_idx:]
print("OK: shDetayGoster timeline v2 yazildi")

# shTimelineHover ve shTimelineHoverKapat fonksiyonlarini kaldir (artik gerek yok)
c = re.sub(r'\nfunction shTimelineHover\(.*?\)\n\}', '', c, flags=re.DOTALL)
c = re.sub(r'\nfunction shTimelineHoverKapat\(\).*?\}', '', c, flags=re.DOTALL)

import re
with open(HTML_PATH, 'w') as f:
    f.write(c)

print("girisYap:", "girisYap" in c)
print("shTlPopup:", "shTlPopup" in c)
