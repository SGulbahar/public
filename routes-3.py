# --- WHITELIST ENDPOINT'LERI ---

class WhitelistRequest(BaseModel):
    service_name: str
    channel_code: str = "*"
    rule_name: str = "*"
    reason: Optional[str] = None


@router.get("/whitelist", dependencies=[require_permission("admin.settings.edit")])
async def list_whitelist(db: AsyncSession = Depends(get_session)):
    result = await db.execute(text(
        "SELECT service_name, channel_code, rule_name, reason, created_by, created_at "
        "FROM service_whitelist ORDER BY service_name, channel_code, rule_name"
    ))
    rows = result.fetchall()
    return [
        {
            "service_name": r.service_name,
            "channel_code": r.channel_code,
            "rule_name": r.rule_name,
            "reason": r.reason,
            "created_by": r.created_by,
            "created_at": r.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/whitelist", dependencies=[require_permission("admin.settings.edit")])
async def add_whitelist(
    body: WhitelistRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    await db.execute(text("""
        INSERT INTO service_whitelist (service_name, channel_code, rule_name, reason, created_by)
        VALUES (:svc, :ch, :rule, :reason, :user)
        ON CONFLICT (service_name, channel_code, rule_name) DO UPDATE
        SET reason = EXCLUDED.reason, created_by = EXCLUDED.created_by, created_at = NOW()
    """), {"svc": body.service_name, "ch": body.channel_code, "rule": body.rule_name,
           "reason": body.reason, "user": user.get("sub")})
    await write_audit(
        db, user.get("sub"), "whitelist.add",
        f"service_whitelist/{body.service_name}/{body.channel_code}/{body.rule_name}",
        f"reason={body.reason}",
        ip_address=get_client_ip(request)
    )
    await db.commit()
    return {"message": "Whitelist kurali eklendi"}


@router.delete(
    "/whitelist/{service_name}/{channel_code}/{rule_name}",
    dependencies=[require_permission("admin.settings.edit")]
)
async def delete_whitelist(
    service_name: str,
    channel_code: str,
    rule_name: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    await db.execute(text(
        "DELETE FROM service_whitelist WHERE service_name=:svc AND channel_code=:ch AND rule_name=:rule"
    ), {"svc": service_name, "ch": channel_code, "rule": rule_name})
    await write_audit(
        db, user.get("sub"), "whitelist.delete",
        f"service_whitelist/{service_name}/{channel_code}/{rule_name}",
        ip_address=get_client_ip(request)
    )
    await db.commit()
    return {"message": "Whitelist kurali silindi"}
