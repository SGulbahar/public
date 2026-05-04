#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. anomaliesHtml'e FP badge ekle
old_ack = "(a.acknowledged ? '<span class=\"tag t-g\" style=\"margin-left:4px\">Onaylandi: ' + (a.acknowledged_by||'') + '</span>' : '<button class=\"btn\" style=\"padding:2px 8px;font-size:9px;margin-left:4px\" onclick=\"event.stopPropagation();ackAnomaly(' + a.id + ')\">Onayla</button>') +"
new_ack = (
    "(a.is_false_positive ? '<span class=\"tag t-r\" style=\"margin-left:4px\">FP: ' + (a.false_positive_by||'') + '</span>' : "
    "a.acknowledged ? '<span class=\"tag t-g\" style=\"margin-left:4px\">Onaylandi: ' + (a.acknowledged_by||'') + '</span>' : "
    "'<button class=\"btn\" style=\"padding:2px 8px;font-size:9px;margin-left:4px\" onclick=\"event.stopPropagation();ackAnomaly(' + a.id + ')\">Onayla</button>') +"
)

if old_ack in content:
    content = content.replace(old_ack, new_ack)
    print('OK: anomaliesHtml FP badge eklendi')
else:
    print('WARN: anomaliesHtml ack satiri bulunamadi')

# 2. Modal'daki onay durumu satirina FP bilgisi ekle
old_modal_ack = "'<div class=\"dr\"><div class=\"dk\">Onay Durumu:</div><div class=\"dv\">' + (a.acknowledged ? 'Onaylandi - ' + (a.acknowledged_by||'') + ' - ' + (a.acknowledged_at ? new Date(a.acknowledged_at).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'}) : '') : 'Onaylanmadi') + '</div></div>' +"
new_modal_ack = (
    "'<div class=\"dr\"><div class=\"dk\">Onay Durumu:</div><div class=\"dv\">' + "
    "(a.is_false_positive ? 'FALSE POSITIVE - ' + (a.false_positive_by||'') + (a.false_positive_reason ? ' - ' + a.false_positive_reason : '') : "
    "a.acknowledged ? 'Onaylandi - ' + (a.acknowledged_by||'') + ' - ' + (a.acknowledged_at ? new Date(a.acknowledged_at).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'}) : '') : 'Onaylanmadi') + "
    "'</div></div>' +"
)

if old_modal_ack in content:
    content = content.replace(old_modal_ack, new_modal_ack)
    print('OK: Modal onay durumu guncellendi')
else:
    print('WARN: Modal onay satiri bulunamadi')

# 3. Modal butonlarina FP butonu ekle
old_btn = "(!a.acknowledged && hasPerm('log.anomalies.ack') ? '<button class=\"btn p\" onclick=\"ackAnomaly(' + a.id + ');closeModal()\">Onayla</button>' : '') +"
new_btn = (
    "(!a.is_false_positive && !a.acknowledged && hasPerm('log.anomalies.ack') ? '<button class=\"btn p\" onclick=\"ackAnomaly(' + a.id + ');closeModal()\">Onayla</button>' : '') +"
    "\n      (!a.is_false_positive && hasPerm('log.anomalies.ack') ? '<button class=\"btn r\" style=\"margin-right:4px\" onclick=\"openFPModal(' + a.id + ')\">False Positive</button>' : '') +"
)

if old_btn in content:
    content = content.replace(old_btn, new_btn)
    print('OK: Modal FP butonu eklendi')
else:
    print('WARN: Modal buton satiri bulunamadi')

# 4. FP Modal HTML ekle - toast-wrap'tan once
fp_modal = '''
<div class="overlay" id="fp-overlay" onclick="if(event.target===this)closeFPModal()">
  <div class="modal" style="width:440px">
    <div class="mh">
      <div><div style="font-size:17px;font-weight:800;color:var(--red)">False Positive Bildir</div></div>
      <button class="mclose" onclick="closeFPModal()">X</button>
    </div>
    <div class="mb">
      <div style="font-size:12px;color:var(--txt2);margin-bottom:14px">Bu anomali yanlis tespit edilmis olarak isaretlenecek.</div>
      <label class="l-lbl">Sebep (Opsiyonel)</label>
      <textarea id="fp-reason" style="width:100%;padding:10px;border-radius:9px;border:1px solid rgba(180,200,240,.5);background:rgba(255,255,255,.75);font-size:12px;color:var(--txt);outline:none;resize:vertical;min-height:80px;font-family:var(--font)" placeholder="Ornek: Esik cok dusuk, bu servis icin normal deger..."></textarea>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn r" onclick="submitFP()">False Positive Onayla</button>
        <button class="btn" onclick="closeFPModal()">Iptal</button>
      </div>
    </div>
  </div>
</div>
'''

if 'fp-overlay' not in content:
    content = content.replace('<div class="toast-wrap" id="toast-wrap"></div>', fp_modal + '\n<div class="toast-wrap" id="toast-wrap"></div>')
    print('OK: FP modal HTML eklendi')
else:
    print('OK: FP modal zaten var')

# 5. FP JS fonksiyonlari ekle
fp_js = '''
var _fpAnomalyId = null;

function openFPModal(id) {
  _fpAnomalyId = id;
  document.getElementById('fp-reason').value = '';
  document.getElementById('fp-overlay').classList.add('open');
  closeModal();
}

function closeFPModal() {
  document.getElementById('fp-overlay').classList.remove('open');
  _fpAnomalyId = null;
}

async function submitFP() {
  if (!_fpAnomalyId) return;
  var reason = document.getElementById('fp-reason').value.trim();
  try {
    await apiFetch('/api/v1/anomalies/' + _fpAnomalyId + '/false-positive', {
      method: 'POST',
      body: JSON.stringify({reason: reason || null})
    });
    closeFPModal();
    toast('False positive olarak isaretlendi', 'w');
    var ap = document.querySelector('.page.active');
    if (ap && ap.id === 'page-anomalies') loadAnomalies('all');
    if (ap && ap.id === 'page-dashboard') loadDashboard();
  } catch(e) { toast('Hata: ' + e.message, 'e'); }
}
'''

if 'submitFP' not in content:
    content = content.replace('function toast(msg, type) {', fp_js + '\nfunction toast(msg, type) {')
    print('OK: FP fonksiyonlari eklendi')
else:
    print('OK: FP fonksiyonlari zaten var')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
