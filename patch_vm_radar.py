"""
VM Radar (Kapasite Radar) endpoint'lerini routes.py'ye ekler.
Calistirma: python3 patch_vm_radar.py
"""
with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

vm_radar_endpoints = '''

# ═══════════════════════════════════════════════════════════
# VM RADAR (KAPASİTE RADAR)
# ═══════════════════════════════════════════════════════════

async def _zabbix_api(url: str, token: str, method: str, params: dict) -> list:
    """Zabbix API cagrisi yapar."""
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        r = await client.post(
            f"{url}/api_jsonrpc.php",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        )
        data = r.json()
        if "error" in data:
            raise HTTPException(status_code=502, detail=f"Zabbix API hatasi: {data['error']}")
        return data.get("result", [])


async def _zabbix_baglan(db: AsyncSession):
    """DB'den Zabbix config ve token alir."""
    result = await db.execute(text("SELECT config, secrets, enabled FROM integrations WHERE key='zabbix'"))
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

    # Login
    async with httpx.AsyncClient(verify=False, timeout=15) as client:
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


@router.get("/vm-radar/groups")
async def vm_radar_groups(db: AsyncSession = Depends(get_session)):
    """Zabbix'ten hypervisor host gruplarini dondurur."""
    url, token = await _zabbix_baglan(db)
    groups = await _zabbix_api(url, token, "hostgroup.get", {
        "output": ["groupid", "name"],
        "search": {"name": "*hypervisor*"},
        "searchWildcardsEnabled": True
    })
    return [{"id": g["groupid"], "name": g["name"]} for g in groups]


@router.get("/vm-radar/hosts")
async def vm_radar_hosts(group_id: str, db: AsyncSession = Depends(get_session)):
    """Seçili gruptaki host'lari dondurur."""
    url, token = await _zabbix_baglan(db)
    hosts = await _zabbix_api(url, token, "host.get", {
        "output": ["hostid", "host", "name", "status"],
        "groupids": [group_id],
        "filter": {"status": "0"}
    })
    return [{"id": h["hostid"], "name": h["name"], "host": h["host"]} for h in hosts]


@router.post("/vm-radar/analyze")
async def vm_radar_analyze(request: Request, db: AsyncSession = Depends(get_session)):
    """
    Seçili host'larin 60 gunluk CPU/RAM trend verisini cekip
    P95/max/avg/spike hesaplar. LLM analizi YAPMAZ.
    """
    body = await request.json()
    host_ids = body.get("host_ids", [])
    gun = int(body.get("gun", 60))

    if not host_ids:
        raise HTTPException(status_code=400, detail="host_ids bos")
    if len(host_ids) > 100:
        raise HTTPException(status_code=400, detail="En fazla 100 host analiz edilebilir")

    url, token = await _zabbix_baglan(db)

    import time
    import statistics
    time_till = int(time.time())
    time_from = time_till - (gun * 86400)

    sonuclar = []

    for host_id in host_ids:
        try:
            # Item'lari bul
            items = await _zabbix_api(url, token, "item.get", {
                "output": ["itemid", "key_", "name", "lastvalue", "units"],
                "hostids": [host_id],
                "filter": {"key_": ["system.cpu.util",
                                    "vm.memory.size[total]",
                                    "vm.memory.size[available]",
                                    "vm.memory.size[pavailable]"]},
                "status": "0"
            })

            item_map = {i["key_"]: i for i in items}

            cpu_item = item_map.get("system.cpu.util")
            mem_total_item = item_map.get("vm.memory.size[total]")
            mem_avail_item = item_map.get("vm.memory.size[pavailable]")

            if not cpu_item or not mem_total_item:
                continue

            # CPU trend verisi
            cpu_trends = await _zabbix_api(url, token, "trend.get", {
                "output": ["clock", "value_min", "value_avg", "value_max"],
                "itemids": [cpu_item["itemid"]],
                "time_from": time_from,
                "time_till": time_till
            })

            # RAM trend verisi
            ram_trends = await _zabbix_api(url, token, "trend.get", {
                "output": ["clock", "value_min", "value_avg", "value_max"],
                "itemids": [mem_avail_item["itemid"]] if mem_avail_item else [],
                "time_from": time_from,
                "time_till": time_till
            }) if mem_avail_item else []

            if not cpu_trends:
                continue

            # CPU istatistikleri
            cpu_avgs = [float(t["value_avg"]) for t in cpu_trends]
            cpu_maxes = [float(t["value_max"]) for t in cpu_trends]

            cpu_avgs_sorted = sorted(cpu_avgs)
            cpu_p95_idx = int(len(cpu_avgs_sorted) * 0.95)
            cpu_p95 = cpu_avgs_sorted[cpu_p95_idx] if cpu_avgs_sorted else 0
            cpu_max = max(cpu_maxes) if cpu_maxes else 0
            cpu_avg = statistics.mean(cpu_avgs) if cpu_avgs else 0
            cpu_spike_saat = sum(1 for v in cpu_maxes if v > 80)

            # RAM istatistikleri (pavailable = bos %)
            ram_kullanim_p95 = 0
            ram_kullanim_max = 0
            ram_kullanim_avg = 0
            ram_total_gb = 0

            if ram_trends:
                # pavailable: bos %, kullanim = 100 - pavailable
                ram_avail_avgs = [float(t["value_avg"]) for t in ram_trends]
                ram_kullanim_avgs = [100 - v for v in ram_avail_avgs]
                ram_kullanim_maxes = [100 - float(t["value_min"]) for t in ram_trends]

                ram_sorted = sorted(ram_kullanim_avgs)
                ram_p95_idx = int(len(ram_sorted) * 0.95)
                ram_kullanim_p95 = ram_sorted[ram_p95_idx] if ram_sorted else 0
                ram_kullanim_max = max(ram_kullanim_maxes) if ram_kullanim_maxes else 0
                ram_kullanim_avg = statistics.mean(ram_kullanim_avgs) if ram_kullanim_avgs else 0

            if mem_total_item:
                ram_total_gb = round(float(mem_total_item["lastvalue"]) / (1024**3), 1)

            # Risk skorlama
            if cpu_p95 < 20 and cpu_max < 60 and ram_kullanim_p95 < 40:
                risk = "LOW"
                risk_tr = "Düşük"
            elif cpu_p95 > 70 or ram_kullanim_p95 > 80:
                risk = "HIGH"
                risk_tr = "Yüksek"
            else:
                risk = "MEDIUM"
                risk_tr = "Orta"

            # Öneri
            oneri = []
            if cpu_p95 < 20 and cpu_max < 60:
                oneri.append("CPU azaltılabilir")
            if ram_kullanim_p95 < 30:
                oneri.append("RAM azaltılabilir")
            if cpu_spike_saat > 0 and cpu_p95 < 20:
                oneri.append(f"Dikkat: {cpu_spike_saat} saatlik CPU spike")

            sonuclar.append({
                "host_id": host_id,
                "host_name": next((h["name"] for h in
                    await _zabbix_api(url, token, "host.get",
                        {"output": ["name"], "hostids": [host_id]}) ), host_id),
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
            sonuclar.append({
                "host_id": host_id,
                "hata": str(e),
                "risk": "UNKNOWN"
            })

    return {"sonuclar": sonuclar, "toplam": len(sonuclar)}


@router.post("/vm-radar/llm-analyze")
async def vm_radar_llm_analyze(request: Request, db: AsyncSession = Depends(get_session)):
    """
    Tek sunucu icin LLM detay analizi yapar.
    Kullanici 'Analiz Et' butonuna tikladiginda cagrilir.
    """
    body = await request.json()
    sunucu = body.get("sunucu")
    if not sunucu:
        raise HTTPException(status_code=400, detail="sunucu verisi eksik")

    host_name = sunucu.get("host_name", "Bilinmiyor")
    gun = sunucu.get("gun", 60)
    cpu = sunucu.get("cpu", {})
    ram = sunucu.get("ram", {})
    risk = sunucu.get("risk_tr", "")
    oneri = sunucu.get("oneri", [])

    prompt = f"""Bir sunucunun {gun} günlük kaynak kullanım verisi aşağıda verilmiştir. Operasyon ekibine yönelik kısa ve net bir değerlendirme yap.

=== SUNUCU BİLGİSİ ===
Sunucu: {host_name}
Analiz Süresi: Son {gun} gün
Risk Seviyesi: {risk}

=== CPU KULLANIMI ===
P95 (normal yük): %{cpu.get('p95', 0)}
Maksimum: %{cpu.get('max', 0)}
Ortalama: %{cpu.get('avg', 0)}
%80+ CPU saat sayısı: {cpu.get('spike_saat', 0)} saat

=== RAM KULLANIMI ===
Toplam RAM: {ram.get('total_gb', 0)} GB
P95 kullanım: %{ram.get('kullanim_p95', 0)}
Maksimum kullanım: %{ram.get('kullanim_max', 0)}
Ortalama kullanım: %{ram.get('kullanim_avg', 0)}

=== GÖREV ===
Aşağıdaki formatta yanıt ver:

**Değerlendirme:** Sunucunun genel kaynak kullanım durumu 2 cümleyle.

**CPU Analizi:** CPU kullanım örüntüsü ve varsa spike nedeni tahmini (batch iş, anlık yük vs).

**RAM Analizi:** RAM kullanım durumu ve yeterliliği.

**Öneri:** {"Azaltma önerisi ver (kaç CPU/GB'a düşürülebilir tahmini)." if risk == "Düşük" else "Mevcut kaynakların korunması veya artırılması gerekip gerekmediğini belirt."}

**Risk:** Bu sunucuda kaynak değişikliği yapılırsa olası riskler (varsa).

Yanıt Türkçe ve kısa olsun. Teknik ve operasyonel ekibe yönelik yaz."""

    # LLM entegrasyonunu DB'den al
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
        async with httpx.AsyncClient(verify=False, timeout=60) as client:
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
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"LLM hatasi: HTTP {r.status_code}")
            data = r.json()
            analiz = data["choices"][0]["message"]["content"]
            return {"analiz": analiz, "host_name": host_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM baglanti hatasi: {e}")

'''

# Zabbix feed endpoint'inden önce ekle
marker = '@router.get("/zabbix/feed")'
if marker in c:
    c = c.replace(marker, vm_radar_endpoints + marker)
    print("OK: VM Radar endpoint'leri eklendi")
else:
    print("WARN: marker bulunamadi, sona ekleniyor")
    c = c + vm_radar_endpoints

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/app/api/routes.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
