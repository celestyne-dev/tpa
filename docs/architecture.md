# Architecture

## Overview

```
Browser ──► Nginx ──► frontend/dist         prerendered public HTML + JS/CSS
                 │      └── /admin/*         client-only admin SPA shell (noindex, no-store)
                 └──► /api/* ──► Gunicorn ──► Flask app factory
                                              ├── api/          public /api/v1 (GET only, CORS allow-list)
                                              ├── api/admin/    /api/v1/admin (JWT cookies + CSRF + RBAC)
                                              ├── auth/         permissions, decorators, sessions, passwords
                                              ├── cms/          blocks, sections, settings registry, defaults
                                              ├── services/     public queries, admin services, audit, publication
                                              └── models/       SQLAlchemy → PostgreSQL (SQLite locally)
```

Flask is the single source of truth. The public React app reads content through `contentApi`; the admin uses `adminApi` (an Axios instance with cookie credentials, CSRF headers and single-flight session refresh). Redux holds shared public content and the admin **profile** (never tokens); individual admin screens keep their data locally via `useAdminQuery`.

## Content repository migration

Batch 01 read JSON files through `LocalContentRepository`. Batch 02 moves topics and articles to SQLAlchemy queries in `services/topic_service.py` and `services/article_service.py`. The public response shapes are unchanged, as the Batch 01 compatibility tests confirm. Products still come from the JSON dataset. The JSON fixtures remain as the import source for `flask seed sample-content`, which matches records by slug and never overwrites existing rows.

## Authorization

`auth/permissions.py` defines permissions and the role → permission mapping. Every admin resource method is wrapped with `@require_permission(...)`, which verifies the access cookie, loads the user (it must be active and its `session_version` must match) and checks permissions from the user's current roles on each request. A test enumerates every admin route to make sure it rejects unauthenticated access. Frontend checks (`usePermissions`, `RequirePermission`, filtered navigation) only improve the experience.

## Publishing / rebuild contract

```
admin action (publish/unpublish/edit published/settings/navigation/topic change)
   └─► content_revisions row (+ audit_logs row)
build: scripts/build-production.sh → npm run build → prerender.mjs writes dist/prerender-manifest.json (generatedAt)
dashboard: GET /api/v1/admin/publishing/status → rebuild_required = latest revision > generatedAt
```

No HTTP request starts a build or runs shell commands. A future batch can add a worker or systemd path unit that watches `content_revisions` and runs the build script, then swaps `dist/` atomically.

Scheduled articles stay hidden until `flask content publish-due` promotes them (`scheduled` → `published`, recording a revision). The public filter also requires `published_at <= now`, so publishing never leaks content early.

## CMS data validation

- **Article blocks** (`cms/blocks.py`): paragraph, heading (level 2–3), ordered or unordered list, quote, callout (info/tip/warning), divider. Plain text only, length limits, and unknown fields are rejected.
- **Page sections** (`cms/sections.py`): approved types with fixed field definitions and layout variants. The admin builds its forms from `GET /admin/section-types`, so field definitions are not duplicated in the frontend.
- **Settings** (`cms/settings_registry.py`): only registered keys can be stored, each with a type (string, text, email, https URL, path or https, boolean). Defaults keep a fresh install working.
- **Navigation:** internal links must be site paths and external links `https://`. Footer groups are one level deep.

## Migration readiness

Articles keep `slug`, `original_slug`, `original_url`, `canonical_url`, `source` (`sample` | `original` | `migrated`) and `noindex`. Legacy URL redirects belong in Nginx (`deploy/nginx/redirects.conf.example`).
