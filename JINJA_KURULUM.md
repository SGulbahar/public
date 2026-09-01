# Lumen — Jinja2 Kurulum Adımları

## 1. VM-1: Klasör yapısını oluştur

```bash
mkdir -p /data/lumen/frontend/templates/layouts
mkdir -p /data/lumen/frontend/templates/includes
mkdir -p /data/lumen/frontend/templates/pages
mkdir -p /data/lumen/frontend/static/css
mkdir -p /data/lumen/frontend/static/js
```

## 2. Dosyaları kopyala

```bash
# Bu repo'dan kopyala
cp templates/layouts/base.html      /data/lumen/frontend/templates/layouts/
cp templates/includes/sidebar.html  /data/lumen/frontend/templates/includes/
cp templates/includes/navbar.html   /data/lumen/frontend/templates/includes/
cp templates/pages/dashboard.html   /data/lumen/frontend/templates/pages/
cp templates/pages/anomaliler.html  /data/lumen/frontend/templates/pages/
# ... diğer sayfalar

cp static/css/lumen.css  /data/lumen/frontend/static/css/
cp static/js/lumen.js    /data/lumen/frontend/static/js/
```

## 3. app/main.py güncelle

```python
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Static dosyalar
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="/app/templates")

# Jinja filter ekle
from datetime import datetime
def strftime_filter(value, fmt="%Y-%m-%d %H:%M"):
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return value

templates.env.filters["strftime"] = strftime_filter
```

## 4. app/api/routes.py güncelle

patch_jinja_routes.py dosyasındaki route'ları ekle.
Mevcut API route'ları /api/v1/... prefix'ini korur, sadece HTML route'ları eklenir.

## 5. docker-compose.yml güncelle

```yaml
services:
  app:
    volumes:
      - /data/lumen/config:/app/config:z
      - /data/lumen/logs:/app/logs:z
      - /data/lumen/ML_Inference:/app/ML_Inference:ro
      - /data/lumen/frontend/templates:/app/templates:z   # YENİ
      - /data/lumen/frontend/static:/app/static:z         # YENİ
      # ESKİ: /data/lumen/frontend:/usr/share/nginx/html:z  → KALDIR
```

## 6. nginx.conf güncelle

```nginx
# Eski: Nginx HTML serve ediyordu
# location / {
#     root /usr/share/nginx/html;
#     try_files $uri $uri/ /index.html;
# }

# Yeni: FastAPI'ye proxy
location / {
    proxy_pass http://app:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Static dosyalar nginx'ten serve edilebilir (opsiyonel, daha hızlı)
location /static/ {
    alias /app/static/;
    expires 7d;
    add_header Cache-Control "public, no-transform";
}
```

## 7. Deploy

```bash
cd /data/lumen
docker compose up -d --build app
docker compose restart nginx
```

## 8. Test

```bash
curl -k https://lumentest.fibabanka.local/
curl -k https://lumentest.fibabanka.local/anomaliler
curl -k https://lumentest.fibabanka.local/static/css/lumen.css
```

## Dosya Yapısı (Final)

```
/data/lumen/frontend/
├── templates/
│   ├── layouts/
│   │   └── base.html            ← Ana şablon (navbar + sidebar)
│   ├── includes/
│   │   ├── sidebar.html         ← {% include %}
│   │   └── navbar.html          ← {% include %}
│   └── pages/
│       ├── dashboard.html
│       ├── anomaliler.html
│       ├── zabbix_alarmlar.html
│       ├── incident_merkezi.html
│       ├── servis_topolojisi.html
│       ├── servis_sagligi.html
│       ├── vm_analiz.html
│       ├── entegrasyonlar.html
│       ├── kullanici_yonetimi.html
│       ├── servis_katalogu.html
│       ├── servis_haritasi.html
│       ├── hata_kodlari.html
│       ├── aksiyon_merkezi.html
│       └── denetim.html
└── static/
    ├── css/
    │   └── lumen.css            ← Tüm stiller (Adminator teması)
    └── js/
        └── lumen.js             ← Tema toggle + ortak fonksiyonlar
```
