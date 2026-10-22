# Deployment (Linux VPS) — reference

> Not yet deployed. Domain names below are placeholders.

## Packages

```bash
sudo apt update && sudo apt install -y nginx postgresql python3-venv python3-pip git curl
# Node 22 LTS for building the frontend (e.g. via nodesource or nvm)
```

## Application

```bash
sudo mkdir -p /var/www/tpa && sudo chown $USER /var/www/tpa
git clone https://github.com/celestyne-dev/tpa.git /var/www/tpa
cd /var/www/tpa/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # set FLASK_CONFIG=production, SECRET_KEY, DATABASE_URL, CORS_ORIGINS, TRUST_PROXY=1
```

## API service (Gunicorn + systemd)

```bash
sudo cp deploy/systemd/tpa-api.service.example /etc/systemd/system/tpa-api.service
sudo systemctl daemon-reload && sudo systemctl enable --now tpa-api
curl http://127.0.0.1:8000/api/v1/health
```

## Frontend build

```bash
cd /var/www/tpa/frontend && npm ci
VITE_SITE_URL=https://example.com VITE_ALLOW_INDEXING=false \
PRERENDER_API_URL=http://127.0.0.1:8000/api/v1 npm run build
```

Set `VITE_ALLOW_INDEXING=true` only for the launch build, after the domain is verified.

## Nginx

```bash
sudo cp deploy/nginx/tpa.conf.example /etc/nginx/sites-available/tpa
sudo cp deploy/nginx/redirects.conf.example /etc/nginx/snippets/tpa-redirects.conf
sudo ln -s /etc/nginx/sites-available/tpa /etc/nginx/sites-enabled/tpa
sudo nginx -t && sudo systemctl reload nginx
# TLS: sudo certbot --nginx -d example.com -d www.example.com
```

Nginx serves the prerendered files, returns `404.html` with HTTP 404 for unknown URLs, applies legacy 301 redirects, caches `/assets/` immutably, and proxies `/api/` to Gunicorn.
