"""
BMC Sync endpoint'ini routes.py'ye ekler.
Calistirma: python3 patch_bmc_sync.py
"""
with open('/data/lumen/app/api/routes.py') as f:
    c = f.read()

marker = '@router.post("/integrations/{key}/test"'
idx = c.find(marker)

sync_endpoint = '''@router.post("/bmc/sync", dependencies=[require_permission("admin.settings.edit")])
async def bmc_sync(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    """BMC Discovery'den Host + BusinessService verisini ceker, bmc_hosts tablosuna yazar."""
    result = await db.execute(text("SELECT * FROM integrations WHERE key = 'bmc'"))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="BMC entegrasyonu bulunamadi")

    config = dict(row.config) if row.config else {}
    secrets_enc = dict(row.secrets) if row.secrets else {}

    sm = _secret_manager()
    secrets = {k: sm.coz(v) if sm else v for k, v in secrets_enc.items()}

    url = config.get("url", "")
    token = secrets.get("token", "")
    if not url or not token:
        raise HTTPException(status_code=400, detail="BMC URL veya token eksik")

    dml_query = (
        "search Host show name, os, "
        "#InferredElement:Inference:Associate:DiscoveryAccess.endpoint as 'ScannedVia', "
        "appcode, application, environment, role, "
        "#Host:HostedSoftware:AggregateSoftware:BusinessService.name as 'Name'"
    )

    try:
        async with httpx.AsyncClient(verify=False, timeout=60) as client:
            r = await client.post(
                f"{url}/api/v1/search",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"query": dml_query}
            )
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"BMC API hatasi: HTTP {r.status_code}")
            sonuc = r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BMC baglanti hatasi: {e}")

    rows = sonuc if isinstance(sonuc, list) else sonuc.get("results", sonuc.get("data", []))
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="BMC yanit formati beklenmedik")

    yazilan = 0
    for r in rows:
        host_name = r.get("name") or r.get("Name")
        if not host_name:
            continue
        biz_raw = r.get("Name")
        if isinstance(biz_raw, list):
            biz_services = biz_raw
        elif biz_raw and biz_raw != host_name:
            biz_services = [biz_raw]
        else:
            biz_services = []
        try:
            await db.execute(text("""
                INSERT INTO bmc_hosts
                    (host_name, os, scanned_via, appcode, application, environment, role,
                     business_services, synced_at)
                VALUES (:host_name, :os, :scanned_via, :appcode, :application, :environment,
                        :role, :business_services, NOW())
                ON CONFLICT (host_name) DO UPDATE SET
                    os = EXCLUDED.os,
                    scanned_via = EXCLUDED.scanned_via,
                    appcode = EXCLUDED.appcode,
                    application = EXCLUDED.application,
                    environment = EXCLUDED.environment,
                    role = EXCLUDED.role,
                    business_services = EXCLUDED.business_services,
                    synced_at = NOW()
            """), {
                "host_name": host_name,
                "os": r.get("os"),
                "scanned_via": r.get("ScannedVia"),
                "appcode": r.get("appcode"),
                "application": r.get("application"),
                "environment": r.get("environment"),
                "role": r.get("role"),
                "business_services": biz_services,
            })
            yazilan += 1
        except Exception:
            continue

    config["last_sync"] = datetime.utcnow().isoformat()
    await db.execute(text("UPDATE integrations SET config = :config WHERE key = 'bmc'"),
                     {"config": json.dumps(config)})
    await db.commit()
    await write_audit(db, user.get("sub", "unknown"), "bmc.sync", "bmc_hosts",
                      f"{yazilan} host senkronize edildi", request)

    return {"status": "ok", "host_count": len(rows), "yazilan": yazilan}


'''

if idx != -1:
    c = c[:idx] + sync_endpoint + c[idx:]
    with open('/data/lumen/app/api/routes.py', 'w') as f:
        f.write(c)
    print("OK: eklendi, marker_idx=" + str(idx))
else:
    print("WARN: marker bulunamadi, routes.py degismedi")
