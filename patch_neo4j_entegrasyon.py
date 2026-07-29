"""
Neo4j entegrasyonunu frontend'e ekler.
Calistirma: python3 patch_neo4j_entegrasyon.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

old = "  bmc: {"
new = """  neo4j: {
    label: 'Neo4j Graph DB',
    icon: 'N4',
    renk: '#018BFF',
    config_fields: [
      {key:'url', label:'URL', placeholder:'http://localhost:7474'},
      {key:'database', label:'Database', placeholder:'neo4j'}
    ],
    secret_fields: [
      {key:'password', label:'Sifre', type:'password'}
    ]
  },
  bmc: {"""

if old in c:
    c = c.replace(old, new)
    print("OK: Neo4j eklendi")
else:
    print("WARN: bmc blogu bulunamadi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("neo4j:", "neo4j:" in c)
print("girisYap:", "girisYap" in c)
