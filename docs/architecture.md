# Architecture

## Overview

```
Browser ──► Nginx ──► /var/www/tpa-site/current (atomic release symlink): prerendered HTML + JS/CSS
                 │      └── /admin/*         client-only admin SPA shell (noindex, no-store)
                 ├──► /media/*  ──► MEDIA_ROOT/public (optimised images, immutable)
                 ├──► @fallback ──► Flask /_redirect/<path> (CMS redirects: 301/302/307/308 or 404)
                 ├──► /_protected_downloads/* (internal only) ──► PRODUCT_FILES_ROOT (X-Accel-Redirect)
                 └──► /api/* ──► Gunicorn ──► Flask app factory
                                              ├── api/          public /api/v1 (content GETs; shop, cart quote)
                                              ├── api/commerce  customer account, checkout, downloads (customer cookie + CSRF + Origin)
                                              │                 and the Paystack webhook (HMAC-SHA512 signature only)
                                              ├── api/admin/    /api/v1/admin (JWT cookies + CSRF + RBAC)
                                              ├── payments/     provider abstraction, Paystack client, payment settings
                                              ├── commerce/     currencies, product types, private file validation
                                              ├── auth/         permissions, decorators, sessions, passwords
                                              ├── cms/          blocks, section registry, design presets, routing, templates, settings
                                              ├── services/     public queries, admin services, audit, publication
                                              ├── media/        Pillow validation + optimisation
                                              ├── storage/      public media + private product files (local; S3 slots)
                                              └── models/       SQLAlchemy → PostgreSQL (SQLite locally)

systemd: tpa-publish-worker ──► publish_jobs queue ──► npm run build ──► releases/<id> ──► current
                          └──► scheduled publishing, order expiry, product file scanning
```

Flask is the single source of truth. The public React app reads content through `contentApi`; the admin uses `adminApi` (an Axios instance with cookie credentials, CSRF headers and single-flight session refresh). Redux holds shared public content and the admin **profile** (never tokens); individual admin screens keep their data locally via `useAdminQuery`.

## Content repository migration

Batch 01 read JSON files through `LocalContentRepository`. Batch 02 moves topics and articles to SQLAlchemy queries in `services/topic_service.py` and `services/article_service.py`. The public response shapes are unchanged, as the Batch 01 compatibility tests confirm. Since Batch 05, products come from the database as well (`services/commerce/catalogue.py`); the JSON product fixture is no longer read. The JSON fixtures remain as the import source for `flask seed sample-content`, which matches records by slug and never overwrites existing rows.

## Authorization

`auth/permissions.py` defines permissions and the role → permission mapping. Every admin resource method is wrapped with `@require_permission(...)`, which verifies the access cookie, loads the user (it must be active and its `session_version` must match) and checks permissions from the user's current roles on each request. A test enumerates every admin route to make sure it rejects unauthenticated access. Frontend checks (`usePermissions`, `RequirePermission`, filtered navigation) only improve the experience.

## Publishing pipeline

```
admin action affecting public pages ─► content_revisions + publish_jobs (debounced, deduplicated)
flask publish worker ─► claim job (atomic, one at a time, file lock) ─► npm run build
   ─► verify output ─► copy to releases/<ts>-jobN ─► atomic symlink switch ─► prune old releases
   failure ─► live release unchanged, retry with backoff, sanitised log in /admin/publishing
```

No HTTP request runs a build. The worker also promotes due scheduled articles with conditional updates, so it is idempotent. The public filter still requires `published_at <= now`.

## Media pipeline

Upload → content sniffing and limits → header-only dimension and pixel checks → `verify()` → EXIF orientation, sRGB, alpha detection, metadata stripped → responsive WebP (+ AVIF when smaller and not worse, + JPEG/PNG fallback) and focal-point crops → atomic writes under `<random id>/v<n>/` → `media_variants` rows. A failure cleans up the files it wrote. Usage is computed from articles (live and pending), authors, topics and page sections; in-use media cannot be deleted.

## Editorial safety

`articles.lock_version` gives optimistic locking (409 `edit_conflict`). Autosave and saves by non-publishers on live articles go to `articles.pending_changes`, so the public page changes only when a publisher publishes them. `article_revisions` stores snapshots: autosaves are coalesced and capped, and restores are audited.

## CMS data validation

- **Article blocks** (`cms/blocks.py`): paragraph, heading (level 2–3), lists, quote, pull quote, callout, divider, image, gallery, video (YouTube/Vimeo id only), button, call to action, related articles, resource, table. Plain text only, safe links (site paths or https), media referenced by id, length limits; unknown fields are rejected.
- **Page sections** (`cms/sections.py`): 24 approved types with typed field definitions, layout variants and design presets. The admin builds its forms from `GET /admin/section-types`, so field definitions are not duplicated in the frontend.
- **Settings** (`cms/settings_registry.py`): only registered keys can be stored, each with a type (string, text, email, https URL, path or https, boolean, media, choice, path list). Sensitive groups require their own permission (`settings.technical`). Defaults keep a fresh install working.
- **Navigation:** internal links must be site paths and external links `https://`. Footer groups and header dropdowns are one level deep. Items carry a device visibility (all, desktop, mobile).

## Page builder (Batch 04)

```
admin builder ──► draft rows (pages, page_sections; lock_version) ──► POST …/preview (no-store, noindex)
      │                                                            └► live preview iframe (postMessage)
      └─ publish ──► page_render.draft_document() ──► pages.published_snapshot + page_revisions
                           └─► record_public_change ──► publish_jobs (debounced) ──► worker rebuild
public API /pages/resolve ──► page_render.resolve_document(snapshot)   (drafts are never read)
   └─ batch-loads media, published articles, topics, authors, global CTAs and shared sections
prerender.mjs ──► GET /site (branding, menus, footer, announcements, cms_overrides) + /pages
   └─► configureSite() ──► static HTML for every published page; favicon + manifest rewritten
```

- **Registry, not code.** `cms/sections.py` describes each section type as typed fields with variants, defaults and per-variant visibility. `check_section` returns clean content, field errors and the ids it references, which feed media usage, link checks and shared-section cycle detection. The frontend renders each type with `components/sections/registry.js`; design choices map to fixed token classes (`design.js`), so arbitrary CSS is impossible.
- **Snapshots.** A published page is a self-contained JSON document. Shared sections and CTAs stay references and are resolved at read time, so "update everywhere" is one write; "keep pages unchanged" rewrites the affected drafts and snapshots with inline copies first.
- **Routing.** `cms/routing.py` owns reserved segments, depth and the overridable built-in paths. The public router tries application routes, then `withCmsOverride` for built-in pages that a published CMS page replaces, then the catch-all `CmsRoute`, which shows the real 404 page (prerendered with HTTP 404 by Nginx) when nothing matches.
- **Time-dependent content.** Section visibility windows and announcements are evaluated at build time and again in the browser (`useNow`, hydration-safe using the build's `generated_at`). The scheduler queues one rebuild when a boundary is crossed.
- **Branding.** Presets are emitted as `data-*` attributes on the root element, and `globals.css` swaps CSS variables, so no CSS is generated from user input. Favicons are generated server-side by Pillow from an already-sanitised raster upload.

## Migration readiness

Articles keep `slug`, `original_slug`, `original_url`, `canonical_url`, `source` (`sample` | `original` | `migrated`) and `noindex`. Legacy URLs are handled by the CMS redirect manager (CSV import with a dry run, loop detection, real HTTP status codes via the Nginx → Flask fallback).

## Digital commerce (Batch 05)

```
/shop, /shop/:slug (prerendered) ──► GET /shop/products (published snapshot + live price/readiness)
cart (localStorage, ids only) ──► POST /cart/quote (server prices, availability, checkout status)
/checkout ──► POST /checkout ──► order + items (price snapshots) ──► Paystack /transaction/initialize
            browser ──► Paystack hosted page ──► /checkout/complete ──► POST …/verify ─┐
Paystack ──► POST /payments/paystack/webhook (HMAC) ──► payment_events (dedupe) ──────┤
                                                                                      ▼
                    GET /transaction/verify/:ref ──► reference, amount, currency, mode checks
                    ──► conditional UPDATE orders → paid (exactly once) ──► entitlements (unique grant keys)
                    ──► receipt + emails (status recorded honestly)
/account/library ──► POST …/downloads ──► hashed short-lived token ──► GET /downloads/:token
                    ──► entitlement + session re-checked ──► stream or X-Accel-Redirect (audited)
```

- **Separation.** Customers have their own model, session table and cookies. Admin JWT cookies are never accepted on customer endpoints, and the customer cookie is never accepted on admin endpoints.
- **Private files.** `storage/private_files.py` writes to a temporary file, validates it (`commerce/files.py`), then moves it atomically under a random key. Nothing under `PRODUCT_FILES_ROOT` is ever served directly.

## VPS storage and premium resources (Batch 08)

```
uploads ──► UPLOAD_TEMP_ROOT (request spooling + validation) ──atomic move──►
   images:   MEDIA_ROOT/public (optimised, /media/ via Nginx) + MEDIA_ROOT/private (originals)
   premium:  PRODUCT_FILES_ROOT/<ebooks|workbooks|templates|courses|downloads>/… (no URL)
download: entitlement (active, not expired) ─► short-lived grant ─► Flask re-check ─►
          X-Accel-Redirect /_protected_downloads/… (Nginx internal) or Flask stream
```

- Resources are products (`product_type` written resource types) with access rules and related resources; purchases, guest checkout, free claims and the future `access.grant()` (memberships, text-based courses) all create entitlements.
- `services/storage_health.py` powers `/admin/storage` and `flask storage check`; `services/commerce/premium_files.py` the media library's premium files view.
- Backups: `deploy/backup/` (verified, encrypted off-server copy, retention, status file read by the app).
- **Payment truth.** Only provider-verified transactions change an order to paid. Webhooks and return pages share one code path (`services/commerce/payments.apply_verified`). Uniqueness constraints make replays, races and repeated clicks harmless.
- **Settings vs secrets.** Non-secret payment settings are stored as site settings. The Paystack secret lives only in the environment. `payments/config.py` computes the effective mode and the readiness checks, and live mode is impossible without `PAYMENTS_LIVE_ALLOWED` plus the checklist.
- **Frontend.** The public shop pages are part of the main SSR bundle so they can be prerendered. The private customer area (cart, checkout, account) is a lazily loaded chunk that is never prerendered with data. `ShopApiContext` supplies the customer API client, which sends the customer CSRF header.

## Partnerships, sponsorships and affiliates (Batch 07)

- **Data.** New tables only (`models/partnerships.py`). Article and newsletter sponsorships are
  side tables (`article_sponsorships`, `newsletter_sponsorships`) loaded with the article or
  campaign, so the existing editor, revisions, SEO and publish queue are reused unchanged.
  `commercial_events` holds the stage/status history of opportunities, campaigns, bookings and
  sponsorships, and the audit log records every sensitive change.
- **Services** (`services/partnerships/`): `crm` (partners, inquiries, opportunities, campaigns),
  `advertising` (placements, rates, bookings, conflict checks, live creatives, boundaries),
  `sponsored` (disclosure and approval gate), `affiliates` (links, redirect, daily click
  aggregates, commission import), `media_kit`, `reports`, `common` (validation, safe URLs, money).
- **Publication gates.** `publish_readiness` and the scheduled publish loop refuse sponsored
  articles without an approved sponsorship and disclosure. Campaign and newsletter approval need
  `sponsorships.approve`.
- **Static site.** Paid sections are resolved at render time from approved bookings live "now".
  `publication_service` queues a rebuild at the next booking start or end, and the browser hides
  expired creatives after hydration (`useNow`). Disclosures and `rel` attributes come from the
  same React components on the server (prerender) and in the browser.
- **Redirect safety.** `/api/v1/go/<slug>` looks up a stored link, re-validates its https
  destination and redirects with `no-store`; request parameters never influence the target.
- **Money.** Integer minor units plus a currency everywhere. Reports group by currency and
  never convert. Pipeline, contracted, invoiced, verified receipts and affiliate commissions
  stay separate.
