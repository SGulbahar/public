"""
VM Radar blogunu temizler ve temiz versiyonunu ekler.
Calistirma: python3 patch_vm_radar_clean.py
"""

VM_RADAR = '''
# ═══════════════════════════════════════════════════════════
# VM RADAR (KAPASİTE RADAR)
# ═══════════════════════════════════════════════════════════

async def _zabbix_baglan(db):
    """DB den Zabbix config ve token alir."""
    import httpx as _httpx
    from sqlalchemy import text as _text
    result = await db.execute(_text("SELECT config, secrets, enabled FROM integrations WHERE key='zabbix'"))
    row = result.fetchone()
    if not row or not row.enabled:
        raise HTTPException(status_code=400, detail="Zabbix entegrasyonu aktif degil")

    config = dict(row.config) if row.config else {}
    secrets_enc = dict(row.secrets) if row.secrets else {}

    sm = _secret_manager()
    secrets = {k: sm.coz(v) if sm else v for k, v in secrets_enc.items()}

    url = config.get("url", "").rstrip("/")
    zabbix_user = config.get("user", "Admin")
    password = secrets.get("password", "")

    if not url or not password:
        raise HTTPException(status_code=400, detail="Zabbix URL veya sifre eksik")

    async with _httpx.AsyncClient(verify=False, timeout=15) as client:
        r = await client.post(
            f"{url}/api_jsonrpc.php",
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "method": "user.login",
                  "params": {"username": zabbix_user, "password": password}, "id": 1}
        )
        data = r.json()
        if "error" in data:
            raise HTTPException(status_code=502, detail=f"Zabbix login hatasi: {data['error']}")
        token = data.get("result")

    return url, token


async def _zabbix_api(url, token, method, params):
    """Zabbix API cagrisi yapar."""
    import httpx as _httpx
    async with _httpx.AsyncClient(verify=False, timeout=30) as client:
        r = await client.post(
            f"{url}/api_jsonrpc.php",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        )
        data = r.json()
        if "error" in data:
            raise HTTPException(status_code=502, detail=f"Zabbix API hatasi: {data['error']}")
        return data.get("result", [])


@router.get("/vm-radar/groups")
async def vm_radar_groups(db: AsyncSession = Depends(get_session)):
    """Zabbix ten hypervisor host gruplarini dondurur."""
    try:
        url, token = await _zabbix_baglan(db)
        groups = await _zabbix_api(url, token, "hostgroup.get", {
            "output": ["groupid", "name"],
            "search": {"name": "*hypervisor*"},
            "searchWildcardsEnabled": True
        })
        return [{"id": g["groupid"], "name": g["name"]} for g in groups]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vm-radar/hosts")
async def vm_radar_hosts(group_id: str, db: AsyncSession = Depends(get_session)):
    """Secili gruptaki host lari dondurur."""
    try:
        url, token = await _zabbix_baglan(db)
        hosts = await _zabbix_api(url, token, "host.get", {
            "output": ["hostid", "host", "name", "status"],
            "groupids": [group_id],
            "filter": {"status": "0"}
        })
        return [{"id": h["hostid"], "name": h["name"], "host": h["host"]} for h in hosts]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vm-radar/analyze")
async def vm_radar_analyze(request: Request, db: AsyncSession = Depends(get_session)):
    """Secili host larin 60 gunluk CPU RAM trend verisini cekip P95 max avg spike hesaplar."""
    import time
    import statistics as _stats
    body = await request.json()
    host_ids = body.get("host_ids", [])
    gun = int(body.get("gun", 60))

    if not host_ids:
        raise HTTPException(status_code=400, detail="host_ids bos")
    if len(host_ids) > 100:
        raise HTTPException(status_code=400, detail="En fazla 100 host")

    url, token = await _zabbix_baglan(db)

    time_till = int(time.time())
    time_from = time_till - (gun * 86400)

    sonuclar = []

    for host_id in host_ids:
        try:
            items = await _zabbix_api(url, token, "item.get", {
                "output": ["itemid", "key_", "name", "lastvalue"],
                "hostids": [host_id],
                "filter": {"key_": [
                    "system.cpu.util",
                    "vm.memory.size[total]",
                    "vm.memory.size[pavailable]"
                ]},
                "status": "0"
            })

            item_map = {i["key_"]: i for i in items}
            cpu_item = item_map.get("system.cpu.util")
            mem_total_item = item_map.get("vm.memory.size[total]")
            mem_avail_item = item_map.get("vm.memory.size[pavailable]")

            if not cpu_item:
                continue

            cpu_trends = await _zabbix_api(url, token, "trend.get", {
                "output": ["clock", "value_avg", "value_max"],
                "itemids": [cpu_item["itemid"]],
                "time_from": time_from,
                "time_till": time_till
            })

            ram_trends = []
            if mem_avail_item:
                ram_trends = await _zabbix_api(url, token, "trend.get", {
                    "output": ["clock", "value_avg", "value_min"],
                    "itemids": [mem_avail_item["itemid"]],
                    "time_from": time_from,
                    "time_till": time_till
                })

            if not cpu_trends:
                continue

            cpu_avgs = sorted([float(t["value_avg"]) for t in cpu_trends])
            cpu_maxes = [float(t["value_max"]) for t in cpu_trends]
            cpu_p95 = cpu_avgs[int(len(cpu_avgs) * 0.95)] if cpu_avgs else 0
            cpu_max = max(cpu_maxes) if cpu_maxes else 0
            cpu_avg = _stats.mean(cpu_avgs) if cpu_avgs else 0
            cpu_spike_saat = sum(1 for v in cpu_maxes if v > 80)

            ram_total_gb = round(float(mem_total_item["lastvalue"]) / (1024**3), 1) if mem_total_item else 0
            ram_kullanim_p95 = 0
            ram_kullanim_max = 0
            ram_kullanim_avg = 0

            if ram_trends:
                ram_kullanim_avgs = sorted([100 - float(t["value_avg"]) for t in ram_trends])
                ram_kullanim_maxes = [100 - float(t["value_min"]) for t in ram_trends]
                ram_kullanim_p95 = ram_kullanim_avgs[int(len(ram_kullanim_avgs) * 0.95)] if ram_kullanim_avgs else 0
                ram_kullanim_max = max(ram_kullanim_maxes) if ram_kullanim_maxes else 0
                ram_kullanim_avg = _stats.mean(ram_kullanim_avgs) if ram_kullanim_avgs else 0

            if cpu_p95 < 20 and cpu_max < 60 and ram_kullanim_p95 < 40:
                risk = "LOW"
                risk_tr = "Dusuk"
            elif cpu_p95 > 70 or ram_kullanim_p95 > 80:
                risk = "HIGH"
                risk_tr = "Yuksek"
            else:
                risk = "MEDIUM"
                risk_tr = "Orta"

            oneri = []
            if cpu_p95 < 20 and cpu_max < 60:
                oneri.append("CPU azaltilabilir")
            if ram_kullanim_p95 < 30:
                oneri.append("RAM azaltilabilir")
            if cpu_spike_saat > 0 and cpu_p95 < 20:
                oneri.append(f"{cpu_spike_saat} saatlik CPU spike dikkat")

            hosts_info = await _zabbix_api(url, token, "host.get", {
                "output": ["name"], "hostids": [host_id]
            })
            host_name = hosts_info[0]["name"] if hosts_info else host_id

            sonuclar.append({
                "host_id": host_id,
                "host_name": host_name,
                "gun": gun,
                "cpu": {
                    "p95": round(cpu_p95, 1),
                    "max": round(cpu_max, 1),
                    "avg": round(cpu_avg, 1),
                    "spike_saat": cpu_spike_saat
                },
                "ram": {
                    "total_gb": ram_total_gb,
                    "kullanim_p95": round(ram_kullanim_p95, 1),
                    "kullanim_max": round(ram_kullanim_max, 1),
                    "kullanim_avg": round(ram_kullanim_avg, 1)
                },
                "risk": risk,
                "risk_tr": risk_tr,
                "oneri": oneri
            })

        except Exception as e:
            sonuclar.append({"host_id": host_id, "hata": str(e), "risk": "UNKNOWN"})

    return {"sonuclar": sonuclar, "toplam": len(sonuclar)}


@router.post("/vm-radar/llm-analyze")
async def vm_radar_llm_analyze(request: Request, db: AsyncSession = Depends(get_session)):
    """Tek sunucu icin LLM detay analizi yapar."""
    import httpx as _httpx
    body = await request.json()
    sunucu = body.get("sunucu")
    if not sunucu:
        raise HTTPException(status_code=400, detail="sunucu verisi eksik")

    host_name = sunucu.get("host_name", "Bilinmiyor")
    gun = sunucu.get("gun", 60)
    cpu = sunucu.get("cpu", {})
    ram = sunucu.get("ram", {})
    risk_tr = sunucu.get("risk_tr", "")
    oneri = sunucu.get("oneri", [])

    prompt = f"""Bir sunucunun {gun} gunluk kaynak kullanim verisi asagida verilmistir. Operasyon ekibine yonelik kisa ve net bir degerlendirme yap.

=== SUNUCU BILGISI ===
Sunucu: {host_name}
Analiz Suresi: Son {gun} gun
Risk Seviyesi: {risk_tr}

=== CPU KULLANIMI ===
P95 (normal yuk): %{cpu.get("p95", 0)}
Maksimum: %{cpu.get("max", 0)}
Ortalama: %{cpu.get("avg", 0)}
%80+ CPU saat sayisi: {cpu.get("spike_saat", 0)} saat

=== RAM KULLANIMI ===
Toplam RAM: {ram.get("total_gb", 0)} GB
P95 kullanim: %{ram.get("kullanim_p95", 0)}
Maksimum kullanim: %{ram.get("kullanim_max", 0)}
Ortalama kullanim: %{ram.get("kullanim_avg", 0)}

Asagidaki formatta Turkce yanit ver:

**Degerlendirme:** Sunucunun genel kaynak kullanim durumu 2 cumleyle.
**CPU Analizi:** CPU kullanim orntusu ve varsa spike nedeni tahmini.
**RAM Analizi:** RAM kullanim durumu.
**Oneri:** {"Azaltma onerisi ver (kac CPU/GB a dusurulebilebilir tahmini)." if risk_tr == "Dusuk" else "Mevcut kaynaklarin korunmasi veya arttirilmasi gerekip gerekmedigi."}
**Risk:** Kaynak degisikligi yapilirsa olasi riskler."""

    result = await db.execute(text("SELECT config, secrets, enabled FROM integrations WHERE key='llm'"))
    row = result.fetchone()
    if not row or not row.enabled:
        raise HTTPException(status_code=400, detail="LLM entegrasyonu aktif degil")

    config = dict(row.config) if row.config else {}
    secrets_enc = dict(row.secrets) if row.secrets else {}
    sm = _secret_manager()
    secrets = {k: sm.coz(v) if sm else v for k, v in secrets_enc.items()}

    base_url = config.get("base_url", "").rstrip("/")
    model = config.get("model", "")
    api_key = secrets.get("api_key", "")
    max_tokens = int(config.get("max_tokens", 500))

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with _httpx.AsyncClient(verify=False, timeout=60) as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.3
                }
            )
            data = r.json()
            analiz = data["choices"][0]["message"]["content"]
            return {"analiz": analiz, "host_name": host_name}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM hatasi: {e}")

'''

with open('/data/lumen/app/api/routes.py') as f:
    lines = f.readlines()

# Eski VM Radar blogunu bul ve sil
start = None
end = None
for i, l in enumerate(lines):
    if '# VM RADAR' in l and start is None:
        start = i
    if start and i > start and l.startswith('@router.') and 'vm-radar' not in l and 'vm_radar' not in l and '_zabbix' not in l:
        end = i
        break

print(f"Eski blog: satir {start}-{end}")

if start is not None and end is not None:
    yeni_lines = lines[:start] + [VM_RADAR + '\n'] + lines[end:]
    with open('/data/lumen/app/api/routes.py', 'w') as f:
        f.writelines(yeni_lines)
    print("OK: temiz versiyon yazildi")
else:
    print("WARN: blog bulunamadi")

import py_compile
try:
    py_compile.compile('/data/lumen/app/api/routes.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
