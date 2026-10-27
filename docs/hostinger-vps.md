# Hostinger VPS deployment guide (Batch 08)

How to run Think Positive Always on one Hostinger VPS, with every file stored on the
server itself: public images, protected premium resources and uploads in progress. No
external object storage (S3, Cloudinary, Supabase Storage …) is used or needed.

> **Not deployed yet.** Nothing in this repository deploys to the live VPS, and
> production payments stay disabled until they are explicitly enabled in
> `/admin/payments` after the live-activation checklist (`docs/commerce.md`). Replace
> `example.com` with the confirmed domain.

Related guides: `docs/backups.md` (backups and tested recovery), `docs/resources.md`
(premium resources and secure delivery), `docs/deployment.md` (per-batch upgrade notes).

## 1. Choosing the VPS and region

**Audience.** Visitors are global and English-speaking, mostly in the United States.

| Choice                                 | Effect                                                                                                                            |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| US data centre (East coast if offered) | Lowest latency for most US visitors (very roughly 20–70 ms within the US, ~80–100 ms to Western Europe). Recommended.             |
| European data centre                   | Roughly 80–150 ms more for US visitors on uncached requests; fine for Europe.                                                     |
| Any region + CDN later                 | Static pages, assets and optimised images can be cached at the edge; premium files stay on the VPS and are never cached publicly. |

The region is chosen when the VPS is created (Hostinger shows the locations available
for each plan) and is not hard-coded anywhere in the application: domains, paths and
URLs all come from environment variables. Moving region later means restoring a backup
on a new VPS (`docs/backups.md`) and switching DNS.

**Why latency matters less than it seems here.** Public pages are prerendered static
HTML served by Nginx with compression and long-lived caching for assets and images, so a
visitor's first page needs only a few requests to the VPS; the API is used for the shop
cart, checkout and accounts.

**Size.** Start with at least 2 vCPU, 4 GB RAM and enough NVMe disk for: the database,
images (optimised versions plus retained originals), premium files _with all their
versions_, and **local backups** (several copies). Leave 30% free; `/admin/storage`
warns below 15% and treats 5% as critical (configurable).

## 2. Ubuntu server setup

Ubuntu 24.04 LTS is assumed.

```bash
# as root, once
adduser --disabled-password --gecos "" deploy          # your SSH login (sudo)
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
adduser --system --group --home /var/lib/tpa --no-create-home tpa   # runs the app
usermod -aG www-data tpa                                 # shares the Nginx group

# SSH: keys only
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/; s/^#\?PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl reload ssh

# Firewall: SSH, HTTP, HTTPS only (PostgreSQL and Redis stay on localhost)
ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable

apt update && apt -y upgrade
apt install -y nginx postgresql redis-server python3-venv python3-pip git curl \
  certbot unattended-upgrades fail2ban age rsync
dpkg-reconfigure -plow unattended-upgrades               # automatic security updates
timedatectl set-timezone UTC                             # logs and schedules in UTC
# Node 22 LTS for the frontend build (nodesource or nvm).
```

Hostinger's control panel may also offer its own firewall and snapshots; they complement
these settings but don't replace the backups in `docs/backups.md`.

## 3. PostgreSQL

```bash
sudo -u postgres createuser --pwprompt tpa
sudo -u postgres createdb --owner tpa tpa
```

PostgreSQL listens on localhost only (Ubuntu's default). Use a long random password and
put it in `DATABASE_URL`. `pg_dump`/`pg_restore` from the same major version are used by
the backup scripts.

## 4. Redis

Redis holds rate-limit counters so they are shared by all Gunicorn workers (with
`memory://` each worker would count separately and limits would be several times too
lenient). It stores nothing that needs a backup.

```bash
sudo sed -i 's/^# *maxmemory .*/maxmemory 64mb/; s/^# *maxmemory-policy .*/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
sudo systemctl enable --now redis-server            # bound to 127.0.0.1 by default
```

`.env`: `RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0`. `/admin/storage` warns in
production when rate limits still use memory. The background workers (publishing,
email) are database-backed queues and don't need Redis.

## 5. Persistent storage layout

All paths come from environment variables; this is the recommended layout:

```
/var/lib/tpa/                    tpa:www-data 0750
├── media/                       MEDIA_ROOT
│   ├── public/                  optimised images (WebP/AVIF/JPEG, all sizes incl.
│   │                            thumbnails), served by Nginx at /media/   0755
│   └── private/                 retained originals (camera metadata), never served   0700
├── resources/
│   └── private/                 PRODUCT_FILES_ROOT: premium files   0750 (group www-data)
│       ├── ebooks/  workbooks/  templates/  courses/  downloads/
│       └── <folder>/<file id>/v<n>/<random>.<ext>
├── temporary/
│   └── uploads/                 UPLOAD_TEMP_ROOT: uploads being received/validated   0700
└── backup-status.json           written by the backup job, read by /admin/storage
```

- **Originals are private.** The suggested layout put originals under `public/`; they
  are kept in `media/private/` instead because uploads can contain GPS and camera
  metadata. Public pages only ever use the optimised versions, which have metadata
  stripped. Existing image URLs (`/media/<id>/v<n>/…`) are unchanged.
- **Premium files** are outside every web root. Nginx can read them only through an
  `internal` location after Flask has authorised a download, so the folder is readable by
  the Nginx group (`www-data`) and by nobody else. When
  `PRODUCT_FILES_ACCEL_REDIRECT_PREFIX` is set the app creates files `0640` and folders
  `0750`; otherwise `0600`/`0700`.
- **Temporary uploads** must be on the same disk as the storage folders so finished
  files are moved into place with an atomic rename (the code also handles a different
  disk safely, by copying next to the destination first).

Create it:

```bash
sudo install -d -o tpa -g www-data -m 0750 /var/lib/tpa /var/lib/tpa/resources
sudo -u tpa bash -c 'cd /var/www/tpa/backend && set -a && . ./.env && set +a && .venv/bin/flask --app wsgi storage init'
sudo -u tpa bash -c 'cd /var/www/tpa/backend && set -a && . ./.env && set +a && .venv/bin/flask --app wsgi storage check'
```

`storage init` creates every folder with the right mode (idempotent). Production start-up
refuses to run if a private folder is inside a public web root or overlaps the media
folder.

**Moving an existing installation** (Batch 05–07 used `/var/lib/tpa/product-files`):
stop the API, `mv /var/lib/tpa/product-files /var/lib/tpa/resources/private`, update
`PRODUCT_FILES_ROOT` and the Nginx `alias`, start the API and run `flask storage check`.
Stored keys are relative, so nothing in the database changes. New uploads go into the
category folders; older files stay where they are.

## 6. Application

```bash
sudo install -d -o deploy -g deploy /var/www/tpa
git clone https://github.com/celestyne-dev/tpa.git /var/www/tpa
cd /var/www/tpa/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 640 .env && sudo chgrp tpa .env
```

### Environment variables (production)

| Variable                                                     | Value / note                                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| `FLASK_CONFIG`                                               | `production`                                                                         |
| `SECRET_KEY`, `JWT_SECRET_KEY`                               | long random values (`python3 -c "import secrets; print(secrets.token_urlsafe(64))"`) |
| `DATABASE_URL`                                               | `postgresql://tpa:…@127.0.0.1:5432/tpa`                                              |
| `SITE_URL`, `ADMIN_BASE_URL`, `CORS_ORIGINS`                 | `https://example.com`                                                                |
| `TRUST_PROXY`                                                | `1` (behind Nginx)                                                                   |
| `RATELIMIT_STORAGE_URI`                                      | `redis://127.0.0.1:6379/0`                                                           |
| `MEDIA_ROOT`                                                 | `/var/lib/tpa/media`                                                                 |
| `PRODUCT_FILES_ROOT`                                         | `/var/lib/tpa/resources/private`                                                     |
| `UPLOAD_TEMP_ROOT`                                           | `/var/lib/tpa/temporary/uploads`                                                     |
| `PRODUCT_FILES_ACCEL_REDIRECT_PREFIX`                        | `/_protected_downloads` (Nginx delivers files)                                       |
| `MEDIA_MAX_UPLOAD_MB`, `PRODUCT_FILE_MAX_MB`                 | image and premium upload limits (keep Nginx `client_max_body_size` one MB higher)    |
| `RESOURCE_FILE_FORMATS`                                      | `pdf,epub,docx,xlsx,zip` (remove what you don't sell)                                |
| `STORAGE_WARN_FREE_PERCENT`, `STORAGE_CRITICAL_FREE_PERCENT` | `15`, `5`                                                                            |
| `BACKUP_STATUS_FILE`                                         | `/var/lib/tpa/backup-status.json`                                                    |
| `MAIL_BACKEND=smtp`, `MAIL_SMTP_*`, `MAIL_FROM`              | transactional email                                                                  |
| `PAYSTACK_SECRET_KEY`                                        | `sk_test_…` until live payments are approved                                         |

Secrets live only in `.env` (and `/etc/tpa/backup.env`), never in Git.

```bash
set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade            # back up first on an existing database
.venv/bin/flask --app wsgi rbac sync
.venv/bin/flask --app wsgi cms seed-defaults
.venv/bin/flask --app wsgi admin create-superadmin --email owner@example.com --name "Owner"
```

## 7. Gunicorn, workers and timers (systemd)

Copy the examples from `deploy/systemd/` to `/etc/systemd/system/` (dropping
`.example`), adjust paths, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tpa-api tpa-publish-worker tpa-email-worker
sudo systemctl enable --now tpa-publish-due.timer tpa-media-prune.timer \
  tpa-storage-maintenance.timer tpa-backup.timer
```

| Unit                            | Purpose                                                                                                       |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `tpa-api`                       | Gunicorn (3 workers, 300 s timeout for large uploads), only writes to `/var/lib/tpa` and the instance folder  |
| `tpa-publish-worker`            | builds and switches prerendered releases                                                                      |
| `tpa-email-worker`              | sends queued email                                                                                            |
| `tpa-publish-due.timer`         | scheduled publishing                                                                                          |
| `tpa-media-prune.timer`         | removes replaced image versions after their retention period                                                  |
| `tpa-storage-maintenance.timer` | hourly: removes abandoned temporary uploads, runs `flask storage check` (fails the unit on critical problems) |
| `tpa-backup.timer`              | nightly backup (`docs/backups.md`)                                                                            |

## 8. React client and prerendered pages

The publishing worker builds the site (`npm run build`: client, SSR bundle, prerender)
into a new release and switches `/var/www/tpa-site/current` atomically. For the first
build:

```bash
cd /var/www/tpa/frontend && npm ci
VITE_SITE_URL=https://example.com VITE_ALLOW_INDEXING=false \
PRERENDER_API_URL=http://127.0.0.1:8000/api/v1 npm run build
```

Set `VITE_ALLOW_INDEXING=true` only for the launch build, once the domain is verified.

## 9. Nginx and HTTPS

```bash
sudo cp /var/www/tpa/deploy/nginx/tpa.conf.example /etc/nginx/sites-available/tpa
sudo ln -s /etc/nginx/sites-available/tpa /etc/nginx/sites-enabled/tpa
sudo rm -f /etc/nginx/sites-enabled/default
sudo install -d /var/www/letsencrypt
# First certificate (temporarily comment out the 443 server block, reload, then):
sudo certbot certonly --webroot -w /var/www/letsencrypt -d example.com -d www.example.com
sudo nginx -t && sudo systemctl reload nginx
```

Certbot installs a renewal timer; add `--deploy-hook "systemctl reload nginx"` to the
renewal config. The example config (validated with `nginx -t` on Nginx 1.24, Ubuntu
24.04's version):

- redirects HTTP to HTTPS, serves HTTP/2, TLS 1.2/1.3 (HSTS line ready to enable);
- serves prerendered HTML with a 5-minute revalidating cache, fingerprinted assets and
  `/media/` images for a year (`immutable`), built-in images for a week;
- gzip for text (Brotli optional with `ngx_brotli`);
- streams premium uploads to Flask (no buffering, 300 s);
- delivers premium files only through `internal` `/_protected_downloads/` after Flask's
  checks (`X-Accel-Redirect`), with `private, no-store`;
- keeps customer and admin pages `no-store` and `noindex`.

## 10. Monitoring

- **`/admin/storage`** (permission _View storage health_): disk space per storage area,
  folder permissions, missing or orphaned files, abandoned uploads, backup age and
  result, and recent upload errors.
- **`flask storage check`** (exit 0 ok, 1 warning, 2 critical) runs hourly via
  `tpa-storage-maintenance.timer`; `systemctl --failed` shows a critical result. Point
  any external monitor at failed systemd units, or run `flask storage check --json`.
- **Services:** `systemctl status tpa-*`, `journalctl -u tpa-api -f`.
- **Disk:** keep 30% free; grow the disk (or prune old premium file versions that were
  never sold, from the media library) before reaching the warning threshold.
- **Uptime:** an external HTTPS check of `/` and `/api/v1/health` from the US.

## 11. Global audience performance checklist

- Prerendered HTML, gzip, HTTP/2 and long-lived caching of assets and images.
- Responsive images: WebP/AVIF with `srcset`, explicit dimensions, lazy loading below the
  fold (Batch 03 pipeline, unchanged).
- Prices are shown in the currencies configured in the CMS (USD first by default) and
  the currency the visitor picks; they are never converted, because there is no
  authoritative exchange-rate source. The visitor's country is never guessed from the
  browser language.
- A CDN can be added later in front of Nginx for HTML, `/assets/` and `/media/`. Never
  cache `/api/`, `/account`, `/checkout`, `/purchases` or `/_protected_downloads/`.
  Original files always stay on the VPS.

## 12. Before go-live

1. `flask storage check` reports `ok`; `/admin/storage` shows no critical findings.
2. A backup ran, and a **test restore** onto a scratch database succeeded
   (`docs/backups.md` §4).
3. HTTPS works on every hostname; enable HSTS.
4. Payment settings still in test mode; live activation only after explicit approval.
5. Rate limits use Redis; email sending works (`MAIL_BACKEND=smtp`).
