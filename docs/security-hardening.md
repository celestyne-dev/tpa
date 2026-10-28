# Release security hardening (Batch 12.1)

A focused review before staging. It covers verified defects (fixed, with regression
tests in `backend/tests/test_security_hardening.py`), controls that were checked and
found sound, potential risks that were not changed, and what needs checking on staging.

## Verified defects (fixed)

| # | Defect | Fix |
|---|--------|-----|
| 1 | **CSV formula injection in the finance revenue export** (`GET /admin/reports/revenue/export`, `finance.export`). Product titles from order lines were written raw, so a title such as `=HYPERLINK(...)` ran as a formula when the file was opened in a spreadsheet. | Now uses the shared safe writer `app/utils/csv_safe.py` (moved from the Batch 11.5 analytics exports, which re-export it). |
| 2 | **CSV formula injection in the orders export** (`GET /admin/orders/export`, `orders.export`). Customer emails (a valid address can start with `=` or `+`) and item titles were written raw. | Safe writer. |
| 3 | **CSV formula injection in the redirect export** (`GET /admin/redirects/export`). Redirect notes are free staff text. | Safe writer. |
| 4 | **Incomplete formula guard in the subscriber export** (`GET /admin/subscribers/export`). The local check `v[:1] in "=+-@"` missed tab and carriage-return prefixes. It also turned every empty cell into `'`, because `"" in "=+-@"` is true in Python. | Uses the shared `safe_cell`, so empty cells stay empty. |
| 5 | **Production start-up accepted mismatched Paystack keys**, for example a `pk_test_` public key with an `sk_live_` secret key (or the reverse, or a secret key in the public key slot). | `ProductionConfig.validate` rejects a public key that is not `pk_` in the same mode as the secret key. |
| 6 | **Production start-up accepted any `MEMBERSHIP_BILLING_MODE`**, including `live`. Billing code only acts on `test`, so this was not exploitable, but a typo or a `live` value went unnoticed. | `validate` requires `disabled` or `test`. Live membership billing can never be configured by environment alone. |

The partnership report export now also uses the safe writer, for consistency. Its cells
today are only currency codes and numbers, so it was not exploitable.

The shared rule prefixes cells that start with `=`, `+`, `-`, `@`, tab or CR with an
apostrophe. Plain numbers, including negative decimal strings such as a net amount of
`-3.00`, are left unchanged so finance figures stay numeric.

Production settings were not changed. These are start-up checks only. A deployment whose
settings are already correct starts exactly as before. A misconfigured one now refuses to
start, with a clear message.

## Controls verified (no change needed)

- **Admin authorisation:** every admin resource method carries `require_permission` or
  `require_any_permission`, except login, refresh and logout.
  - The analytics overview and exports include a module only when the user holds that
    module's own permission.
  - Financial CSV exports need `finance.export`.
  - The learning, membership and audience reports return aggregates only.
- **Customer data:** account endpoints require a customer session and only read the signed-in
  customer's own records. Learning search returns only preview or accessible content.
- **Payments:** orders become `paid` only in `apply_verified`, after the provider verifies the
  reference, amount, currency, mode and provider transaction id. The update is conditional
  on a payable status, so it is race-safe.
- **Memberships:** subscriptions become `active` only from a verified charge
  (`activate_from_order`, `apply_renewal`). Live membership billing is refused unless
  `MEMBERSHIP_BILLING_MODE=test`.
- **Test checkout:**
  - In production, test-mode checkout is limited to customers flagged as test accounts.
  - `PAYMENTS_TEST_CHECKOUT_PUBLIC` is rejected at start-up.
  - The effective mode is capped by the secret key's mode and by `PAYMENTS_LIVE_ALLOWED`.
- **Webhooks:**
  - HMAC-SHA512 signature compared in constant time.
  - 512 KB body cap.
  - Events are deduplicated through a unique `PaymentEvent.dedupe_key`.
  - A transaction is recorded at most once (unique key plus a savepoint).
- **CSRF:**
  - Admin uses JWT cookies with double-submit CSRF and SameSite=Strict.
  - Customer sessions check the `X-Customer-CSRF` header against the cookie and the stored hash.
  - Private API prefixes also get an origin check.
- **Rate limits:** set on admin login, customer login (also per email), registration, password reset, email
  verification, checkout, downloads and public tracking.
- **Logs:** payment logs carry order numbers and references only, never card data or
  secrets. The console mail backend logs full emails, but production refuses to start with it.
- **Tracking:** no IP addresses, cookies or query strings except UTM tags. Admin, account
  and checkout paths are never recorded.

## Potential risks (not changed)

- **Rate-limit storage defaults to `memory://`.** With 3 gunicorn workers each worker keeps
  its own counters, so the effective limit is about three times the configured one. The
  systemd example already says to set `RATELIMIT_STORAGE_URI=redis://…`. Making Redis
  mandatory would be new infrastructure, so it is only documented here.
- **`ProxyFix` trusts one proxy hop** (`x_for=1`). That is correct behind nginx. If another
  proxy or CDN is added in front, client IPs, and so rate limits, will be wrong.
- **New CSV exports** must use `app.utils.csv_safe.SafeWriter`. After this batch, the
  subscriber export is the only other module that writes CSV, and it uses `safe_cell`.
- **Unrelated failing test:** `test_seo_publishing.py::test_static_paths_match_the_frontend`
  also fails on the base commit. The frontend static routes, for example `/membership` and
  `/affiliate-disclosure`, no longer match the sitemap's `STATIC_PATHS`. It is an SEO and
  sitemap drift, not a security issue, and is left for a separate fix.

## Staging verification

1. **Paystack test webhook:** a real test-mode webhook with a correct signature is accepted
   once, and a replay is a no-op. A tampered body is rejected with 400.
2. **Secure cookies:** over HTTPS, admin and customer cookies carry `Secure`, `HttpOnly`
   (session) and the expected SameSite flags.
3. **Client IP behind nginx:** rate limits key on the real client IP (`X-Forwarded-For`
   from nginx), not 127.0.0.1.
4. **Redis-backed limits:** `RATELIMIT_STORAGE_URI` points at Redis, and limits hold
   across workers.
5. **Billing stays off:**
   - `MEMBERSHIP_BILLING_MODE` is `disabled` or `test`.
   - `PAYMENTS_LIVE_ALLOWED` is unset or false.
   - Admin payment settings show checkout `disabled` or `test`.
   - Public and secret key modes match, otherwise the app refuses to start.
6. **Exports in a spreadsheet:** open the revenue, orders, redirect and subscriber exports
   in Excel and LibreOffice. Cells starting with `=` show as text, and numbers stay numeric.
