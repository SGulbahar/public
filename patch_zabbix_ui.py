"""
Zabbix Alarmlari listesini kart bazli UI ile yeniden yazar.
Calistirma: python3 patch_zabbix_ui.py
"""
import re

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

# zabbixListeYukle fonksiyonunu bul ve degistir
start_idx = c.find('async function zabbixListeYukle(sadece_aktif) {')
if start_idx == -1:
    print("WARN: zabbixListeYukle bulunamadi")
    exit()

# Fonksiyon sonunu bul
depth = 0
i = c.find('{', start_idx)
while i < len(c):
    if c[i] == '{':
        depth += 1
    elif c[i] == '}':
        depth -= 1
        if depth == 0:
            end_idx = i + 1
            break
    i += 1

NEW_LISTE = """async function zabbixListeYukle(sadece_aktif) {
  var el = document.getElementById('zb-liste');
  if (el) el.innerHTML = ldg();

  try {
    var url = '/api/v1/zabbix/events?limit=100&aktif=' + (sadece_aktif ? 'true' : 'false');
    var data = await apiFetch(url) || [];

    if (!data.length) {
      el.innerHTML = '<div class="card"><div class="cb" style="text-align:center;color:var(--txt3);padding:24px">' +
        (sadece_aktif ? '\\u2713 Aktif DISASTER alarm yok' : 'Kay\\u0131t bulunamad\\u0131') + '</div></div>';
      return;
    }

    var html = '<div style="display:flex;flex-direction:column;gap:10px">';

    data.forEach(function(e) {
      var zaman = e.clock ? new Date(e.clock).toLocaleString('tr-TR', {timeZone:'Europe/Istanbul'}) : '-';
      var sure = '';
      if (e.clock) {
        var ms = Date.now() - new Date(e.clock).getTime();
        var dk = Math.floor(ms / 60000);
        var sa = Math.floor(dk / 60);
        sure = sa > 0 ? sa + ' saat ' + (dk % 60) + ' dk' : dk + ' dk';
      }

      var aktif = !e.resolved_at;
      var statusCss = aktif ? 'c-r' : 'c-g';
      var statusTr = aktif ? 'Aktif' : 'C\\u00f6z\\u00fcld\\u00fc';

      var bmcHtml = '';
      if (e.bmc_eslesmis && e.bmc_services && e.bmc_services.length) {
        bmcHtml = '<div style="margin-top:8px;padding:8px 10px;background:var(--bg4);border-radius:6px;border-left:3px solid var(--teal)">' +
          '<div style="font-size:9px;font-weight:700;color:var(--teal);margin-bottom:4px;font-family:JetBrains Mono,monospace">BMC TOPOLOJ\\u0130</div>';
        if (e.host_env) bmcHtml += '<div style="font-size:10px;color:var(--txt2)">Ortam: <strong>' + e.host_env + '</strong></div>';
        if (e.host_application) bmcHtml += '<div style="font-size:10px;color:var(--txt2)">Uygulama: <strong>' + e.host_application + '</strong></div>';
        bmcHtml += '<div style="font-size:10px;color:var(--txt2);margin-top:3px">Business Services:</div>';
        e.bmc_services.forEach(function(s) {
          bmcHtml += '<div style="font-size:10px;color:var(--txt);padding:1px 0;font-family:JetBrains Mono,monospace">\\u2022 ' + s + '</div>';
        });
        bmcHtml += '</div>';
      } else if (!e.bmc_eslesmis) {
        bmcHtml = '<div style="margin-top:6px;font-size:10px;color:var(--txt3)">\\u26a0\\ufe0f BMC topoloji e\\u015fle\\u015fmesi yok</div>';
      }

      html += '<div class="card">';
      html += '<div class="cb">';

      // Baslik satiri
      html += '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px">';
      html += '<div style="flex:1">';
      html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">';
      html += '<span class="sbg d" style="font-size:9px;padding:2px 8px">DISASTER</span>';
      html += '<span class="chip ' + statusCss + '" style="font-size:9px">' + statusTr + '</span>';
      if (aktif && sure) html += '<span style="font-size:10px;color:var(--txt3)">' + sure + ' \\u00f6nce</span>';
      html += '</div>';
      html += '<div style="font-size:13px;font-weight:700;line-height:1.4;color:var(--txt)">' + e.name + '</div>';
      html += '</div>';
      html += '<div style="text-align:right;flex-shrink:0">';
      html += '<div style="font-size:10px;color:var(--txt3);font-family:JetBrains Mono,monospace">' + zaman + '</div>';
      if (e.resolved_at) {
        var resolvedZaman = new Date(e.resolved_at).toLocaleString('tr-TR', {timeZone:'Europe/Istanbul'});
        html += '<div style="font-size:9px;color:var(--green);margin-top:2px">\\u2713 ' + resolvedZaman + '</div>';
      }
      html += '</div>';
      html += '</div>';

      // Host bilgisi
      if (e.host_name) {
        html += '<div style="font-size:11px;color:var(--txt2);font-family:JetBrains Mono,monospace;margin-bottom:4px">';
        html += '\\ud83d\\udcbb ' + e.host_name;
        html += '</div>';
      }

      // BMC bilgisi
      html += bmcHtml;

      // LLM butonu
      html += '<div style="margin-top:10px;display:flex;justify-content:flex-end">';
      html += '<button class="btn btn-gh btn-sm" data-eid="' + e.id + '" onclick="zabbixLlmAnalizEt(this.dataset.eid, this)">\\ud83e\\udd16 LLM Analiz</button>';
      html += '</div>';

      // LLM sonuc alani
      html += '<div id="zb-llm-' + e.id + '" style="margin-top:8px"></div>';

      html += '</div></div>';
    });

    html += '</div>';
    el.innerHTML = html;

  } catch(e) {
    el.innerHTML = htaHtml(e.message);
  }
}"""

c = c[:start_idx] + NEW_LISTE + c[end_idx:]
print("OK: zabbixListeYukle yeniden yazildi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("girisYap:", "function girisYap" in c)
print("zabbixListeYukle:", "async function zabbixListeYukle" in c)
