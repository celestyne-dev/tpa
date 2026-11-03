# Legacy website inventory and SEO migration (Batch 12.4A)

Protects every public URL, article, backlink and search signal of the current
`https://thinkpositivealways.com` before the new site replaces it. The current website
stays untouched until the comparison below passes: every tool here only **reads** it
(HTTP GET, robots.txt respected, one request per second by default).

Nothing in this workflow deploys, changes DNS, deletes content or modifies either CMS.
The only write is `flask legacy import-redirects --apply`, which creates redirects in the
**new** CMS for approved rows and never replaces an existing redirect, article or page.

## Editorial decisions (revised 2026-11-03)

The legacy CMS holds 89 article records: 45 Published and 44 Draft.

1. **Only the 45 published articles are rewrite candidates.** The 44 drafts are listed in
   `draft-articles.csv` and are never rewritten, published or imported. A draft is never
   reported as a missing published article. A record without an explicit status counts
   as `unknown`: it goes to `other-status-articles.csv` and isn't assumed published.
2. **Published articles are rewritten from scratch later,** with original content. No
   step copies legacy body text, and the rewrite plan has no content column.
3. **Exact URLs only.** Each published article's public URL and canonical URL come from
   the export, the page itself or the inventory. Slugs are never derived from titles.
4. **Established canonical paths are preserved where the new site supports them.**
   - A canonical of the form `/articles/<slug>` stays exactly the same.
   - Any other path (for example root-level `/<slug>`) keeps its own slug at
     `/articles/<slug>` and gets one 301, because the new site serves articles only
     under `/articles/`.
5. **The legacy taxonomy is not reused automatically.** New sections come only from
   approved editorial decisions in `taxonomy-decisions.csv`. Category URLs redirect only
   by such a decision. Article URLs never depend on a category or section, so
   restructuring the taxonomy can't change them.
6. **Specialist topics need an expert or exclusion.** Medical, mental-health, legal and
   financial topics are flagged `EXPERT_REVIEW`. The site doesn't give independent
   regulated professional advice: such articles need a qualified reviewer (recorded in
   `suitability_decided_by`) or are excluded.
7. **The live website stays untouched** until the new articles, canonical URLs and
   redirects pass the prelaunch checks.

## What we know so far (2026-11-03)

- **The live site is a client-rendered JavaScript app.** Its homepage HTML has a title,
  a description and a canonical, but no links, so an HTML crawl can't find articles by
  itself. The inventory's probe detects this and marks app-shell pages as `shell_only`.
  Their content must be confirmed from the database export, the article API or Search
  Console.
- **Live URLs use several patterns:**
  - articles under `/articles/<slug>`
  - at least one root-level article: `/50-kindness-quotes-to-brighten-your-day`
  - root-level pages and categories with trailing slashes: `/about-us/`, `/lifestyle/`,
    `/quotes-affirmations/`
- **The April 2026 legacy code differs from the live site.** `celestyne-dev/TPA-frontend`
  routed articles at `/article/<id>` and listed only 10 static pages in its sitemap,
  including `/about` while the route was `/about-us`. It's older than what's deployed,
  but backlinks to those patterns may still exist.
- **Seed file:** [`legacy-migration/discovered-urls-2026-11-03.csv`](legacy-migration/discovered-urls-2026-11-03.csv)
  lists the 26 URLs found so far, each with its evidence (12 from web search, 14 from the
  legacy repository). It is a starting seed, not the inventory.
- **No crawl yet.** The live site couldn't be crawled from the build environment because
  egress policy blocked it. Run the inventory from the VPS or any normal machine.

## Workflow

Run from `backend/`. The toolkit uses only the Python standard library, so it runs on
the current VPS without installing anything.

```bash
# 1. Inventory the legacy site (repeat on another day: retiring needs two observations).
python -m legacy_migration inventory \
  --base-url https://thinkpositivealways.com --host www.thinkpositivealways.com \
  --start /articles/ --start /quotes-affirmations/ --start /lifestyle/ \
  --seeds ../docs/legacy-migration/discovered-urls-2026-11-03.csv \
  --seeds gsc-pages.csv --seeds gsc-links.csv --seeds old-sitemaps.txt \
  --articles-csv legacy-articles-db.csv \
  --articles-api https://thinkpositivealways.com/api/public/articles?limit=1000 \
  --out migration/inventory-2026-11-03

# 2. Rewrite plan: published articles only, with exact URLs, section and suitability.
#    Re-run with --previous after editing: editor columns are kept, URLs recomputed.
python -m legacy_migration rewrite-plan \
  --export legacy-articles-db.csv \
  --inventory migration/inventory-2026-11-03/inventory.csv \
  --taxonomy taxonomy-decisions.csv --base-url https://thinkpositivealways.com \
  --expect-published 45 --expect-draft 44 --out migration/rewrite
python -m legacy_migration validate-rewrite migration/rewrite/rewrite-worklist.csv

# 3. Export the new CMS's live URLs (read-only; on staging).
flask --app wsgi legacy export-cms --out migration/new-site.csv

# 4. Propose the URL mapping, the content worklist and the report.
python -m legacy_migration map \
  --inventory migration/inventory-2026-11-10/inventory.csv \
  --inventory migration/inventory-2026-11-03/inventory.csv \
  --articles migration/inventory-2026-11-10/legacy-articles.csv \
  --taxonomy taxonomy-decisions.csv \
  --new-site migration/new-site.csv --out migration/map

# 5. Review migration/map/url-mapping.csv: set approved=yes, approved_by and note; edit
#    action/target_path where needed. Re-run step 4 with --overrides <reviewed file>
#    once rewritten articles are in the CMS: approved decisions are kept.
python -m legacy_migration validate migration/map/url-mapping.csv --new-site migration/new-site.csv

# 6. Publish the rewritten articles at proposed_new_path (setting original_url and
#    original_slug), then apply redirects.
flask --app wsgi legacy import-redirects migration/map/url-mapping.csv           # dry run
flask --app wsgi legacy import-redirects migration/map/url-mapping.csv --apply --actor-email you@example.com
python -m legacy_migration gone-conf migration/map/url-mapping.csv --out tpa-legacy-gone.conf

# 7. Prelaunch: every legacy URL against staging, then the new sitemap.
python -m legacy_migration compare migration/map/url-mapping.csv \
  --new-base https://staging.example.com --canonical-base https://thinkpositivealways.com \
  --out migration/compare.csv
python -m legacy_migration sitemap-check https://staging.example.com/sitemap.xml \
  --canonical-base https://thinkpositivealways.com --mapping migration/map/url-mapping.csv \
  --out migration/sitemap-check.csv
python -m legacy_migration report migration/map/url-mapping.csv \
  --inventory migration/inventory-2026-11-10/inventory.csv \
  --worklist migration/map/content-worklist.csv \
  --compare migration/compare.csv --sitemap migration/sitemap-check.csv \
  --out migration/migration-report.md
```

`compare` and `sitemap-check` exit 1 on any failure. A high-priority URL still marked
`REVIEW` counts as a failure unless you pass `--allow-unresolved`.

**Launch readiness:**
- `validate-rewrite` reports no errors, and every rewritten article is live at its
  `proposed_new_path`.
- `validate` reports no errors.
- `compare` has no `fail` results.
- `sitemap-check` has no `fail` results.
- The report shows 0 high-priority unresolved URLs.

Then repeat `compare` against production straight after the DNS switch.

## Search Console reconciliation and selective migration

Not everything from the old site moves to the relaunched site. `reconcile` combines:
- the legacy CMS export
- the inventory runs
- Google Search Console exports

It records **every** URL and gives each one an editorial decision. Only the published
articles an editor selects get rewritten, and production migration stays blocked while
any selected article has an unresolved canonical or content decision.

```bash
python -m legacy_migration reconcile \
  --export legacy-articles-db.csv \
  --inventory migration/inventory-2026-11-10/inventory.csv \
  --inventory migration/inventory-2026-11-03/inventory.csv \
  --gsc gsc/performance-pages.zip --gsc gsc/top-linked-pages.csv \
  --gsc gsc/url-inspection.csv \
  --gsc-index "Crawled - currently not indexed" gsc/crawled-not-indexed.csv \
  --gsc-index "Discovered - currently not indexed" gsc/discovered-not-indexed.csv \
  --gsc-index "Not found (404)" gsc/not-found.csv \
  --gsc-index "Indexed" gsc/indexed.csv \
  --taxonomy taxonomy-decisions.csv --new-site migration/new-site.csv \
  --expect-published 45 --out migration/reconcile

# Editors fill the decision columns, then re-run with their files; decisions are kept:
python -m legacy_migration reconcile ... \
  --previous-master migration/reconcile/master-url-inventory.csv \
  --previous-register migration/reconcile/rewrite-register.csv --out migration/reconcile

# Production gate: exits 1 while anything blocking remains.
python -m legacy_migration reconcile ... --gate --out migration/reconcile
```

**Search Console inputs.** Each `--gsc` / `--gsc-index` file can be a `.csv`, the
downloaded `.zip` or an unzipped folder. From a zip or folder, `Table.csv` is read and
the issue name is taken from `Metadata.csv`.
- **Performance → Pages:** clicks, impressions, CTR, position.
- **Links → Top linked pages:** backlinks.
- **Pages report drill-downs** (`URL`, `Last crawled`): one file per issue, named with
  `--gsc-index`.
- **URL Inspection results:** `Google-selected canonical` / `User-declared canonical`.

Index statuses are normalised to one of:
- `INDEXED`
- `CRAWLED_NOT_INDEXED`, `DISCOVERED_NOT_INDEXED`
- `NOT_FOUND_404`, `SOFT_404`
- `PAGE_WITH_REDIRECT`, `REDIRECT_ERROR`
- `ALTERNATE_CANONICAL`, `GOOGLE_CHOSE_DIFFERENT_CANONICAL`, `DUPLICATE_NO_CANONICAL`
- `NOINDEX`, `BLOCKED_ROBOTS`, `BLOCKED_ACCESS`
- `SERVER_ERROR`, `OTHER`

Only `INDEXED` means indexed: "Crawled – currently not indexed" is **not**. Index status
and last-crawled date are **evidence fields only**. When a URL appears in several
reports, the most recent crawl wins.

**Rules the tool enforces:**
- **It only suggests.** Each URL gets a `suggested_decision` hint from the evidence, but
  it never selects an article, never suggests `RETIRE_410`, and never treats "not
  indexed" as a reason to drop a page.
- **Drafts are excluded by rule.** Their URLs get `EXCLUDE_DRAFT` automatically. Giving a
  draft `REWRITE`, `EXPERT_REVIEW` or `PRESERVE_PAGE` is a blocking error. A draft URL
  with search history can still get a 301 or 410 decision for the URL itself.
- **Legacy categories and sections are registered, not recreated.** Only an approved
  `REPLACE` taxonomy decision suggests a 301 to the new topic, and an editor must
  still approve it. Article slugs and canonical paths never depend on taxonomy.
- **A 301 needs an approved, relevant destination:** `destination`, `approved=yes` and
  `decided_by`. Validation rejects:
  - the homepage (except for homepage aliases)
  - itself, or a chain to another redirect or to a retired URL
  - for a selected article, any path other than its new path
  - with `--new-site`, a path that isn't live
- **A 410 needs `approved=yes`, `decided_by` and a justification** in `decision_notes`.
  Not being indexed alone is not a reason.
- **History is kept.** URLs from the previous master that are no longer discovered stay,
  with `still_present=no` and their decisions.

**Editorial decisions** (`editorial_decision`):

| Decision | Meaning |
|---|---|
| `REWRITE` | Selected published article: rewrite from scratch at its preserved path |
| `EXPERT_REVIEW` | Selected published article on a specialist topic: rewrite with a qualified reviewer |
| `PRESERVE_PAGE` | Keep a non-article page at the same path on the new site (not for articles) |
| `REDIRECT_301` | One permanent redirect to an approved, relevant destination |
| `RETIRE_410` | Gone for good, approved and justified |
| `EXCLUDE_DRAFT` | Draft: never rewritten, published or imported (automatic) |
| `REVIEW` | Undecided |

A published article's decision is made once, in `rewrite-register.csv`. Its
established URL in the master inventory shows that decision
(`decision_source=rewrite-register`). Every other URL is decided in
`master-url-inventory.csv`.

**What blocks production** (`readiness-report.md`, `readiness-issues.csv`):
- **Every published article** must have a decision (`article_undecided`).
- **A selected article** (`REWRITE` / `EXPERT_REVIEW`) is blocked by:
  - `canonical_unresolved`: no or ambiguous established URL
  - `canonical_conflict` and `canonical_unverified`, unless `canonical_confirmed_by` is
    filled in after checking URL Inspection
  - `new_path_missing`
  - `expert_review_pending`: specialist topics need `suitability_decided_by`
  - `suitability_excluded`
  - `content_not_ready`: `rewrite_status` must be `READY` or `PUBLISHED_NEW`
  - the rewrite-plan errors
- **Any invalid decision anywhere,** and any undecided URL of a selected article.

Other undecided URLs (old pages, categories, system URLs) are listed as warnings.

### `master-url-inventory.csv`

| Column | Meaning |
|---|---|
| `url_key` / `url` / `variants` | Matching key (path for the legacy site), representative URL, all spellings seen |
| `url_type` | `article` (linked to a CMS record), `category`, `section`, `page`, `home`, `media`, `system`, … |
| `sources` | `cms`, `inventory`, `gsc` (all that found it) |
| `still_present` / `first_recorded` / `last_seen` | History: `no` = only in an earlier run |
| `cms_id` / `cms_status` / `cms_link` | Linked legacy record, its status, and how: `export`, `page_canonical`, `found_by_slug`, `slug` or `id` (exact matches only) |
| `title` | From the CMS or the page |
| `live_status` / `live_class` / `live_canonical` / `redirects_to` | From the inventory |
| `gsc_index_status` / `gsc_index_reason` / `gsc_last_crawled` | Index evidence (normalised status, the report's wording, last crawl) |
| `gsc_clicks` / `gsc_impressions` / `gsc_ctr` / `gsc_position` / `gsc_backlinks` | Performance and links |
| `gsc_google_canonical` / `gsc_user_canonical` | From URL Inspection |
| `suitability_flags` | Specialist topics of the linked article |
| `suggested_decision` / `suggested_destination` / `suggestion_reason` | Tool hint (never applied by itself) |
| `editorial_decision` / `destination` / `approved` / `decided_by` / `decision_notes` | The decision (editor, register or rule) |
| `decision_source` | `rewrite-register`, `editor` or `rule` |
| `readiness` | Issue codes for this URL |

### `rewrite-register.csv`

This is `rewrite-worklist.csv` (all published articles) with these extra columns:

| Column | Meaning |
|---|---|
| `selected` | `yes` when the decision is `REWRITE` or `EXPERT_REVIEW` |
| `editorial_decision` / `destination` / `approved` / `decided_by` / `decision_notes` | The article's decision |
| `canonical_verification` | `VERIFIED` (live page or URL Inspection confirms it), `UNVERIFIED`, `CONFLICT`, `AMBIGUOUS` or `MISSING` |
| `canonical_confirmed_by` | Who confirmed the canonical manually (URL Inspection), when not `VERIFIED` |
| `gsc_index_status` / `gsc_last_crawled` / `gsc_clicks` / `gsc_impressions` / `gsc_backlinks` | Evidence for the established URL |
| `suggested_decision` / `suggestion_reason` | `REWRITE` or `EXPERT_REVIEW` with search value, otherwise `REVIEW` |
| `blocking_issues` | What stops production for this article |

### `draft-exclusion-register.csv`

`legacy_id`, `title`, `original_slug`, `status`, `legacy_category`, `legacy_section`,
`known_urls`, `gsc_clicks`, `gsc_impressions`, `editorial_decision` (always
`EXCLUDE_DRAFT`), `note`.

### `taxonomy-register.csv`

`legacy_type` (`category` / `section`), `legacy_slug`, `legacy_name`,
`published_articles`, `draft_articles`, `legacy_urls`, `gsc_clicks`, `gsc_impressions`,
`register_decision` (`REPLACE`, `RETIRE` or `REVIEW`), `new_section`, `approved`, `note`,
`url_decisions` (the master decisions of its URLs).

### `canonical-preservation-report.csv`

`legacy_id`, `title`, `selected`, `editorial_decision`, `original_url`,
`established_canonical`, `canonical_source`, `canonical_verification`,
`canonical_confirmed_by`, `gsc_index_status`, `proposed_new_path`,
`canonical_preserved`, `redirect_from` (old paths that need a 301 to the new path),
`outcome`:
- `PRESERVED`: same path
- `REDIRECTED`: kept slug, with one 301
- `UNRESOLVED`: blocking issues remain
- `NOT_SELECTED`

## Historical URL cleanup (Search Console coverage history)

The historical audit holds 865 distinct URLs from ten coverage-report exports. They come
from earlier versions of the website: forums, an old shop, abandoned categories, filters
and previous article routes. `cleanup` imports and deduplicates them, reconciles each one
against the CMS export and the new site's routes, and proposes one class per URL:

| Class | Outcome on the new site | Needs approval |
|---|---|---|
| `KEEP_200` | A live page (or a published article's preserved path) | no |
| `REDIRECT_301` | One direct 301 to an approved, live, relevant page | yes |
| `RETIRE_410` | Explicitly gone: an exact Nginx rule | yes |
| `ALLOW_404` | Nothing to do: the site answers a genuine 404 | no |
| `REVIEW` | Undecided, or a proposed 301/410 still awaiting approval | – |

```bash
python -m legacy_migration cleanup \
  --coverage-report "Not found (404)" gsc/history/not-found.csv \
  --coverage-report "Crawled - currently not indexed" gsc/history/crawled.csv \
  --coverage gsc/history/page-with-redirect.zip    # issue name read from Metadata.csv
  ... (all ten exports) ... \
  --export legacy-articles-db.csv --inventory migration/inventory-2026-11-10/inventory.csv \
  --new-site migration/new-site.csv --taxonomy taxonomy-decisions.csv \
  --expect-urls 865 --expect-published 45 --out migration/cleanup

# Editors set decision / target / approved / approved_by / notes, then re-run:
python -m legacy_migration cleanup ... --previous migration/cleanup/cleanup-decisions.csv \
  --out migration/cleanup
python -m legacy_migration cleanup ... --gate     # exit 1 until nothing is unresolved
```

**Import and deduplication.** Each export can be a `.csv`, a `.zip` or a folder. The
summary reports the raw rows, distinct URLs, distinct paths and query-string variants:
- `http`/`https` and `www`/apex spellings of one URL count once
- a URL listed in several reports keeps all their names (`reports`) and statuses
- the latest `last_crawled` is kept

**Protection** (validation errors, never warnings):
- **Published articles** (all 45 are rewrite candidates):
  - A preserved canonical path is `KEEP_200` only.
  - A moved one is `REDIRECT_301` straight to its new `/articles/<slug>` path only.
  - A historical URL with exactly a published article's slug is never retired or left to
    404.

  A Search Console status (even "Not found (404)") never overrides this.
- **Drafts** (44) are never `KEEP_200`: they are never published. Their URLs default to
  `ALLOW_404`.
- **Essential routes of the new site** are `KEEP_200` only: the homepage, `/articles`,
  `/topics`, `/shop`, the static pages, sign-in pages, `/sitemap.xml` and every live
  path from `flask legacy export-cms`. A test keeps this list in sync with
  `seo_service.STATIC_PATHS` and the frontend routes.
- **Application areas** never get a redirect or a 410 rule: `/api`, `/media`, `/assets`,
  `/admin`, `/learn`, `/certificates`, `/cart`, `/checkout`, `/account`, `/purchases`.

**Families** (`family`): `current_article`, `draft`, `previous_article_route`
(`/article/<id>`, `/YYYY/MM/<slug>`, `/blog/<slug>`), `forum`, `shop_account`,
`category`, `filter`, `page`, `home`, `app_shell`, `api`, `asset`, `probe` (e.g.
`/wp-login.php`), `search_feed` and `unknown`.

What the tool proposes for each family:
- **Forums** and **old shop paths** not in the new shop: `RETIRE_410`.
- **Previous article routes of published articles:** `REDIRECT_301` to the article's new
  path. Routes of drafts or of unknown records: `ALLOW_404`.
- **Categories:** follow only approved taxonomy decisions (REPLACE → 301 to the live
  topic, RETIRE → 410). Otherwise `REVIEW`.
- **Unknown URLs:** `ALLOW_404` only when Search Console already reports them gone and
  nothing in the CMS matches. Otherwise `REVIEW`. Not being indexed is never a reason to
  retire.

**Query strings.** Nginx rules and CMS redirects match the *path*, so every query-string
variant follows its path:
- A filter or tracking variant of a live page is `KEEP_200` (the page is canonical
  without the query).
- A variant can't be given a different 301/410 than its path (`variant_conflict`).
- A path known only through its query variants (e.g. `/forums?page=2`) gets one rule for
  the path itself.

**Redirects** are direct. Validation rejects:
- a target that isn't a live path (or a published article's new path)
- the homepage (`homepage_redirect`)
- itself
- a target that is itself redirected, retired or left to 404 (`redirect_chain`)
- for a published article, any target other than its new path

**Nothing is applied.** A 301 or 410 takes effect (`effective_class`) only with
`decision`, `approved=yes` and `approved_by`. The outputs are previews:
- **`approved-redirects.csv`:** approved, error-free 301s in the mapping format, for
  `flask legacy import-redirects` (a dry run unless `--apply`; run on staging).
- **`tpa-legacy-gone.conf`:** approved 410s only. Each is an exact rule,
  `location = /path { return 410; }`, plus the trailing-slash form; a rule covers every
  query string. There are no prefix or regex rules, and the file has a header with a
  checksum. It is verified after generation: exact rules only, approved paths only,
  nothing protected, live, homepage or in an application area. If any 410 decision has
  an error, the file is **not written** and the summary says why. Install it on staging
  only:
  - copy it to `/etc/nginx/snippets/tpa-legacy-gone.conf`
  - enable the commented include in `deploy/nginx/tpa.conf.example`
  - run `nginx -t`
- **`cleanup-mapping.csv`:** the same decisions in mapping format, for `compare` and
  `sitemap-check`. Both now understand `ALLOW_404`: `compare` expects a genuine 404, and
  `sitemap-check` reports such a path in the sitemap.

**Genuine 404s on the new site.** Unknown paths never get a successful React homepage:
- **Public paths:** Nginx serves prerendered files (`/x/index.html`), then asks Flask
  `/_redirect/x` for a CMS redirect. Otherwise it serves the prerendered `404.html` with
  **status 404**. The build fails unless the not-found route renders with status 404, and
  `npm run serve:dist` behaves the same way.
- **Customer area:** only its prerendered shells answer 200. Any other
  `/account/...`, `/cart/...`, `/checkout/...` or `/purchases/...` path is now a real 404
  (before this batch it served `404.html` with status 200).
- **`/admin`, `/learn`, `/certificates`:** these answer with their own `noindex` app
  shell, never the homepage.

`tests/test_deploy_config.py` checks all of this statically, and against a real Nginx
when one is installed (including a generated 410 snippet).

**Sitemap, navigation and links:**
- **Sitemap.** The sitemap already excludes drafts, `noindex` pages, canonicalised pages
  and paths with an active redirect. `sitemap-check` verifies it against
  `cleanup-mapping.csv` over HTTP.
- **Links.** `flask --app wsgi legacy check-links migration/cleanup/cleanup-decisions.csv`
  (read-only) lists every link to a legacy URL whose outcome isn't `KEEP_200`, with the
  fix (link to the 301 target, or remove the link). It checks navigation menus,
  published articles and pages (link fields, Markdown and HTML links, relative or on the
  site's domain) and topic intros. It exits 1 while any remain.

### Read-only HTTP status verification

```bash
# What the current site answers today (record only):
python -m legacy_migration verify-status migration/cleanup/cleanup-decisions.csv \
  --base https://thinkpositivealways.com --out migration/status-legacy.csv --max-seconds 1800
# Staging against the approved decisions:
python -m legacy_migration verify-status migration/cleanup/cleanup-decisions.csv \
  --base https://staging.example.com --expect --out migration/status-staging.csv
```

How it behaves:
- **Read-only:** GET only, on `--base` only. Historical URLs on `--site-host` (default
  `thinkpositivealways.com`) are requested by path and query; other hosts are skipped.
- **Bounded:** each request has a timeout (`--timeout`, default 10s) and at most 10
  redirect hops, with a pause between requests (`--delay`). A run can be capped with
  `--max-seconds` or `--limit`.
- **Progress:** printed every `--progress-every` URLs, as `[n/total] pass= fail= …`.
- **Resumable:** each result is appended and flushed immediately, so a stopped run
  continues where it left off (`--recheck-failed` retries failures).
- **Soft-404 detection:** a random probe path is requested first. A page identical to
  the probe's answer is flagged `matches_unknown_url_response` (soft 404 or app shell).

With `--expect`, each URL is checked against its decision:
- `KEEP_200`: 200, no redirect, not the unknown-URL response
- `REDIRECT_301`: one 301/308 straight to the target, which answers 200
- `RETIRE_410`: 410
- `ALLOW_404`: 404 (or 410), never 200

Result columns: `url`, `tested_url`, `expected`, `expected_target`, `status`, `location`,
`redirect_hops`, `final_status`, `final_url`, `matches_unknown_url_response`,
`elapsed_ms`, `error`, `result` (`pass`, `fail`, `error`, `info`, `skipped`), `problem`,
`checked_at`.

### `cleanup-decisions.csv`

| Column | Meaning |
|---|---|
| `url` / `path` / `path_key` / `query` / `variants` | Normalised URL, its path and query, the matching key, and how many spellings and variants share the path |
| `reports` / `index_statuses` / `last_crawled` | Every coverage report that listed it, normalised statuses, latest crawl (evidence only) |
| `family` | See above |
| `cms_id` / `cms_status` | Linked legacy record (`published` / `draft`) |
| `protected` | Why the URL is protected (published article, draft, essential route) |
| `new_site_live` | The path is live (or planned for a published article) on the new site |
| `proposed_class` / `proposed_target` / `reason` | The tool's proposal |
| `decision` / `target` / `approved` / `approved_by` / `notes` | The editor's decision |
| `effective_class` / `effective_target` | What will actually happen (301/410 only when approved) |
| `problems` | Validation codes for this URL |

Other outputs:
- **`cleanup-problems.csv`:** `severity`, `code`, `path_key`, `url`, `message`.
- **`cleanup-summary.md`/`.json`:**
  - the import counts
  - URLs preserved (200), redirected (301), retired (410), left as 404 and unresolved
  - how many are awaiting approval
  - families, errors and warnings
  - the snippet's state (`verified` / `refused`)
  - `ready_for_staging`: no errors, a verified snippet and nothing unresolved

## Mapping rules

| Action | Meaning | Applied by |
|---|---|---|
| `KEEP` | The same path is live on the new site (a trailing slash doesn't matter) | nothing to do |
| `REDIRECT_301` | One permanent redirect straight to the final new page | `flask legacy import-redirects` |
| `RETIRE_410` | Gone for good | Nginx snippet from `gone-conf` |
| `REVIEW` | Needs a person: rewrite content, choose a target, or confirm it's gone | – |

Proposals come in this order (the first match wins):
1. An approved override.
2. The same path exists on the new site.
3. The legacy redirect's final destination (chains are flattened).
4. A CMS article's `original_url` or `original_slug`.
5. An identical article slug. Article URLs never depend on a category or section.
6. For category and section URLs, an approved taxonomy decision (`--taxonomy`). A new
   topic that merely has the same slug isn't enough. After that, an alias rule
   (`/about-us` → `/about`, `/terms-of-service` → `/terms`). Both apply only when the
   target is live.
7. `RETIRE_410`, only when the URL was gone (404/410) in at least 2 inventories at least
   7 days apart, and has no Search Console clicks or impressions, no backlinks, no
   internal links, no sitemap entry and no article evidence.
8. Everything else → `REVIEW`.

**Safeguards:**
- **Slugs are never generated.** There's no case folding or fuzzy matching. A rewritten
  article is published with its established slug (rewrite plan `proposed_new_path`), so
  `/articles/<slug>` stays identical (`KEEP`). A root-level article such as
  `/50-kindness-quotes-to-brighten-your-day` keeps its slug and gets one 301 to
  `/articles/<same-slug>`, because the new site serves articles only under `/articles/`.
- **No homepage redirects.** Validation rejects any target `/` except from homepage
  aliases (`/index.html`, `/home`). A legacy URL that already redirects to the
  homepage becomes `REVIEW`.
- **One 404 never retires a URL,** and gone articles are always `REVIEW`.
- **Approval is required to apply anything.** Every `REDIRECT_301` and `RETIRE_410`
  needs `approved=yes`, unapproved rows are skipped, and `import-redirects` refuses a
  mapping that fails validation (chains, loops, self-redirects, redirects to retired
  paths, duplicates).
- **The sitemap lists only canonical, indexable URLs.** It excludes drafts, `noindex`
  pages, pages canonicalised elsewhere and, since this batch, any path with an active
  redirect. `sitemap-check` verifies the result over HTTP.

## Files and CSV formats

All CSVs are UTF-8 with a header row. Cells that would start a spreadsheet formula
(`=`, `+`, `-`, `@`) are prefixed with `'` (scraped titles are untrusted). Booleans are
`yes` or empty.

### Inputs

- **Seeds** (`--seeds`, repeatable): any CSV with a URL column. These headers are
  recognised: `url`, `page`, `top pages`, `address`, `landing page`, `target page`,
  `loc`, `legacy_url`. Optional columns:
  - `clicks`, `impressions` (a Search Console "Pages" export works as is)
  - `backlinks`, `links` or `incoming links` (Search Console "Links → Top linked pages")
  - `source`
  
  A plain text file with one URL per line also works.
- **Legacy CMS export** (`rewrite-plan --export`, `inventory --articles-csv`): `id`,
  `slug`, `title`, `author`, `published_at`, `updated_at`, `status`, `category`,
  `section`, `url`, `canonical_url`, `excerpt`.
  - **Status is required.** `status` (or `publication_status` / `state`, or a boolean
    `is_published`) is normalised to `published`, `draft`, `scheduled`, `archived` or
    `unknown`. Only an explicit published value counts as published.
  - `url` and `canonical_url` are used only if the database stores them; URLs are never
    constructed.
  - `excerpt` is read only to flag specialist topics. It isn't copied anywhere.
- **Taxonomy decisions** (`--taxonomy`, written by editors): `legacy_category`,
  `legacy_section`, `legacy_path`, `decision`, `new_section`, `approved`, `note`. One row
  per legacy category, section or category URL, with `decision`:
  - `REPLACE`: give the new topic slug in `new_section`
  - `RETIRE`: leave `new_section` blank
  
  A blank `decision` with a `new_section` means REPLACE. Only rows with `approved=yes`
  are used; leave the row out for "not decided yet".
- **Article API** (`--articles-api`): a JSON list, or `{data: [...]}`, `{articles: [...]}`
  or `{items: [...]}`, with the same field names.
- **New site** (`flask legacy export-cms`): `path`, `kind`, `slug`, `title`, `status`,
  `indexable`, `author`, `published_at`, `source`, `original_url`, `original_slug`.

### `inventory.csv` (one row per discovered URL)

| Column | Meaning |
|---|---|
| `url` | URL as discovered (scheme, host, path, pagination query only) |
| `path` | Path (+ pagination query) |
| `kind` | `home`, `article`, `category`, `page`, `media`, `feed`, `forum`, `shop`, `system`, `asset`, `search`, `sitemap` (path rules refined by `og:type` / JSON-LD) |
| `discovered_via` | `sitemap`, `start`, `link`, `canonical`, `image`, `seed:<file>`, `articles:<source>` (all that apply) |
| `referrer` | First page that linked to it |
| `in_sitemap` / `sitemap_lastmod` | Listed in a legacy sitemap, with its lastmod |
| `in_archive` | Linked from an archive/category start page (including `?page=N`) |
| `inlinks` | Internal links pointing to it |
| `checked_at` | UTC time of the request |
| `status` / `final_status` / `final_url` | First response, final response after redirects, where it ended |
| `redirect_hops` / `redirect_chain` | Number of redirects and each hop (`301 url | 302 url`) |
| `page_class` | `ok`, `gone` (404/410), `client_error`, `server_error`, `error` (network), `redirect_error`, `soft_404`, `shell_only`, `not_checked` |
| `content_type` | Final Content-Type |
| `title` / `meta_description` / `h1` | Page metadata |
| `canonical` / `canonical_status` | Canonical URL; `self`, `other`, `cross_site` or `missing` |
| `robots_meta` / `x_robots_tag` / `noindex` | Robots directives and whether they say noindex |
| `og_type` / `schema_type` | Open Graph type and JSON-LD `@type` |
| `published_time` / `modified_time` / `author` / `section` | Article metadata (meta tags, JSON-LD or the article export) |
| `word_count` | Visible words in the HTML |
| `og_image` | Social image |
| `seed_clicks` / `seed_impressions` / `seed_backlinks` | From seed files (Search Console) |
| `issues` | `;`-separated: `broken_links:N`, `linked_but_broken`, `redirect_chain`, `redirect_loop`, `redirect_offsite`, `temporary_redirect`, `missing_canonical`, `canonical_elsewhere`, `canonical_not_ok`, `multiple_canonicals`, `noindex`, `accidental_noindex`, `sitemap_lists_non_indexable`, `missing_from_archive` (published records only), `draft_record_is_public`, `missing_title`, `missing_description`, `soft_404`, `shell_only`, `server_error`, `error` |
| `error` | Network error, robots.txt exclusion or why it wasn't checked |

The inventory step also writes:
- `links.csv`: `source_url`, `target_url`, `anchor`, `target_final_status`, `broken`
- `legacy-articles.csv`: the article records with `publication_status`, `matched_url`,
  `match` (`url`, `slug` or `id`), `in_sitemap`, `in_archive`, `missing_from_archive` and
  `no_public_url` (the last two only ever set for published records)
- `run.json`: the probe result, counts and notes

### `url-mapping.csv` (the file you review)

| Column | Meaning |
|---|---|
| `legacy_url` / `legacy_path` | Legacy URL and its matching key (no trailing slash or query) |
| `kind` | As in the inventory |
| `variants` | Spellings merged into this row (www/apex, trailing slash) |
| `legacy_status` / `legacy_class` | Latest final status and page class |
| `observations` | Every inventory result, e.g. `2026-11-03=404;2026-11-10=404` |
| `last_checked` | Latest inventory time |
| `title` / `author` / `published_time` | From the legacy page |
| `in_sitemap` | In a legacy sitemap |
| `seed_clicks` / `seed_impressions` / `seed_backlinks` | Search Console evidence |
| `priority` | `high` (articles, categories, home, sitemap, clicks or backlinks) or `normal` |
| `action` | `KEEP`, `REDIRECT_301`, `RETIRE_410` or `REVIEW` |
| `target_path` | New-site path for `KEEP` / `REDIRECT_301` |
| `confidence` | `exact`, `cms_original_url`, `cms_original_slug`, `slug` (articles only), `taxonomy`, `rule`, `observed_gone` or `manual` |
| `reason` | Why this was proposed |
| `content_action` | `NONE`, `REWRITE` (published article: rewrite from scratch), `DRAFT_NO_ACTION`, `IMPORT_MEDIA`, `CREATE_OR_REDIRECT` or `REVIEW` |
| `approved` / `approved_by` / `note` | Your decision (`yes` to apply) |

The map step also writes `mapping-problems.csv` (validation results), `excluded-urls.csv`
(system URLs such as `/login` or `/admin`), and `migration-report.md` / `.json`.

### `rewrite-worklist.csv` (published articles only; the editorial plan)

`rewrite-plan` writes this file plus:
- `draft-articles.csv`: drafts, listed for the record only (`legacy_id`, `title`,
  `original_slug`, `status`, `publication_status`, `legacy_category`, `legacy_section`,
  `note`)
- `other-status-articles.csv`: blank, unknown, scheduled or archived records, to check
- `rewrite-problems.csv`
- `rewrite-summary.json`: counts by status, URL evidence, suitability and section

With `--expect-published 45 --expect-draft 44` the step fails if the export doesn't
match those counts.

| Column | Meaning |
|---|---|
| `legacy_id` / `title` / `author` | From the export (author for attribution) |
| `original_published_at` / `original_modified_at` | Publication metadata to carry over where appropriate |
| `legacy_category` / `legacy_section` | For reference only; never copied as the new section |
| `original_slug` | Slug as stored in the legacy CMS (never derived from the title) |
| `original_url` | Exact public URL: the export's `url`, or the live page whose path ends with exactly `original_slug` |
| `original_canonical_url` / `canonical_source` | Established canonical: `export`, `page` (the page's own canonical tag), or `unverified_app_shell` (the app shell's canonical isn't trusted) |
| `url_status` | `CONFIRMED` (export URL seen live), `EXPORT_ONLY` (export URL, not yet seen), `FOUND_BY_SLUG`, `AMBIGUOUS` (several live URLs end with the slug: see `url_candidates`), `FIND_URL` (none: look it up, never guess) |
| `url_candidates` | Competing URLs when `AMBIGUOUS` |
| `proposed_new_path` | `/articles/<slug>` with the slug of the established canonical (or public) URL. Empty when no URL is known or the slug isn't valid in the new CMS |
| `canonical_preserved` | `yes`: the canonical path stays identical. `no`: the new path differs and the old path needs one 301 |
| `url_note` | Explanation |
| `proposed_section` / `section_status` | New section from an approved taxonomy decision (`DECIDED`), an editor's choice (`EDITOR`), or `NEEDS_DECISION` |
| `suitability_flags` | Specialist terms found (`medical:…`, `mental_health:…`, `legal:…`, `financial:…`); hints, not decisions |
| `editorial_suitability` | `GENERAL`, `EXPERT_REVIEW` (default when flagged) or `EXCLUDE` |
| `suitability_decided_by` | Qualified reviewer or editor who decided. It's required before a flagged article is `READY`, or before it's marked `GENERAL` |
| `rewrite_status` | `NOT_STARTED`, `ASSIGNED`, `DRAFTING`, `EXPERT_REVIEW`, `READY`, `PUBLISHED_NEW` or `EXCLUDED` |
| `rewrite_owner` / `editor_notes` | Editorial tracking |

**Re-running the plan.** Editors may change `proposed_section`, `section_status`,
`editorial_suitability`, `suitability_decided_by`, `rewrite_status`, `rewrite_owner` and
`editor_notes`. Re-running with `--previous` keeps those columns and recomputes the URL
columns from the evidence.

**Validation** (`validate-rewrite`) rejects:
- a non-published row
- a duplicate id or duplicate new path
- a path that isn't `/articles/<valid-slug>`
- a slug that differs from the established URL's slug
- an invalid status
- a flagged article marked `GENERAL` without a named reviewer
- a flagged article marked `READY` before its expert review is recorded

When publishing a rewritten article in the new CMS:
- Create a new article at `proposed_new_path`. Never edit an existing article to "make
  it match".
- Set `source=migrated`, `original_url` (the established URL) and `original_slug`, so the
  URL mapping redirects the old path automatically.
- Keep the original topic and author attribution. Set `first_published_at` to the
  original date where appropriate.
- Write new, original content: legacy text is not copied, and specialist claims are
  either reviewed by a qualified expert or removed.

### `content-worklist.csv` (URL-driven content list from `map`)

| Column | Meaning |
|---|---|
| `priority` | As in the mapping |
| `content_action` | `REWRITE` (live article without a new page: plan it in the rewrite worklist), `IMPORT_MEDIA` (image or file to review for reuse), `FIND_URL` (published record with no public URL found: look it up, never guess), `CREATE_OR_REDIRECT`, `REVIEW`. Drafts never appear here |
| `legacy_url` | Legacy URL (empty for `FIND_URL`) |
| `keep_slug` | The established slug, unchanged |
| `new_path` | Where it will live (`/articles/<keep_slug>`) |
| `title` / `author` / `published_time` / `modified_time` / `category` | Attribution and publication metadata for reference |
| `word_count` / `legacy_class` / `source` / `notes` | Context for the editor |

### Prelaunch outputs

- `compare.csv`: `legacy_path`, `priority`, `action`, `target_path`, `approved`,
  `tested_url`, `status`, `location`, `final_url`, `final_status`, `redirect_hops`,
  `canonical`, `noindex`, `result` (`pass`, `warn`, `fail`, `unresolved`), `problems`.
- `sitemap-check.csv`: `loc`, `path`, `final_status`, `redirect_hops`, `noindex`,
  `canonical`, `result`, `problems`. Problems include:
  - `legacy_redirect_source`, `retired_path`, `redirects`, `noindex`,
    `canonical_elsewhere`, `host`, `duplicate`
  - `mapped_target_not_in_sitemap` (a warning)

## Nginx 410 rules

`gone-conf` writes `location = /path { return 410; }` (with and without the trailing
slash) for approved `RETIRE_410` rows only. It refuses a mapping that has validation
errors. Install it on the new server as
`/etc/nginx/snippets/tpa-legacy-gone.conf` and enable the commented include in
`deploy/nginx/tpa.conf.example`. 301s live in the CMS redirect manager, not in Nginx.

## Still needed (from the VPS or Google Search Console)

1. **Search Console, property `thinkpositivealways.com` (domain property preferred):**
   - Performance → Pages, last 16 months, exported as CSV (clicks and impressions per URL)
   - Links → Top linked pages (external), exported
   - Pages (indexing report): "Indexed" and "Not found (404)" lists
   - Sitemaps: the submitted sitemap URLs and when they were last read
2. **The current production CMS export, with publication status** (all 89 records:
   drafts are needed to separate them, not to use them). In the old `TPA-backend`
   schema, adjust to the deployed schema if it differs:

   ```sql
   SELECT a.id, a.slug, a.title, u.name AS author, a.published_at, a.status,
          a.excerpt, c.slug AS category, s.slug AS section
   FROM articles a
   LEFT JOIN users u ON u.id = a.user_id
   LEFT JOIN categories c ON c.id = a.category_id
   LEFT JOIN sections s ON s.id = a.section_id
   ORDER BY a.id;
   ```

   If the deployed CMS stores a canonical or full URL per article, add it as
   `canonical_url` / `url`. Export the result as CSV for `rewrite-plan --export` and
   `inventory --articles-csv`, and keep a full backup of the database and the uploaded
   media. It's a read-only query: the live CMS is not modified.
3. **Editorial taxonomy decisions** (`taxonomy-decisions.csv`): the new section for each
   legacy category or section, approved by an editor.
4. **From the current VPS:**
   - the Nginx (or other web server) site configuration, for any existing redirects
     and rewrite rules
   - 90 days of access logs, for URLs that real visitors and bots request
   - the deployed frontend's route table or build, which shows how root-level article
     URLs like `/50-kindness-quotes-to-brighten-your-day` are served
   - the live `sitemap.xml` and `robots.txt` (the inventory fetches these itself)
5. **Any earlier sitemaps, Wayback Machine URL lists or old analytics exports,** passed
   as extra `--seeds`.
