# Technical release: runbook (staging rehearsal, then production)

The coordinated technical-foundation release:

- crawlable pagination
- search
- author pages
- inline links and sources
- material "Last updated" dates
- structured data
- AI crawler policy and RSS
- two-step sign-in
- Content-Security-Policy
- request ids
- environment isolation checks
- CI

Nothing here changes article content, slugs, canonicals, author assignments or publication dates. Both migrations only add nullable columns, with no backfill.

> **Order:** baseline → staging rehearsal → your sign-off → production. Nothing deploys automatically. CI only tests and builds.

## 0. Production baseline (read-only, before anything else)

Run on the VPS:

```bash
sudo /var/www/tpa-staging/deploy/verify/tpa-baseline.sh thinkpositivealways.com /var/www/tpa-production-site 8101
```

It prints:

- the nginx server blocks for the domain (root, proxies, includes) and the upstream ports
- the active release (`current` symlink target) and its prerender manifest
- the built homepage's markers, compared with what the origin serves at 127.0.0.1 and what the public URL serves. Cache headers (`Age`, `CF-Cache-Status`, `Via`, `X-Cache`) show whether anything in front is serving a stored copy.
- TPA services and timers, the legacy `tpa-backend.service` state, and listening ports 80/443/5000/8000/8100/8101
- for every TPA hostname nginx serves: certificate names and expiry, whether HTTP redirects to HTTPS, and any HSTS header

It changes nothing, and prints no environment values. Keep the output with the release notes.

**How to read it:**

- **The origin and the built homepage match** (theme-color `#f7f2e8`, no `/uploads/` references, `/assets/` scripts): the server serves the rebuild. Any older page seen elsewhere is a cache or a search index, not the server.
- **The public response differs from the origin:** something in front (a CDN or proxy) or a browser cache holds an old copy. Purge it there; nothing on the server needs to change.
- After this release every page carries `<meta name="tpa-build" content="<commit>">`, and `/api/v1/health` reports `release` and `tier`, so "which code is live?" is a one-line check.

## 1. Staging rehearsal

Environments (each with its own database, Redis prefix, folders and API port):

| | Staging | Production |
|---|---|---|
| API | 127.0.0.1:8100 | 127.0.0.1:8101 |
| Database | `tpa_staging` | `tpa_production` |
| Site | `https://staging.thinkpositivealways.com` | `https://thinkpositivealways.com` |
| `TPA_ENVIRONMENT` | `staging` | `production` |

1. **Back up staging:** `deploy/backup/tpa-backup.sh` (see `docs/backups.md`).
2. **Check out the release branch** in `/var/www/tpa-staging`, then update dependencies:
   - `pip install -r backend/requirements.txt` (no new Python packages)
   - `npm ci` in `frontend/`
3. **Settings:** add `TPA_ENVIRONMENT=staging` and `TPA_RELEASE=$(git rev-parse --short HEAD)` to the staging `.env`, then run `flask --app wsgi deploy check`. It must report no errors. It now refuses any production database, Redis prefix, folder or port (8101).
4. **Database:** `flask --app wsgi db upgrade` (two additive revisions: `b3d5f7a9c124`, `c4e6a8b0d235`).
5. **nginx:**
   1. Install `deploy/nginx/tpa-http.conf.example` once as `/etc/nginx/conf.d/tpa-http.conf`. It is shared by both TPA sites; a second copy would clash.
   2. Merge the new locations from `tpa.conf.example` into the staging site: page-1 redirects, `/search`, `/feed.xml`, and the slash rule in `location /`.
   3. Install the new `tpa-security-headers.conf`, which adds the CSP in report-only mode.
   4. Run `sudo nginx -t`, then `sudo systemctl reload nginx`.
6. **Restart the API:** `sudo systemctl reload <staging api unit>`.
7. **Publish:** request a publish from Admin › Publishing (or `flask publish request`). The prerender now writes `/articles/page/N`, author pages, `/feed.xml`, the new `robots.txt`, and the release id.
8. **Check staging:**
   - `curl -s https://staging…/api/v1/health` reports `tier: staging` and the commit.
   - `robots.txt`: staging must still be `Disallow: /` (indexing off).
   - `/articles/page/2` exists once there are more than 12 articles; `/articles/page/1` redirects to `/articles`; `/articles/` redirects to `/articles`; legacy 410 and CMS redirect URLs behave as before (re-run the crawl from `docs/legacy-migration.md`).
   - `/search?q=…` returns results and the response has `X-Robots-Tag: noindex, follow`.
   - `/feed.xml` lists summaries with `Content-Type: application/rss+xml`.
   - Rich Results Test or the Schema Markup Validator on an article and the About page.
   - Browser console and `journalctl -u <api unit> | grep "CSP report"`: review every report for a week of normal use, including admin, checkout (Paystack redirect), video embeds and the homepage builder preview.
   - **Two-step sign-in:**
     1. Account › Two-step sign-in: set up with an authenticator app and save the recovery codes.
     2. Sign out, then sign in with a code.
     3. Sign in with a recovery code.
     4. Only after every administrator has enrolled: Settings › Technical › "Require two-step sign-in".
   - Lighthouse and axe on the homepage, the archive, an article, search and an author page.

## 2. Production

Only after your sign-off on staging:

1. Run `tpa-baseline.sh` again and keep the output.
2. Back up `tpa_production` (`tpa-backup.sh`) and confirm the backup verifies.
3. Repeat steps 2–7 for production:
   - Set `TPA_ENVIRONMENT=production`; `deploy check` then refuses anything that points at staging.
   - `tpa-http.conf` is already installed; don't add it twice.
4. **Smoke checks:**
   - `/api/v1/health` (`tier: production`)
   - the homepage `tpa-build` meta tag
   - `robots.txt`: training crawlers blocked, search crawlers allowed, sitemap listed
   - `/sitemap.xml` and `/feed.xml`
   - an article, an author page (only for authors marked as real people with a bio), and `/search`
   - admin sign-in
5. **Rollback:**
   1. Point `current` back to the previous release (`docs/operations.md` §10).
   2. `flask db downgrade c4e6a8b0d235`, then `flask db downgrade b3d5f7a9c124`. This drops only the new columns.
   3. Restore the previous nginx site file, run `nginx -t`, then reload.

## 3. Settings to review after the release (Admin › Settings)

- **Technical › AI training crawlers:** all seven are blocked by default (GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, CCBot, Meta-ExternalAgent, Bytespider). Each switch approves one; the change takes effect at the next publish. Search engines and AI search crawlers (OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot, Perplexity-User) are never blocked.
- **Technical › Require two-step sign-in:** off until every administrator has enrolled.
- **Trust › Editorial / corrections policy page:** the paths of your policy pages. Create the pages under Pages with your wording. They appear in the footer and in Organization structured data only while published.
- **Authors:** an author gets a public page only when marked as a real person, active, and with a bio. Editorial bylines stay attributed to the organisation.

## 4. Monitoring

**UptimeRobot** (free plan, 5-minute checks). Create four monitors with alerts by email:

| Monitor | Type | URL | Expect |
|---|---|---|---|
| Production site | Keyword | `https://thinkpositivealways.com/` | keyword `tpa-build` |
| Production API | Keyword | `https://thinkpositivealways.com/api/v1/health/ready` | keyword `"ready"` |
| Staging site | HTTP(s) | `https://staging.thinkpositivealways.com/` | 200 |
| Certificate | SSL monitoring | the production URL | alert 14 days before expiry |

- `/api/v1/health/ready` checks the database and Redis and answers 503 when either is down. It reports no hostnames or versions.
- Keep the monitors' User-Agent default. The site has no bot blocking that would refuse them.

**Errors:**

- Every API response carries `X-Request-ID`, and unhandled errors are logged with it, so `journalctl -u <api unit> | grep <id>` finds the exact failure a visitor reports.
- **Self-hosted error alerts (`tpa-error-alert.timer`):** a full Sentry or GlitchTip install (PostgreSQL, Redis, workers; about 1 GB RAM) would strain a VPS that already runs both TPA tiers and other sites. Instead, every 15 minutes `flask monitor errors` reads only the API journal lines written since its previous run and, when there are unhandled errors, emails one summary to `ERROR_ALERT_EMAIL` through the app's own mail settings.
  - **What the email holds:** counts by route, and up to 10 request ids. Long token-like path segments are redacted, and no query strings, addresses or headers are included.
  - **Load:** a short one-shot process with no resident service and no database.
  - **Install (per tier):**
    1. Set `ERROR_ALERT_EMAIL` in the tier's `.env`.
    2. Copy `deploy/systemd/tpa-error-alert.service.example` and `.timer.example`, adjusting the unit name, paths and `--unit` to that tier's API unit.
    3. Run `sudo systemctl enable --now tpa-error-alert.timer`.
    4. Check with `sudo systemctl start tpa-error-alert.service; journalctl -u tpa-error-alert.service -n 20`.
  - **Exit codes:**
    - 1: errors were found but nothing could be emailed (no recipient, or mail not configured)
    - 2: the journal couldn't be read
    - Either marks the unit failed in `systemctl --failed`.
