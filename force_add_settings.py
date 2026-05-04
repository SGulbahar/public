#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Kontrol
if 'async function loadAnomSettings' in content:
    print('Fonksiyon zaten var - silip tekrar ekleyecegiz')
    # Eski referansi temizle (sadece loadAnomSettings kelimesini degil, fonksiyonu bul ve sil)
    import re
    content = re.sub(
        r'async function loadAnomSettings\(\).*?^}',
        '',
        content,
        flags=re.DOTALL | re.MULTILINE
    )
    print('Eski fonksiyon silindi')

func = '''
async function loadAnomSettings() {
  var el = document.getElementById('page-anomsettings');
  if (!el) { console.error('page-anomsettings bulunamadi'); return; }
  el.innerHTML = '<div class="phead"><div><div class="pt">Anomali Ayarlari</div><div class="ps">Motor konfigurasyonu</div></div><div class="pactions"><button class="btn p" id="save-settings-btn" onclick="saveAnomSettings()">Kaydet</button></div></div><div id="anom-settings-content">' + loadingHtml() + '</div>';
  try {
    var settings = await apiFetch('/api/v1/settings');
    var s = {};
    settings.forEach(function(item) { s[item.key] = item.value; });
    document.getElementById('anom-settings-content').innerHTML =
      '<div class="g2">' +
      '<div class="card"><div class="ctitle">Model Ayarlari</div>' +
      '<div class="pr" style="margin-bottom:14px"><div class="pl" style="font-size:12px;font-weight:600">Z-Score Motoru</div><button id="toggle-zscore" class="toggle ' + (s.zscore_enabled==="true"?"on":"off") + '" onclick="toggleSetting(\'zscore_enabled\',this)"></button><span style="font-size:10px;color:var(--txt2);margin-left:8px">' + (s.zscore_enabled==="true"?"Aktif":"Pasif") + '</span></div>' +
      '<div class="pr" style="margin-bottom:14px"><div class="pl" style="font-size:12px;font-weight:600">Isolation Forest</div><button id="toggle-if" class="toggle ' + (s.if_enabled==="true"?"on":"off") + '" onclick="toggleSetting(\'if_enabled\',this)"></button><span style="font-size:10px;color:var(--txt2);margin-left:8px">' + (s.if_enabled==="true"?"Aktif":"Pasif") + '</span></div>' +
      '</div>' +
      '<div class="card"><div class="ctitle">Genel Ayarlar</div>' +
      settingInput("min_tx_count","Min. Islem Sayisi",s.min_tx_count,"Anomali icin minimum TX") +
      settingInput("cooldown_seconds","Cooldown (sn)",s.cooldown_seconds,"Ayni anomali icin bekleme") +
      settingInput("sliding_window_seconds","Sliding Window (sn)",s.sliding_window_seconds,"Hata kodu penceresi") +
      '</div>' +
      '<div class="card"><div class="ctitle">Elapsed Esikleri (ms)</div>' +
      settingInput("rule_elapsed_disaster","DISASTER Esigi (ms)",s.rule_elapsed_disaster,"Kritik gecikme") +
      settingInput("rule_elapsed_high","HIGH Esigi (ms)",s.rule_elapsed_high,"Yuksek gecikme") +
      '</div>' +
      '<div class="card"><div class="ctitle">Hata Orani Esikleri</div>' +
      settingInput("rule_error_rate_disaster","DISASTER Esigi (0-1)",s.rule_error_rate_disaster,"0.50 = %50") +
      settingInput("rule_error_rate_high","HIGH Esigi (0-1)",s.rule_error_rate_high,"0.30 = %30") +
      '</div>' +
      '<div class="card"><div class="ctitle">Hata Kodu Spike Esikleri</div>' +
      settingInput("sys_error_code_threshold","SYS Spike Esigi",s.sys_error_code_threshold,"SYS kac kez anomali") +
      settingInput("biz_error_code_threshold","BIZ Spike Esigi",s.biz_error_code_threshold,"BIZ kac kez anomali") +
      '</div>' +
      '</div>';
  } catch(e) { document.getElementById('anom-settings-content').innerHTML = errorHtml(e.message); }
}

function settingInput(key, label, value, hint) {
  return '<div style="margin-bottom:12px"><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">' + label + '</label><input id="setting-' + key + '" value="' + (value||'') + '" style="width:100%;padding:7px 10px;border-radius:7px;border:1px solid rgba(180,200,240,.5);background:rgba(255,255,255,.75);font-size:12px;color:var(--txt);outline:none" /><div style="font-size:9px;color:var(--txt3);margin-top:2px">' + hint + '</div></div>';
}

function toggleSetting(key, btn) {
  btn.classList.toggle('on');
  btn.classList.toggle('off');
  var span = btn.nextElementSibling;
  if (span) span.textContent = btn.classList.contains('on') ? 'Aktif' : 'Pasif';
}

async function saveAnomSettings() {
  var btn = document.getElementById('save-settings-btn');
  btn.disabled = true;
  btn.textContent = 'Kaydediliyor...';
  try {
    var body = {};
    var zscore = document.getElementById('toggle-zscore');
    if (zscore) body['zscore_enabled'] = zscore.classList.contains('on') ? 'true' : 'false';
    var ifToggle = document.getElementById('toggle-if');
    if (ifToggle) body['if_enabled'] = ifToggle.classList.contains('on') ? 'true' : 'false';
    ['min_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_disaster','rule_elapsed_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold'].forEach(function(k) {
      var el = document.getElementById('setting-' + k);
      if (el) body[k] = el.value.trim();
    });
    await apiFetch('/api/v1/settings', {method: 'POST', body: JSON.stringify(body)});
    toast('Ayarlar kaydedildi', 's');
  } catch(e) { toast('Hata: ' + e.message, 'e'); }
  btn.disabled = false;
  btn.textContent = 'Kaydet';
}
'''

# Toast fonksiyonundan once ekle
if 'function toast(msg, type) {' in content:
    content = content.replace('function toast(msg, type) {', func + '\nfunction toast(msg, type) {')
    print('OK: Fonksiyonlar eklendi')
else:
    print('WARN: toast fonksiyonu bulunamadi')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
