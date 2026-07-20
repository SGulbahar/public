"""
Zabbix Collector'a kapanan alarm takibi ekler.
Calistirma: python3 patch_zabbix_resolved.py
"""

with open('/data/lumen/engine/zabbix_collector.py') as f:
    c = f.read()

old = '''                        async with self._pool.acquire() as conn:
                                for event in events:
                                    await self._event_kaydet(conn, event)'''

new = '''                        aktif_idler = [str(e.get("eventid", "")) for e in events]
                        async with self._pool.acquire() as conn:
                                for event in events:
                                    await self._event_kaydet(conn, event)
                                # Kapanan alarmlari isaretle
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

if old in c:
    c = c.replace(old, new)
    print("OK: resolved_at takibi eklendi")
else:
    print("WARN: blok bulunamadi")

with open('/data/lumen/engine/zabbix_collector.py', 'w') as f:
    f.write(c)

import py_compile
try:
    py_compile.compile('/data/lumen/engine/zabbix_collector.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax HATA: {e}")
