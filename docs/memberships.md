# Memberships (Batch 10.1: plans foundation)

Batch 10.1 adds CMS-controlled membership plans. **Billing is not open:** there is no
checkout, no subscription and no entitlement grant. The public page shows plans with a
"coming soon" notice. Subscriptions, renewals and access arrive in Batches 10.2–10.4 (see
the Batch 10 architecture audit).

## Data model (migration `b8d0f6c4e215`, revises `a7c9e5b3d104`)

- `membership_plans`: name, slug (fixed after first publication), tagline, plain-text
  description, benefits (up to 12), `tier_rank` (unique; 1 = first paid tier, for future
  upgrades and downgrades), status (`draft` | `published` | `archived`), `lock_version`.
- `membership_plan_prices`: append-only. Interval (`month` | `year`), currency (USD only for
  now), `amount_minor` (integer cents, at least 100). A partial unique index allows one
  `active` price per plan, interval and currency. Prices are never edited: a new price
  retires the old one. A price that has been public (`shown_at`) can only be retired,
  never deleted.
- `membership_plan_access`: the products a plan includes (unique per plan). Only products
  marked **Included in memberships** (`membership_eligible`) can be added — premium
  resources and course products. Bundles, free items and membership products can't.

## Rules

- Publishing needs a description, a benefit, at least one active price, and at least one
  published, eligible included product. Only one plan can be published at a time (one
  paid tier initially).
- Every change sends `lock_version`; stale edits get `409 edit_conflict`.
- Public APIs only return published plans, their active prices and their published,
  eligible included products.
- Membership products are refused by the cart (`/cart/quote`, and therefore checkout).
- Existing purchases and entitlements are untouched.

## Permissions

| Permission | Allows | Default roles |
|---|---|---|
| `memberships.view` | Read plans in the admin | administrator, editor in chief, product manager, marketing manager, customer support, finance manager |
| `memberships.manage` | Content, prices, included products | administrator, editor in chief, product manager |
| `memberships.publish` | Publish, unpublish, archive | administrator, editor in chief |

## API

- Public:
  - `GET /api/v1/memberships`
  - `GET /api/v1/memberships/<slug>`
- Admin:
  - `GET`, `POST /api/v1/admin/membership-plans`
  - `GET`, `PATCH /api/v1/admin/membership-plans/<id>`
  - `POST …/<id>/status`
  - `POST …/<id>/prices`
  - `POST …/<id>/prices/<price_id>/remove`
  - `PUT …/<id>/access`
  - `GET /api/v1/admin/membership-eligible-products`

## Screens

- Admin → Learning → **Membership plans**: the list, and an editor for content, benefits,
  monthly and yearly prices with history, included courses and resources, and status.
- Public **`/membership`**: plans, prices (with the yearly saving), benefits and included
  items, plus a disabled "Coming soon" button.
