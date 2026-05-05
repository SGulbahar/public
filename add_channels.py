#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Sidebar'a Kanal Tanimlari menusu ekle
old_sidebar = "html += '<div class=\"ni\" id=\"nav-anomsettings\" onclick=\"showPage(\\'anomsettings\\',this)\"><span class=\"ni-icon\">&#9881;</span>Anomali Ayarlari</div>';"
new_sidebar = (
    "html += '<div class=\"ni\" id=\"nav-anomsettings\" onclick=\"showPage(\\'anomsettings\\',this)\"><span class=\"ni-icon\">&#9881;</span>Anomali Ayarlari</div>';\n"
    "    html += '<div class=\"ni\" id=\"nav-channels\" onclick=\"showPage(\\'channels\\',this)\"><span class=\"ni-icon\">&#128279;</span>Kanal Tanimlari</div>';"
)

if old_sidebar in content:
    content = content.replace(old_sidebar, new_sidebar)
    print('OK: Sidebar kanal menusu eklendi')
else:
    print('WARN: Sidebar admin bolumu bulunamadi')

# 2. buildPages'e yeni sayfa ekle
old_pages = "'<div class=\"page\" id=\"page-anomsettings\"></div>' +"
new_pages = (
    "'<div class=\"page\" id=\"page-anomsettings\"></div>' +\n"
    "    '<div class=\"page\" id=\"page-channels\"></div>' +"
)

if old_pages in content:
    content = content.replace(old_pages, new_pages)
    print('OK: buildPages guncellendi')
else:
    print('WARN: buildPages bulunamadi')

# 3. showPage loaders ve names guncelle
old_loaders = "var loaders = {dashboard:loadDashboard, anomalies:function(){loadAnomalies('all');}, errorcodes:loadErrorCodes, runs:loadRuns, sre:loadSRE, anomsettings:loadAnomSettings, settings:loadSettings};"
new_loaders = "var loaders = {dashboard:loadDashboard, anomalies:function(){loadAnomalies('all');}, errorcodes:loadErrorCodes, runs:loadRuns, sre:loadSRE, anomsettings:loadAnomSettings, channels:loadChannels, settings:loadSettings};"

if old_loaders in content:
    content = content.replace(old_loaders, new_loaders)
    print('OK: Loaders guncellendi')
else:
    print('WARN: Loaders bulunamadi')

old_names = "var names = {dashboard:'Dashboard',anomalies:'Anomaliler',errorcodes:'Hata Kodlari',runs:'Detection Runs',sre:'SRE Agent',anomsettings:'Anomali Ayarlari',settings:'Sistem Ayarlari'};"
new_names = "var names = {dashboard:'Dashboard',anomalies:'Anomaliler',errorcodes:'Hata Kodlari',runs:'Detection Runs',sre:'SRE Agent',anomsettings:'Anomali Ayarlari',channels:'Kanal Tanimlari',settings:'Sistem Ayarlari'};"

if old_names in content:
    content = content.replace(old_names, new_names)
    print('OK: Names guncellendi')
else:
    print('WARN: Names bulunamadi')

# 4. anomaliesHtml'de channel_code yerine channel_name goster
old_ch = "'<div class=\"aname\">' + (a.service||'-') + ' [' + (a.channel_code||'-') + ']</div>' +"
new_ch = "'<div class=\"aname\">' + (a.service||'-') + ' [' + (a.channel_name||a.channel_code||'-') + ']</div>' +"

if old_ch in content:
    content = content.replace(old_ch, new_ch)
    print('OK: anomaliesHtml kanal ismi guncellendi')
else:
    print('WARN: anomaliesHtml aname satiri bulunamadi')

# 5. Modal basliginda da kanal ismi goster
old_modal_title = "document.getElementById('m-title').textContent = (a.service||'-') + ' [' + (a.channel_code||'-') + ']';"
new_modal_title = "document.getElementById('m-title').textContent = (a.service||'-') + ' [' + (a.channel_name||a.channel_code||'-') + ']';"

if old_modal_title in content:
    content = content.replace(old_modal_title, new_modal_title)
    print('OK: Modal baslik guncellendi')
else:
    print('WARN: Modal baslik bulunamadi')

# 6. Modal iceriginde kanal kodu + isim goster
old_modal_ch = "'<div class=\"dr\"><div class=\"dk\">Kanal:</div><div class=\"dv\">' + (a.channel_code||'-') + '</div></div>' +"
new_modal_ch = "'<div class=\"dr\"><div class=\"dk\">Kanal:</div><div class=\"dv\">' + (a.channel_name||a.channel_code||'-') + (a.channel_name && a.channel_name !== a.channel_code ? ' (' + a.channel_code + ')' : '') + '</div></div>' +"

if old_modal_ch in content:
    content = content.replace(old_modal_ch, new_modal_ch)
    print('OK: Modal kanal satiri guncellendi')
else:
    print('WARN: Modal kanal satiri bulunamadi')

# 7. loadChannels ve yardimci fonksiyonlar ekle
channels_js = '''
async function loadChannels() {
  var el = document.getElementById('page-channels');
  el.innerHTML = '<div class="phead"><div><div class="pt">Kanal Tanimlari</div><div class="ps">Kanal kodu - isim eslestirmesi</div></div></div>' +
    '<div class="card" style="margin-bottom:16px"><div class="ctitle">Yeni Kanal Ekle / Guncelle</div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr 2fr auto;gap:10px;align-items:end">' +
    '<div><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">Kanal Kodu</label><input id="ch-code" class="sinput" placeholder="708"/></div>' +
    '<div><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">Kanal Adi</label><input id="ch-name" class="sinput" placeholder="Gorumez Bankacilik"/></div>' +
    '<div><label style="font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600">Aciklama (Opsiyonel)</label><input id="ch-desc" class="sinput" placeholder="Aciklama..."/></div>' +
    '<div><button class="btn g" onclick="saveChannel()">Kaydet</button></div>' +
    '</div></div>' +
    '<div id="ch-list">' + loadingHtml() + '</div>';
  await loadChannelList();
}

async function loadChannelList() {
  try {
    var channels = await apiFetch('/api/v1/channel-mappings');
    var html = '<div class="card"><div class="ctitle">Tanimli Kanallar (' + channels.length + ')</div>' +
      '<div style="overflow:auto;max-height:500px"><table class="tbl"><thead><tr><th>Kod</th><th>Kanal Adi</th><th>Aciklama</th><th>Guncelleme</th><th>Islem</th></tr></thead><tbody>';
    channels.forEach(function(c) {
      html += '<tr>' +
        '<td style="font-weight:700;color:var(--acc)">' + c.channel_code + '</td>' +
        '<td style="font-weight:600">' + c.channel_name + '</td>' +
        '<td style="color:var(--txt2)">' + (c.description||'-') + '</td>' +
        '<td>' + (c.updated_at ? new Date(c.updated_at).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'}) : '-') + '</td>' +
        '<td><button class="btn r" style="padding:2px 8px;font-size:9px" onclick="deleteChannel(\'' + c.channel_code + '\')">Sil</button></td>' +
        '</tr>';
    });
    html += '</tbody></table></div></div>';
    document.getElementById('ch-list').innerHTML = html;
  } catch(e) {
    document.getElementById('ch-list').innerHTML = errorHtml(e.message);
  }
}

async function saveChannel() {
  var code = document.getElementById('ch-code').value.trim();
  var name = document.getElementById('ch-name').value.trim();
  var desc = document.getElementById('ch-desc').value.trim();
  if (!code || !name) { toast('Kod ve ad zorunlu', 'w'); return; }
  try {
    await apiFetch('/api/v1/channel-mappings', {
      method: 'POST',
      body: JSON.stringify({channel_code: code, channel_name: name, description: desc || null})
    });
    toast('Kanal kaydedildi: ' + code + ' -> ' + name, 's');
    document.getElementById('ch-code').value = '';
    document.getElementById('ch-name').value = '';
    document.getElementById('ch-desc').value = '';
    await loadChannelList();
  } catch(e) { toast('Hata: ' + e.message, 'e'); }
}

async function deleteChannel(code) {
  if (!confirm(code + ' kanalini silmek istiyor musunuz?')) return;
  try {
    await apiFetch('/api/v1/channel-mappings/' + code, {method: 'DELETE'});
    toast('Kanal silindi: ' + code, 'w');
    await loadChannelList();
  } catch(e) { toast('Hata: ' + e.message, 'e'); }
}
'''

if 'loadChannels' not in content:
    content = content.replace('function toast(msg, type) {', channels_js + '\nfunction toast(msg, type) {')
    print('OK: Kanal fonksiyonlari eklendi')
else:
    print('OK: Kanal fonksiyonlari zaten var')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
