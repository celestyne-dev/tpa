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
cp .env.example .env    # set FLASK_CONFIG=production, SECRET_KEY, JWT_SECRET_KEY, DATABASE_URL,
                        # CORS_ORIGINS=https://your-domain, TRUST_PROXY=1, RATELIMIT_STORAGE_URI
                        # MAIL_BACKEND=smtp + MAIL_SMTP_* + MAIL_FROM, ADMIN_BASE_URL=https://your-domain
set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade            # back up first on existing databases
.venv/bin/flask --app wsgi cms seed-defaults     # safe: creates only missing defaults
.venv/bin/flask --app wsgi admin create-superadmin --email owner@your-domain --name "Owner"
# Do NOT run `seed sample-content` in production (it refuses unless --allow-production).
```

## Backups

```bash
pg_dump --format=custom --file=/var/backups/tpa-$(date +%F).dump "$DATABASE_URL"
# restore: pg_restore --clean --dbname "$DATABASE_URL" /var/backups/tpa-YYYY-MM-DD.dump
```

Back up before every migration, and keep off-server copies.

## Scheduled publishing (optional)

Scheduled articles go live only when `flask --app wsgi content publish-due` runs, followed by a rebuild. You can run both from a systemd timer or cron job, for example every 15 minutes, with `scripts/build-production.sh` pointing at the live API.

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

Nginx serves the prerendered files, serves the admin shell for `/admin/*` with `no-store` and `noindex`, returns `404.html` with HTTP 404 for unknown URLs, applies legacy 301 redirects, caches `/assets/` immutably, and proxies `/api/` to Gunicorn.
