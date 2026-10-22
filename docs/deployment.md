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

## Directories and permissions (Batch 03)

```bash
sudo useradd --system --home /var/www/tpa --shell /usr/sbin/nologin tpa   # if not present
sudo mkdir -p /var/lib/tpa/media /var/www/tpa-site/releases
sudo chown -R tpa:www-data /var/lib/tpa/media /var/www/tpa-site /var/www/tpa/frontend /var/www/tpa/backend/instance
sudo chmod 750 /var/lib/tpa/media && sudo chmod 2755 /var/www/tpa-site
# backend/.env
MEDIA_ROOT=/var/lib/tpa/media                 # public/ is served by Nginx at /media, private/ never
PUBLISH_RELEASES_DIR=/var/www/tpa-site/releases
PUBLISH_CURRENT_LINK=/var/www/tpa-site/current
FRONTEND_BUILD_MANIFEST=/var/www/tpa-site/current/prerender-manifest.json
FRONTEND_DIR=/var/www/tpa/frontend
PUBLISH_API_URL=http://127.0.0.1:8000/api/v1
SITE_URL=https://example.com
```

Nginx (user `www-data`) needs read access to `/var/lib/tpa/media/public` and `/var/www/tpa-site`, but not to `/var/lib/tpa/media/private`, which holds the retained originals: `sudo chmod 750 /var/lib/tpa/media/private` (owner `tpa`).

## Publishing worker and scheduling

```bash
sudo cp deploy/systemd/tpa-publish-worker.service.example /etc/systemd/system/tpa-publish-worker.service
sudo cp deploy/systemd/tpa-media-prune.service.example /etc/systemd/system/tpa-media-prune.service
sudo cp deploy/systemd/tpa-media-prune.timer.example /etc/systemd/system/tpa-media-prune.timer
sudo systemctl daemon-reload
sudo systemctl enable --now tpa-publish-worker tpa-media-prune.timer
journalctl -u tpa-publish-worker -f
```

The worker polls every 5 seconds. It publishes due scheduled articles (idempotent and locked), then runs queued builds one at a time: `npm run build` against `PUBLISH_API_URL`, verification, a copy to a new release directory and an atomic `current` symlink switch. A failed build leaves the live release in place and is retried with backoff. Build history and retries are in `/admin/publishing`.

Optional: run the scheduler from a timer instead (`tpa-publish-due.service`/`.timer`) and start the worker with `--no-scheduler`.

First release after upgrading: `flask --app wsgi publish request && sudo systemctl start tpa-publish-worker`, then point Nginx `root` at `/var/www/tpa-site/current`.

**Cloud/CDN deployment** is not configured. To mirror each release elsewhere, set `PUBLISH_DEPLOY_COMMAND` (a JSON argv, e.g. rsync to a CDN origin). CDN cache purging must be added per provider.

## API service (Gunicorn + systemd)

```bash
sudo cp deploy/systemd/tpa-api.service.example /etc/systemd/system/tpa-api.service
sudo systemctl daemon-reload && sudo systemctl enable --now tpa-api
curl http://127.0.0.1:8000/api/v1/health
```

## Upgrading from Batch 02

```bash
cd /var/www/tpa && git fetch && git checkout <release tag or branch>
pg_dump --format=custom --file=/var/backups/tpa-$(date +%F)-pre-batch03.dump "$DATABASE_URL"
cd backend && .venv/bin/pip install -r requirements.txt     # adds Pillow
set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade                       # a817c9636960
.venv/bin/flask --app wsgi rbac sync                        # should report all zeros
cd ../frontend && npm ci
sudo systemctl restart tpa-api && sudo systemctl enable --now tpa-publish-worker
```

Rollback: stop the worker, restore the dump with `pg_restore --clean`, or run `flask --app wsgi db downgrade` (drops the Batch 03 tables and columns, including revisions, redirects and jobs; uploaded files stay on disk), check out the previous release, and point Nginx back at the previous `dist/`.

## Upgrading from Batch 03

```bash
cd /var/www/tpa && git fetch && git checkout <release tag or branch>
pg_dump --format=custom --file=/var/backups/tpa-$(date +%F)-pre-batch04.dump "$DATABASE_URL"
cd backend && .venv/bin/pip install -r requirements.txt
set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade                       # de3d968df6ce
.venv/bin/flask --app wsgi rbac sync                        # should report all zeros
cd ../frontend && npm ci
sudo systemctl restart tpa-api tpa-publish-worker
cd ../backend && .venv/bin/flask --app wsgi publish request # first rebuild with CMS header/footer/branding
```

No new environment variables are required. The migration keeps the existing homepage and published pages exactly as they were (see the README, "Upgrading to Batch 04"). Generated favicons are written under `MEDIA_ROOT/public/branding/`, so the existing `/media/` Nginx location serves them. CMS pages are prerendered to `<path>/index.html` in each release, so no Nginx change is needed.

Rollback: stop the worker, restore the dump with `pg_restore --clean` (preferred), or run `flask --app wsgi db downgrade` (converts sections back and drops page revisions, shared sections, global CTAs and announcements), check out the previous release, and repoint `current` at the previous release directory.

## Frontend build (manual)

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

Nginx serves the current release (`/var/www/tpa-site/current`), serves `/media/` from `MEDIA_ROOT/public` with immutable caching, sends paths without a static file to Flask `/_redirect/…` for CMS redirects (real 301/302/307/308 responses, otherwise the prerendered 404 page), gzips text, raises the upload body limit for `/api/v1/admin/media`, and serves serves the admin shell for `/admin/*` with `no-store` and `noindex`, returns `404.html` with HTTP 404 for unknown URLs, applies legacy 301 redirects, caches `/assets/` immutably, and proxies `/api/` to Gunicorn.
