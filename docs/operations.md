# Operations runbook: staging deployment (Batch 12.3)

How to deploy Think Positive Always to **staging** on one Ubuntu 24.04 VPS and keep it
running. The stack is Nginx, Gunicorn/Flask, PostgreSQL 16, Redis, the React/Vite
prerendered site and systemd.

> **Nothing here has been run against the VPS yet.** Live Paystack payments stay
> disabled. Staging uses `sk_test_` keys, `PAYMENTS_LIVE_ALLOWED=false` and
> `MEMBERSHIP_BILLING_MODE=disabled`; `flask deploy check` reports anything else.

Related guides:

- `docs/hostinger-vps.md`: server setup, storage layout, Redis, monitoring.
- `docs/backups.md`: the backup and restore scripts in detail.
- `docs/deployment.md`: per-batch upgrade notes.
- `docs/security-hardening.md` and `docs/performance.md`: Batches 12.1 and 12.2.

## 1. Prerequisites

| Item | Notes |
|------|-------|
| VPS | Ubuntu 24.04 LTS, at least 2 vCPU, 4 GB RAM, NVMe with 30% free after backups |
| DNS | `staging.<domain>` A/AAAA record pointing at the VPS (staging until launch) |
| Packages | `nginx postgresql redis-server python3-venv git certbot age rsync fail2ban unattended-upgrades`, Node 22 LTS (`docs/hostinger-vps.md` §2) |
| Users | `deploy` (SSH, sudo), `tpa` (system user that runs the app, in group `www-data`) |
| Secrets | `SECRET_KEY`, `JWT_SECRET_KEY`, the DB password, SMTP credentials and **Paystack test keys**. Generate each on the server and keep a copy in the password manager. Never use production credentials on staging. |
| Off-server backup | An age key pair (secret key **offline**) and an rclone/rsync target |
| Firewall | `ufw`: OpenSSH and "Nginx Full" only. PostgreSQL and Redis listen on localhost only. |

## 2. Files in this repository

| File | Install as |
|------|------------|
| `deploy/nginx/tpa.conf.example` | `/etc/nginx/sites-available/tpa` |
| `deploy/nginx/tpa-security-headers.conf.example` | `/etc/nginx/snippets/tpa-security-headers.conf` (**required**, included by `tpa.conf`) |
| `deploy/nginx/redirects.conf.example` | `/etc/nginx/snippets/tpa-redirects.conf` (optional legacy redirects) |
| `deploy/env/staging.env.example` | starting point for `/var/www/tpa/backend/.env` (the full list is in `backend/.env.example`) |
| `deploy/systemd/*.example` | `/etc/systemd/system/<name>` without `.example` |
| `deploy/backup/backup.env.example` | `/etc/tpa/backup.env` (`chmod 600`, root) |

## 3. Staging deployment procedure

Follow `docs/hostinger-vps.md` §2–§6 for the server, PostgreSQL, Redis, storage and the
application checkout. Then:

```bash
cd /var/www/tpa && git fetch && git checkout <release tag or commit>   # record it
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../deploy/env/staging.env.example .env        # fill in every CHANGE-ME
sudo chown deploy:tpa .env && sudo chmod 640 .env
set -a && . ./.env && set +a

# 1. Preflight: configuration only. No changes are made and no secrets are printed.
.venv/bin/flask --app wsgi deploy check          # must finish with "status: ok" or warnings only
# 2. Schema and defaults (take a backup first on an existing database).
.venv/bin/flask --app wsgi db upgrade            # head: a7c2e9f4b318
.venv/bin/flask --app wsgi rbac sync
.venv/bin/flask --app wsgi cms seed-defaults
.venv/bin/flask --app wsgi storage init && .venv/bin/flask --app wsgi storage check
.venv/bin/flask --app wsgi deploy check          # now also checks the schema revision
```

**Exit codes:** `flask deploy check` exits 0 (ok), 1 (warnings) or 2 (errors).

**What it checks:**

- `FLASK_CONFIG`;
- secret length, placeholders and that the two keys differ;
- that PostgreSQL is reachable and the schema is at head;
- `TRUST_PROXY`;
- that Redis is used and reachable;
- that `SITE_URL`, `ADMIN_BASE_URL` and `CORS_ORIGINS` are HTTPS;
- Secure, CSRF-protected and SameSite cookies;
- `PAYMENTS_LIVE_ALLOWED`, the Paystack key mode, the admin checkout mode and
  `MEMBERSHIP_BILLING_MODE`;
- that mail is configured, that Nginx serves media and downloads, that `PUBLISH_API_URL`
  is loopback, and `BACKUP_STATUS_FILE`.

Fix every error before continuing.

**Services and timers** (§5 lists what each does):

```bash
sudo cp /var/www/tpa/deploy/systemd/*.example /etc/systemd/system/
cd /etc/systemd/system && for f in tpa-*.example; do sudo mv "$f" "${f%.example}"; done
sudo systemctl daemon-reload
sudo systemctl enable --now tpa-api tpa-publish-worker tpa-email-worker
sudo systemctl enable --now tpa-analytics-maintain.timer tpa-membership-reconcile.timer \
  tpa-storage-maintenance.timer tpa-media-prune.timer tpa-backup.timer
# Do NOT enable tpa-publish-due.timer: the publishing worker already runs that scheduler.
```

**First site build, then Nginx and TLS (§6):**

```bash
cd /var/www/tpa/backend && .venv/bin/flask --app wsgi publish request
journalctl -u tpa-publish-worker -f              # wait for "Job N: succeeded"
```

Keep `VITE_ALLOW_INDEXING=false` on staging, so search engines don't index it.

## 4. Gunicorn, restarts and health checks

**Workers.** The API uses synchronous workers.

- **How many:** start with `2 × vCPU + 1` as a ceiling and less if RAM is tight. Each
  worker uses roughly 120–200 MB after warm-up, and image uploads use more for a moment.
  `--workers 3` suits 2 vCPU / 4 GB.
- **Timeouts:** `--timeout 300` covers synchronous image optimisation and premium-file
  uploads. `--graceful-timeout 30` lets requests in progress finish on reload or stop.
- **Buffering:** Nginx buffers request and response bodies, so slow clients don't hold a
  worker. The exception is premium-file uploads, which are streamed on purpose; see §10.
- **Shared rate limits:** limits are only shared between workers through Redis
  (`RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0`). If Redis stops, the API keeps
  working with per-worker counters (`RATELIMIT_IN_MEMORY_FALLBACK_ENABLED=true`). Limits
  stay on but are looser until Redis is back; `flask deploy check` and
  `/api/v1/health/ready` show it.

**Trusted proxy.**

- `TRUST_PROXY=1` makes Flask trust exactly **one** proxy. It takes the right-most
  `X-Forwarded-For` entry, which Nginx appends with the real client address, so a value a
  client sends in front of it is ignored.
- Nginx sets `X-Forwarded-Proto` and `X-Forwarded-Host` itself, so client values never
  reach Flask. The one-proxy assumption is tested in `backend/tests/test_deploy_config.py`.
- **If a CDN or load balancer is ever put in front of Nginx,** this trust must be changed
  (Nginx `real_ip_from` or a higher `x_for`). Otherwise every visitor appears to come from
  the CDN.

**Restarts.**

| Change | Command |
|--------|---------|
| Python code or `.env` (normal deploy) | `sudo systemctl reload tpa-api` (HUP: new workers start on the new code, old ones finish their request), then `sudo systemctl restart tpa-publish-worker tpa-email-worker` |
| Gunicorn options or the unit file | `sudo systemctl daemon-reload && sudo systemctl restart tpa-api` |
| Nginx config | `sudo nginx -t && sudo systemctl reload nginx` (never restart a config that failed `-t`) |
| Redis | `sudo systemctl restart redis-server` (counters reset; nothing else is stored) |
| Timers | `sudo systemctl daemon-reload` after editing; the next run picks it up |

The workers stop cleanly on SIGTERM:

- the publishing worker finishes its poll, and an interrupted build is retried;
- the email worker records its batch, with up to 60 s allowed.

**Health checks.**

| URL | Meaning | Use |
|-----|---------|-----|
| `GET /api/v1/health` | Liveness: the API process answers. Checks no dependencies. | Uptime monitor |
| `GET /api/v1/health/ready` | Readiness: the database and the rate-limit storage answer. 200 when ready, 503 otherwise. Reports only `ok`/`unavailable`. | After each deploy or restart, and in monitoring |
| `flask storage check` | Disk, folder modes, missing files, backup age (exit 0, 1 or 2) | Hourly timer; `systemctl --failed` |
| `flask deploy check` | Configuration (exit 0, 1 or 2) | Before every deploy |

```bash
curl -fsS https://staging.example.com/api/v1/health/ready
systemctl --failed; systemctl list-timers 'tpa-*'
journalctl -u tpa-api -u tpa-publish-worker -u tpa-email-worker --since -1h
```

## 5. Scheduled jobs (no duplicates)

| Unit | Schedule | What it does |
|------|----------|--------------|
| `tpa-publish-worker` (service) | every 5 s | Site builds and releases; due articles, pages and courses; visibility windows; expiry of unpaid orders; malware scans of new premium files |
| `tpa-email-worker` (service) | every 10 s | Email queue, scheduled campaigns, automations |
| `tpa-analytics-maintain.timer` | hourly at :05 | Analytics rollups and retention |
| `tpa-membership-reconcile.timer` | hourly | Membership grace, expiry, cancellations, early webhooks |
| `tpa-storage-maintenance.timer` | hourly | Removes abandoned uploads, then `flask storage check` |
| `tpa-media-prune.timer` | daily | Deletes image variants superseded more than `MEDIA_SUPERSEDED_RETENTION_DAYS` ago |
| `tpa-backup.timer` | 03:10 daily | Database and files backup, verification, off-server copy, retention |
| `tpa-publish-due.timer` | *not enabled* | Only for a worker started with `--no-scheduler` |

Every job is idempotent and locked where overlap matters, so a missed run catches up
(`Persistent=true`). Nothing else needs scheduling: entitlements expire by their own
dates, and Redis needs no maintenance. The `systemd-analyze verify` and command checks in
`test_deploy_config.py` keep the units valid.

## 6. TLS certificates and cookie security

**First certificate.** The full site config refers to the certificate, so get it with a
port-80-only site first:

```bash
sudo install -d /var/www/letsencrypt
sudo tee /etc/nginx/sites-available/tpa-acme >/dev/null <<'EOF'
server {
    listen 80; listen [::]:80;
    server_name staging.example.com;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 404; }
}
EOF
sudo ln -sf /etc/nginx/sites-available/tpa-acme /etc/nginx/sites-enabled/tpa-acme
sudo rm -f /etc/nginx/sites-enabled/default && sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/letsencrypt -d staging.example.com \
  --deploy-hook "systemctl reload nginx"
```

**Then the real site.** Copy the site config and the snippet, set the domain, swap the
sites:

```bash
sudo cp /var/www/tpa/deploy/nginx/tpa.conf.example /etc/nginx/sites-available/tpa
sudo cp /var/www/tpa/deploy/nginx/tpa-security-headers.conf.example \
  /etc/nginx/snippets/tpa-security-headers.conf
sudo sed -i 's/example\.com/staging.example.com/g' /etc/nginx/sites-available/tpa
sudo rm /etc/nginx/sites-enabled/tpa-acme && sudo ln -sf /etc/nginx/sites-available/tpa /etc/nginx/sites-enabled/tpa
sudo nginx -t && sudo systemctl reload nginx
```

**Renewal.**

- Certbot's systemd timer renews automatically. The `--deploy-hook` above is stored in
  `/etc/letsencrypt/renewal/<domain>.conf` and reloads Nginx after each renewal.
- Check with `sudo certbot renew --dry-run` and `systemctl list-timers certbot.timer`.
- Monitor expiry from outside, for example by checking that the uptime monitor's TLS
  certificate is valid for more than 14 days.

**HSTS.** Enable it in `/etc/nginx/snippets/tpa-security-headers.conf` only once HTTPS
works on every hostname that shares the parent domain. Start with `max-age=300`, then
raise it to `31536000`. Browsers remember it, so it can't be undone quickly.

**Header and cookie checks** after each Nginx change:

```bash
H=https://staging.example.com
for p in / /admin /media/ /api/v1/health; do echo "== $p"; curl -sI "$H$p" | grep -iE 'x-content-type|referrer-policy|x-frame|cache-control'; done
curl -sI http://staging.example.com/ | grep -i location        # 301 to https
curl -s -o /dev/null -w '%{http_code}\n' "$H/_protected_downloads/x"   # 404
curl -s -o /dev/null -w '%{http_code}\n' "$H/.env"                     # 404
curl -sk --resolve evil.test:443:<VPS IP> https://evil.test/ -o /dev/null -w '%{http_code}\n' || echo refused   # refused
```

Then sign in to `/admin` and to a customer account, and check the cookies in the
browser's developer tools (Application → Cookies):

- **Every** TPA cookie is `Secure`.
- Admin access and refresh cookies are `HttpOnly` with `SameSite=Strict`. The
  `csrf_*` cookies are readable by design.
- The customer session cookie is `HttpOnly`. The customer CSRF cookie is readable by
  design.

`flask deploy check` reports the matching settings.

## 7. Rate limiting with Redis

Install and limit Redis as in `docs/hostinger-vps.md` §4: localhost only, 64 MB,
`allkeys-lru`. Set:

```
RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0
RATELIMIT_KEY_PREFIX=tpa-staging        # separate prefix if production shares the Redis
```

**Verify** (from your computer, not the VPS):

```bash
for i in $(seq 1 6); do curl -s -o /dev/null -w '%{http_code} ' -X POST \
  -H 'Content-Type: application/json' -H "Origin: $H" \
  -d '{"email":"nobody@example.com","password":"x"}' "$H/api/v1/admin/auth/login"; done; echo
# expect: 401 401 401 401 401 429. A second address (e.g. phone on mobile data) still gets 401.
redis-cli --scan --pattern 'tpa-staging*' | head   # on the VPS: counters exist
```

If every client gets 429 after a few attempts, `TRUST_PROXY` is off: all clients appear
as 127.0.0.1.

## 8. PostgreSQL backups and recovery

The job and scripts are described in `docs/backups.md`. Key points for staging:

**Schedule and retention.** Backups run nightly at 03:10 (`tpa-backup.timer`). The
script keeps the newest 7 daily backups, plus the newest of each of the last 4 weeks and
6 months (`BACKUP_KEEP_*`). Each backup is verified with checksums,
`pg_restore --list` and tar listings before it counts. The result goes to
`BACKUP_STATUS_FILE` and is shown in `/admin/storage`, with a warning after 36 hours.

**Secrets.**

- `/etc/tpa/backup.env` is root-only (`chmod 600`).
- The database password is passed to the PostgreSQL tools through `PGPASSWORD`, never on
  the command line (which other local users could see with `ps`; Batch 12.3). Both
  `postgresql://` and the application's `postgresql+psycopg://` URL forms work.
- Off-server copies are age-encrypted to public keys; the secret key stays offline.

**Before every deploy that migrates:**
`sudo systemctl start tpa-backup.service && journalctl -u tpa-backup -n 20`.

**Recovery verification drill:** monthly, and after any backup configuration change.

```bash
sudo /var/www/tpa/deploy/backup/tpa-restore.sh --from /var/backups/tpa/latest --verify-only
sudo -u postgres createdb --owner tpa tpa_restore_test
sudo PGPASSWORD='…' /var/www/tpa/deploy/backup/tpa-restore.sh --from /var/backups/tpa/latest \
  --database postgresql://tpa@127.0.0.1/tpa_restore_test \
  --media-root /var/tmp/tpa-drill/media --resources-root /var/tmp/tpa-drill/private --yes
sudo -u postgres psql -d tpa_restore_test -Atc "select version_num from alembic_version; select count(*) from orders;"
sudo -u postgres dropdb tpa_restore_test && sudo rm -rf /var/tmp/tpa-drill
```

Record the date, backup name, revision and row counts. Restore the off-server copy (the
`.tar.age` file with your offline key) at least once a quarter: it is the copy that
matters if the VPS is lost. `backend/tests/test_backup_scripts.py` runs the full backup,
encrypted off-server copy and restore cycle against PostgreSQL in CI or WSL (set
`TEST_DATABASE_URL`).

## 9. Files, media and storage permissions

| Path | Owner:group | Mode | Backed up | Recovery |
|------|-------------|------|-----------|----------|
| `/var/lib/tpa/media/public` | tpa:www-data | 0755 | `media.tar` | restore; `flask media verify` lists any missing variant files |
| `/var/lib/tpa/media/private` (originals) | tpa:www-data | 0700 | `media.tar` | restore only (no other copy) |
| `/var/lib/tpa/resources/private` (premium files) | tpa:www-data | 0750, files 0640 | `resources.tar` | restore only; entitlements reference these keys |
| `/var/lib/tpa/temporary/uploads` | tpa | 0700 | no | transient |
| `/var/www/tpa-site/releases`, `current` | tpa:www-data | 2755 | no | rebuilt by `flask publish request` |
| `/var/www/tpa/backend/.env` | deploy:tpa | 0640 | **no** | from the password manager |
| `/etc/tpa/backup.env`, `/var/backups/tpa` | root | 0600 / 0700 | no / itself | from the password manager |

Nginx (`www-data`) reads `media/public`, the release folders and, only through the
`internal` `/_protected_downloads/` location, premium files. `flask storage check` and
`/admin/storage` report wrong modes and missing files.

**After a restore:**

```bash
sudo chown -R tpa:www-data /var/lib/tpa/media /var/lib/tpa/resources/private
flask storage check
```

## 10. Rollback

Record the release tag or commit, the Alembic revision and the backup name before each
deploy (`flask db current`, `ls -l /var/backups/tpa/latest`).

1. **Site content only** (bad build): point `current` at the previous release:
   `ls /var/www/tpa-site/releases`, then
   `sudo -u tpa ln -sfn /var/www/tpa-site/releases/<previous> /var/www/tpa-site/current`.
   Nginx picks it up within 10 s.
2. **Code without a migration:**
   ```bash
   git checkout <previous tag>
   .venv/bin/pip install -r requirements.txt
   sudo systemctl reload tpa-api
   sudo systemctl restart tpa-publish-worker tpa-email-worker
   ```
3. **Code with a migration:**
   ```bash
   sudo systemctl stop tpa-api tpa-publish-worker tpa-email-worker
   # restore the pre-deploy backup into a new database (docs/backups.md §3), point
   # DATABASE_URL at it, git checkout <previous tag>, then start the services
   ```
   `flask db downgrade` is possible for the latest batches, but several downgrades refuse
   while dependent data exists. A restore is the dependable route.
4. **Nginx:** keep the previous file (`/etc/nginx/sites-available/tpa.bak`). Restore it,
   then run `nginx -t` and reload.
5. **After any rollback:** run `flask deploy check`, `curl /api/v1/health/ready` and the
   §11 checks.

## 11. Post-deploy verification checklist

- [ ] `flask deploy check`: no errors; `flask storage check`: `ok`.
- [ ] `/api/v1/health/ready` answers 200 with `database` and `rate_limit_storage` `ok`.
- [ ] `systemctl --failed` is empty; `systemctl list-timers 'tpa-*'` shows 5 timers.
- [ ] Headers and cookies as in §6; HTTP redirects to HTTPS; unknown hostnames are refused.
- [ ] Rate limit test from §7: 429 after 5 failed logins for one client only.
- [ ] Public pages, `/shop`, `/courses`, `/membership` load. A deep link
      (`/articles/<slug>`, `/learn/<course>`) and an unknown URL (404 page, status 404) work.
- [ ] Admin sign-in works. A role without a permission can't open that area (403 from
      the API).
- [ ] Image upload (up to 20 MB), premium file upload, and an assignment document over 2 MB
      all succeed: no 413 from Nginx.
- [ ] Paystack **test** checkout with a test account: payment verified, then download
      works; `/_protected_downloads/...` opened directly gives 404.
      `flask commerce payments-status` shows `test`. Nothing is in live mode.
- [ ] Paystack test webhook reaches `/api/v1/payments/paystack/webhook`; a replay is ignored.
- [ ] A scheduled article publishes within a minute; the site rebuild succeeds.
- [ ] `sudo systemctl start tpa-backup.service` succeeds; `--verify-only` on `latest` passes.
- [ ] `certbot renew --dry-run` succeeds.

## 12. Remaining operational risks

- **Single VPS.** The database, files, Redis and the site all share one machine and one
  disk. The off-server encrypted copy is the only protection against losing the server.
  Set it up before real data arrives.
- **Recovery point.** Up to about 24 hours of data can be lost with nightly backups. Run
  the job more often once orders are frequent. There is no point-in-time recovery (WAL
  archiving).
- **Monitoring.** There is no external alerting by default. Add an uptime check on
  `/api/v1/health/ready`, TLS expiry monitoring and something that reports failed systemd
  units (email or push).
- **Uploads.** Premium-file uploads are streamed to synchronous workers, so a slow
  300 MB upload holds one of three workers for the duration.
- **Secrets on disk.** Secrets are plaintext in `.env` and `backup.env`, protected by file
  permissions. Rotate them if the server is ever compromised.
- **Redis outage.** Limits fall back to per-worker counting, so they are looser until
  Redis returns.
- **Proxy trust.** It assumes Nginx is the only proxy (see §4).
- **Shared Redis.** Staging and production must not share a database or Paystack keys. If
  they share a Redis instance, use different `RATELIMIT_KEY_PREFIX` values.
