"""
RAG context'e Zabbix kritik alarm bilgisi ekler.
Calistirma: python3 patch_rag_zabbix.py
"""

with open('/data/lumen/engine/rag_context.py') as f:
    c = f.read()

# Zabbix problem cekme metodu - __init__'ten once sinif icerisine ekle
old_init = '    def __init__(self, db_dsn: str):'

new_zabbix_method = '''    async def _zabbix_problemleri_al(self, anomali_zamani) -> str:
        """Anomali zamani etrafindaki Zabbix kritik alarmlarini ceker."""
        try:
            import json as _json
            import aiohttp as _aiohttp
            from cryptography.fernet import Fernet as _Fernet
            import os as _os
            from datetime import datetime as _dt, timedelta as _td

            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='zabbix'"
                )
                if not row or not row['enabled']:
                    return ""

                config = dict(row['config']) if row['config'] else {}
                secrets_raw = dict(row['secrets']) if row['secrets'] else {}

            secret_key = _os.environ.get("LUMEN_SECRET_KEY", "")
            secrets = {}
            if secret_key:
                f = _Fernet(secret_key.encode())
                for k, v in secrets_raw.items():
                    try:
                        secrets[k] = f.decrypt(v.encode()).decode()
                    except Exception:
                        secrets[k] = v
            else:
                secrets = secrets_raw

            url = config.get("url", "").rstrip("/")
            user = config.get("user", "Admin")
            password = secrets.get("password", "")

            if not url or not password:
                return ""

            # Anomali zamani etrafinda +/- 30 dakika
            try:
                if isinstance(anomali_zamani, str):
                    dt = _dt.fromisoformat(anomali_zamani.replace("Z", ""))
                else:
                    dt = _dt.utcnow()
            except Exception:
                dt = _dt.utcnow()

            time_from = int((dt - _td(minutes=30)).timestamp())
            time_till = int((dt + _td(minutes=30)).timestamp())

            async with _aiohttp.ClientSession() as session:
                # Login
                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    json={"jsonrpc": "2.0", "method": "user.login",
                          "params": {"username": user, "password": password}, "id": 1},
                    ssl=False, timeout=_aiohttp.ClientTimeout(total=10)
                ) as r:
                    data = await r.json()
                    token = data.get("result")
                    if not token:
                        return ""

                # Kritik eventleri cek (severity 4=High, 5=Disaster)
                async with session.post(
                    f"{url}/api_jsonrpc.php",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"jsonrpc": "2.0", "method": "event.get", "params": {
                        "output": ["eventid", "name", "severity", "clock", "acknowledged"],
                        "severities": [4, 5],
                        "value": 1,
                        "time_from": time_from,
                        "time_till": time_till,
                        "selectHosts": ["hostid", "name"],
                        "limit": 10
                    }, "id": 1},
                    ssl=False, timeout=_aiohttp.ClientTimeout(total=10)
                ) as r:
                    data = await r.json()
                    events = data.get("result", [])

            if not events:
                return ""

            SEV_MAP = {"4": "Yuksek", "5": "Kritik"}
            satirlar = []
            for e in events:
                host_adi = e["hosts"][0]["name"] if e.get("hosts") else "Bilinmiyor"
                sev = SEV_MAP.get(str(e.get("severity", "")), str(e.get("severity", "")))
                satirlar.append(f"  - [{sev}] {e['name']} | Host: {host_adi}")

            return (
                f"Anomali Zamani Zabbix Alarmlari (+-30 dakika, {len(events)} alarm):\n" +
                "\n".join(satirlar)
            )

        except Exception as e:
            logger.debug(f"Zabbix problem cekme hatasi: {e}")
            return ""

    def __init__(self, db_dsn: str):'''

if old_init in c:
    c = c.replace(old_init, new_zabbix_method)
    print("OK: _zabbix_problemleri_al eklendi")
else:
    print("WARN: __init__ bulunamadi")

# parts listesine Zabbix context ekle - return oncesinde
old_return = '''        if not parts:
            return None

        context = "\\n\\n".join(parts)
        logger.info(f"RAG context olusturuldu: {service} ({len(context)} karakter)")
        return context'''

new_return = '''        # Zabbix kritik alarmlar
        try:
            zabbix_ctx = await self._zabbix_problemleri_al(detected_at)
            if zabbix_ctx:
                parts.append(zabbix_ctx)
        except Exception as zb_e:
            logger.debug(f"Zabbix RAG hatasi: {zb_e}")

        if not parts:
            return None

        context = "\\n\\n".join(parts)
        logger.info(f"RAG context olusturuldu: {service} ({len(context)} karakter)")
        return context'''

if old_return in c:
    c = c.replace(old_return, new_return)
    print("OK: Zabbix context parts'a eklendi")
else:
    print("WARN: return blogu bulunamadi")

with open('/data/lumen/engine/rag_context.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/engine/rag_context.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
