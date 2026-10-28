# Memberships (Batch 10.1: plans foundation; Batch 10.2: test-mode checkout below)

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

# Batch 10.2: subscription checkout and verified activation (test mode only)

## Data model (migration `c9e1a7d5f326`, revises `b8d0f6c4e215`)

- `membership_provider_plans`: the Paystack plan code for each plan price, per provider
  and mode (`test`/`live`). `verified_at` is set when the remote plan was checked for
  amount, currency, interval and mode.
- `customer_subscriptions`: one row per checkout. Statuses are `pending`, `active`,
  `past_due`, `grace`, `incomplete` and `ended`. A partial unique index allows only one
  live subscription (`pending`/`active`/`past_due`/`grace`) per customer. It also stores
  the order, the provider codes (customer, subscription, email token), the period, and
  `access_until`.
- `subscription_periods`: billing periods. Period 1 is created as `pending` and becomes
  `paid` on activation.
- `subscription_events`: an append-only history of status changes and provider links.
- `membership_plans.product_id`: a hidden backing `membership` product per plan, so
  subscription orders reuse the existing order, payment-attempt, receipt and email
  infrastructure. These products never appear in the shop or the admin products list.
- `orders.kind` (`purchase` | `subscription`).
- `course_enrollments.source` also allows `membership`.

The downgrade refuses while any subscriptions, subscription orders or membership
enrolments exist.

## Opening checkout

Checkout stays closed (`coming_soon` / `unavailable`) unless **all** of these hold:

1. `MEMBERSHIP_BILLING_MODE=test` is set. This is an operator attestation that recurring
   USD charges were verified on the Paystack test account. `live` is never accepted in
   this phase.
2. The payment mode is `test`, the configured key is a test key, and USD is an enabled
   checkout currency.
3. The customer passes the existing test-checkout rule: test accounts only, unless
   `PAYMENTS_TEST_CHECKOUT_PUBLIC` is set.
4. The price has a verified Paystack test plan. An admin runs **Sync with Paystack
   (test)** in the plan editor. Checkout re-fetches the plan before each new checkout and
   refuses if it has drifted.

## Flow

1. `POST /api/v1/account/membership/checkout` with `price_id`, `idempotency_key`,
   `expected_amount_minor`, `currency` (`USD`) and `accept_terms`.
   - The customer must have a verified email.
   - The server compares the amount with the active price; on a mismatch it returns
     409 `price_changed`.
   - It refuses an existing active membership (409 `already_member`).
   - A retry with the same key, or an unpaid pending checkout for the same price, resumes
     that checkout instead of creating a new one.
   - The order, the subscription (`pending`), period 1 and a `checkout_started` event are
     committed **before** Paystack is called.
   - Paystack is initialised with the plan code. The customer returns to
     `/account/membership?subscription=<id>`.
2. The return page calls `POST /api/v1/account/membership/verify`. This and the
   `charge.success` webhook both go through `apply_verified`, which checks the
   reference, amount, currency, mode and status with Paystack. For subscription orders it
   also checks the plan code and the provider mode. A mismatch flags the order for review
   and never activates.
3. On the first verified payment, the subscription becomes `active`:
   - The period runs for one interval from the payment.
   - Membership entitlements (`source=membership`, expiring at the period end) are
     granted for the plan's published, eligible products, and course enrolments are
     synced.
   - Confirmation, receipt and "membership activated" emails are sent.
   - Replays and duplicate webhooks are no-ops.
4. A `subscription.create` webhook is re-fetched from Paystack and only links the
   subscription code and email token, by plan code and customer. It never grants access,
   and it may arrive before or after the charge.

Separately purchased products and courses keep their own `purchase` entitlements and are
never changed by a membership.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/v1/account/membership` | Own membership, included items, history and billing status |
| POST | `/api/v1/account/membership/checkout` | 201 created / 200 resumed; 10 per minute |
| POST | `/api/v1/account/membership/verify` | `subscription_id`; own subscriptions only (404 otherwise); 30 per minute |
| POST | `/api/v1/admin/membership-plans/<id>/provider-sync` | `lock_version`; needs `memberships.manage`; test keys only |

## Not in this phase

There are no renewals, failed-payment or past-due handling, grace periods,
cancellation, plan changes or live mode. Membership access expires at the end of the
first period until renewal processing arrives in Batch 10.3. The Paystack behaviours
(plan initialisation, `subscription.create` payloads, USD plans) are covered by fakes
here and still need checking against the real test account.
