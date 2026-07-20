"""
Zabbix Alarmlari frontend sayfasini ekler.
Calistirma: python3 patch_zabbix_alarmlar_frontend.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

ZABBIX_ALARMLAR_JS = """
/* ─────────────────────────────────────────
   ZABBİX ALARMLARI
───────────────────────────────────────── */
async function zabbixAlarmlariYukle() {
  var el = document.getElementById('pg-zabbix-alarmlar');
  if (!el) return;

  el.innerHTML =
    '<div class="pgh"><div>' +
    '<div class="pgey">Altyap\\u0131</div>' +
    '<div class="pgt">Zabbix Alarmlar\\u0131</div>' +
    '<div class="pgs">DISASTER seviyesindeki aktif Zabbix alarmlar\\u0131 \\u2014 BMC topoloji bilgisi ile</div>' +
    '</div></div>' +
    '<div class="card" style="margin-bottom:14px"><div class="cb" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">' +
    '<div style="display:flex;gap:6px">' +
    '<button class="btn btn-gh" id="zb-btn-aktif" onclick="zabbixFiltrele(true)" style="border-color:var(--acc)">Aktif</button>' +
    '<button class="btn btn-gh" id="zb-btn-tumu" onclick="zabbixFiltrele(false)">Tümü</button>' +
    '</div>' +
    '<div style="flex:1;text-align:right;font-size:10px;color:var(--txt3)" id="zb-ozet"></div>' +
    '</div></div>' +
    '<div id="zb-liste">' + ldg() + '</div>';

  await zabbixOzetYukle();
  await zabbixListeYukle(true);
}

async function zabbixOzetYukle() {
  try {
    var ozet = await apiFetch('/api/v1/zabbix/events/ozet') || {};
    var el = document.getElementById('zb-ozet');
    if (el) {
      el.innerHTML =
        '<span class="chip c-r" style="margin-right:6px">Aktif: ' + (ozet.aktif || 0) + '</span>' +
        '<span class="chip c-g" style="margin-right:6px">Çözüldü: ' + (ozet.cozulmus || 0) + '</span>' +
        '<span class="chip c-gr">Toplam: ' + (ozet.toplam || 0) + '</span>';
    }
    // Badge güncelle
    var badge = document.getElementById('nb-zabbix');
    if (badge) badge.textContent = ozet.aktif || 0;
  } catch(e) {}
}

async function zabbixListeYukle(sadece_aktif) {
  var el = document.getElementById('zb-liste');
  if (el) el.innerHTML = ldg();

  try {
    var url = '/api/v1/zabbix/events?limit=100&aktif=' + (sadece_aktif ? 'true' : 'false');
    var data = await apiFetch(url) || [];

    if (!data.length) {
      el.innerHTML = '<div class="card"><div class="cb" style="text-align:center;color:var(--txt3);padding:20px">' +
        (sadece_aktif ? 'Aktif DISASTER alarm yok ✓' : 'Kayıt bulunamadı') + '</div></div>';
      return;
    }

    var html = '<div class="card"><div class="cb">' +
      '<table style="width:100%;border-collapse:collapse;font-size:11px">' +
      '<thead><tr style="border-bottom:1px solid var(--border)">' +
      '<th style="text-align:left;padding:8px 6px;color:var(--txt3);font-weight:600">Alarm</th>' +
      '<th style="text-align:left;padding:8px 6px;color:var(--txt3);font-weight:600">Host</th>' +
      '<th style="text-align:left;padding:8px 6px;color:var(--txt3);font-weight:600">BMC Servisler</th>' +
      '<th style="text-align:center;padding:8px 6px;color:var(--txt3);font-weight:600">Ortam</th>' +
      '<th style="text-align:center;padding:8px 6px;color:var(--txt3);font-weight:600">Zaman</th>' +
      '<th style="text-align:center;padding:8px 6px;color:var(--txt3);font-weight:600">Durum</th>' +
      '<th style="text-align:center;padding:8px 6px;color:var(--txt3);font-weight:600">LLM</th>' +
      '</tr></thead><tbody>';

    data.forEach(function(e) {
      var zaman = e.clock ? new Date(e.clock).toLocaleString('tr-TR', {timeZone:'Europe/Istanbul'}) : '-';
      var bmcBadge = e.bmc_eslesmis ?
        '<span class="chip c-t" style="font-size:8px">BMC ✓</span>' :
        '<span class="chip c-gr" style="font-size:8px">BMC ✗</span>';
      var servisler = e.bmc_services && e.bmc_services.length ?
        '<div style="font-size:9px;color:var(--txt2);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + e.bmc_services.join(', ') + '">' + e.bmc_services.slice(0,2).join(', ') + (e.bmc_services.length > 2 ? ' +' + (e.bmc_services.length-2) : '') + '</div>' :
        '<span style="font-size:9px;color:var(--txt3)">-</span>';
      var cozuldu = e.resolved_at ?
        '<span class="chip c-g" style="font-size:8px">Çözüldü</span>' :
        '<span class="chip c-r" style="font-size:8px">Aktif</span>';
      var ortam = e.host_env ?
        '<span class="chip c-gr" style="font-size:8px">' + e.host_env + '</span>' : '-';

      html += '<tr style="border-bottom:1px solid var(--border2)">';
      html += '<td style="padding:8px 6px;max-width:250px">' +
        '<div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + e.name + '">' + e.name + '</div>' +
        '</td>';
      html += '<td style="padding:8px 6px;font-family:JetBrains Mono,monospace;font-size:10px">' +
        (e.host_name || '-') + '<br>' + bmcBadge + '</td>';
      html += '<td style="padding:8px 6px">' + servisler + '</td>';
      html += '<td style="text-align:center;padding:8px 6px">' + ortam + '</td>';
      html += '<td style="text-align:center;padding:8px 6px;font-size:10px;color:var(--txt3)">' + zaman + '</td>';
      html += '<td style="text-align:center;padding:8px 6px">' + cozuldu + '</td>';
      html += '<td style="text-align:center;padding:8px 6px">' +
        '<button class="btn btn-gh btn-sm" data-eid="' + e.id + '" onclick="zabbixLlmAnalizEt(this.dataset.eid, this)">Analiz</button>' +
        '</td>';
      html += '</tr>';
      html += '<tr id="zb-llm-' + e.id + '" style="display:none"><td colspan="7" style="padding:0 6px 8px 6px"></td></tr>';
    });

    html += '</tbody></table></div></div>';
    el.innerHTML = html;

  } catch(e) {
    el.innerHTML = htaHtml(e.message);
  }
}

function zabbixFiltrele(sadece_aktif) {
  document.getElementById('zb-btn-aktif').style.borderColor = sadece_aktif ? 'var(--acc)' : '';
  document.getElementById('zb-btn-tumu').style.borderColor = sadece_aktif ? '' : 'var(--acc)';
  zabbixListeYukle(sadece_aktif);
}

async function zabbixLlmAnalizEt(eventId, btn) {
  var satirEl = document.getElementById('zb-llm-' + eventId);
  if (!satirEl) return;

  if (satirEl.style.display !== 'none') {
    satirEl.style.display = 'none';
    btn.textContent = 'Analiz';
    return;
  }

  btn.textContent = '...';
  satirEl.style.display = 'table-row';
  satirEl.querySelector('td').innerHTML = ldg();

  try {
    var data = await apiFetch('/api/v1/zabbix/events/' + eventId + '/llm-analiz', {method: 'POST'});
    var analiz = (data.analiz || '').replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
    satirEl.querySelector('td').innerHTML =
      '<div style="background:var(--bg3);border-radius:8px;padding:12px 16px;font-size:11px;line-height:1.8">' +
      (data.bmc_eslesmis ? '<div style="font-size:9px;color:var(--teal);margin-bottom:8px;font-family:JetBrains Mono,monospace">✓ BMC topoloji bilgisi kullanıldı</div>' : '') +
      analiz + '</div>';
    btn.textContent = 'Kapat';
  } catch(e) {
    satirEl.querySelector('td').innerHTML = htaHtml(e.message);
    btn.textContent = 'Analiz';
  }
}

"""

old = 'async function ayarlarYukle()'
if old in c:
    c = c.replace(old, ZABBIX_ALARMLAR_JS + '\nasync function ayarlarYukle()', 1)
    print("OK: JS eklendi")
else:
    print("WARN: ayarlarYukle bulunamadi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("zabbixAlarmlariYukle:", "zabbixAlarmlariYukle" in c)
print("girisYap:", "girisYap" in c)
