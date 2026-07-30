"""
Zabbix Collector'a Neo4j senkronizasyonu ekler.
Her polling sonunda kapanan alarmlari Neo4j'de de gunceller.
Calistirma: python3 patch_neo4j_sync.py
"""

with open('/data/lumen/engine/zabbix_collector.py') as f:
    c = f.read()

# Neo4j sync fonksiyonu ekle - _event_kaydet metodundan once
old = '    async def _event_kaydet(self, conn, event: dict) -> bool:'
new = '''    async def _neo4j_sync(self, kapanan_idler: list):
        """Kapanan alarmlari Neo4j'de gunceller."""
        if not kapanan_idler:
            return
        try:
            import requests as _req
            from base64 import b64encode as _b64
            import os as _os

            # Neo4j config DB'den al
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='neo4j'"
                )
                if not row or not row['enabled']:
                    return

                import json as _json
                config = row['config'] if isinstance(row['config'], dict) else _json.loads(row['config'] or '{}')
                secrets_raw = row['secrets'] if isinstance(row['secrets'], dict) else _json.loads(row['secrets'] or '{}')

            from cryptography.fernet import Fernet as _Fernet
            secret_key = _os.environ.get('LUMEN_SECRET_KEY', '')
            password = ''
            if secret_key and secrets_raw.get('password'):
                try:
                    password = _Fernet(secret_key.encode()).decrypt(secrets_raw['password'].encode()).decode()
                except Exception:
                    password = secrets_raw.get('password', '')
            else:
                password = secrets_raw.get('password', '')

            url = config.get('url', '').rstrip('/')
            database = config.get('database', 'neo4j')
            if not url or not password:
                return

            auth = _b64(f'neo4j:{password}'.encode()).decode()
            headers = {'Content-Type': 'application/json', 'Authorization': f'Basic {auth}'}

            # Kapanan alarmlari neo4j'de guncelle
            _req.post(
                f'{url}/db/{database}/tx/commit',
                headers=headers,
                json={'statements': [{'statement':
                    'MATCH (a:ZabbixEvent) WHERE a.event_id IN $ids SET a.aktif = false RETURN count(a)',
                    'parameters': {'ids': kapanan_idler}
                }]},
                verify=False, timeout=10
            )
            logger.debug(f"Neo4j sync: {len(kapanan_idler)} alarm guncellendi")
        except Exception as e:
            logger.debug(f"Neo4j sync hatasi: {e}")

    async def _event_kaydet(self, conn, event: dict) -> bool:'''

if old in c:
    c = c.replace(old, new)
    print("OK: _neo4j_sync eklendi")
else:
    print("WARN: _event_kaydet bulunamadi")

# Ana dongude kapanan alarmlari Neo4j'ye de gonder
old2 = '''                        # Kapanan alarmlari isaretle
                                if aktif_idler:
                                    await conn.execute(
                                        """
                                        UPDATE zabbix_events
                                        SET resolved_at = NOW()
                                        WHERE resolved_at IS NULL
                                          AND zabbix_event_id != ALL($1::text[])
                                          AND clock >= NOW() - INTERVAL '24 hours'
                                        """,
                                        aktif_idler
                                    )'''

new2 = '''                        # Kapanan alarmlari isaretle
                                if aktif_idler:
                                    # Kapanan idleri bul (once)
                                    kapananlar = await conn.fetch("""
                                        SELECT zabbix_event_id FROM zabbix_events
                                        WHERE resolved_at IS NULL
                                          AND zabbix_event_id != ALL($1::text[])
                                          AND clock >= NOW() - INTERVAL '24 hours'
                                    """, aktif_idler)
                                    kapanan_idler = [r['zabbix_event_id'] for r in kapananlar]

                                    await conn.execute(
                                        """
                                        UPDATE zabbix_events
                                        SET resolved_at = NOW()
                                        WHERE resolved_at IS NULL
                                          AND zabbix_event_id != ALL($1::text[])
                                          AND clock >= NOW() - INTERVAL '24 hours'
                                        """,
                                        aktif_idler
                                    )
                                    # Neo4j'yi de guncelle
                                    if kapanan_idler:
                                        asyncio.create_task(self._neo4j_sync(kapanan_idler))'''

if old2 in c:
    c = c.replace(old2, new2)
    print("OK: Neo4j sync donguye eklendi")
else:
    print("WARN: dongü blogu bulunamadi")

with open('/data/lumen/engine/zabbix_collector.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/engine/zabbix_collector.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
