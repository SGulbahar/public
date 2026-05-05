#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# toast fonksiyonu var mi kontrol et
if 'function toast(msg, type)' not in content:
    print('WARN: toast fonksiyonu bulunamadi')
else:
    print('OK: toast fonksiyonu bulundu')

# loadChannels ekle
js = (
    'async function loadChannels() {\n'
    '  var el = document.getElementById("page-channels");\n'
    '  el.innerHTML = "<div class=\"phead\"><div><div class=\"pt\">Kanal Tanimlari</div><div class=\"ps\">Kanal kodu - isim eslestirmesi</div></div></div>" +\n'
    '    "<div class=\"card\" style=\"margin-bottom:16px\"><div class=\"ctitle\">Yeni Kanal Ekle / Guncelle</div>" +\n'
    '    "<div style=\"display:grid;grid-template-columns:1fr 1fr 2fr auto;gap:10px;align-items:end\">" +\n'
    '    "<div><label style=\"font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600\">Kanal Kodu</label><input id=\"ch-code\" class=\"sinput\" placeholder=\"708\"/></div>" +\n'
    '    "<div><label style=\"font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600\">Kanal Adi</label><input id=\"ch-name\" class=\"sinput\" placeholder=\"Gorumez Bankacilik\"/></div>" +\n'
    '    "<div><label style=\"font-size:10px;color:var(--txt2);display:block;margin-bottom:4px;font-weight:600\">Aciklama</label><input id=\"ch-desc\" class=\"sinput\" placeholder=\"Aciklama...\"/></div>" +\n'
    '    "<div><button class=\"btn g\" onclick=\"saveChannel()\">Kaydet</button></div>" +\n'
    '    "</div></div>" +\n'
    '    "<div id=\"ch-list\">" + loadingHtml() + "</div>";\n'
    '  await loadChannelList();\n'
    '}\n'
    '\n'
    'async function loadChannelList() {\n'
    '  try {\n'
    '    var channels = await apiFetch("/api/v1/channel-mappings");\n'
    '    var html = "<div class=\"card\"><div class=\"ctitle\">Tanimli Kanallar (" + channels.length + ")</div>" +\n'
    '      "<div style=\"overflow:auto;max-height:500px\"><table class=\"tbl\"><thead><tr><th>Kod</th><th>Kanal Adi</th><th>Aciklama</th><th>Islem</th></tr></thead><tbody>";\n'
    '    channels.forEach(function(c) {\n'
    '      html += "<tr>" +\n'
    '        "<td style=\"font-weight:700;color:var(--acc)\">" + c.channel_code + "</td>" +\n'
    '        "<td style=\"font-weight:600\">" + c.channel_name + "</td>" +\n'
    '        "<td style=\"color:var(--txt2)\">" + (c.description||"-") + "</td>" +\n'
    '        "<td><button class=\"btn r\" style=\"padding:2px 8px;font-size:9px\" onclick=\"deleteChannel(\\'" + c.channel_code + "\\')\">Sil</button></td>" +\n'
    '        "</tr>";\n'
    '    });\n'
    '    html += "</tbody></table></div></div>";\n'
    '    document.getElementById("ch-list").innerHTML = html;\n'
    '  } catch(e) { document.getElementById("ch-list").innerHTML = errorHtml(e.message); }\n'
    '}\n'
    '\n'
    'async function saveChannel() {\n'
    '  var code = document.getElementById("ch-code").value.trim();\n'
    '  var name = document.getElementById("ch-name").value.trim();\n'
    '  var desc = document.getElementById("ch-desc").value.trim();\n'
    '  if (!code || !name) { toast("Kod ve ad zorunlu", "w"); return; }\n'
    '  try {\n'
    '    await apiFetch("/api/v1/channel-mappings", {method:"POST", body:JSON.stringify({channel_code:code, channel_name:name, description:desc||null})});\n'
    '    toast("Kanal kaydedildi: " + code + " -> " + name, "s");\n'
    '    document.getElementById("ch-code").value = "";\n'
    '    document.getElementById("ch-name").value = "";\n'
    '    document.getElementById("ch-desc").value = "";\n'
    '    await loadChannelList();\n'
    '  } catch(e) { toast("Hata: " + e.message, "e"); }\n'
    '}\n'
    '\n'
    'async function deleteChannel(code) {\n'
    '  if (!confirm(code + " kanalini silmek istiyor musunuz?")) return;\n'
    '  try {\n'
    '    await apiFetch("/api/v1/channel-mappings/" + code, {method:"DELETE"});\n'
    '    toast("Kanal silindi: " + code, "w");\n'
    '    await loadChannelList();\n'
    '  } catch(e) { toast("Hata: " + e.message, "e"); }\n'
    '}\n'
    '\n'
)

if 'function loadChannels' not in content:
    # </script> oncesine ekle
    content = content.replace('</script>', js + '</script>')
    print('OK: Kanal fonksiyonlari eklendi')
else:
    print('Zaten var')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
