#!/usr/bin/env python3
"""
Frontend index.html'e acknowledge ozelligi ekler.
Kullanim: python3 update_frontend.py
"""
import sys

path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. anomaliesHtml fonksiyonuna acknowledge butonu ekle
old_zabbix = "(a.zabbix_sent ? '<span class=\"tag t-g\">Zabbix</span>' : '<span class=\"tag t-y\">Bekliyor</span>') +"
new_zabbix = (
    "(a.zabbix_sent ? '<span class=\"tag t-g\">Zabbix</span>' : '<span class=\"tag t-y\">Bekliyor</span>') +\n"
    "        (a.acknowledged ? '<span class=\"tag t-g\" style=\"margin-left:4px\">Onaylandi: ' + (a.acknowledged_by||'') + '</span>' : "
    "'<button class=\"btn\" style=\"padding:2px 8px;font-size:9px;margin-left:4px\" onclick=\"event.stopPropagation();ackAnomaly(' + a.id + ')\">Onayla</button>') +"
)

if old_zabbix in content:
    content = content.replace(old_zabbix, new_zabbix)
    print('OK: anomaliesHtml acknowledge butonu eklendi')
else:
    print('WARN: anomaliesHtml Zabbix satiri bulunamadi')

# 2. openAnomModal fonksiyonuna acknowledge bilgisi ekle
old_modal = "'<div class=\"dr\"><div class=\"dk\">Zabbix:</div>"
new_modal = (
    "'<div class=\"dr\"><div class=\"dk\">Onay Durumu:</div><div class=\"dv\">' + "
    "(a.acknowledged ? 'Onaylandi - ' + (a.acknowledged_by||'') + ' / ' + (a.acknowledged_at ? new Date(a.acknowledged_at).toLocaleString('tr-TR', {timeZone: 'Europe/Istanbul'}) : '') : 'Onaylanmadi') + "
    "'</div></div>' +\n      "
    "'<div class=\"dr\"><div class=\"dk\">Zabbix:</div>"
)

if old_modal in content:
    content = content.replace(old_modal, new_modal)
    print('OK: openAnomModal acknowledge bilgisi eklendi')
else:
    print('WARN: openAnomModal Zabbix satiri bulunamadi')

# 3. Modal icine acknowledge butonu ekle
old_close_btn = "isSRE() ? '<button class=\"btn g\" onclick=\"closeModal();toast"
new_close_btn = (
    "!a.acknowledged && hasPerm('log.anomalies.ack') ? "
    "'<button class=\"btn p\" style=\"margin-right:8px\" onclick=\"ackAnomaly(' + a.id + ');closeModal()\">Onayla</button>' : '' +"
    "\n      " + old_close_btn
)

if old_close_btn in content:
    content = content.replace(old_close_btn, new_close_btn)
    print('OK: Modal acknowledge butonu eklendi')
else:
    print('WARN: Modal buton satiri bulunamadi')

# 4. ackAnomaly fonksiyonunu ekle
ack_func = """
async function ackAnomaly(id) {
  try {
    await apiFetch('/api/v1/anomalies/' + id + '/acknowledge', {method: 'POST'});
    toast('Anomali onaylandi', 's');
    var ap = document.querySelector('.page.active');
    if (ap && ap.id === 'page-anomalies') loadAnomalies('all');
    if (ap && ap.id === 'page-dashboard') loadDashboard();
  } catch(e) {
    toast('Hata: ' + e.message, 'e');
  }
}
"""

if 'ackAnomaly' not in content:
    content = content.replace('function toast(msg, type) {', ack_func + '\nfunction toast(msg, type) {')
    print('OK: ackAnomaly fonksiyonu eklendi')
else:
    print('OK: ackAnomaly zaten var')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi: ' + path)
