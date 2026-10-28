# Website analytics (Batch 11.1)

First-party, cookieless page-view analytics for the public site, built into the existing
Flask API and React admin. No external analytics vendor and no new service are used.

## How it works

1. **Browser.** `frontend/src/analytics/pageViews.js` (used by `RootLayout`) sends one
   beacon per route with `navigator.sendBeacon` to `POST /api/v1/analytics/collect`:
   - on first load and on each client-side navigation;
   - query-only changes are not new page views;
   - the body holds the path, the query string (only UTM tags survive on the server),
     the referrer on first load only, and whether it was an in-app navigation;
   - no cookies or browser storage are used, and there is no fallback request.

   The beacon is skipped for automated browsers (`navigator.webdriver`), Do Not Track,
   Global Privacy Control and private routes. Prerendering never runs effects, so
   prerendered pages send nothing.
2. **Ingestion.** `services/analytics/tracking.py` validates and minimises the beacon,
   then inserts one row into `analytics_page_views`. The endpoint always answers `204`
   with no body.
3. **Rollups.** The timer runs `flask analytics maintain` hourly
   (`deploy/systemd/tpa-analytics-maintain.{service,timer}.example`):
   - each completed day (UTC) is aggregated once into `analytics_daily_pages`,
     `analytics_daily_sources` and `analytics_rollup_days`;
   - then retention is applied.
4. **Reports.** `GET /api/v1/admin/analytics/traffic` reads rollups for completed days and
   raw rows for days not yet rolled up (normally just today).

## What is recorded and what is never stored

| Recorded | Never stored |
| --- | --- |
| Normalised path (no query string or fragment, no trailing slash) | IP address (only a truncated /24 or /48 network is used, in memory, for the hash) |
| Page type (home, article, topic, shop, product, course, membership, resource, page) | User agent |
| Article or topic id resolved from the slug | Cookies, browser ids, account, customer or admin ids |
| Source (direct, search, social, email, referral, campaign, internal) | Full referrer URL (host only) |
| Referrer host | Query parameters other than the UTM allowlist |
| UTM `source`, `medium`, `campaign`, `content`, `term` (lowercased, `[a-z0-9._+- ]`, ≤100 chars, dropped if they contain `@`) | |
| Server receive time and UTC day | |
| A visitor hash | |

The visitor hash is SHA-256 of (random daily salt, truncated network, user agent), cut
to 16 hex characters. A new random salt is created each UTC day and deleted once the
day is over, so hashes can't be reversed or linked across days.

**Not recorded at all:**

- **Routes:** admin and API routes, and account, checkout, cart, purchases, learning,
  certificates, sign-in and registration pages, email verification, password reset,
  newsletter confirm/preferences/unsubscribe, and resource access links.
- **Paths:** any path segment that looks like a token (32+ hex characters, or a long
  mixed-case string with digits), and paths containing `@`.
- **Requests:**
  - bots and automation tools (user-agent patterns, including headless browsers and
    prerenderers), and requests with an empty user agent;
  - `DNT: 1` and `Sec-GPC: 1` (switch with `ANALYTICS_RESPECT_DNT`);
  - cross-site requests (`Sec-Fetch-Site: cross-site`, or an untrusted `Origin`) and
    prefetches;
  - bodies over 2 KB and malformed JSON;
  - repeat hits of the same path by the same visitor hash within 30 seconds
    (reloads, double fires).
- **Health checks** never touch the beacon.

### Visitors and sessions

- **Visitors** are estimated per day (distinct hashes). The same person on two days counts
  twice, so ranges show "daily visitors (sum)" and the dashboard says so. Visitors
  sharing a network and browser version can merge, so this is an estimate.
- **Sessions are not measured**: without cookies they can't be identified reliably.

### Consent

Nothing is stored on or read from the visitor's device, and no personal data is kept.
Raw IPs and user agents are only used transiently to compute the daily hash. This
approach normally needs no cookie banner. The site owner should still:

- mention first-party analytics in the privacy policy;
- confirm the approach with their own legal advice for their audience's jurisdictions.

Do Not Track and GPC are honoured by default.

## Configuration (`backend/.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANALYTICS_TRACKING` | `enabled` | `disabled` stops recording; reports still show stored data |
| `ANALYTICS_RESPECT_DNT` | `true` | Ignore `DNT: 1` / `Sec-GPC: 1` requests |
| `ANALYTICS_RAW_RETENTION_DAYS` | `90` (7–400) | Raw page views, deleted only after their day is rolled up |
| `ANALYTICS_AGGREGATE_RETENTION_DAYS` | `760` (30–3650) | Daily rollups |
| `RATELIMIT_ANALYTICS_COLLECT` | `60 per minute;1000 per hour` | Per client address (Flask-Limiter; use Redis in production as for other limits) |

nginx must forward the client address (`X-Forwarded-For`, already used with `ProxyFix`).
Otherwise every visitor shares one hash and one rate limit.

## Permissions

Reports reuse the existing `analytics.view` permission ("View content analytics"). It is
held by the Super Admin, Administrator, Editor-in-Chief, Analyst, Marketing Manager and SEO Manager roles, as
already defined in RBAC. No new permission was needed. The endpoint is checked
server-side, and the admin "Analytics" section is hidden from other roles.

## Admin API

`GET /api/v1/admin/analytics/traffic` takes these parameters:

| Parameter | Values |
| --- | --- |
| `range` | `7d`, `30d` (default), `90d`, `365d` |
| `date_from`, `date_to` | `YYYY-MM-DD`; ranges up to 800 days |
| `granularity` | `day`, `week` or `month` (automatic by default) |

It returns:

- totals;
- a series with every period in range, zero when nothing was recorded;
- top pages and page types;
- popular articles with their topic;
- top categories (article views by primary topic, plus topic page views);
- sources, referring hosts and campaigns;
- measurement notes and tracking/retention status.

## Performance

- **Ingestion** is one small indexed duplicate check plus one insert per page view, with
  no extra requests. An article or topic slug lookup uses a unique index. On a Hostinger
  VPS with PostgreSQL this is far below the cost of serving the page itself. For very
  high traffic, the endpoint can be moved to a queue without changing the schema.
- **Reports** over completed days read only daily rollups: about one row per page per
  day, plus source combinations. Raw rows are only scanned for days not yet rolled up.
- **Indexes:**
  - raw `(day, page_type)`, plus `(visitor_hash, occurred_at)` for duplicate checks;
  - unique `(day, path)` and `(day, source, referrer, utm…)` on the rollups.
- **Rollups and retention** run hourly and are idempotent. A missed run is caught up on
  the next one, and reports include not-yet-rolled days from raw rows.

## Deployment

```bash
flask db upgrade            # adds f2b6d8e4a173 (tables only)
sudo cp deploy/systemd/tpa-analytics-maintain.{service,timer}.example /etc/systemd/system/
# drop the .example suffix, then:
sudo systemctl daemon-reload && sudo systemctl enable --now tpa-analytics-maintain.timer
```

Not included yet: commerce, learning and membership analytics (later Batch 11 phases),
device/country breakdowns, and real-time views.

# Commerce and revenue analytics (Batch 11.2)

The Commerce tab of Admin → Analytics is backed by `GET /api/v1/admin/analytics/commerce`
and a CSV export at `GET …/commerce/export`. No schema changes; it reads existing
orders, order lines, payment transactions and products, plus the Batch 11.1 page views.

## Access

| Endpoint | Requires |
| --- | --- |
| Report | `finance.view` (existing financial permission) |
| CSV | `finance.export`; exports are audited (`finance.commerce_analytics_exported`) |

- Analytics-only roles (`analytics.view` without `finance.view`, e.g. Analyst, Marketing,
  SEO) don't see the Commerce tab, and the API refuses them.
- The report is aggregates only: no order numbers, customer names, emails or ids.

## Definitions (same as the existing finance revenue report)

| Term | Meaning |
| --- | --- |
| Gross revenue / verified sales | Provider-verified `charge` payment transactions (written only after Paystack verification), by recorded time |
| Refunds | Processed `refund` transactions. Net = gross − refunds, before provider fees |
| Paid orders | Orders that reached `paid` (or were later refunded), by `paid_at`. Pending, awaiting payment, failed and cancelled/expired orders are never sales; they appear only in "Orders by status" (by creation date) |
| Average order value | Total of paid orders ÷ number of paid orders, per currency |
| Product revenue | Historical order-line totals (the price actually paid), never current catalogue prices |

**Scope:** product purchases (`orders.kind = 'purchase'`). Membership subscription
payments are in Membership reports.

**Filters:**

- **Mode:** live by default, or test. Test and live are never mixed. A separate table
  shows both modes side by side.
- **Currency:** each currency is reported separately; there is no conversion and no
  combined total.
- **Dates:** the same date presets and grouping as the Website tab.

## Products

The tab shows:

- best sellers by units, with revenue and attributable refunds;
- courses vs premium resources vs bundles;
- product types;
- categories, using each product's current category links with historical revenue;
- published paid products with no sales in the range.

Refunds are attributed to a product only when the refunded order has a single line.
Refunds on multi-product orders are shown as "unattributed".

## Conversion

- **Sales per measured page view:** paid orders per 1,000 page views, and units per 100
  product-page views per product.
  - Computed only on days where page views were measured, and only for live payments.
  - These are ratios of counts, not conversion rates: buyers can purchase without viewing
    a product page, and opted-out visitors aren't measured.
- **Visitor or session purchase conversion is unavailable**, and is always reported as
  such. Orders are deliberately not linked to visitors (cookieless tracking, no
  identifiers).

# Learning analytics (Batch 11.3)

The Learning tab of Admin → Analytics is backed by `GET /api/v1/admin/analytics/learning`.

- **Parameters:** `range` / `date_from` / `date_to`, `granularity` (day, week or month)
  and `course` (id).
- **Sources:** existing LMS records only: enrollments, lesson progress, assessment
  attempts, and assignment submissions, attempts and grades.
- **No new tracking, no schema change.**

## Access and privacy

| Section | Requires |
| --- | --- |
| Endpoint and Learning tab | `courses.view_reports` (Super Admin, Administrator, Editor-in-Chief, Analyst, Marketing Manager) |
| Assignment and grading section | Also `assignments.view_reports`; otherwise reported as unavailable |

- Roles with only `analytics.view` (e.g. SEO Manager) get a 403.
- Responses are aggregates only. They never contain learner names, emails, answers,
  essay responses, feedback, private notes or individual grades. Learner-level detail
  stays in the existing course enrolment and grading screens with their own permissions.

## Definitions

| Metric | Meaning |
| --- | --- |
| Enrollment | One row per learner and course (unique), so duplicates are impossible. "Current" excludes revoked access |
| Access type | `free`, `purchase` (bought individually), `membership` (included in a membership) or `manual` (staff grant), from the enrollment's source |
| Started | At least one lesson viewed, or completed. Start time = first lesson view (or completion time when no views were recorded) |
| Completed | Completion recorded by the course's own completion rules |
| Completion rate | Completed ÷ current enrollments, plus completed ÷ started |
| Unfinished | Started, not completed. "Not started" = current enrollments with no lesson view |
| Active learners (range) | Learners with a lesson view, lesson completion, assessment or assignment submission in the range. Only the first and latest view of each lesson are stored, so this is a minimum |
| Trends | New enrollments (`enrolled_at`), starts and completions per day, week or month |
| Course table | All-time enrolled, started, completed and average progress, plus non-draft assignment submissions, assessment participants and the average of each learner's best score on graded, non-practice quizzes. New enrollments and completions are also given for the range |
| Lesson progress (one course) | Per published lesson: learners who viewed it and completed it (and % of started learners). "Stopped here" = unfinished learners whose furthest completed lesson is this one: where learners stall, not why |
| Assessments (range) | Submitted attempts by type: graded quizzes, timed (time limit, not practice), practice, and ungraded reflections/self-assessments. Expired timed attempts are counted separately. Pass rate = passed ÷ graded attempts; retakes count as attempts, participants are distinct learners |
| Assignments (range) | Attempts submitted (and late); grades published with pass/fail and average percent; "changes requested" grades. The grading queue (pending, under review, resubmitted) and submissions awaiting resubmission are current snapshots |

## Performance and limitations

- Range-bound attempt, grade and lesson-view queries filter by date in SQL using the
  existing tables. There is no new index; on very large histories consider an index on
  `assessment_attempts.submitted_at` and `assignment_attempts.submitted_at`.
- Course-level figures are computed from the course's enrollments (all time) in Python.
  That is fine at the current scale, but it hasn't been load-tested.
- Time spent per lesson, repeated lesson views and session lengths aren't stored, so they
  aren't reported.

# Membership and audience analytics (Batch 11.4)

No schema changes and no new tracking or integrations.

## Membership tab

`GET /api/v1/admin/analytics/membership` takes `range` or `date_from`/`date_to`, and
`plan` (public id). It requires `memberships.view_reports` (Super Admin, Administrator,
Analyst, Finance Manager).

It extends the Batch 10.4 membership report rather than duplicating it.

| Area | Content and definition |
| --- | --- |
| Overview (from 10.4) | Paid subscribers (verified activation; active, past due or grace), monthly/yearly split, past-due and grace counts, cancelling, complimentary (separate, never paid). Period figures: new subscriptions, paid renewals, cancellations requested, endings by reason, monthly trend with churn (ended ÷ active at month start; "not enough data" without a base), membership access |
| Realised revenue | Verified Paystack charges and processed refunds on membership orders, grouped by mode and currency, never converted. Revenue by plan attributes each payment through its billing period to the plan it paid for |
| MRR / ARR | **Estimates, not revenue.** Active, non-cancelling subscriptions at the price agreed at checkout (yearly ÷ 12); ARR = MRR × 12, per mode and currency. Past-due, grace and cancelling memberships are shown separately as "at risk" |
| Plan filter | Applies to the plan, recurring, revenue-by-plan and complimentary tables. The overview covers all plans |

Test-mode payments are always labelled.

## Audience tab

`GET /api/v1/admin/analytics/audience` takes `range` or `date_from`/`date_to`,
`granularity` and `campaign` (public id). It requires `newsletters.reports` (Super Admin,
Administrator, Marketing Manager, Newsletter Manager).

| Metric | Definition |
| --- | --- |
| Subscribed contacts | Status `subscribed` now. Pending, unsubscribed, bounced/complained and quarantined are shown separately |
| Signups | Subscriber records created in range, including unconfirmed |
| New subscriptions | Double opt-in confirmations in range |
| Unsubscriptions | Unsubscribes recorded in range |
| Growth | New − unsubscriptions per period. A historical running total is **not** reconstructed, because statuses change in place |
| Sources | The recorded signup source: new in range, and subscribed now |
| Campaigns | Campaigns finished sending in range (or the selected one): eligible, accepted by the provider (not proof of delivery), and delivered / bounced / complained, which exist only from signed provider feedback |
| Opens and clicks | **Not tracked** (no pixels or link redirects); always reported as unavailable |
| Lead magnets | Claims in range, and confirmed subscribers whose signup source is that lead magnet |

## Privacy

Both endpoints return aggregates only, with no emails, names or individual activity.
Each tab is shown only to staff holding its permission, and the server enforces the same
permission.
