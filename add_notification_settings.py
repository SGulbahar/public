#!/usr/bin/env python3
"""Frontend anomali ayarlari sayfasina bildirim bolumu ekle."""

path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# saveAnomSettings key listesine bildirim ayarlarini ekle
old_keys = "['min_tx_count','min_slow_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_p99_disaster','rule_elapsed_p95_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold']"
new_keys = "['min_tx_count','min_slow_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_p99_disaster','rule_elapsed_p95_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold','teams_webhook_url','smtp_host','smtp_port','smtp_user','smtp_password','smtp_from','smtp_to','notification_cooldown']"

if old_keys in content:
    content = content.replace(old_keys, new_keys)
    print('OK: saveAnomSettings key listesi guncellendi')
else:
    print('WARN: saveAnomSettings key listesi bulunamadi')

# Bildirim kartini anomali ayarlari sayfasina ekle
# Son karti bulduk - spike eslikleri kartinin sonuna ekle
old_card_end = (
    "ayarGirdisi('biz_error_code_threshold','\\u0130\\u015f Hatas\\u0131 Spike E\\u015fi\\u011fi',s['biz_error_code_threshold'],'30 dakikada bu kadar BIZ hata kodu g\\u00f6r\\u00fclmesi halinde anomali \\u00fcretilir')+"
    "\n      '</div>'+"
    "\n      '</div>'+"
)

new_card_end = (
    "ayarGirdisi('biz_error_code_threshold','\\u0130\\u015f Hatas\\u0131 Spike E\\u015fi\\u011fi',s['biz_error_code_threshold'],'30 dakikada bu kadar BIZ hata kodu g\\u00f6r\\u00fclmesi halinde anomali \\u00fcretilir')+"
    "\n      '</div>'+"
    "\n      '</div>'+"
    "\n      '<div class=\"iki-kolon\" style=\"margin-top:0\">'+\n"
    "      '<div class=\"kart\"><div class=\"kart-baslik\">Bildirim Ayarlar\\u0131</div>'+\n"
    "      toggleSatir('toggle-notification','Bildirim Sistemi',s['notification_enabled']==='true')+\n"
    "      '<div style=\"margin-bottom:12px\"><label style=\"font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600\">Minimum Bildirim D\\u00fczeyi</label>'+\n"
    "      '<select id=\"ayar-notification_min_severity\" class=\"form-girdi\">'+\n"
    "      '<option value=\"DISASTER\"'+(s['notification_min_severity']==='DISASTER'?' selected':'')+'>Yaln\\u0131zca Kritik</option>'+\n"
    "      '<option value=\"HIGH\"'+(s['notification_min_severity']==='HIGH'?' selected':'')+'>Y\\u00fcksek ve \\u00dczeri</option>'+\n"
    "      '<option value=\"WARNING\"'+(s['notification_min_severity']==='WARNING'?' selected':'')+'>Uyar\\u0131 ve \\u00dczeri</option>'+\n"
    "      '</select></div>'+\n"
    "      ayarGirdisi('notification_cooldown','Bildirim Bekleme S\\u00fcresi (sn)',s['notification_cooldown'],'Ayn\\u0131 anomali i\\u00e7in tekrar bildirim g\\u00f6ndermeden \\u00f6nce bekleme s\\u00fcresi')+\n"
    "      '</div>'+\n"
    "      '<div class=\"kart\"><div class=\"kart-baslik\">Microsoft Teams</div>'+\n"
    "      ayarGirdisi('teams_webhook_url','Webhook URL',s['teams_webhook_url'],'Teams kanal webhook adresi')+\n"
    "      '<button class=\"btn mavi\" style=\"margin-top:4px\" onclick=\"bildirimTest()\">Test G\\u00f6nder</button>'+\n"
    "      '</div></div>'+\n"
    "      '<div class=\"kart\" style=\"margin-bottom:16px\"><div class=\"kart-baslik\">E-Posta (SMTP)</div>'+\n"
    "      '<div style=\"display:grid;grid-template-columns:2fr 1fr;gap:10px\">'+\n"
    "      '<div>'+ayarGirdisi('smtp_host','SMTP Sunucusu',s['smtp_host'],'\\u00d6rnek: mail.sirket.com')+'</div>'+\n"
    "      '<div>'+ayarGirdisi('smtp_port','Port',s['smtp_port'],'587 (TLS) veya 465 (SSL)')+'</div>'+\n"
    "      '</div>'+\n"
    "      '<div style=\"display:grid;grid-template-columns:1fr 1fr;gap:10px\">'+\n"
    "      '<div>'+ayarGirdisi('smtp_user','Kullan\\u0131c\\u0131 Ad\\u0131',s['smtp_user'],'SMTP kullan\\u0131c\\u0131 ad\\u0131')+'</div>'+\n"
    "      '<div>'+ayarGirdisi('smtp_password','\\u015eifre',s['smtp_password'],'SMTP \\u015fifre')+'</div>'+\n"
    "      '</div>'+\n"
    "      ayarGirdisi('smtp_from','G\\u00f6nderen Adres',s['smtp_from'],'\\u00d6rnek: lumen@sirket.com')+\n"
    "      ayarGirdisi('smtp_to','Al\\u0131c\\u0131 Adresleri',s['smtp_to'],'Birden fazla adres i\\u00e7in virg\\u00fcl ile ay\\u0131r\\u0131n')+\n"
    "      '</div>'+"
)

if old_card_end in content:
    content = content.replace(old_card_end, new_card_end)
    print('OK: Bildirim kartlari eklendi')
else:
    print('WARN: Kart sonu bulunamadi')

# Bildirim toggle kaydini saveAnomSettings'e ekle
old_save = "var z=document.getElementById('toggle-zscore'); if(z) govde['zscore_enabled']=z.classList.contains('acik')?'true':'false';"
new_save = (
    "var z=document.getElementById('toggle-zscore'); if(z) govde['zscore_enabled']=z.classList.contains('acik')?'true':'false';\n"
    "    var notif=document.getElementById('toggle-notification'); if(notif) govde['notification_enabled']=notif.classList.contains('acik')?'true':'false';\n"
    "    var notifSev=document.getElementById('ayar-notification_min_severity'); if(notifSev) govde['notification_min_severity']=notifSev.value;"
)

if old_save in content:
    content = content.replace(old_save, new_save)
    print('OK: saveAnomSettings toggle guncellendi')
else:
    print('WARN: saveAnomSettings toggle bulunamadi')

# bildirimTest fonksiyonu ekle
test_js = """
async function bildirimTest() {
  try {
    // Once ayarlari kaydet
    await anomaliAyarlariKaydet();
    // Sonra test gonder
    var yanit = await fetch(window.location.origin.replace('8080','8001') + '/test-notification', {method:'POST'});
    if (yanit.ok) {
      bildirimGoster('Test bildirimi g\\u00f6nderildi! Teams ve e-postay\\u0131 kontrol edin.', 'basarili');
    } else {
      bildirimGoster('Test bildirimi g\\u00f6nderilemedi', 'hata');
    }
  } catch(e) {
    bildirimGoster('Hata: ' + e.message, 'hata');
  }
}
"""

if 'function bildirimTest' not in content:
    content = content.replace('function yukleniyorHtml()', test_js + '\nfunction yukleniyorHtml()')
    print('OK: bildirimTest fonksiyonu eklendi')
else:
    print('OK: bildirimTest zaten var')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
