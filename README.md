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
  - `7cf88d33a308`: dynamic roles. It adds the `permissions` and `role_permissions` tables, new role columns (`label`, `kind`, `is_active`, `grants_all`, timestamps) and article review columns. It changes tables with `ALTER TABLE … ADD COLUMN` only, so nothing is dropped or rebuilt. It then seeds the permission catalogue and the 14 role templates, marks the four existing roles as protected system roles and maps their permissions. Users, roles, role assignments and invitations are preserved. Downgrade removes the new tables and columns, plus any template role nobody holds, and keeps every user and assignment.

Upgrading an existing installation to dynamic roles:

```bash
# 1. back up (see above), then:
flask --app wsgi db upgrade        # applies 7cf88d33a308
flask --app wsgi rbac sync         # idempotent; should report all zeros right after the upgrade
```

`flask --app wsgi rbac sync` reconciles the database with the catalogue in `backend/app/auth/permissions.py`. Run it after deploying code that adds permissions or templates. It:

- inserts new permissions; permissions removed from code are marked unavailable, never deleted;
- resets the built-in roles to their definitions;
- creates missing templates and leaves edited templates alone;
- strips sensitive or unavailable grants from non-system roles.

It never deletes users, roles or assignments.

PostgreSQL (development or production):

```bash
sudo -u postgres psql -c "CREATE USER tpa_user WITH PASSWORD 'choose-a-strong-password';"
sudo -u postgres psql -c "CREATE DATABASE tpa OWNER tpa_user;"
# backend/.env
DATABASE_URL=postgresql+psycopg://tpa_user:choose-a-strong-password@127.0.0.1:5432/tpa
flask --app wsgi db upgrade
```

### Database model overview

| Area       | Tables                                                                                                                                                                                                |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Access     | `users`, `roles`, `user_roles` (who assigned, when), `permissions`, `role_permissions`, `refresh_tokens` (rotation and revocation), `account_tokens` (hashed, single-use invitation and reset tokens) |
| Editorial  | `articles` (JSON/JSONB blocks, status, SEO, canonical, provenance), `topics`, `tags`, `authors`, `article_topics`, `article_tags`, `media_assets` (public/private metadata)                           |
| CMS        | `site_settings` (registered, validated keys), `navigation_menus`, `navigation_items`, `pages`, `page_sections` (approved types and variants)                                                          |
| Operations | `audit_logs` (sanitised), `content_revisions` (public-affecting changes, drives the rebuild indicator)                                                                                                |

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

Roles, permissions and their links live in the database. The permission catalogue is defined in `backend/app/auth/permissions.py` and synchronised into the `permissions` table (see `flask rbac sync`). A user may hold **several roles**. Their effective permissions are the union of the permissions of their **active** roles, resolved on every request, so changes apply immediately. The frontend receives the resolved list and the API enforces it on every endpoint.

**Role kinds**

- **Built-in (system)**: Super Admin, Editor, Moderator and Analyst. They are protected and cannot be edited, deactivated or deleted. Super Admin (`grants_all`) resolves to every permission, including sensitive ones and those of future modules.
- **Templates**: Administrator, Editor-in-Chief, Content Editor, Content Writer, Product Manager, Orders Manager, Customer Support, Partnerships Manager, Affiliate Manager, Marketing Manager, Newsletter Manager, SEO Manager, Website Manager and Finance Manager. They are seeded once and editable afterwards. Templates for modules that do not exist yet (products, orders, customers, partnerships, affiliates, newsletters, finance) grant only `dashboard.view`. Their intended permissions are shown as _Planned_ and stay locked until the module ships.
- **Custom**: roles a Super Admin creates at `/admin/roles`.

**Permission catalogue** (✓ = built-in role holds it; templates are listed at `/admin/roles`)

| Permission                                                                    | Super Admin | Editor | Moderator | Analyst |
| ----------------------------------------------------------------------------- | :---------: | :----: | :-------: | :-----: |
| dashboard.view                                                                |      ✓      |   ✓    |     ✓     |    ✓    |
| analytics.view                                                                |      ✓      |        |           |    ✓    |
| articles.view (all articles, including others' drafts)                        |      ✓      |   ✓    |     ✓     |    ✓    |
| articles.create, articles.edit_own, articles.edit_any                         |      ✓      |   ✓    |           |         |
| articles.submit_review, articles.approve, articles.publish                    |      ✓      |   ✓    |           |         |
| articles.unpublish, articles.archive                                          |      ✓      |   ✓    |     ✓     |         |
| articles.delete (never-published drafts only)                                 |      ✓      |        |           |         |
| topics.manage, tags.manage, authors.manage                                    |      ✓      |   ✓    |           |         |
| media.view                                                                    |      ✓      |   ✓    |     ✓     |    ✓    |
| pages.view                                                                    |      ✓      |   ✓    |     ✓     |         |
| pages.edit                                                                    |      ✓      |   ✓    |           |         |
| navigation.manage, settings.manage, seo.manage (the "SEO defaults" settings)  |      ✓      |        |           |         |
| users.view, users.manage, audit.view                                          |      ✓      |        |           |         |
| roles.manage, roles.assign, settings.security, payments.configure (sensitive) |      ✓      |        |           |         |

Future-module permissions are also in the catalogue but marked **unavailable** and cannot be granted: media upload and delete, products, orders, refunds, customers, partnerships, advertising, affiliates, newsletters, subscribers, courses, memberships and finance.

**Rules enforced by the API**

- **Least privilege.** Endpoints check specific actions such as `articles.publish`, never a role name.
- **Ownership.** Users with `articles.edit_own` but not `articles.view` only see articles they created. Other articles return 404. They can edit their own articles only while they are drafts, and submit them for review. `articles.edit_any` edits any article. Each article response includes `can` flags computed on the server.
- **Review workflow.** `submit` and then `approve`. An edit by someone without `articles.approve` withdraws a pending or granted approval.
- **Sensitive permissions** (`roles.manage`, `roles.assign`, `settings.security`, `payments.configure`) cannot be granted to any role. In practice only Super Admin holds them.
- **No escalation.**
  - Granting roles (create, invite, change roles) needs `roles.assign` and every permission those roles grant.
  - Creating or editing a role only allows permissions the actor holds.
  - Accounts can only be managed by someone holding a superset of their permissions. For example, an Administrator can manage Editors but not a Super Admin.
- **Safeguards.**
  - The last active Super Admin cannot be demoted, disabled or locked out.
  - A role assigned to users or to pending invitations cannot be deleted. Deactivate it instead: it then grants nothing immediately and cannot be newly assigned, and an invitation carrying it cannot be accepted.

`/admin` opens the dashboard for users with `dashboard.view`. Users without it go to their first permitted area, or see an access-denied page.

## 9. Admin routes

`/admin/login`, `/admin/activate` and `/admin/reset-password` (token links, public), `/admin` (dashboard), `/admin/articles`, `/admin/articles/new`, `/admin/articles/:id/edit`, `/admin/topics`, `/admin/tags`, `/admin/authors`, `/admin/pages` (and `/admin/pages/:id`), `/admin/navigation`, `/admin/settings`, `/admin/users`, `/admin/roles` (and `/admin/roles/new`, `/admin/roles/:id`: Roles & Permissions), `/admin/audit-log`, `/admin/account` (change password).

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
