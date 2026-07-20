"""
Zabbix Events endpoint'lerini routes.py'ye ekler.
Calistirma: python3 patch_zabbix_events_api.py
"""

with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

ZABBIX_EVENTS_ENDPOINTS = '''

# ═══════════════════════════════════════════════════════════
# ZABBİX EVENTS
# ═══════════════════════════════════════════════════════════

@router.get("/zabbix/events")
async def zabbix_events_listesi(
    limit: int = 50,
    aktif: bool = True,
    db: AsyncSession = Depends(get_session)
):
    """
    Zabbix DISASTER alarmlarini dondurur.
    BMC topoloji bilgisi ve korelasyon durumu ile birlikte.
    """
    filtre = "AND ze.resolved_at IS NULL" if aktif else ""

    result = await db.execute(text(f"""
        SELECT
            ze.id,
            ze.zabbix_event_id,
            ze.name,
            ze.severity,
            ze.host_name,
            ze.host_id,
            ze.clock,
            ze.resolved_at,
            ze.correlated_incident_id,
            ze.synced_at,
            -- BMC topoloji bilgisi
            bh.os as host_os,
            bh.environment as host_env,
            bh.application as host_application,
            bh.business_services as bmc_services,
            -- Incident bilgisi
            i.status as incident_status
        FROM zabbix_events ze
        LEFT JOIN bmc_hosts bh ON LOWER(bh.host_name) = LOWER(ze.host_name)
        LEFT JOIN incidents i ON i.id = ze.correlated_incident_id
        WHERE 1=1 {filtre}
        ORDER BY ze.clock DESC
        LIMIT :limit
    """), {"limit": limit})

    rows = result.fetchall()
    return [{
        "id": r.id,
        "zabbix_event_id": r.zabbix_event_id,
        "name": r.name,
        "severity": r.severity,
        "host_name": r.host_name,
        "clock": (r.clock.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.clock else None,
        "resolved_at": (r.resolved_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.resolved_at else None,
        "correlated_incident_id": r.correlated_incident_id,
        "bmc_eslesmis": r.bmc_services is not None,
        "bmc_services": list(r.bmc_services) if r.bmc_services else [],
        "host_os": r.host_os,
        "host_env": r.host_env,
        "host_application": r.host_application,
        "incident_status": r.incident_status,
    } for r in rows]


@router.get("/zabbix/events/ozet")
async def zabbix_events_ozet(db: AsyncSession = Depends(get_session)):
    """Dashboard icin Zabbix alarm ozeti."""
    result = await db.execute(text("""
        SELECT
            COUNT(*) as toplam,
            COUNT(CASE WHEN resolved_at IS NULL THEN 1 END) as aktif,
            COUNT(CASE WHEN resolved_at IS NOT NULL THEN 1 END) as cozulmus,
            COUNT(CASE WHEN correlated_incident_id IS NOT NULL THEN 1 END) as korele,
            MAX(clock) as son_alarm
        FROM zabbix_events
    """))
    r = result.fetchone()
    return {
        "toplam": r.toplam,
        "aktif": r.aktif,
        "cozulmus": r.cozulmus,
        "korele": r.korele,
        "son_alarm": (r.son_alarm.strftime("%Y-%m-%dT%H:%M:%S") + "Z") if r.son_alarm else None,
    }


@router.post("/zabbix/events/{event_id}/llm-analiz")
async def zabbix_event_llm_analiz(
    event_id: int,
    db: AsyncSession = Depends(get_session)
):
    """Tek bir Zabbix alarmi icin LLM analizi yapar."""
    result = await db.execute(text("""
        SELECT
            ze.*,
            bh.os, bh.environment, bh.application,
            bh.business_services, bh.role as host_role
        FROM zabbix_events ze
        LEFT JOIN bmc_hosts bh ON LOWER(bh.host_name) = LOWER(ze.host_name)
        WHERE ze.id = :id
    """), {"id": event_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event bulunamadi")

    bmc_bilgi = ""
    if row.business_services:
        bmc_bilgi = f"""
BMC Topoloji Bilgisi:
  Host OS: {row.os or 'Bilinmiyor'}
  Ortam: {row.environment or 'Bilinmiyor'}
  Uygulama: {row.application or 'Bilinmiyor'}
  Bagli Business Service'ler: {', '.join(list(row.business_services)[:5])}
  Host Rolu: {row.host_role or 'Bilinmiyor'}"""

    prompt = f"""Zabbix'te bir DISASTER seviyesi alarm tespit edildi. Operasyon ekibine yonelik kisa ve net analiz yap.

=== ALARM BILGISI ===
Alarm: {row.name}
Host: {row.host_name or 'Bilinmiyor'}
Zaman: {row.clock.strftime('%Y-%m-%d %H:%M:%S') if row.clock else '-'}
{bmc_bilgi}

=== GOREV ===
Asagidaki formatta Turkce yanit ver:

**Alarm Degerlendirmesi:** Bu alarmin ne anlama geldigini 1-2 cumleyle acikla.

**Olasilik Analizi:** Bu tip alarmin en sik gorülen 2-3 nedeni.

**Oncelikli Kontroller:** Hemen yapilmasi gereken 2-3 kontrol maddesi.

**Etki Analizi:** {('Bu host uzerinde calistigi bilinen uygulamalar: ' + ', '.join(list(row.business_services)[:3])) if row.business_services else 'BMC topoloji bilgisi mevcut degil, etki alani bilinmiyor.'}

Yanit kisa ve aksiyona donuk olsun."""

    # LLM entegrasyonu
    llm_result = await db.execute(text(
        "SELECT config, secrets, enabled FROM integrations WHERE key='llm'"
    ))
    llm_row = llm_result.fetchone()
    if not llm_row or not llm_row.enabled:
        raise HTTPException(status_code=400, detail="LLM entegrasyonu aktif degil")

    config = dict(llm_row.config) if llm_row.config else {}
    secrets_enc = dict(llm_row.secrets) if llm_row.secrets else {}
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
            data = r.json()
            analiz = data["choices"][0]["message"]["content"]
            return {
                "analiz": analiz,
                "host_name": row.host_name,
                "alarm_adi": row.name,
                "bmc_eslesmis": row.business_services is not None
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM hatasi: {e}")

'''

# Zabbix feed'den once ekle
marker = '@router.get("/zabbix/feed")'
if marker in c:
    c = c.replace(marker, ZABBIX_EVENTS_ENDPOINTS + marker)
    print("OK: Zabbix events endpoint'leri eklendi")
else:
    print("WARN: marker bulunamadi, sona ekleniyor")
    c = c + ZABBIX_EVENTS_ENDPOINTS

with open('/data/lumen/app/api/routes.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/app/api/routes.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
