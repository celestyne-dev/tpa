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

| Variable                                             | Purpose                                                                                                                                                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FLASK_CONFIG`                                       | `development` (default), `testing` or `production`                                                                                                                                                      |
| `SECRET_KEY`, `JWT_SECRET_KEY`                       | Required in production (JWT key at least 32 characters). Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`                                                                   |
| `DATABASE_URL`                                       | PostgreSQL in production. Development defaults to `backend/instance/tpa-dev.db` (SQLite)                                                                                                                |
| `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`         | Session lifetimes (default 15 minutes / 14 days)                                                                                                                                                        |
| `JWT_COOKIE_SECURE`                                  | Forced on in production; Secure cookies need HTTPS                                                                                                                                                      |
| `RATELIMIT_STORAGE_URI`                              | `memory://` for one process; use Redis when running several Gunicorn workers                                                                                                                            |
| `CORS_ORIGINS`, `TRUST_PROXY`                        | Approved browser origins (also used for the admin Origin check); set `TRUST_PROXY=1` behind Nginx                                                                                                       |
| `FRONTEND_BUILD_MANIFEST`                            | Where the prerender manifest is read for the "rebuild required" indicator                                                                                                                               |
| `MAIL_BACKEND`                                       | `none`, `console` (development only: links printed in the Flask terminal) or `smtp` (`MAIL_SMTP_*`, `MAIL_FROM`). Development defaults to `console`; production refuses `console`                       |
| `ADMIN_BASE_URL`                                     | Public admin origin used in invitation and reset links (default `http://localhost:5173`)                                                                                                                |
| `INVITATION_TTL_HOURS`, `PASSWORD_RESET_TTL_MINUTES` | Link lifetimes (default 72 hours / 60 minutes)                                                                                                                                                          |
| `TEST_DATABASE_URL`                                  | Optional: run pytest against a disposable PostgreSQL database                                                                                                                                           |
| `MEDIA_*`                                            | Media storage and limits: `MEDIA_ROOT`, `MEDIA_STORAGE`, `MEDIA_PUBLIC_BASE_URL`, `MEDIA_MAX_UPLOAD_MB`, `MEDIA_MAX_PIXELS`, `MEDIA_MAX_DIMENSION`, `MEDIA_RETENTION`, `MEDIA_ENABLE_AVIF` (section 10) |
| `SITE_URL`, `REDIRECT_ALLOWED_HOSTS`                 | Public site origin for canonical checks and sitemaps; external hosts redirects may point to                                                                                                             |
| `PUBLISH_*`, `FRONTEND_DIR`                          | Publishing worker: release directories, debounce, retries, build timeout, build/deploy commands (section 13)                                                                                            |

Frontend variables (`VITE_SITE_URL`, `VITE_ALLOW_INDEXING`, `VITE_API_BASE_URL`, `PRERENDER_API_URL`) are unchanged from Batch 01.

Backend Python dependencies now include **Pillow** (pinned in `requirements.txt`; its wheels bundle libwebp, libavif and LittleCMS, so no system packages are needed on Ubuntu x86-64). Check codec support with `python -c "import PIL.features as f; print(f.check('webp'), f.check('avif'))"`. If AVIF is unavailable, uploads still work and only WebP plus JPEG/PNG are produced.

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

  - `a817c9636960` (Batch 03): media library, revisions, redirects and publishing jobs. It adds the `media_variants`, `article_revisions`, `redirects` and `publish_jobs` tables; new `media_assets` columns (public id, title, caption, credit, status, checksum, retained original, focal point, version …), new `articles` columns (social title/description, `lock_version`, pending changes) and `authors.is_person`, using `ALTER TABLE … ADD COLUMN` and unique indexes only (no table rebuilds). It brings the permission catalogue up to date and grants the new permissions to the built-in roles and to role templates that still exist; custom roles are unchanged. Existing built-in `/images/…` media keep working. Downgrade removes the new tables, columns and permissions, but uploaded files on disk are left in place.

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
| media.upload, media.edit, media.replace                                       |      ✓      |   ✓    |           |         |
| media.delete (archive/delete unused media)                                    |      ✓      |        |           |         |
| articles.view_revisions                                                       |      ✓      |   ✓    |     ✓     |         |
| articles.restore_revisions (only where the user may edit)                     |      ✓      |   ✓    |           |         |
| articles.preview (private draft preview)                                      |      ✓      |   ✓    |     ✓     |    ✓    |
| seo.view (SEO audit and checks)                                               |      ✓      |   ✓    |           |    ✓    |
| redirects.manage                                                              |      ✓      |        |           |         |
| publishing.view (publishing jobs and build status)                            |      ✓      |   ✓    |     ✓     |    ✓    |
| publishing.manage (rebuild, retry, cancel)                                    |      ✓      |        |           |         |
| pages.view                                                                    |      ✓      |   ✓    |     ✓     |         |
| pages.edit                                                                    |      ✓      |   ✓    |           |         |
| navigation.manage, settings.manage                                            |      ✓      |        |           |         |
| seo.manage (SEO defaults, canonical/noindex, post-publication slug changes)   |      ✓      |        |           |         |
| users.view, users.manage, audit.view                                          |      ✓      |        |           |         |
| roles.manage, roles.assign, settings.security, payments.configure (sensitive) |      ✓      |        |           |         |

Batch 03 template grants: Administrator and Editor-in-Chief get all media permissions, revisions, preview, SEO audit and publishing management (Administrator also redirects); Content Editor gets upload, edit, revisions and preview; Content Writer gets upload, revisions and preview (restores only on their own drafts); SEO Manager gets media alt-text editing, preview, SEO audit and redirects; Website Manager gets upload, edit, replace, SEO audit and publishing status; Marketing Manager gets preview and the SEO audit. Templates you have already edited keep your other changes.

Future-module permissions are also in the catalogue but marked **unavailable** and cannot be granted: products, orders, refunds, customers, partnerships, advertising, affiliates, newsletters, subscribers, courses, memberships and finance.

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

`/admin/login`, `/admin/activate` and `/admin/reset-password` (token links, public), `/admin` (dashboard), `/admin/articles`, `/admin/articles/new`, `/admin/articles/:id/edit`, `/admin/articles/:id/preview` (private preview), `/admin/workflow` (editorial board), `/admin/media` (media library), `/admin/topics`, `/admin/tags`, `/admin/authors`, `/admin/pages` (and `/admin/pages/:id`), `/admin/navigation`, `/admin/seo` (SEO audit), `/admin/redirects`, `/admin/settings`, `/admin/users`, `/admin/roles` (and `/admin/roles/new`, `/admin/roles/:id`), `/admin/publishing` (publishing jobs), `/admin/audit-log`, `/admin/account` (change password).

The sidebar shows only what the signed-in user may use. Future commercial modules (products, orders, customers, newsletter, partnerships, advertising, affiliates, courses, memberships, analytics, eBooks/licensing) are listed as **Planned**, without links.

## 10. Media library and image optimisation

**Uploads** (`/admin/media`, `POST /api/v1/admin/media`): multiple files, drag and drop, per-file progress. Each upload is processed synchronously by `app/media/processing.py`:

1. The size limit (`MEDIA_MAX_UPLOAD_MB`, default 20) is checked, then the **actual content** is sniffed. The extension and declared type are ignored.
2. Accepted formats: **JPEG, PNG, WebP, GIF (still) and AVIF**. **SVG uploads are refused** (untrusted SVG can contain script). The built-in SVG artwork shipped with the site is unaffected. Animated images are refused.
3. Decompression-bomb protection: dimensions and pixel count (`MEDIA_MAX_DIMENSION` 12,000 px, `MEDIA_MAX_PIXELS` 50 MP) are checked from the header before decoding, and Pillow's bomb warning is treated as an error. A full `verify()` pass rejects truncated or corrupt files.
4. EXIF orientation is applied, ICC profiles and CMYK are converted to sRGB, and transparency is kept only when it is actually used. **EXIF/GPS/XMP metadata is never written to public files.**
5. Derivatives (never upscaled):

| Preset                                | Files                                                                                                           | Use                                          |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| `responsive` (original aspect)        | WebP at 160/320/640/960/1280/1600 px (up to the original), AVIF where better, JPEG/PNG fallback at 640 and 1280 | article body, featured/hero, cards, homepage |
| `avatar` (1:1, focal-point crop)      | WebP 160/320/640 + fallback                                                                                     | author portraits                             |
| `social` (1200×630, focal-point crop) | one JPEG                                                                                                        | Open Graph / X cards                         |
| `thumbnail`, `featured`, `homepage`   | derived from `responsive`, cropped in the browser at the focal point                                            | 16:10 cards, featured image, 21:9 banners    |
| `ebook_cover` (2:3)                   | on demand: `flask --app wsgi media generate-preset ebook_cover --all`                                           | future eBook covers                          |

**Compression policy.** Photos are encoded as WebP at the preset quality (76–82). Quality steps down towards the size target (thumbnails about 20–80 KB, featured 60–180 KB, banners 80–250 KB, avatars 15–50 KB) only while PSNR stays at or above 34 dB, so targets are goals, not caps. Flat artwork, screenshots and text-heavy graphics are detected and compared lossless versus high-quality lossy, keeping the sharper option. AVIF is kept only when it is at least 8% smaller than the WebP and not visibly worse (PSNR within 1.5 dB). Identical uploads are detected by SHA-256 and reuse the existing asset.

**Library features:** search; filters by type, usage (used, unused, missing alt text), status and upload date; sorting by newest, oldest, file name or size; a detail view showing dimensions, uploaded and served file sizes, all versions and where the image is used; alt text, title, caption, credit and source editing; a click-to-set focal point (regenerates crops as a new version); copy URL; replace (new optimised version, old files kept until pruned); archive and restore; and delete. Deletion is refused while any article (live or pending changes), author, topic or page section uses the image, and archiving is offered instead. Archived images keep working where already used but cannot be newly chosen.

**Storage** (`app/storage`): `MEDIA_STORAGE=local` writes to `MEDIA_ROOT/public` (optimised files, URLs under `MEDIA_PUBLIC_BASE_URL`, default `/media`) and `MEDIA_ROOT/private` (retained originals, never served). Keys are generated as `<random id>/v<version>/<slug>-<width>.<ext>` and never use the uploaded file name as a path, so URLs stay stable across metadata edits. Files are written atomically. A failed upload removes every file it wrote and leaves no database record. In development, Flask serves `/media` (`MEDIA_SERVE_FROM_FLASK`, also proxied by Vite); in production, Nginx serves it with `Cache-Control: immutable`. `MEDIA_RETENTION=original` keeps the uploaded file privately. `master` keeps a metadata-free 2560 px copy instead, so no usable high-quality source is discarded. Storage totals appear in the library. `flask --app wsgi media prune` deletes superseded versions older than `MEDIA_SUPERSEDED_RETENTION_DAYS`, and `flask --app wsgi media verify` checks that files exist. `MEDIA_STORAGE=s3` is a documented adapter slot and is not activated in this release.

**Frontend:** `ContentImage` renders `<picture>` (AVIF, then WebP) with a JPEG/PNG `srcset`, placement-specific `sizes`, intrinsic width and height (no layout shift), a dominant-colour placeholder and focal-point cropping, and degrades gracefully when an image is missing. The hero (LCP) image is eager with `fetchpriority="high"`; everything else lazy-loads.

## 11. Article editor, revisions, previews and workflow

- **Editor** (`/admin/articles/:id/edit`): tabs for Content, Details (featured image picker, author, topics, tags), SEO and History, plus a live word count and reading time, autosave status, last-saved time, draft notice, unsaved-change protection and field-level validation errors.
- **Blocks** (`cms/blocks.py`, validated server-side, no HTML): paragraph, H2/H3 heading, ordered and unordered lists, quote, pull quote, callout (info/tip/warning/success), divider, image (alignment, caption, per-placement alt), gallery (2–12 images, 2–4 columns), video (YouTube/Vimeo stored as provider + id, loaded only when the reader presses play, via youtube-nocookie), button, call to action, related articles (published only), resource/product recommendation (product kind reserved for commerce), and accessible tables. Blocks can be inserted, reordered, duplicated and removed with keyboard-accessible controls.
- **Autosave:** debounced (2.5 s), one request at a time, stale responses never overwrite newer typing, retries with backoff when offline. Every write increments `articles.lock_version`, and a save based on an older version gets **409 `edit_conflict`**; the editor then offers "load their version" or "keep mine".
- **Live articles stay safe:** autosave never changes a published article; changes are kept as **pending changes** (`articles.pending_changes`). Saves by people without `articles.publish` also become pending changes ("Save for review"). Publishers use **Publish changes** or **Discard**. Publishing triggers a rebuild.
- **Revisions** (`article_revisions`): numbered snapshots of title, subtitle, excerpt, body, images, author, topics, tags, SEO, social and publication fields, each with editor, timestamp, kind and change summary. Consecutive autosaves by the same editor within 10 minutes share one revision, and at most 20 autosave revisions are kept per article. Any two revisions can be compared (field and block level) and restored. A restore creates a new revision and an audit entry; on a live article it becomes pending changes.
- **Preview:** `/admin/articles/:id/preview` renders the working copy with the public components. Responses come from the authenticated admin API with `Cache-Control: no-store` and `X-Robots-Tag: noindex`. Previews are never prerendered, and the public API only ever returns published content.
- **Workflow:** draft → submitted → approved → scheduled/published → archived. Writers submit, approvers approve, and publishers publish or schedule, all enforced by the backend (a Publish button in the UI grants nothing). Every transition is audit-logged. The `/admin/workflow` board groups drafts, review, approved, pending changes and scheduled articles.
- **Scheduling:** the publishing worker (or the optional timer) runs `publish-due` every few seconds. It promotes due articles with a conditional `UPDATE` (idempotent, so overlapping runs never double-publish) under a file lock, records failures in the audit log and queues a rebuild. Timestamps are timezone-aware UTC. No browser tab or in-process thread is involved.

## 12. Technical SEO and redirects

- **Article SEO tab:** SEO title, meta description, slug (with an availability check), canonical URL, noindex, social title, description and image, a search-result preview, a social card preview, character counts (as guidance) and non-blocking checks. The checks flag a missing title or description, empty or thin content, heading hierarchy problems, missing featured image, alt text or dimensions, broken internal links, noindex, external or duplicate canonicals, missing author or topic, and a redirect shadowing the slug.
- **Indexing controls** (`canonical_url`, `noindex`) and **slug changes after publication** require `seo.manage`. A published slug change automatically creates a **301** from the old URL, repoints chains and never creates loops.
- **Structured data:** WebSite and Organization site-wide; BlogPosting (published and modified dates, ImageObjects with dimensions, publisher) and BreadcrumbList on articles. **Person** is used only for authors marked "This is a real person"; editorial bylines remain Organization. No ratings or commercial schema.
- **Meta:** canonical, robots, Open Graph (title, description, 1200×630 image), X/Twitter cards, and `article:published_time`/`modified_time`/`section`/`tag`.
- **Sitemap:** generated from `GET /api/v1/sitemap`. It includes only published, indexable articles whose canonical URL is their own, active topics and static pages (minus unpublished or noindex CMS pages), with `lastmod` and `<image:image>` entries. Admin, auth, previews, drafts and archived content are never included. Builds stay `noindex` with a blocking `robots.txt` unless `VITE_ALLOW_INDEXING=true`.
- **Redirect manager** (`/admin/redirects`): source path, destination, 301/302/307/308, active flag, origin (manual, slug change, import) and timestamps. Sources are normalised; `/admin`, `/api`, `/media` and `/assets` are refused, and duplicates are rejected. Loops and chains longer than 5 hops are blocked. Destinations must be site paths or https URLs on `REDIRECT_ALLOWED_HOSTS`, which prevents open redirects. CSV import (with a dry run and per-row errors) and export are supported.
- **How redirects are served:** Nginx tries the static file first. Unknown paths go to Flask `/_redirect/<path>`, which answers with the real status code or 404, after which Nginx shows the prerendered 404 page. Changes apply immediately without an Nginx reload. `npm run serve:dist` mirrors this locally, and the React 404 page also follows redirects for client-side navigation.
- **SEO dashboard** (`/admin/seo`): published article count, articles with issues, metadata/alt/noindex/canonical/broken-link totals, redirects, sitemap URL and image counts, and build freshness and indexing status. No Search Console or ranking data is shown or invented.

## 13. Static publishing pipeline

```
CMS change affecting public pages ─► content_revisions row + publish_jobs (pending, debounced 30 s, max 5 min)
flask publish worker (systemd) ─► claims one due job (atomic UPDATE; one build at a time; file lock)
   └─► npm run build (Vite + SSR + prerender from PUBLISH_API_URL) → verify index/404/sitemap/fresh manifest
   └─► copy to PUBLISH_RELEASES_DIR/<timestamp-jobN> → atomic symlink switch of PUBLISH_CURRENT_LINK
   └─► prune old releases (keep PUBLISH_KEEP_RELEASES) → optional PUBLISH_DEPLOY_COMMAND
failure ─► live release untouched; retried with backoff (1, 2, 4 min) up to PUBLISH_MAX_ATTEMPTS, then "failed"
```

- Builds are triggered by publishing, unpublishing, archiving, scheduled publication, edits to live articles, topic, page, navigation and settings changes, media changes on published content, and redirect changes.
- Admin endpoints never run commands. The worker runs a fixed argv list (no shell) with a timeout. Diagnostics are stored sanitised (paths, credentials and database URLs redacted) and shown on `/admin/publishing`, where users with `publishing.manage` can rebuild, retry or cancel. Stale running jobs (no heartbeat) are recovered automatically.
- **Development:** run builds on demand with `flask --app wsgi publish request` followed by `flask --app wsgi publish worker --once`, or keep `flask --app wsgi publish worker` running. **Production:** the `tpa-publish-worker` systemd unit (see `docs/deployment.md`). `scripts/build-production.sh` still works for manual builds.
- **Not automated:** CDN cache purging and remote/cloud deployment. `PUBLISH_DEPLOY_COMMAND` provides the hook, but no provider is configured.

## 14. Tests and checks

```bash
# Backend
cd backend && source .venv/bin/activate
python -m pytest                     # auth, RBAC, CMS, media, editorial, SEO, publishing, migrations
ruff check . && ruff format --check .
# Optional: run the suite against PostgreSQL
TEST_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/tpa_pytest python -m pytest

# Frontend
cd frontend
npm run check                        # ESLint + Prettier + Vitest
npm run build                        # needs the API running (or use ../scripts/build-production.sh)
npm run serve:dist                   # preview the static build at http://localhost:4173 (proxies /api to :5000)
```

## 15. Security precautions

- Never commit `.env` files, database files or dumps. Generate unique `SECRET_KEY` and `JWT_SECRET_KEY` values per environment.
- Serve production over HTTPS only, with Secure cookies, and keep the admin same-origin with the API.
- Use a shared rate-limit store (Redis) when running more than one Gunicorn worker.
- Article blocks, section content and settings accept **plain text only**: HTML tags, control characters and `javascript:` links are rejected. React renders all content as text.
- Request bodies are validated with strict Marshmallow schemas (unknown fields rejected). Queries go through the SQLAlchemy ORM (parameterised).
- The audit log redacts any field that looks like a password, token or secret. Errors never include stack traces.
- Deleting topics, authors or tags that articles still use is refused (reassign or archive instead). Articles are archived; only never-published drafts can be deleted.
- Uploads: content sniffing, size, dimension and pixel limits, no SVG, metadata stripped, random storage keys, atomic writes. Originals live in private storage that is never served. Media still in use cannot be deleted.
- Redirect destinations are restricted to site paths and allow-listed hosts (no open redirects). Video embeds are limited to YouTube/Vimeo IDs.
- Admin API responses (including previews) are `no-store` and `noindex`. The publishing worker runs with least-privilege systemd settings, and failed builds never replace the live site.

## 16. Known limitations and deferred features

- **Working now:** media uploads and optimisation, the media library, the advanced editor, autosave, revisions, pending changes, previews, workflow, scheduling via the worker, SEO checks and dashboard, sitemap with images, redirects, and the publishing queue with atomic releases.
- **Limitations:** image processing runs inside the upload request (large files can take a few seconds; Gunicorn `--timeout 120`). The S3 storage adapter and CDN purging are not activated. Revisions record field and block-level differences, not character-level diffs. Search Console and ranking data are not connected. Homepage and page sections are editable but public pages still render their approved designs from code (Batch 04).
- **Deferred:** self-service "forgot password", branded email templates, the public page builder (Batch 04), product catalogue and checkout (Paystack), customers and orders, newsletter provider integration, memberships, courses, affiliates, advertising, analytics, two-factor authentication, and migration of the previous website's articles (redirect import is ready for it).
