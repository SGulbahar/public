"""
Yeni Zabbix alarmlari Neo4j'ye de ekler.
Calistirma: python3 patch_neo4j_new_alarm_sync.py
"""

with open('/data/lumen/engine/zabbix_collector.py') as f:
    c = f.read()

# _neo4j_alarm_ekle fonksiyonu ekle - _neo4j_sync'ten once
old = '    async def _neo4j_sync(self, kapanan_idler: list):'
new = '''    async def _neo4j_alarm_ekle(self, event: dict):
        """Yeni Zabbix alarmini Neo4j'ye ekler ve host ile iliskilendirir."""
        try:
            import requests as _req
            from base64 import b64encode as _b64
            import os as _os
            import json as _json
            from cryptography.fernet import Fernet as _Fernet

            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT config, secrets, enabled FROM integrations WHERE key='neo4j'"
                )
                if not row or not row['enabled']:
                    return

                config = row['config'] if isinstance(row['config'], dict) else _json.loads(row['config'] or '{}')
                secrets_raw = row['secrets'] if isinstance(row['secrets'], dict) else _json.loads(row['secrets'] or '{}')

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

            host_info = event.get('hosts', [{}])
            host_name = host_info[0].get('name', '') if host_info else ''
            event_id = str(event.get('eventid', ''))
            from datetime import datetime as _dt
            clock = _dt.utcfromtimestamp(int(event.get('clock', 0))).isoformat()

            # Alarm node olustur ve host ile iliskilendir
            cypher = (
                "MERGE (a:ZabbixEvent {event_id: $event_id}) "
                "SET a.name = $name, a.severity = 5, a.clock = $clock, a.aktif = true "
                "WITH a "
                "MATCH (h:Host) WHERE toLower(h.name) = toLower($host_name) "
                "MERGE (h)-[:HAS_ALARM]->(a) "
                "RETURN count(a)"
            )
            _req.post(
                f'{url}/db/{database}/tx/commit',
                headers=headers,
                json={'statements': [{'statement': cypher, 'parameters': {
                    'event_id': event_id,
                    'name': event.get('name', ''),
                    'clock': clock,
                    'host_name': host_name
                }}]},
                verify=False, timeout=10
            )
            logger.debug(f"Neo4j: yeni alarm eklendi {event_id} -> {host_name}")
        except Exception as e:
            logger.debug(f"Neo4j alarm ekleme hatasi: {e}")

    async def _neo4j_sync(self, kapanan_idler: list):'''

if old in c:
    c = c.replace(old, new)
    print("OK: _neo4j_alarm_ekle eklendi")
else:
    print("WARN: _neo4j_sync bulunamadi")

# _calistir dongusunde yeni alarm eklenince Neo4j'ye de ekle
old2 = '''                        async with self._pool.acquire() as conn:
                                for event in events:
                                    await self._event_kaydet(conn, event)'''

new2 = '''                        async with self._pool.acquire() as conn:
                                for event in events:
                                    yeni = await self._event_kaydet(conn, event)
                                    if yeni:
                                        asyncio.create_task(self._neo4j_alarm_ekle(event))'''

if old2 in c:
    c = c.replace(old2, new2)
    print("OK: Neo4j alarm ekleme donguye eklendi")
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
