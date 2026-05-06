#!/usr/bin/env python3
"""Frontend anomali ayarlari sayfasina bildirim bolumu ekle."""

path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. saveAnomSettings key listesine bildirim ayarlarini ekle
old_keys = "['min_tx_count','min_slow_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_p99_disaster','rule_elapsed_p95_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold']"
new_keys = "['min_tx_count','min_slow_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_p99_disaster','rule_elapsed_p95_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold','teams_webhook_url','smtp_host','smtp_port','smtp_user','smtp_password','smtp_from','smtp_to','notification_cooldown']"

if old_keys in content:
    content = content.replace(old_keys, new_keys)
    print('OK: saveAnomSettings key listesi guncellendi')
else:
    print('WARN: Key listesi bulunamadi')

# 2. Bildirim toggle kaydini ekle
old_save = "var z=document.getElementById('toggle-zscore'); if(z) govde['zscore_enabled']=z.classList.contains('acik')?'true':'false';"
new_save = (
    "var z=document.getElementById('toggle-zscore'); if(z) govde['zscore_enabled']=z.classList.contains('acik')?'true':'false';\n"
    "    var notif=document.getElementById('toggle-notification'); if(notif) govde['notification_enabled']=notif.classList.contains('acik')?'true':'false';\n"
    "    var nSev=document.getElementById('ayar-notification_min_severity'); if(nSev) govde['notification_min_severity']=nSev.value;"
)
if old_save in content:
    content = content.replace(old_save, new_save)
    print('OK: Bildirim toggle kaydi eklendi')
else:
    print('WARN: Toggle kaydi bulunamadi')

# 3. Son karttan sonra bildirim kartlarini ekle
old_end = (
    "      '</div>'+\n"
    "      '<div style=\"margin-top:12px;padding:10px 14px;background:rgba(202,138,4,.06);"
)
new_end = (
    "      '</div>'+\n"
    "      '<div class=\"iki-kolon\" style=\"margin-top:0\">'+\n"
    "      '<div class=\"kart\"><div class=\"kart-baslik\">Bildirim Ayarlar\\u0131</div>'+\n"
    "      toggleSatir('toggle-notification','Bildirim Sistemi',s['notification_enabled']==='true')+\n"
    "      '<div style=\"margin-bottom:12px\"><label style=\"font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600\">Minimum Bildirim D\\u00fczeyi</label>'+\n"
    "      '<select id=\"ayar-notification_min_severity\" class=\"form-girdi\">'+\n"
    "      '<option value=\"DISASTER\"'+(s['notification_min_severity']==='DISASTER'?' selected':'')+'>Yaln\\u0131zca Kritik</option>'+\n"
    "      '<option value=\"HIGH\"'+(s['notification_min_severity']==='HIGH'?' selected':'')+'>Y\\u00fcksek ve \\u00dczeri</option>'+\n"
    "      '<option value=\"WARNING\"'+(s['notification_min_severity']==='WARNING'?' selected':'')+'>Uyar\\u0131 ve \\u00dczeri</option>'+\n"
    "      '</select></div>'+\n"
    "      ayarGirdisi('notification_cooldown','Bildirim Bekleme S\\u00fcresi (sn)',s['notification_cooldown'],'Ayn\\u0131 anomali i\\u00e7in tekrar bildirim aralar\\u0131')+\n"
    "      '</div>'+\n"
    "      '<div class=\"kart\"><div class=\"kart-baslik\">Microsoft Teams</div>'+\n"
    "      ayarGirdisi('teams_webhook_url','Webhook URL',s['teams_webhook_url'],'Teams kanal webhook adresi')+\n"
    "      '<button class=\"btn mavi\" style=\"margin-top:4px\" onclick=\"bildirimTest(\\'teams\\')\">Teams Test G\\u00f6nder</button>'+\n"
    "      '</div></div>'+\n"
    "      '<div class=\"kart\" style=\"margin-bottom:16px\"><div class=\"kart-baslik\">E-Posta (SMTP)</div>'+\n"
    "      '<div style=\"display:grid;grid-template-columns:2fr 1fr;gap:10px\">'+\n"
    "      '<div>'+ayarGirdisi('smtp_host','SMTP Sunucusu',s['smtp_host'],'\\u00d6rnek: mail.sirket.com')+'</div>'+\n"
    "      '<div>'+ayarGirdisi('smtp_port','Port',s['smtp_port'],'587 veya 465')+'</div>'+\n"
    "      '</div>'+\n"
    "      '<div style=\"display:grid;grid-template-columns:1fr 1fr;gap:10px\">'+\n"
    "      '<div>'+ayarGirdisi('smtp_user','Kullan\\u0131c\\u0131 Ad\\u0131',s['smtp_user'],'SMTP kullan\\u0131c\\u0131 ad\\u0131')+'</div>'+\n"
    "      '<div>'+ayarGirdisi('smtp_password','\\u015eifre',s['smtp_password'],'SMTP \\u015fifre')+'</div>'+\n"
    "      '</div>'+\n"
    "      ayarGirdisi('smtp_from','G\\u00f6nderen Adres',s['smtp_from'],'\\u00d6rnek: lumen@sirket.com')+\n"
    "      ayarGirdisi('smtp_to','Al\\u0131c\\u0131 Adresleri',s['smtp_to'],'Birden fazla adres virg\\u00fcl ile ay\\u0131r\\u0131n')+\n"
    "      '<button class=\"btn mavi\" style=\"margin-top:4px\" onclick=\"bildirimTest(\\'email\\')\">E-posta Test G\\u00f6nder</button>'+\n"
    "      '</div>'+\n"
    "      '<div style=\"margin-top:12px;padding:10px 14px;background:rgba(202,138,4,.06);"
)

if old_end in content:
    content = content.replace(old_end, new_end)
    print('OK: Bildirim kartlari eklendi')
else:
    print('WARN: Kart sonu bulunamadi')

# 4. bildirimTest fonksiyonu ekle
test_js = """
var _bildirimTestEngineUrl = '';

async function bildirimTest(kanal) {
  kanal = kanal || 'hepsi';
  try {
    // Once ayarlari kaydet
    await anomaliAyarlariKaydet();
    await new Promise(function(r){setTimeout(r,1000);});
    // Engine URL'i bul
    var engineUrl = window.location.origin.replace(':8080','').replace(':443','').replace(':80','') + ':8001';
    var yanit = await fetch(engineUrl + '/test-notification?kanal=' + kanal, {method:'POST'});
    var veri = await yanit.json();
    if (veri.status === 'ok') {
      if (kanal === 'teams') {
        bildirimGoster('Teams test bildirimi g\u00f6nderildi! Kanal\u0131 kontrol edin.', 'basarili');
      } else if (kanal === 'email') {
        bildirimGoster('E-posta test bildirimi g\u00f6nderildi! Gelen kutusu\u0131 kontrol edin. Al\u0131c\u0131lar: ' + (veri.alicilar||[]).join(', '), 'basarili');
      } else {
        bildirimGoster('Test bildirimleri g\u00f6nderildi!', 'basarili');
      }
    } else {
      bildirimGoster('Test ba\u015far\u0131s\u0131z: ' + (veri.message || 'Bilinmeyen hata'), 'hata');
    }
  } catch(e) {
    bildirimGoster('Ba\u011flant\u0131 hatas\u0131: Engine\'e ula\u015f\u0131lamad\u0131. ' + e.message, 'hata');
  }
}
"""

if 'function bildirimTest' not in content:
    content = content.replace('function yukleniyorHtml()', test_js + '\nfunction yukleniyorHtml()')
    print('OK: bildirimTest fonksiyonu eklendi')
else:
    # Mevcut fonksiyonu guncelle
    import re
    content = re.sub(
        r'async function bildirimTest\(.*?\{.*?\}',
        test_js.strip(),
        content,
        flags=re.DOTALL
    )
    print('OK: bildirimTest guncellendi')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
