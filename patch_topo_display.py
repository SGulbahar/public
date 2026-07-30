"""
Topoloji servis chip'lerine varsayilan display ekler.
Calistirma: python3 patch_topo_display.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    lines = f.readlines()

# 1701. satiri bul (index 1700)
target = None
for i, l in enumerate(lines):
    if 'topo-svc-chip' in l and 'data-alarm' in l and 'padding:4px' in l:
        target = i
        break

if target is None:
    print("WARN: satir bulunamadi")
else:
    lines[target] = (
        '    html += \'<div class="topo-svc-chip" data-svc="\' + s.name + \'" data-alarm="\' + (s.alarm_count > 0 ? \'1\' : \'0\') + \'"\''
        " + ' onclick=\"topoYukle(this.dataset.svc)\"'"
        " + ' style=\"' + alarmCss + ';padding:4px 10px;border-radius:20px;cursor:pointer;font-size:10px;font-family:JetBrains Mono,monospace;display:' + (s.alarm_count > 0 ? 'inline-block' : 'none') + '\"'"
        " + ' onmouseover=\"this.style.opacity=0.7\" onmouseout=\"this.style.opacity=1\">'\n"
        "    + \n"
    )
    print(f"OK: satir {target+1} guncellendi")

with open(HTML_PATH, 'w') as f:
    f.writelines(lines)

print("girisYap:", "girisYap" in open(HTML_PATH).read())
