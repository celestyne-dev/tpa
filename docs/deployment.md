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

Batch 08 adds verified, encrypted, monitored backups of the database, images and premium
files with a tested restore script: see `docs/backups.md`. Before a migration, run the
backup job by hand (`sudo systemctl start tpa-backup.service`) or at least:

```bash
pg_dump --format=custom --file=/var/backups/tpa-$(date +%F).dump "$DATABASE_URL"
# restore: pg_restore --clean --dbname "$DATABASE_URL" /var/backups/tpa-YYYY-MM-DD.dump
```

For a complete Hostinger VPS setup (Ubuntu, Nginx, Gunicorn, PostgreSQL, Redis, storage,
HTTPS, monitoring) see `docs/hostinger-vps.md`.

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

## Upgrading from Batch 04 (digital commerce)

```bash
cd /var/www/tpa && git fetch && git checkout <release tag or branch>
pg_dump --format=custom --file=/var/backups/tpa-$(date +%F)-pre-batch05.dump "$DATABASE_URL"
sudo mkdir -p /var/lib/tpa/product-files
sudo chown tpa:www-data /var/lib/tpa/product-files && sudo chmod 750 /var/lib/tpa/product-files
cd backend && .venv/bin/pip install -r requirements.txt
set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade                       # 758d4c510551
.venv/bin/flask --app wsgi rbac sync                        # should report all zeros
.venv/bin/flask --app wsgi commerce payments-status         # checkout: disabled
cd ../frontend && npm ci
sudo systemctl restart tpa-api tpa-publish-worker
cd ../backend && .venv/bin/flask --app wsgi publish request # rebuild with /shop product pages
```

New settings in `backend/.env` (all optional until you sell; see `backend/.env.example` and `docs/commerce.md`):

```bash
PRODUCT_FILES_ROOT=/var/lib/tpa/product-files      # private; never under a web root or MEDIA_ROOT
PRODUCT_FILES_ACCEL_REDIRECT_PREFIX=/_protected_downloads
# PRODUCT_FILES_SCAN_COMMAND=["clamdscan", "--no-summary", "--fdpass", "{path}"]
PAYSTACK_SECRET_KEY=sk_test_...                    # test key first; restrict .env to 600
PAYMENTS_LIVE_ALLOWED=false                        # true only after the live activation checklist
MAIL_BACKEND=smtp                                  # receipts and download instructions must arrive
```

- **Nginx.** Copy the new locations from `deploy/nginx/tpa.conf.example`:
  - the product file upload location (`client_max_body_size` = `PRODUCT_FILE_MAX_MB` + 1, request buffering off);
  - the `internal` `/_protected_downloads/` alias to `PRODUCT_FILES_ROOT`;
  - `no-store`/`noindex` for `/cart`, `/checkout` and `/account`.
  - Nginx (`www-data`) needs read access to `PRODUCT_FILES_ROOT` only when X-Accel-Redirect is used. Otherwise keep the directory `700` and owned by `tpa`.
- **Backups.** Back up `PRODUCT_FILES_ROOT` together with the database: entitlements reference file versions by storage key.
- **Webhook.** Paystack must reach `https://<domain>/api/v1/payments/paystack/webhook` (POST, no authentication other than the signature). Do not put it behind basic auth or a WAF rule that rewrites bodies, because the signature covers the raw body.
- **Workers.** The publishing worker now also expires unpaid orders and runs the optional malware scanner. Keep it running.
- **Checkout stays disabled** after the upgrade. Follow `docs/commerce.md` → "Paystack sandbox" for test mode and "Live activation checklist" before taking real payments.

Rollback: restore the dump with `pg_restore --clean` (preferred), or run `flask --app wsgi db downgrade`. The downgrade drops every commerce table (products, customers, orders, payments, entitlements) and removes the Batch 05 permissions. Private files stay on disk. Check out the previous release and repoint `current`.

## Upgrading from Batch 05 (newsletter)

```bash
pg_dump --format=custom --file=/var/backups/tpa-$(date +%F)-pre-batch06.dump "$DATABASE_URL"
cd /var/www/tpa/backend && set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade                  # 0ded798b0061
.venv/bin/flask --app wsgi rbac sync                   # should report all zeros
.venv/bin/flask --app wsgi newsletter seed-defaults    # starter templates + draft automations
sudo cp ../deploy/systemd/tpa-email-worker.service.example /etc/systemd/system/tpa-email-worker.service
sudo systemctl daemon-reload && sudo systemctl enable --now tpa-email-worker
sudo systemctl restart tpa-api
.venv/bin/flask --app wsgi newsletter status           # mode stays "disabled" until configured
```

Before bulk sending:

- Configure SMTP and `NEWSLETTER_FROM_EMAIL` on an authenticated domain (SPF, DKIM and DMARC from your provider; see `docs/newsletter.md`).
- Set `EMAIL_FEEDBACK_SECRET` and, for bounce and complaint handling, a provider webhook adapter.
- Send a test in **test** mode.
- Only then set `NEWSLETTER_LIVE_ALLOWED=true` and complete the checklist in `/admin/email-settings`.
- No Nginx change is needed: `/api/v1/newsletter/`, `/api/v1/lead-magnets/` and `/api/v1/email/` are served by the existing `/api/` location.

## Upgrading from Batch 06 (partnerships)

```bash
pg_dump --format=custom --file=/var/backups/tpa-$(date +%F)-pre-batch07.dump "$DATABASE_URL"
cd /var/www/tpa/backend && set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade                  # 4a65b8174c82 (new tables only)
.venv/bin/flask --app wsgi rbac sync                   # should report all zeros
sudo systemctl restart tpa-api tpa-publish-worker
.venv/bin/flask --app wsgi publish request             # rebuild: /advertise, partner form, labels
```

- Optional: set `PARTNERSHIP_NOTIFY_EMAIL` (with a sending `MAIL_BACKEND`) and `RATELIMIT_PARTNERSHIP_INQUIRY`.
- No Nginx change is needed: `/api/v1/partnership-inquiries`, `/api/v1/media-kit` and `/api/v1/go/` are served by the existing `/api/` location. With several Gunicorn workers, use Redis for `RATELIMIT_STORAGE_URI` so the inquiry limits are shared.
- The publishing worker already handles rebuilds at booking start and end times.

## Upgrading from Batch 07 (customer accounts, Batch 07.5)

No migration. Rebuild and restart:

```bash
cd /var/www/tpa/backend && set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db current                  # still 4a65b8174c82
sudo systemctl restart tpa-api
.venv/bin/flask --app wsgi publish request             # rebuild: /login, /register, … shells
```

- Optional: `CUSTOMER_SHORT_SESSION_HOURS` (default 12) for sessions without "Keep me signed in".
- New verification and reset emails link to `/verify-email#token=…` and `/reset-password#token=…`. Links in emails sent before the upgrade still work: the old `/account/…` addresses are prerendered as shells that redirect in the browser, keeping the token.
- No Nginx change: the new pages are static files in the release; the API routes are unchanged under `/api/`.

## Upgrading from Batch 07.5 (guest checkout, Batch 07.6)

One migration, `a136d95dd67c`. It is non-destructive: it allows a `guest` customer status and a `guest_access` token purpose, and adds `orders.is_guest`, `orders.guest_token_hash` and `download_grants.guest` with safe defaults. Back up first, as for every migration:

```bash
cd /var/www/tpa/backend && set -a && . ./.env && set +a
pg_dump "$DATABASE_URL" > ~/tpa-before-07-6.sql
.venv/bin/flask --app wsgi db upgrade                   # 4a65b8174c82 -> a136d95dd67c
sudo systemctl restart tpa-api
.venv/bin/flask --app wsgi publish request             # rebuild: /purchases shell, new checkout
```

- Optional settings (defaults shown in `backend/.env.example`): `GUEST_ACCESS_TTL_HOURS` (72), `GUEST_ORDER_ACCESS_HOURS` (168), `GUEST_ORDER_DOWNLOAD_HOURS` (24) and `RATELIMIT_GUEST_ACCESS`.
- Nginx: add `purchases` to the customer-area location so `/purchases` is `no-store` and `noindex`, as in `deploy/nginx/tpa.conf.example`. The page's prerendered shell is already `noindex`, and robots.txt disallows it.
- In test mode, guests can pay only where `PAYMENTS_TEST_CHECKOUT_PUBLIC` is set, which is refused in production; otherwise only signed-in test accounts can pay. Live payments stay off until enabled in `/admin/payments`.
- Downgrading refuses while guest buyer records exist, because orders and receipts depend on them.

## Upgrading from Batch 07.6 (VPS storage and premium resources, Batch 08)

One migration, `c3e8d1f20b47` (non-destructive): media categories, resource access rules
and related resources, entitlement expiry with two reserved sources (membership,
course), and the `storage.view` permission (granted to the Administrator and Website
Manager templates).

```bash
sudo systemctl start tpa-backup.service || pg_dump --format=custom --file=/var/backups/tpa-before-08.dump "$DATABASE_URL"
cd /var/www/tpa/backend && .venv/bin/pip install -r requirements.txt   # adds redis
set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade        # a136d95dd67c -> c3e8d1f20b47
.venv/bin/flask --app wsgi rbac sync         # should report zeros
.venv/bin/flask --app wsgi storage init      # creates temp/category folders, fixes modes
.venv/bin/flask --app wsgi storage check
sudo systemctl restart tpa-api tpa-publish-worker tpa-email-worker
.venv/bin/flask --app wsgi publish request   # rebuild: /resources page, access terms
```

- **Fix for Nginx delivery:** with `PRODUCT_FILES_ACCEL_REDIRECT_PREFIX` set, premium files
  must be readable by the Nginx group. Earlier releases created them owner-only, so Nginx
  answered 403. After upgrading, fix existing files once:
  `sudo chgrp -R www-data /var/lib/tpa/product-files && sudo find /var/lib/tpa/product-files -type d -exec chmod 0750 {} + && sudo find /var/lib/tpa/product-files -type f -exec chmod 0640 {} +`
  (use your `PRODUCT_FILES_ROOT`). `/admin/storage` reports it if it's still wrong.
- **New settings** (see `backend/.env.example`): `UPLOAD_TEMP_ROOT`
  (`/var/lib/tpa/temporary/uploads`), `RESOURCE_FILE_FORMATS`, `STORAGE_WARN_FREE_PERCENT`,
  `STORAGE_CRITICAL_FREE_PERCENT`, `BACKUP_STATUS_FILE`, `BACKUP_MAX_AGE_HOURS`, and
  `RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0` (install `redis-server`).
- **Optional move** to the Batch 08 layout (`/var/lib/tpa/resources/private`): see
  `docs/hostinger-vps.md` §5. Keys are relative, so no database change is needed.
- **New units:** `tpa-storage-maintenance.{service,timer}` and `tpa-backup.{service,timer}`
  (`deploy/systemd/`); `tpa-api.service` now uses a 300 s timeout and `ProtectSystem=strict`
  with `ReadWritePaths=/var/lib/tpa /var/www/tpa/backend/instance`.
- **Nginx:** update the `/_protected_downloads/` alias if you move premium files; the new
  example adds HTTPS, HTTP/2, cache headers for built-in images and a deny rule for storage
  paths.
- Downgrading refuses while membership or course entitlements exist.

## Upgrading from Batch 08.1 (text-based courses, Batch 09)

One migration, `d4f9a2c61e58` (additive): the course tables and ten `courses.*`
permissions with their default grants. No existing table changes.

```bash
sudo systemctl start tpa-backup.service || pg_dump --format=custom --file=/var/backups/tpa-before-09.dump "$DATABASE_URL"
cd /var/www/tpa/backend && set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade        # c3e8d1f20b47 -> d4f9a2c61e58
.venv/bin/flask --app wsgi rbac sync         # should report zeros
sudo systemctl restart tpa-api tpa-publish-worker
.venv/bin/flask --app wsgi publish request   # rebuild: /courses, course pages, /learn shells
```

- **Nginx:** add the `/learn` and `/certificates` locations from
  `deploy/nginx/tpa.conf.example` (client-only shells, `no-store`, `noindex`). Without them
  learner links would show the 404 page.
- **Scheduling:** scheduled courses are published by the existing `tpa-publish-due` timer;
  nothing new to install.
- **Worksheets** are ordinary product files (same storage, permissions and backups as
  Batch 08).
- **Payments:** course products use the existing checkout; live Paystack payments stay
  disabled until explicitly approved.
- Downgrading refuses while any course exists. See `docs/courses.md`.

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

Nginx serves the current release (`/var/www/tpa-site/current`), serves `/media/` from `MEDIA_ROOT/public` with immutable caching, sends paths without a static file to Flask `/_redirect/…` for CMS redirects (real 301/302/307/308 responses, otherwise the prerendered 404 page), gzips text, raises the upload body limit for `/api/v1/admin/media` and for product file uploads, serves paid downloads only through the internal `/_protected_downloads/` location, marks `/cart`, `/checkout` and `/account` as `no-store`/`noindex`, serves the admin shell for `/admin/*` with `no-store` and `noindex`, returns `404.html` with HTTP 404 for unknown URLs, applies legacy 301 redirects, caches `/assets/` immutably, and proxies `/api/` to Gunicorn.
