# Digital product commerce (Batch 05)

This guide covers the product catalogue, private product files, the storefront, customer accounts, orders, Paystack payments, refunds, receipts and reports. Checkout is **disabled by default**. Live (real money) payments stay off until the deployment explicitly allows them **and** a Super Admin completes the readiness checklist (see [Live activation checklist](#live-activation-checklist)).

## 1. Overview

| Area                           | Where                                                                                                                                                                                                                                                                                                                |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product CMS                    | `/admin/products`, `/admin/products/:id`, `/admin/product-collections`, `/admin/bundles`                                                                                                                                                                                                                             |
| Orders, customers, access      | `/admin/orders`, `/admin/customers`, `/admin/entitlements`                                                                                                                                                                                                                                                           |
| Reports                        | `/admin/reports/revenue`                                                                                                                                                                                                                                                                                             |
| Payment settings (Super Admin) | `/admin/payments`                                                                                                                                                                                                                                                                                                    |
| Storefront                     | `/shop`, `/shop/collections/:slug`, `/shop/:productSlug`, `/cart`, `/checkout`, `/checkout/complete`                                                                                                                                                                                                                 |
| Customer account               | `/login`, `/register`, `/verify-email`, `/forgot-password`, `/reset-password`, `/account`, `/account/library`, `/account/orders`, `/account/settings` (the Batch 05 `/account/login`, `/account/register`, `/account/verify-email` and `/account/reset-password` addresses redirect, keeping `?next=` and `#token=`) |

Backend code:

- `app/models/{commerce,customer,orders}.py`
- `app/services/commerce/*`
- `app/payments/*` (provider abstraction, Paystack, payment settings)
- `app/storage/private_files.py`
- `app/api/commerce.py` (public, customer and webhook endpoints)
- `app/api/admin/commerce.py` (admin endpoints)

## 2. Products

**Types.** The registry lives in `app/commerce/product_types.py`. Sellable now: ebook, workbook, journal, planner, reflection guide, worksheet, resource pack, bundle and free resource. Online course and membership are registered as _planned_ and cannot be selected yet. To add a type, add an entry to the registry; the admin and the API pick it up.

**Lifecycle.** Each product has a publication status (draft, published, archived) and, separately, a sales status (`coming_soon` or `on_sale`) plus an optional availability window (`available_from` / `available_until`).

- Editing a published product changes its draft. The public page keeps showing the **published snapshot** until you publish again.
- Prices and file readiness are always read live, so a removed price or file takes effect immediately.
- Every publish stores a revision. Revisions can be restored from the History tab.

**Purchasable** means all of the following:

- published;
- on sale;
- inside its availability window;
- has an active deliverable file, or, for a bundle, every child has one;
- has a price in the shopper's currency, or is free.

The storefront never shows Add to cart or Buy now otherwise, and the server re-checks every cart line at quote and at checkout. On `/admin/products`, the **Problems** filter ("Missing files or invalid setup") lists products with missing files, missing prices or invalid configuration.

**Money.** Amounts are stored as integers in minor units with an explicit ISO currency code (`app/commerce/currency.py`). USD and KES are configured, and more can be added there.

- There is **no currency conversion**: each price is entered per currency.
- Shoppers choose which currency prices are shown in (the display currencies are set in Site settings → Shop).
- An order is charged in one currency.
- Each order item stores a price snapshot (currency, unit amount, compare-at amount and title) that never changes afterwards.
- Compare-at prices are shown only when higher than the price. Promotional prices can carry a start and end time.

**Bundles.** A bundle lists child products.

- Cycles are rejected: a bundle cannot contain itself, directly or indirectly.
- Buying a bundle grants an entitlement to the bundle **and** to each child, recorded with the composition at the time of sale. Later changes to the bundle never remove what a customer already received.

**Collections and categories.** Categories group products for filtering. Collections are curated, ordered sets with their own page at `/shop/collections/:slug`. Both appear in the CMS link picker and in the homepage **Products** section.

**Starter catalogue.** The migration seeds five titles as _coming soon_ and one bundle as a _draft_:

- The Power of Starting Again
- The 30-Day Mindset Reset Workbook
- The Daily Reflection Journal
- The Confidence & Self-Worth Workbook
- The Letting Go & Moving Forward Guide
- The Fresh Start Collection (the draft bundle)

They have no prices, files, page counts, testimonials, reviews or claims. The seed only creates slugs that do not exist, so it never overwrites admin edits. Re-run it with `flask --app wsgi commerce seed-catalogue`.

## 3. Private product files

Product files are **never** stored in the public media library, the Git repository or the Vite build. They live in private storage (`PRODUCT_FILES_ROOT`, default `backend/instance/product-files/`, git-ignored) under random keys, and are only reachable through authorised, short-lived download links.

**Accepted formats:** PDF, EPUB and ZIP. `app/commerce/files.py` validates every upload:

- the real content type, sniffed from the bytes (the extension and declared type must agree with it);
- the size limit (`PRODUCT_FILE_MAX_MB`) and a sanitised display filename;
- **PDF:** structure check; PDFs containing JavaScript, launch actions or embedded files are rejected;
- **EPUB:** the `mimetype` entry and container structure;
- **ZIP:** entry count, total uncompressed size and compression ratio (`PRODUCT_ZIP_MAX_*`); rejects path traversal, absolute paths, symlinks, encrypted entries and any entry whose file type is not on the allowlist (documents, images, audio and video);
- a SHA-256 checksum stored for integrity;
- free disk space checked before the upload is committed (`PRODUCT_FILES_MIN_FREE_MB`).

**Malware scanning (optional).** Set `PRODUCT_FILES_SCAN_COMMAND` to a JSON argv list, for example `["clamdscan","--no-summary","--fdpass","{path}"]`.

- New versions are then held as `pending` until the background worker (`flask publish worker`) or `flask --app wsgi commerce scan-files` scans them.
- The command runs **without a shell, outside web requests**. Exit 0 means clean, exit 1 means infected; anything else is an error.
- Only `clean` versions (or `not_configured` when no scanner is set) are delivered.

**Versions.** Replacing a file adds a new version. Older versions are kept.

**Version policy.** Customers can download:

1. the latest active version of each active file of the product, and
2. the exact version they originally received.

Deactivating a file hides it from new buyers. Customers who already bought it keep access to the version they received. Admins can download any version (audited) and see where each file is used.

**Downloads.**

1. The library calls `POST /api/v1/account/library/:id/downloads`. The server checks the entitlement (active, not revoked, not refunded) and returns a one-off URL `/api/v1/downloads/:token`.
2. The token is random; only its hash is stored. It is bound to the customer session, expires after `DOWNLOAD_LINK_TTL_SECONDS` (default 300) and allows at most `DOWNLOAD_LINK_MAX_USES` uses.
3. Downloads are rate-limited (`RATELIMIT_DOWNLOADS`), and an optional per-entitlement download limit can be set in Payment settings.
4. Responses carry a safe `Content-Disposition: attachment` header, `no-store` and `X-Content-Type-Options: nosniff`.
5. Flask streams the file, or hands it to Nginx with `X-Accel-Redirect` when `PRODUCT_FILES_ACCEL_REDIRECT_PREFIX` is set (see `docs/deployment.md`).
6. Every authorisation, download and refusal is recorded (Download Entitlements → downloads audit).

Revoked or refunded entitlements are refused immediately.

**Storage backends.** `PRODUCT_FILES_STORAGE=local` is implemented. An `s3` slot exists in `app/storage/private_files.py` but is not implemented, and tests never need S3 credentials.

## 4. Storefront and SEO

- `/shop` offers:
  - search, filters (type, category, collection) and sorting;
  - an explicit currency switcher;
  - honest availability labels (Available, Coming soon, Not available);
  - Add to cart only when the product is purchasable in the selected currency.
- The product page shows the description, what is included (actual file names and formats), FAQs, related products and the price.
- The cart is kept in the browser (product IDs only). The server prices every cart through `POST /api/v1/cart/quote`, so a tampered price or currency is ignored.
- **Checkout** requires a signed-in customer with a verified email.
  1. The server validates the cart again.
  2. It creates an order with price snapshots.
  3. It initialises a Paystack transaction and sends the browser to Paystack's hosted page.
  - No card data ever reaches this site.
  - Returning from Paystack only triggers a server-side verification. A browser redirect is **never** treated as proof of payment (see section 7).
- **SEO.**
  - Published products and collections are prerendered at build time and listed in the sitemap.
  - Product pages carry `Product` JSON-LD. The `Offer` is included only when the product is actually purchasable, with the exact price and currency.
  - No ratings, reviews or invented data are ever emitted.
  - Drafts, archived products and private pages (`/cart`, `/checkout`, `/account/*`) are excluded from the sitemap, marked `noindex` and disallowed in `robots.txt`.
  - Unknown product slugs return the real 404 page, and changed slugs can be redirected with the existing redirect manager.
- **Homepage.** The **Products** section (`product_previews`) shows real catalogue items in one of three modes: featured, chosen products in a set order, or a collection. You choose the count, whether prices show, and the CTA.

## 5. Customer accounts

Customers are completely separate from administrators.

- They have their own table, an opaque session cookie (`tpa_customer`, HttpOnly, SameSite=Lax, Secure in production) and a CSRF token cookie that must be echoed in the `X-Customer-CSRF` header.
- Customer state-changing endpoints also check the `Origin` header.
- An admin session is never a customer session, and a customer session never grants admin access.

Account features (refined in Batch 07.5):

- **Registration** asks for a name, email, password and confirmation, plus acceptance of the terms. Password rules are shown up front and checked again on the server. Registering an existing address answers exactly like a new registration; the owner is emailed a reset link instead.
- **Newsletter opt-in** at registration and in Settings is optional and never pre-ticked. It uses the normal double opt-in signup (source `account`) and only appears while newsletter sign-ups are open.
- **Email verification** links (`/verify-email#token=…`) need a click to confirm. A new link can be requested while signed in, or from `/verify-email` by email with a generic answer. Unverified customers can sign in and see a reminder; they need a confirmed address to buy.
- **Log in** has show/hide password and an opt-in **Keep me signed in** (persistent cookie for `CUSTOMER_SESSION_DAYS`). Without it the cookie ends with the browser and the session expires after `CUSTOMER_SHORT_SESSION_HOURS`. Failures are generic and rate-limited per IP and per address. An ended session is reported once (`session_expired`); its cookies are cleared and the customer is sent to log in with a notice.
- **Password recovery** (`/forgot-password` → email → `/reset-password#token=…`) uses single-use, hashed tokens that expire after `CUSTOMER_RESET_TTL_MINUTES`. Requesting a new link invalidates older ones. Completing a reset signs the customer out everywhere.
- **Redirects** after log in or registration only follow same-site paths: never `//host`, `/\host`, encoded variants, `/admin`, `/api` or another sign-in page.
- **Header (Batch 08.1):** one labelled **Log in** button, always to `/login` (with a safe `?next=` back to the current page), for everyone who isn't signed in as a customer, prerendered pages included. Signed-in customers get the account menu (My account, library, orders, settings, Log out). The cart icon keeps its accessible name ("Cart, 2 items") and tooltip. See _Unified login entry_ below.
- Customers can update their name, and change their password (other devices are signed out).
- **Library:** single products, bundle contents and free items, each listing the versions they may download.
- **Orders:** history with honest statuses, receipts and refund state.
- **Privacy:**
  - `POST /api/v1/account/export` with the current password returns the customer's data (re-authentication; audited).
  - **Delete account** anonymises the profile and ends sessions, but keeps orders, payments, receipts and refunds, which must be retained for financial records.
  - Staff with `customers.manage` can anonymise an account on request.

**Free products** are claimed from the product page by signed-in customers. They create an entitlement with source `free`, with **no order**.

### Unified login entry (Batch 08.1)

There is one public way in, but **two separate authentication systems**: customers
(`customers` table, `tpa_customer` cookies, `X-Customer-CSRF`, `/api/v1/account/*`) and staff
(`users` table, JWT cookies, `X-CSRF-TOKEN`, `/api/v1/admin/auth/*`). Nothing is merged.

- `/login` is the customer sign-in: email, password, _Forgot your password?_, _Create an
  account_, _Find your purchase_ (guest orders) and a discreet **Sign in as staff** link to
  `/admin/login`. If the requested return path is a staff page (`?next=/admin/…`), the page
  says so and the staff link carries that path; the customer form never sends anyone to
  `/admin` (customers land on `/account` or a safe customer path).
- `/admin/login` ("Staff sign in") stays the dedicated staff URL. Staff who are already
  signed in go straight to `/admin` or a safe `next` inside `/admin` (`/admin`, `/admin/…`
  only; protocol-relative, backslash, whitespace and `/admin/login` values are ignored).
  There is no staff registration; _Forgot your password?_ explains that an administrator
  sends a reset link from **Users & access** (the existing admin reset mechanism).
- After sign-in everyone with a staff account lands on the dashboard; the sidebar and every
  API call still follow their role's permissions, so reaching `/admin` grants nothing
  extra (a limited role sees "You don't have access to this area" on other modules).
- **Same email in both systems:** allowed. The page the person chose decides which system
  is asked; the server never tries the other one, so a staff password typed into `/login`
  fails like any wrong password. Errors are generic and identical for unknown emails, and
  customer password-reset requests answer the same way (and send nothing) for staff-only
  addresses.
- **Rate limits** are separate: each login endpoint has its own per-address limit
  (`RATELIMIT_LOGIN`) and its own per-email limit, so locking one doesn't affect the other.
- **Footer:** the bottom bar has a discreet **Staff login** link by default (the _Footer legal
  links_ menu in **Navigation**), which administrators can rename or remove. Internal links
  to `/login`, `/register`, `/forgot-password`, `/purchases`, `/account/settings` and
  `/admin/login` no longer show "does not point to a published page" warnings.

### Guest checkout (Batch 07.6)

Customers can buy without an account. At checkout, signed-out shoppers choose **Continue as guest** (email address, optional name) or **Log in** (or create an account). Signed-in customers check out as before.

**Same payment path.** `POST /api/v1/checkout/guest` validates and normalises the email, then reuses the account checkout code. Prices and totals come from the server (`expected_total_minor` must match), the idempotency key resumes rather than duplicates, and orders become paid only through Paystack verification or a signed webhook (`payments.apply_verified`). Nothing is downloadable before that. Card data never reaches the site.

**Buyer records and no enumeration.** A guest order belongs to the customer record for its email:

- a new **guest** record (status `guest`, no password, can't sign in), or
- the existing account for that address.

The response is identical either way: it carries no profile, library or account state, and only a masked email (`b•••@example.com`). A disabled record gets the generic "contact us" refusal.

**Order token.** `POST /checkout/guest` returns an `order_token` once. Only its SHA-256 is stored (`orders.guest_token_hash`), and it rotates when the same checkout key is resumed.

- The browser keeps it in session storage (never in a URL or cookie) and sends it as `X-Guest-Order-Token`.
- It opens only that order (`/checkout/guest-orders/<id>` and its `verify`, `retry`, `cancel` and `downloads`) for `GUEST_ORDER_ACCESS_HOURS`.
- Downloads from the order page are available for `GUEST_ORDER_DOWNLOAD_HOURS` after payment.

**Access links and recovery.** When a guest order is paid, its emails carry a private link, `/purchases#token=…`.

- It is a hashed `guest_access` customer token, valid for `GUEST_ACCESS_TTL_HOURS`. It is reusable until then, and each new link invalidates older ones.
- It opens only that address's guest-checkout purchases (`POST /guest/library`, `POST /guest/library/downloads`). The token travels in the request body, and the page removes it from the address bar.
- `/purchases` without a valid link asks for the email address (`POST /guest/access-request`). The answer is always the same `202`. A link is sent only if the address has paid guest purchases. Requests are rate-limited per IP and per address.

**Downloads.** Guest downloads use the normal `DownloadGrant`: short-lived (`DOWNLOAD_LINK_TTL_SECONDS`), a few uses, and re-checked when served, so refunds and revocations block them at once. The grant is marked `guest` and is the only kind that skips the session-cookie match. There are no permanent public file links.

**Claiming with an account.** Guest purchases appear in an account (library, orders, downloads, data export) only when its email address is **confirmed**:

- Registering with an address that only has guest purchases turns the guest record into the account. The response looks exactly like a new sign-up, the account starts unconfirmed, and the confirmation email says confirming adds the purchases.
- Someone who registers another person's address can't confirm it, so they see nothing. If they delete that unconfirmed account, the record goes back to being a guest record and the purchases are kept.
- If the real owner resets the password, that proves the inbox: the address becomes confirmed and all other sessions are signed out.
- Unconfirmed accounts always see the same note in their library, whether or not guest purchases exist.

**Admin.** Orders show `guest_checkout`. Guest records appear in Customers with status `guest`. They can be disabled, and "reactivating" one makes it a guest record again, never an account. Refunds, revocations, restores, receipts and the audit trail work the same as for account orders.

## 6. Orders and entitlements

**Order states:** `pending` → `awaiting_payment` → `paid`, then optionally `partially_refunded` or `refunded`.

- `failed`: the provider declined or reversed the payment. The customer can retry, which creates a new payment attempt with a new reference.
- `cancelled`: cancelled by the customer or staff, or expired after `order_expiry_minutes` (default 60).
- Transitions are enforced in the services.
- Paystack's `abandoned` status (the customer has not finished paying yet) keeps the order `awaiting_payment`.
- A payment confirmed after an order failed or expired is still fulfilled, because the money was taken; the order is flagged for staff review.

**Fulfilment is idempotent.** It is performed exactly once per order:

- by a conditional status update (`UPDATE … WHERE status IN (payable states)`);
- backed by unique constraints on provider transaction IDs, on entitlement grant keys and on webhook dedupe keys.

Concurrent webhooks and return-page verifications are safe. PostgreSQL concurrency is covered by a test, `test_concurrent_finalisation_grants_access_once`.

**Entitlements** record the source (purchase, bundle, free, manual), the order item, the purchased file versions and the status (active, revoked, refunded), with a full event history.

- Staff with `entitlements.manage` can grant access manually (with a reason), revoke it or restore it.
- Every change is audited.

## 7. Paystack integration

**Flow.**

1. `POST /api/v1/checkout`: validates the cart and creates the order. The idempotency key and cart hash make repeated clicks return the same order.
2. `POST https://api.paystack.co/transaction/initialize` is called with the amount in subunits, the currency, a unique reference, the callback URL `SITE_URL/checkout/complete?order=…`, the enabled channels and metadata (no personal data beyond the email Paystack needs).
3. The customer pays on Paystack's hosted page.
4. Paystack calls the webhook `POST /api/v1/payments/paystack/webhook`. The return page also calls `POST /api/v1/checkout/orders/:id/verify`. Both paths verify the transaction **server-side** with `GET /transaction/verify/:reference` and check:
   - status `success`;
   - the reference matches the payment attempt;
   - the amount equals the order total in subunits;
   - the currency equals the order currency;
   - the `domain` (test or live) matches the checkout mode.
5. Any mismatch flags the order for review and grants nothing.
6. On success: fulfilment, then the receipt, the order confirmation and the download instructions emails.

**Webhook security.**

- The `x-paystack-signature` header must equal the HMAC-SHA512 of the raw body keyed with `PAYSTACK_SECRET_KEY`, compared in constant time. Otherwise the response is 401.
- `PAYSTACK_WEBHOOK_IPS` optionally restricts source addresses as well.
- Events are stored with a dedupe key. Replays return `duplicate`, and out-of-order events are handled; for example, a refund event that arrives before the payment is confirmed is deferred and reprocessed.
- Stored payloads are sanitised (no card or authorisation data).
- Payment events can be reviewed, and reprocessed, at `/admin/payments` (`payments.view_events`).

**Modes.** `payments.checkout_mode` is `disabled` (the default), `test` or `live`.

- **Test** needs a `sk_test_` key, and only customers marked as test accounts can pay. Staff mark a customer as a test account in `/admin/customers`. `PAYMENTS_TEST_CHECKOUT_PUBLIC=true` lifts the restriction for local development only, and production refuses it.
- **Live** needs `PAYMENTS_LIVE_ALLOWED=true`, a `sk_live_` key and every readiness check passing, including the attestations below.
- Test and live payments are stored with their mode, labelled everywhere ("TEST MODE (no real money)") and reported separately.

**Secrets.** `PAYSTACK_SECRET_KEY` (and optionally `PAYSTACK_PUBLIC_KEY`) live only in `backend/.env`. The admin shows whether a key is configured and its mode, never the key itself. The settings stored in the database are non-secret: mode, currencies, channels, expiry, refund handling, terms version, download limit and attestations.

**Local development without Paystack.** `backend/scripts/paystack_mock.py` is a loopback-only stand-in. It implements initialise, verify and refund, plus a fake hosted page with "Simulate successful/declined payment" buttons, and signs its webhooks like Paystack. No money moves.

```bash
cd backend && source .venv/bin/activate
export PAYSTACK_SECRET_KEY=sk_test_local_mock MAIL_BACKEND=console
python scripts/paystack_mock.py --port 8765 --webhook http://127.0.0.1:5000/api/v1/payments/paystack/webhook &
PAYSTACK_API_BASE=http://127.0.0.1:8765 flask --app wsgi run --debug
```

Production configuration refuses any `PAYSTACK_API_BASE` other than `https://api.paystack.co`.

**Paystack sandbox (real test keys).**

1. Create a Paystack account. Then, in Dashboard → Settings → API Keys & Webhooks:
   - copy the **test secret key** into `PAYSTACK_SECRET_KEY` in `backend/.env`;
   - set the **Test Webhook URL** to `https://<your-domain>/api/v1/payments/paystack/webhook`. Paystack cannot reach `localhost`; for local testing use a tunnel, or rely on the return-page verification.
   - Callback URLs are sent per transaction, so the dashboard callback field can stay empty.
2. Restart Flask. Then, in `/admin/payments`:
   - set mode **Test**;
   - enable the currencies your Paystack account supports (KES for Kenyan merchants; USD only if Paystack has approved it for your account);
   - choose the channels and save.
3. Mark your own customer account as a test account, buy a product, and pay with Paystack's test cards or test mobile money.
4. Check the order in `/admin/orders`: payment verification, webhook event, entitlement, emails.

## 8. Refunds

Refunds are started from an order (`orders.refund`, which maps to the existing `refunds.issue` permission). Each refund takes an amount, a reason, whether to revoke access, and an idempotency key.

- **Provider refunds** (only when "Refunds via Paystack" is enabled in Payment settings): the refund is sent to `POST /refund` and stays `processing` until Paystack confirms it, by webhook (`refund.processed`) or by "Check status". Only then does the order become `refunded` or `partially_refunded` and access get revoked (if chosen). A failure is recorded as `failed`, and the order is unchanged.
- **Manual review** (the default): the refund is recorded as _Awaiting manual refund_. Staff refund the customer in the Paystack dashboard, then use **Record completed refund**, entering the Paystack reference and an explicit confirmation, or **Reject**.

The system never marks a refund as successful on its own. Refund emails are sent only after a confirmed refund.

## 9. Emails and receipts

Templates (`app/services/commerce/emails.py`), plain text:

- email verification
- password reset
- order confirmation
- payment received
- payment failed
- download instructions (guest orders: the private access link instead of the library)
- guest access link (`/purchases`)
- refund confirmation

Every send is recorded in `email_deliveries` with its **real** outcome:

| Recorded status                 | Meaning                       |
| ------------------------------- | ----------------------------- |
| sent                            | SMTP accepted the message     |
| Not sent (development log only) | `MAIL_BACKEND=console`        |
| not configured                  | no mail backend is configured |
| failed                          | delivery failed               |

The admin order page shows these statuses honestly. Staff with `orders.manage` can resend a receipt.

Receipts are numbered (`R-…`), issued only for verified payments, and show the mode (test or live). They are not tax invoices; tax handling is not implemented.

## 10. Reports

`/admin/reports/revenue` (`finance.view`) shows, per currency and per period, gross paid, refunded and net amounts plus order counts.

- Currencies are **never added together**.
- Test and live payments are separate: a selector, with live as the default.
- CSV export needs `finance.export`. Order export needs `orders.export`.

## 11. Permissions

| Permission                                                                   | What it allows                                                                         |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `products.view`, `products.create`, `products.edit`                          | Catalogue access and drafts                                                            |
| `products.publish`, `products.archive`                                       | Publish, unpublish, schedule, archive                                                  |
| `products.manage_prices`, `products.manage_files`, `products.manage_bundles` | Prices, private files, bundle contents                                                 |
| `orders.view`, `orders.manage`, `orders.export`                              | Orders, notes, verification, cancellation, receipts, export                            |
| `refunds.issue` (the "orders.refund" capability)                             | Start, complete and reject refunds                                                     |
| `customers.view`, `customers.support`, `customers.manage`                    | View, resend verification or reset emails, change status, test-account flag, anonymise |
| `entitlements.view`, `entitlements.manage`                                   | View access; grant, revoke, restore                                                    |
| `downloads.audit`                                                            | Download history                                                                       |
| `finance.view`, `finance.export`                                             | Revenue reports and exports                                                            |
| `payments.view_events`                                                       | Payment provider events                                                                |
| `payments.configure` (the "payments.manage_settings" capability; sensitive)  | Payment settings and live activation: Super Admin only                                 |

Role templates:

- **Super Admin:** all permissions.
- **Administrator:** all product permissions, plus orders (view, manage, export), customers (all), entitlements (all), downloads audit, payment events and finance view.
- **Product Manager:** all product permissions, plus media view, upload and edit.
- **Orders Manager:** products view, orders (view, manage, export), refunds, customers (view, support), entitlements (all), downloads audit, payment events.
- **Customer Support:** products view, orders view, customers (view, support), entitlements view, downloads audit.
- **Finance Manager:** products view, orders (view, export), refunds, payment events, finance (view, export).
- **Marketing Manager:** products view.
- **Editorial roles** (Editor, Content Editor, Content Writer, Moderator, Analyst …): no commerce permissions.

## 12. Live activation checklist

Live checkout cannot be switched on until **every** item below passes. `/admin/payments` shows each check and blocks the Live option until all pass.

Deployment (server administrator):

- [ ] Production config passes validation (`FLASK_CONFIG=production`): HTTPS, Secure cookies, SMTP mail (`MAIL_BACKEND=smtp`), PostgreSQL, Redis rate limits.
- [ ] `PAYSTACK_SECRET_KEY` is a **live** key (`sk_live_…`), stored only in `backend/.env` with restricted file permissions.
- [ ] `PAYSTACK_API_BASE` is unset or `https://api.paystack.co`.
- [ ] `PAYMENTS_LIVE_ALLOWED=true` is set deliberately.
- [ ] `PRODUCT_FILES_ROOT` is on persistent, backed-up storage outside the web root, writable by the app user only. Nginx `internal` location configured if using `X-Accel-Redirect`.
- [ ] Publishing worker running (scheduled publishing, order expiry, file scanning). Malware scanner configured if possible.

Paystack merchant (business owner):

- [ ] The Paystack business is fully activated: compliance approved, settlement account verified.
- [ ] Every enabled currency is approved for **live** charges on the account (USD and international cards need explicit Paystack approval).
- [ ] The **Live Webhook URL** `https://<domain>/api/v1/payments/paystack/webhook` is saved in the Paystack dashboard.
- [ ] Payment channels enabled in the admin match those active on the account.

Content and policy (Super Admin in the admin):

- [ ] Terms of sale, refund policy and privacy policy are published and reviewed for digital products. The **terms version** is recorded in Payment settings.
- [ ] Products for sale have correct prices per currency, final files, and accurate descriptions (no placeholder or invented claims).
- [ ] A complete **test-mode** purchase has been verified end to end: payment, webhook processed, library download, receipt email received, refund recorded.
- [ ] The five attestations in Payment settings are ticked by the Super Admin.
- [ ] Switch mode to **Live**, make one small real purchase, verify it and refund it, and confirm the report shows it under **live**.

## 13. Operations

```bash
flask --app wsgi commerce payments-status     # mode, readiness checks (no secrets printed)
flask --app wsgi commerce expire-orders       # also run by the publish worker
flask --app wsgi commerce scan-files          # run the configured malware scanner now
flask --app wsgi commerce seed-catalogue      # re-add missing starter titles (never overwrites)
```
