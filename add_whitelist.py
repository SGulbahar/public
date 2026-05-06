#!/usr/bin/env python3
"""Frontend'e servis whitelist sayfasi ekle."""

path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Sidebar'a menu ogesi ekle
old_menu = "html += '<div class=\"menu-ogesi\" id=\"menu-denetim-kayitlari\" onclick=\"sayfaGoster(\\'denetim-kayitlari\\',this)\"><span class=\"menu-ikon\">&#128196;</span>Denetim Kay\\u0131tlar\\u0131</div>';"
new_menu = (
    "html += '<div class=\"menu-ogesi\" id=\"menu-denetim-kayitlari\" onclick=\"sayfaGoster(\\'denetim-kayitlari\\',this)\"><span class=\"menu-ikon\">&#128196;</span>Denetim Kay\\u0131tlar\\u0131</div>';\n"
    "    html += '<div class=\"menu-ogesi\" id=\"menu-whitelist\" onclick=\"sayfaGoster(\\'whitelist\\',this)\"><span class=\"menu-ikon\">&#128683;</span>Servis Muafiyetleri</div>';"
)

if old_menu in content:
    content = content.replace(old_menu, new_menu)
    print('OK: Menu eklendi')
else:
    print('WARN: Menu satiri bulunamadi')

# 2. SAYFA_ADLARI objesine ekle
old_names = "'denetim-kayitlari': 'Denetim Kay\\u0131tlar\\u0131'"
new_names = (
    "'denetim-kayitlari': 'Denetim Kay\\u0131tlar\\u0131',\n"
    "  'whitelist': 'Servis Muafiyetleri'"
)
if old_names in content:
    content = content.replace(old_names, new_names)
    print('OK: SAYFA_ADLARI guncellendi')
else:
    print('WARN: SAYFA_ADLARI bulunamadi')

# 3. sayfalarOlustur'a yeni sayfa div'i ekle
old_sayfalar = "'<div class=\"sayfa\" id=\"sayfa-denetim-kayitlari\"></div>';"
new_sayfalar = (
    "'<div class=\"sayfa\" id=\"sayfa-denetim-kayitlari\"></div>' +\n"
    "    '<div class=\"sayfa\" id=\"sayfa-whitelist\"></div>';"
)
if old_sayfalar in content:
    content = content.replace(old_sayfalar, new_sayfalar)
    print('OK: sayfalarOlustur guncellendi')
else:
    print('WARN: sayfalarOlustur bulunamadi')

# 4. yukleme map'ine ekle
old_yukle = "'denetim-kayitlari': denetimKayitlariYukle"
new_yukle = (
    "'denetim-kayitlari': denetimKayitlariYukle,\n"
    "    'whitelist': whitelistYukle"
)
if old_yukle in content:
    content = content.replace(old_yukle, new_yukle)
    print('OK: yukleme map guncellendi')
else:
    print('WARN: yukleme map bulunamadi')

# 5. Whitelist fonksiyonlarini ekle
whitelist_js = """
async function whitelistYukle() {
  var el = document.getElementById('sayfa-whitelist');
  var kurallar = [
    'elapsed_p99_disaster',
    'elapsed_p95_high',
    'sys_error_rate_disaster',
    'sys_error_rate_high',
    'biz_error_rate_disaster',
    'biz_error_rate_high',
    'sys_error_code_spike',
    'biz_error_code_spike',
    'service_down',
    '*'
  ];
  var kuralSecenekleri = kurallar.map(function(k) {
    return '<option value="' + k + '">' + k + '</option>';
  }).join('');

  el.innerHTML =
    '<div class="sayfa-ust"><div>' +
    '<div class="sayfa-baslik">Servis Muafiyetleri</div>' +
    '<div class="sayfa-aciklama">Belirli servis ve kanal kombinasyonlar\\u0131n\\u0131 anomali tespitinden muaf tut</div>' +
    '</div></div>' +
    '<div class="kart" style="margin-bottom:16px"><div class="kart-baslik">Yeni Muafiyet Kural\\u0131 Ekle</div>' +
    '<div style="display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:10px;align-items:end">' +
    '<div><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">Servis Ad\\u0131</label>' +
    '<input id="wl-servis" class="form-girdi" placeholder="ORNEK_SERVIS_ADI (veya * t\\u00fcm servisler)"/></div>' +
    '<div><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">Kanal Kodu</label>' +
    '<input id="wl-kanal" class="form-girdi" placeholder="708 (veya * t\\u00fcm kanallar)" value="*"/></div>' +
    '<div><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">Kural</label>' +
    '<select id="wl-kural" class="form-girdi">' + kuralSecenekleri + '</select></div>' +
    '<div><button class="btn yesil" onclick="whitelistKaydet()">Ekle</button></div>' +
    '</div>' +
    '<div style="margin-top:10px"><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">A\\u00e7\\u0131klama (Opsiyonel)</label>' +
    '<input id="wl-aciklama" class="form-girdi" placeholder="\\u00d6rnek: Bu servis do\\u011fas\\u0131 gere\\u011fi yava\\u015f, gecikme alarmi gereksiz..."/></div>' +
    '<div style="margin-top:10px;padding:10px;background:rgba(37,99,235,.05);border:1px solid rgba(37,99,235,.15);border-radius:8px;font-size:10px;color:var(--txt2)">' +
    '<strong>Wildcard kullan\\u0131m\\u0131:</strong> Kanal = * (t\\u00fcm kanallar), Kural = * (t\\u00fcm kurallar), Servis = * (t\\u00fcm servisler)' +
    '</div>' +
    '</div>' +
    '<div id="wl-liste">' + yukleniyorHtml() + '</div>';
  await whitelistListesiYukle();
}

async function whitelistListesiYukle() {
  try {
    var liste = await apiFetch('/api/v1/whitelist');
    var html = '<div class="kart"><div class="kart-baslik">Aktif Muafiyet Kurallar\\u0131 (' + liste.length + ' adet)</div>';
    if (liste.length === 0) {
      html += bosEkranHtml('Hen\\u00fcz muafiyet kural\\u0131 tan\\u0131mlanmam\\u0131\\u015f');
    } else {
      html += '<table class="tablo"><thead><tr>' +
        '<th>Servis</th><th>Kanal</th><th>Kural</th><th>Sebep</th><th>Ekleyen</th><th>Tarih</th><th>\\u0130\\u015flem</th>' +
        '</tr></thead><tbody>';
      liste.forEach(function(w) {
        html += '<tr>' +
          '<td style="font-weight:700;color:var(--acc)">' + w.service_name + '</td>' +
          '<td>' + (w.channel_code === '*' ? '<span class="etiket et-gri">T\\u00fcm Kanallar</span>' : w.channel_code) + '</td>' +
          '<td>' + (w.rule_name === '*' ? '<span class="etiket et-gri">T\\u00fcm Kurallar</span>' : '<span class="etiket et-turuncu">' + w.rule_name + '</span>') + '</td>' +
          '<td style="max-width:200px;white-space:normal;color:var(--txt2)">' + (w.reason || '-') + '</td>' +
          '<td style="color:var(--txt2)">' + (w.created_by || '-') + '</td>' +
          '<td>' + (w.created_at ? new Date(w.created_at).toLocaleString('tr-TR', {timeZone:'Europe/Istanbul'}) : '-') + '</td>' +
          '<td><button class="btn kirmizi" style="padding:2px 8px;font-size:9px" ' +
          'onclick="whitelistSil(\\'' + w.service_name + '\\',\\'' + w.channel_code + '\\',\\'' + w.rule_name + '\\')">Kald\\u0131r</button></td>' +
          '</tr>';
      });
      html += '</tbody></table>';
    }
    html += '</div>';
    document.getElementById('wl-liste').innerHTML = html;
  } catch(e) {
    document.getElementById('wl-liste').innerHTML = hataHtml(e.message);
  }
}

async function whitelistKaydet() {
  var servis = document.getElementById('wl-servis').value.trim();
  var kanal = document.getElementById('wl-kanal').value.trim() || '*';
  var kural = document.getElementById('wl-kural').value;
  var aciklama = document.getElementById('wl-aciklama').value.trim();
  if (!servis) { bildirimGoster('Servis ad\\u0131 zorunludur', 'uyari'); return; }
  try {
    await apiFetch('/api/v1/whitelist', {
      method: 'POST',
      body: JSON.stringify({service_name: servis, channel_code: kanal, rule_name: kural, reason: aciklama || null})
    });
    bildirimGoster('Muafiyet kural\\u0131 eklendi: ' + servis + ' / ' + kanal + ' / ' + kural, 'basarili');
    document.getElementById('wl-servis').value = '';
    document.getElementById('wl-kanal').value = '*';
    document.getElementById('wl-aciklama').value = '';
    await whitelistListesiYukle();
  } catch(e) { bildirimGoster('Hata: ' + e.message, 'hata'); }
}

async function whitelistSil(servis, kanal, kural) {
  if (!confirm(servis + ' / ' + kanal + ' / ' + kural + ' kural\\u0131 kald\\u0131r\\u0131lacak. Onayl\\u0131yor musunuz?')) return;
  try {
    await apiFetch('/api/v1/whitelist/' + encodeURIComponent(servis) + '/' + encodeURIComponent(kanal) + '/' + encodeURIComponent(kural), {method: 'DELETE'});
    bildirimGoster('Muafiyet kural\\u0131 kald\\u0131r\\u0131ld\\u0131', 'uyari');
    await whitelistListesiYukle();
  } catch(e) { bildirimGoster('Hata: ' + e.message, 'hata'); }
}
"""

if 'function whitelistYukle' not in content:
    content = content.replace('function yukleniyorHtml()', whitelist_js + '\nfunction yukleniyorHtml()')
    print('OK: Whitelist fonksiyonlari eklendi')
else:
    print('Whitelist fonksiyonlari zaten var')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
