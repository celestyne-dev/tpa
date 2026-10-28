# Performance and scalability (Batch 12.2)

What changed before staging, how it was checked, and what is left. No feature, permission,
payment or report definition changed.

## Frontend

### Admin code splitting

`frontend/src/admin/AdminApp.jsx` used to import all ~68 admin screens eagerly, so the
`AdminApp` chunk held every admin page and opening any admin URL downloaded all of them.

- **One lazy chunk per screen.** Each screen is now a `React.lazy` import, with the loaders
  in `frontend/src/admin/screens.js`.
- **Guards still run first.** A permission guard renders its page only when access is
  allowed, so a page's code is never even requested for users without access. Hiding UI
  remains a convenience; Flask still authorises every request.
- **Still eager:** login, account activation, password reset and the dashboard, which is
  the admin landing page.
- **Loading state:** the admin layout wraps its `<Outlet/>` in a `Suspense` boundary, so the
  sidebar and header stay usable while a screen loads. The three full-screen preview routes
  have their own boundary.
- **SSR and prerender are unaffected.** The admin area was already a lazy chunk that is
  never prerendered, and public routes are unchanged.
- **Tests:**
  - `preloadAdminApp()` in the test utilities also preloads every screen.
  - `src/admin/screens.test.js` checks that each lazy screen resolves to a real export, and
    that none is imported statically again.

**Bundle sizes.** No production build was run during implementation. The existing
`frontend/dist` (built 27 October, before Batches 11.2–12.1) is the only measured
reference:

| Chunk | Raw | Gzip |
|-------|-----|------|
| `index` (public entry) | 602 KB | 181 KB |
| `AdminApp` | 570 KB | 141 KB |
| `pages` (customer/learner) | 142 KB | 36 KB |
| CSS | 88 KB | 15 KB |

After `npm run build:client`, expect a much smaller `AdminApp` chunk plus about 60 small
per-screen chunks. Shared admin components are split into common chunks automatically.
To compare, run `ls -l dist/assets/*.js` and `gzip -c <file> | wc -c` in WSL.

### CSS optimizer warnings

The 5 warnings come from Lightning CSS (Vite 8's CSS minifier). All of them are about the
`::highlight(tpa-hl-*)` rules in `src/assets/styles/globals.css`. These are valid CSS
Custom Highlight API rules for reader highlights (Batch 9.1); Lightning CSS doesn't
recognise the pseudo-element yet. All 5 rules are kept in the minified output, so the
warnings are cosmetic and the CSS was left unchanged.

## Analytics

### Unified overview

The overview used to build every module's **full** report twice, once for the current
range and once for the previous one:

- trends, product, category and refund tables, and commerce conversion, which re-reads
  page views;
- all-time enrollment loads and per-course, assessment and assignment tables;
- the membership monthly trend, about 5 queries per month for up to 25 months, plus the
  access breakdown;
- every subscriber signup, confirmation and unsubscribe row in the range.

The overview figures themselves only need a fraction of that.

Each module now has a summary function built from the **same helpers** as its full report,
so the definitions can't drift:

| Module | Summary | What it skips |
|--------|---------|---------------|
| Website | `traffic_totals` (previous range) | Pages, sources and articles for the previous range |
| Commerce | `commerce_summary` | Trends, refund attribution, categories, unsold products, conversion; products for the previous range |
| Learning | `learning_summary` | Enrollments loaded once for both ranges; no per-course, assessment or assignment tables |
| Membership | `membership_summary` | Monthly trend, access, per-plan tables; current figures computed once |
| Audience | `audience_summary` | Counts in SQL instead of loading rows; no campaign list or lead magnets |

For a 12-month overview with all modules, the test data set needed **246 queries** for the
old approach (each full report for both ranges) and needs **68** now. See
`test_overview_issues_far_fewer_queries_than_full_reports`.

`campaigns_sent` keeps the audience report's existing 50-campaign cap, so the overview and
the Audience tab show the same number.

### Other analytics changes

- **Website sources:** rolled-up daily source rows are summed with `GROUP BY` in the database.
  Before, one row per day and source combination was loaded and summed in Python. The
  result is identical because visitors are per-day counts, so their sum is the same "sum of
  daily visitors".
- **Commerce test vs live:** sales per mode and currency are counted with one grouped
  query instead of loading every charge in both modes.

### Indexes

Migration `a7c2e9f4b318` adds indexes only:

| Index | Supports |
|-------|----------|
| `payment_transactions (kind, created_at)` | Finance, commerce and membership revenue ranges |
| `orders (paid_at)` | Recognised orders in a range |
| `subscribers (created_at)`, `(confirmed_at)`, `(unsubscribed_at)` | Audience period counts |

### Caching

No cache was added. With several gunicorn workers, an in-process cache would give each
worker a different view. Financial figures are expected to reflect a refund or payment
straight away. After the changes above, the overview is a single-digit number of queries
per module. Revisit with Redis, which is already recommended for rate limits, only if
real traffic shows a need.

## API listings (N+1)

| Listing | Before | After |
|---------|--------|-------|
| Affiliate links (`list_links`) | One click-sum query per link | One grouped query |
| Entitlements (`list_entitlements`, max 100 per page) | Events and order queries per row | Events and orders batched per page |
| Membership subscriptions (`list_subscriptions`, max 100 per page) | Customer and plan lookups per row | Batched per page |

Single-item serialisers (`link_dict`, `entitlement_dict`) behave as before when called on
their own. In tests, the affiliate list stayed at the same number of queries from 2 to 8
links, where before it grew from 3 to 9. The entitlement list stayed flat from 2 to 8 rows,
where before it grew from 15 to 39.

Already efficient, unchanged:

- product, file, version and assignment-attempt relationships load with `selectin`;
- admin page sizes are clamped to 1–100.

## Remaining risks

- **Public entry bundle (~600 KB raw):** every public page is in the entry bundle on
  purpose, because prerendered pages hydrate without a loading flash. Splitting them would
  need the route's chunk preloaded before hydration. The admin API client (~32 KB of
  source) is also in the public bundle because the store wires it in. Moving it out would
  change how the store is set up, so it is left for a separate change.
- **Admin products list:** unpaginated, because the admin filters it in the browser. It is
  fine for a catalogue of hundreds of products. Paginate it if the catalogue grows into
  thousands.
- **Full module reports:** the full Learning report still loads all enrollments for each
  request, and the Membership tab's monthly trend still runs about 5 count queries per
  month. Both are bounded (25 months at most), but they grow with history.
- **Raw page views:** the website report reads raw page views only for days not yet rolled
  up. If the `tpa-analytics-maintain` timer stops, raw-day reads grow. The health panel
  already warns about this.
