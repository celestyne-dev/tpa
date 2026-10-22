# Think Positive Always

The commercial home of **Think Positive Always (TPA)**: personal development articles, digital products, free resources, the newsletter, and brand partnerships.

The stack is a React/Vite frontend and a Python Flask API on PostgreSQL. Public pages are **prerendered to static HTML at build time** from API data. Since Batch 02, editorial content, site settings and navigation live in the database and are managed through a secure admin dashboard at `/admin`.

## 1. Technology stack

| Layer    | Technology                                                                                                                                                                                               |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend | React 19, Vite 8, JavaScript/JSX, Tailwind CSS 4, React Router 8, Redux Toolkit 2, React Redux 9, Axios, Lucide React                                                                                    |
| Backend  | Python 3.11+, Flask 3, Flask-RESTful, Flask-CORS, Flask-SQLAlchemy / SQLAlchemy 2, Flask-Migrate (Alembic), Marshmallow, Flask-JWT-Extended, Flask-Limiter, Werkzeug (scrypt password hashing), Gunicorn |
| Database | PostgreSQL in production (psycopg 3, JSONB); SQLite for local development and tests                                                                                                                      |
| Testing  | pytest and Ruff (backend); Vitest, React Testing Library, ESLint and Prettier (frontend)                                                                                                                 |
| Hosting  | Linux VPS with Nginx, Gunicorn, systemd and PostgreSQL (see `docs/deployment.md`)                                                                                                                        |

## 2. Folder structure

```
tpa/
├── frontend/
│   ├── scripts/                prerender.mjs (static HTML, sitemap, robots, admin shell), serve-dist.mjs
│   └── src/
│       ├── admin/              Admin dashboard (lazy-loaded chunk, never prerendered)
│       │   ├── components/     Layout, DataTable, Modal, ConfirmDialog, Fields, BlockEditor, Notifications, Guards
│       │   ├── hooks/          useAdminQuery, usePermissions, useUnsavedChanges
│       │   ├── pages/          Login, Dashboard, Articles, ArticleEditor, Taxonomy, Pages, Navigation, Settings, Users, AuditLog, Account
│       │   └── navigation.js   Sidebar sections and planned modules
│       ├── components/ …       Public design system and page sections
│       ├── pages/              Public pages
│       ├── services/           apiClient.js, contentApi.js (public), adminApi.js (admin, cookie + CSRF aware)
│       └── store/              Redux slices: site, topics, articles, products, auth
├── backend/
│   ├── app/
│   │   ├── api/                Public /api/v1 resources; api/admin/ for /api/v1/admin resources
│   │   ├── auth/               permissions.py (roles → permissions), decorators.py, session.py (JWT cookies), passwords.py, roles.py
│   │   ├── cms/                blocks.py (article blocks), sections.py (page sections), settings_registry.py, defaults.py
│   │   ├── models/             SQLAlchemy models (user, content, cms, audit, portable types)
│   │   ├── schemas/            Marshmallow request schemas (strict) and public response schemas
│   │   ├── services/           Public queries, admin services, audit, settings, navigation, publication, seed
│   │   ├── data/               JSON fixtures: import source for the sample content and products dataset
│   │   └── cli.py              flask admin / seed / cms / content commands
│   ├── migrations/             Alembic migrations (version-controlled)
│   └── tests/                  pytest suite
├── deploy/                     Nginx and systemd examples
├── docs/                       architecture.md, deployment.md
└── scripts/build-production.sh
```

## 3. Requirements

- Python 3.11 or newer (tested with 3.13), with `python3-venv`
- Node.js 20.19+ or 22.12+ and npm (Node 22 LTS recommended)
- PostgreSQL 14+ for production. It is **not** needed for local development or tests, which use SQLite.

## 4. Environment variables

```bash
cp backend/.env.example backend/.env          # server-side only; never commit it
cp frontend/.env.example frontend/.env.local  # VITE_* values are public; never put secrets there
```

Key backend variables (all documented in `backend/.env.example`):

| Variable                                             | Purpose                                                                                                                                                                           |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FLASK_CONFIG`                                       | `development` (default), `testing` or `production`                                                                                                                                |
| `SECRET_KEY`, `JWT_SECRET_KEY`                       | Required in production (JWT key at least 32 characters). Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`                                             |
| `DATABASE_URL`                                       | PostgreSQL in production. Development defaults to `backend/instance/tpa-dev.db` (SQLite)                                                                                          |
| `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`         | Session lifetimes (default 15 minutes / 14 days)                                                                                                                                  |
| `JWT_COOKIE_SECURE`                                  | Forced on in production; Secure cookies need HTTPS                                                                                                                                |
| `RATELIMIT_STORAGE_URI`                              | `memory://` for one process; use Redis when running several Gunicorn workers                                                                                                      |
| `CORS_ORIGINS`, `TRUST_PROXY`                        | Approved browser origins (also used for the admin Origin check); set `TRUST_PROXY=1` behind Nginx                                                                                 |
| `FRONTEND_BUILD_MANIFEST`                            | Where the prerender manifest is read for the "rebuild required" indicator                                                                                                         |
| `MAIL_BACKEND`                                       | `none`, `console` (development only: links printed in the Flask terminal) or `smtp` (`MAIL_SMTP_*`, `MAIL_FROM`). Development defaults to `console`; production refuses `console` |
| `ADMIN_BASE_URL`                                     | Public admin origin used in invitation and reset links (default `http://localhost:5173`)                                                                                          |
| `INVITATION_TTL_HOURS`, `PASSWORD_RESET_TTL_MINUTES` | Link lifetimes (default 72 hours / 60 minutes)                                                                                                                                    |
| `TEST_DATABASE_URL`                                  | Optional: run pytest against a disposable PostgreSQL database                                                                                                                     |

Frontend variables (`VITE_SITE_URL`, `VITE_ALLOW_INDEXING`, `VITE_API_BASE_URL`, `PRERENDER_API_URL`) are unchanged from Batch 01.

## 5. Local setup (Ubuntu WSL, SQLite)

```bash
# Backend
cd ~/development/code/tpa/backend
python3 -m venv .venv            # skip if it already exists
source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app wsgi db upgrade                     # create or upgrade the schema (explicit, never automatic)
flask --app wsgi seed sample-content            # development only: 6 sample articles + 8 topics (idempotent)
flask --app wsgi cms seed-defaults              # editable default navigation + homepage section config
flask --app wsgi admin create-superadmin --email you@example.com --name "Your Name"   # prompts for a password
flask --app wsgi run --debug                    # http://127.0.0.1:5000/api/v1/health

# Frontend (second terminal)
cd ~/development/code/tpa/frontend
npm install
npm run dev                                     # http://localhost:5173 and http://localhost:5173/admin
```

The Vite dev server proxies `/api` to Flask, so the admin's HttpOnly cookies are same-origin. Always open the admin through `localhost:5173`, not the Flask port.

## 6. Database and migrations

- The schema is managed **only** by Alembic. The app never calls `create_all()` at startup.
- Upgrade: `flask --app wsgi db upgrade`. Check status: `flask --app wsgi db current`.
- After changing models: `flask --app wsgi db migrate -m "describe change"`, **review the generated file**, then upgrade.
- Downgrade one step: `flask --app wsgi db downgrade` (Flask-Migrate's default is one revision back). Downgrading the initial migration drops every table. Back up first:
  - PostgreSQL: `pg_dump --format=custom --file=tpa-$(date +%F).dump "$DATABASE_URL"`
  - SQLite: `cp backend/instance/tpa-dev.db backend/instance/tpa-dev-$(date +%F).db`
- Migrations so far:
  - `746bd93e2089`: initial schema plus the four roles.
  - `5e0cca7bc654`: adds the `account_tokens` table for invitations and password reset links. It is incremental and leaves existing data untouched.

PostgreSQL (development or production):

```bash
sudo -u postgres psql -c "CREATE USER tpa_user WITH PASSWORD 'choose-a-strong-password';"
sudo -u postgres psql -c "CREATE DATABASE tpa OWNER tpa_user;"
# backend/.env
DATABASE_URL=postgresql+psycopg://tpa_user:choose-a-strong-password@127.0.0.1:5432/tpa
flask --app wsgi db upgrade
```

### Database model overview

| Area       | Tables                                                                                                                                                                      |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Access     | `users`, `roles`, `user_roles` (who assigned, when), `refresh_tokens` (rotation and revocation), `account_tokens` (hashed, single-use invitation and reset tokens)          |
| Editorial  | `articles` (JSON/JSONB blocks, status, SEO, canonical, provenance), `topics`, `tags`, `authors`, `article_topics`, `article_tags`, `media_assets` (public/private metadata) |
| CMS        | `site_settings` (registered, validated keys), `navigation_menus`, `navigation_items`, `pages`, `page_sections` (approved types and variants)                                |
| Operations | `audit_logs` (sanitised), `content_revisions` (public-affecting changes, drives the rebuild indicator)                                                                      |

All timestamps are timezone-aware UTC. Statuses are enforced with check constraints. Slugs are unique, and foreign keys use `RESTRICT` where deletion would orphan content.

## 7. Authentication architecture

- **Login** (`POST /api/v1/admin/auth/login`): credentials are checked against a Werkzeug **scrypt** hash. Unknown email, wrong password and disabled account all return the same generic error, with similar timing.
- **Sessions:** Flask-JWT-Extended sets **HttpOnly, SameSite=Strict** cookies (Secure in production).
  - Access token: 15 minutes, cookie path `/api/`.
  - Refresh token: 14 days, cookie path `/api/v1/admin/auth/`, recorded in `refresh_tokens`.
  - No token is ever exposed to JavaScript, localStorage or Redux.
- **Refresh** rotates the refresh token. Presenting an already-rotated token is treated as theft and revokes every session of that user.
- **Logout** revokes the refresh token and clears the cookies. **Password change** and **account disable** bump the user's `session_version`, which invalidates every outstanding access token immediately.
- **CSRF:** double-submit tokens. Every cookie-authenticated mutation must send `X-CSRF-TOKEN` matching the readable `csrf_*` cookie. Admin mutations from untrusted `Origin`s are also rejected.
- **Rate limits:** login is limited to 5/minute and 20/hour per IP, plus 10/hour per email. Password changes are limited to 10/minute, and refresh to 30/minute.
- **CORS:** the admin API has no CORS. It is only served same-origin, through the Vite proxy or Nginx.

### First super administrator

```bash
flask --app wsgi admin create-superadmin --email owner@example.com --name "Owner Name"
# Password prompt is hidden and asked twice. For automation without shell history:
#   read -s PW && printf '%s\n' "$PW" | flask --app wsgi admin create-superadmin --email … --name … --password-stdin
```

There are no default credentials and no development backdoor. The command refuses to run if an active super administrator already exists; add further admins from **Admin → Users**.

### Inviting administrators (recommended)

1. In **Admin → Users**, choose **Invite user**. Enter the email address, optionally a name, and the roles.
2. The invitee receives a **single-use link** valid for 72 hours (`/admin/activate#token=…`). They choose their own password and are signed in.
3. Security properties:
   - Only a SHA-256 hash of the token is stored.
   - The token travels in the URL fragment, so it is never sent to servers or in `Referer` headers, and the page removes it from the address bar.
   - Redemption is atomic, so a link cannot be used twice.
   - Expired or revoked links are rejected, and a new invitation or **Resend** invalidates the previous link.
   - Tokens are never returned by the API or written to the audit log.
4. **Delivery:** with `MAIL_BACKEND=console` (the development default), the link is printed in the Flask terminal. Without a configured email backend, invitations are refused rather than creating unusable links.
5. **Create user** (with an initial password) remains available as an alternative. Share that password in person or through a password manager, never by email.
6. **Password reset links** (**Send reset link**) follow the same token rules (60 minutes). Completing a reset signs the user out everywhere. Disabling an account ends its sessions immediately and revokes its outstanding links.

## 8. Roles and permissions

Roles are stored in the database. What each role may do is defined centrally in `backend/app/auth/permissions.py`, and the frontend receives the resolved permission list.

| Permission                                                                      | Super admin | Editor | Moderator | Analyst |
| ------------------------------------------------------------------------------- | :---------: | :----: | :-------: | :-----: |
| dashboard.view, content.read                                                    |      ✓      |   ✓    |     ✓     |    ✓    |
| content.write (create and edit articles)                                        |      ✓      |   ✓    |           |         |
| taxonomy.manage (topics, tags, authors)                                         |      ✓      |   ✓    |           |         |
| content.publish (publish, schedule)                                             |      ✓      |   ✓    |           |         |
| content.moderate (unpublish, archive)                                           |      ✓      |   ✓    |     ✓     |         |
| pages.read                                                                      |      ✓      |   ✓    |     ✓     |         |
| pages.write                                                                     |      ✓      |   ✓    |           |         |
| navigation.manage, settings.manage                                              |      ✓      |        |           |         |
| users.manage (accounts, invitations, password resets), roles.assign, audit.read |      ✓      |        |           |         |
| analytics.view (content analytics)                                              |      ✓      |        |           |    ✓    |

The last active super administrator cannot be demoted or disabled, and administrators cannot disable their own account. Nobody can grant a role whose permissions they do not hold themselves, which keeps future delegated roles safe. Role changes take effect on the next request. Every admin endpoint is enforced in Flask, whatever the UI shows.

To add a specialised role later, add a `RoleDefinition` in `permissions.py` and a data migration inserting the role row. The UI reads roles, labels and permissions from `/api/v1/admin/roles`.

`/admin` opens the dashboard for users with `dashboard.view`. Users without it go to their first permitted area, or see an access-denied page.

## 9. Admin routes

`/admin/login`, `/admin/activate` and `/admin/reset-password` (token links, public), `/admin` (dashboard), `/admin/articles`, `/admin/articles/new`, `/admin/articles/:id/edit`, `/admin/topics`, `/admin/tags`, `/admin/authors`, `/admin/pages` (and `/admin/pages/:id`), `/admin/navigation`, `/admin/settings`, `/admin/users`, `/admin/audit-log`, `/admin/account` (change password).

Future modules (products, orders, customers, newsletter, partnerships, advertising, affiliates, courses, memberships, analytics, SEO tools, media library, licensing) are listed in the sidebar as **Planned**, without links.

## 10. CMS publishing workflow and SEO build

1. Editors create a **draft**, edit content blocks and metadata, and preview.
2. **Publish now** makes the article `published` immediately. **Schedule** sets `scheduled` with a future `published_at`.
3. Public endpoints only return articles that are `published` with `published_at` in the past. Drafts, scheduled and archived articles never appear publicly.
4. The static site is **not** rebuilt automatically, and no API request runs shell commands. Every public-affecting change is recorded in `content_revisions`, and the dashboard compares it with the last build's `prerender-manifest.json`, showing **"rebuild required"** when they differ.
5. Rebuild: `./scripts/build-production.sh`. Prerendering discovers articles and topics from the API, so new slugs need no frontend changes and the sitemap updates automatically.
6. **Scheduled articles do not publish themselves.** Run `flask --app wsgi content publish-due` (manually, or from a systemd timer or cron job), then rebuild. Until then they stay hidden even after their time passes.
7. The slug is locked after first publication, so URLs stay stable. Indexing stays disabled unless `VITE_ALLOW_INDEXING=true` is set for the production build.

**What the CMS controls today, publicly:** articles, topics, tags, authors, site name and descriptions, contact email, social links, SEO defaults (title, description, sharing image), footer text, newsletter-open flag, media-kit URL, and primary and footer navigation. All of these appear on the website after the next build. **Not yet:** the homepage and page section content are stored and editable in the admin, but the public pages still render their approved designs from code; connecting them is the Batch 04 page builder. The products endpoint still serves the JSON preview dataset until the commerce batch.

## 11. Tests and checks

```bash
# Backend
cd backend && source .venv/bin/activate
python -m pytest                     # auth, RBAC, CMS, migrations, public API compatibility
ruff check . && ruff format --check .
# Optional: run the suite against PostgreSQL
TEST_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/tpa_pytest python -m pytest

# Frontend
cd frontend
npm run check                        # ESLint + Prettier + Vitest
npm run build                        # needs the API running (or use ../scripts/build-production.sh)
npm run serve:dist                   # preview the static build at http://localhost:4173 (proxies /api to :5000)
```

## 12. Security precautions

- Never commit `.env` files, database files or dumps. Generate unique `SECRET_KEY` and `JWT_SECRET_KEY` values per environment.
- Serve production over HTTPS only, with Secure cookies, and keep the admin same-origin with the API.
- Use a shared rate-limit store (Redis) when running more than one Gunicorn worker.
- Article blocks, section content and settings accept **plain text only**: HTML tags, control characters and `javascript:` links are rejected. React renders all content as text.
- Request bodies are validated with strict Marshmallow schemas (unknown fields rejected). Queries go through the SQLAlchemy ORM (parameterised).
- The audit log redacts any field that looks like a password, token or secret. Errors never include stack traces.
- Deleting topics, authors or tags that articles still use is refused (reassign or archive instead). Articles are archived, never hard-deleted.

## 13. Deferred features

Self-service "forgot password" on the login page (resets are started by a super administrator), branded HTML email templates, media uploads and the media library UI, the rich page builder connected to public pages (Batch 04), automatic rebuild/deploy on publish, an automatic scheduler, product catalogue and checkout (Paystack), customers and orders, newsletter provider integration, memberships, courses, affiliates, advertising, analytics, two-factor authentication, and migration of the previous website's articles.
