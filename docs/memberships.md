# Memberships (Batch 10.1: plans; 10.2: test-mode checkout; 10.3: lifecycle — see below)

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

# Batch 10.3: subscription lifecycle and billing recovery (test mode only)

## Data model (migration `d4a2f7c9e815`, revises `c9e1a7d5f326`)

- `customer_subscriptions` gains:
  - `cancel_at_period_end` (false for existing rows) and `cancel_requested_at`;
  - `past_due_since`, the first unpaid renewal of the current cycle;
  - `last_reconciled_at`.
- `subscription_periods.order_id` is now unique, so one payment can only ever pay for one
  billing period.
- The downgrade refuses while a cancellation is scheduled or any renewal period exists.

New setting: `MEMBERSHIP_GRACE_DAYS` (default 3, allowed 0–14).

## Renewals

1. Paystack charges a renewal with its own reference. The `charge.success` webhook, or a
   paid `invoice.update`, only matters when it carries a plan or subscription code.
2. The reference is verified with `GET /transaction/verify`. The verified plan code and
   Paystack customer code select the membership.
3. A renewal `Order` (`kind=subscription`, total = the price agreed at checkout,
   idempotency key `renewal-<provider transaction id>`), a `PaymentAttempt` and the next
   `SubscriptionPeriod` are created together.
4. They then go through the normal `payments.apply_verified`. That checks reference,
   amount, currency, mode, plan and the membership's customer code, then records the
   payment transaction, receipt and emails. A mismatch flags the order and extends nothing.
5. On success the period becomes `paid` and the membership stays or becomes `active`:
   - Periods are contiguous: the next period starts at the previous period end, even when
     the payment came during grace.
   - The plan's entitlements are extended to the new period end.
   - The `membership_renewed` email is sent.
6. Duplicates and races are prevented by:
   - unique payment events;
   - unique payment transactions per provider id;
   - unique order keys;
   - unique periods per (subscription, sequence) and per order;
   - entitlement grant keys;
   - row locks on PostgreSQL.

   A delivery that crashed half-way is finished by the next delivery.
7. A renewal for a membership whose first payment isn't confirmed yet is deferred and
   retried by reconciliation.
8. A charge after a membership ended is recorded as a paid order flagged for refund. It
   never reactivates the membership.

## Failed payments and grace

- `invoice.payment_failed` is confirmed by re-fetching the subscription from Paystack.
  - If the failure arrives while the current period is still paid and more than 3 days
    from its end, it is treated as stale (out of order) and ignored.
  - Otherwise the membership becomes `past_due`, or `grace` once the paid period is over.
- In both states access continues until `current_period_end + MEMBERSHIP_GRACE_DAYS`.
  This is fixed when grace starts and is never measured from "now". Entitlement
  `expires_at` is set to the same moment. The `membership_payment_failed` email is sent.
- A verified renewal at any point during grace restores `active`.
- After grace the membership ends (`payment_failed`):
  - membership entitlements are revoked;
  - Paystack is asked to disable the subscription;
  - the `membership_ended` email is sent.

## Cancellation, resumption and payment method

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/v1/account/membership/cancel` | `subscription_id`; 10 per minute |
| POST | `/api/v1/account/membership/resume` | `subscription_id`; 10 per minute |
| POST | `/api/v1/account/membership/payment-method` | `subscription_id`; returns a Paystack-hosted `url`; 10 per minute |

- **Cancel:**
  - `POST /subscription/disable` (code + email token) runs first. If Paystack can't
    confirm it, nothing changes locally (502).
  - The membership then keeps access until the end of the paid period. Unpaid grace time
    is dropped.
  - Reconciliation ends it after that date.
  - Before the Paystack subscription is linked (`subscription.create` not yet received),
    cancel returns 409 `subscription_not_linked`.
- **Resume** (only while paid time remains): `POST /subscription/enable`. If Paystack
  refuses, the response is 409 `resume_unavailable`.
- **Payment method:** `GET /subscription/:code/manage/link`. Only https links on
  `paystack.com` are accepted. Nothing about the card is stored or proxied.
- **Cancelled at Paystack:** a `subscription.not_renew` / `subscription.disable` webhook,
  or reconciliation finding a non-renewing status, is confirmed by re-fetching and then
  treated as a cancellation at period end.

All of these act only on the signed-in customer's own membership; any other id returns 404.

## Reconciliation: `flask memberships reconcile [--no-provider]`

Run hourly by `deploy/systemd/tpa-membership-reconcile.{service,timer}.example`. It:

- marks abandoned pending checkouts `incomplete`;
- moves active memberships whose paid period ended without a verified renewal into grace
  (after checking whether Paystack reports them cancelled);
- moves `past_due` → `grace` once the paid period is over;
- ends memberships whose grace or cancellation date has passed;
- retries deferred membership webhooks.

It is idempotent. It can end or shorten access but never extends it. If Paystack is
unreachable, the time-based rules still apply.

## Refunds and disputes

- Refunds keep using the admin refund workflow.
- When a refund of a membership payment is processed with "revoke access", the membership
  ends (`refunded`): membership entitlements are revoked and Paystack is asked to stop
  charging. A refund without revoke is recorded in the history only.
- `charge.dispute.*` webhooks, for any order, flag the order for review and record a
  `payment_disputed` membership event. Access is left to staff.

## Notifications

Email templates: `membership_renewed`, `membership_payment_failed`,
`membership_cancelled` and `membership_ended`. They are sent through the existing email
infrastructure and recorded in `email_deliveries`.

## Not confirmed without a real Paystack test merchant

These behaviours follow Paystack's public documentation, but the tests use the in-memory
fake. Check each against the test dashboard before relying on it:

- **Renewal charges:**
  - that `GET /transaction/verify` includes the `plan` and the `customer.customer_code`;
  - that the `charge.success` payload carries the plan.
- **Invoice payloads:** the shape of `invoice.update` and `invoice.payment_failed`
  (`subscription.subscription_code`, `transaction.reference`, `status`/`paid`), and when
  Paystack sends them relative to its retries.
- **Disable:** the exact status after `/subscription/disable` (`non-renewing` or
  `cancelled`), and whether Paystack still charges the current cycle.
- **Enable:** whether `/subscription/enable` works on a disabled subscription, and whether
  the next payment date is kept.
- **Manage link:** the host and lifetime of the `manage/link` URL.
- **Disputes:** the dispute event names (`charge.dispute.create/remind/resolve`) and their
  `transaction.reference` field.
- **Customer codes:** that they are stable per customer email, since renewals are matched
  by customer code plus plan code.

Live billing stays disabled: `MEMBERSHIP_BILLING_MODE` only accepts `test`, and any
live-mode charge is a mismatch.
