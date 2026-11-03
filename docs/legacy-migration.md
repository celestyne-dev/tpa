# Legacy website inventory and SEO migration (Batch 12.4A)

Protects every public URL, article, backlink and search signal of the current
`https://thinkpositivealways.com` before the new site replaces it. The current website
stays untouched until the comparison below passes: every tool here only **reads** it
(HTTP GET, robots.txt respected, one request per second by default).

Nothing in this workflow deploys, changes DNS, deletes content or overwrites CMS records.
The only write is `flask legacy import-redirects --apply`, which creates CMS redirects
for approved rows and never replaces an existing redirect, article or page.

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

# 2. Export the new CMS's live URLs (read-only; on staging).
flask --app wsgi legacy export-cms --out migration/new-site.csv

# 3. Propose the mapping, the content worklist and the report.
python -m legacy_migration map \
  --inventory migration/inventory-2026-11-10/inventory.csv \
  --inventory migration/inventory-2026-11-03/inventory.csv \
  --articles migration/inventory-2026-11-10/legacy-articles.csv \
  --new-site migration/new-site.csv --out migration/map

# 4. Review migration/map/url-mapping.csv: set approved=yes, approved_by and note; edit
#    action/target_path where needed. Re-run step 3 with --overrides <reviewed file>
#    after importing content: approved decisions are kept, the rest is re-proposed.
python -m legacy_migration validate migration/map/url-mapping.csv --new-site migration/new-site.csv

# 5. Import content in the CMS keeping slugs (content-worklist.csv), then apply redirects.
flask --app wsgi legacy import-redirects migration/map/url-mapping.csv           # dry run
flask --app wsgi legacy import-redirects migration/map/url-mapping.csv --apply --actor-email you@example.com
python -m legacy_migration gone-conf migration/map/url-mapping.csv --out tpa-legacy-gone.conf

# 6. Prelaunch: every legacy URL against staging, then the new sitemap.
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
- `validate` reports no errors.
- `compare` has no `fail` results.
- `sitemap-check` has no `fail` results.
- The report shows 0 high-priority unresolved URLs.

Then repeat `compare` against production straight after the DNS switch.

## Mapping rules

| Action | Meaning | Applied by |
|---|---|---|
| `KEEP` | The same path is live on the new site (a trailing slash doesn't matter) | nothing to do |
| `REDIRECT_301` | One permanent redirect straight to the final new page | `flask legacy import-redirects` |
| `RETIRE_410` | Gone for good | Nginx snippet from `gone-conf` |
| `REVIEW` | Needs a person: import content, choose a target, or confirm it's gone | – |

Proposals come in this order (the first match wins):
1. An approved override.
2. The same path exists on the new site.
3. The legacy redirect's final destination (chains are flattened).
4. A CMS article's `original_url` or `original_slug`.
5. An identical article or topic slug.
6. An alias rule (`/about-us` → `/about`, `/terms-of-service` → `/terms`), only when
   the target is live.
7. `RETIRE_410`, only when the URL was gone (404/410) in at least 2 inventories at least
   7 days apart, and has no Search Console clicks or impressions, no backlinks, no
   internal links, no sitemap entry and no article evidence.
8. Everything else → `REVIEW`.

**Safeguards:**
- **Slugs are never generated.** There's no case folding or fuzzy matching. An article
  missing from the CMS is imported with its legacy slug (worklist `keep_slug`), so
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
- **Legacy article export** (`--articles-csv`): `id`, `slug`, `title`, `author`,
  `published_at`, `updated_at`, `status`, `category`, `section`, `url`. Only `slug` or
  `id` is required. `url` is used only if the database stores it; URLs are never
  constructed.
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
| `issues` | `;`-separated: `broken_links:N`, `linked_but_broken`, `redirect_chain`, `redirect_loop`, `redirect_offsite`, `temporary_redirect`, `missing_canonical`, `canonical_elsewhere`, `canonical_not_ok`, `multiple_canonicals`, `noindex`, `accidental_noindex`, `sitemap_lists_non_indexable`, `missing_from_archive`, `missing_title`, `missing_description`, `soft_404`, `shell_only`, `server_error`, `error` |
| `error` | Network error, robots.txt exclusion or why it wasn't checked |

The inventory step also writes:
- `links.csv`: `source_url`, `target_url`, `anchor`, `target_final_status`, `broken`
- `legacy-articles.csv`: the article records with `matched_url`, `match` (`url`, `slug`
  or `id`), `in_sitemap`, `in_archive`, `missing_from_archive` and `no_public_url`
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
| `confidence` | `exact`, `cms_original_url`, `cms_original_slug`, `slug`, `rule`, `observed_gone` or `manual` |
| `reason` | Why this was proposed |
| `content_action` | `NONE`, `IMPORT`, `REWRITE_REVIEW`, `IMPORT_FROM_EXPORT`, `IMPORT_MEDIA`, `CREATE_OR_REDIRECT` or `REVIEW` |
| `approved` / `approved_by` / `note` | Your decision (`yes` to apply) |

The map step also writes `mapping-problems.csv` (validation results), `excluded-urls.csv`
(system URLs such as `/login` or `/admin`), and `migration-report.md` / `.json`.

### `content-worklist.csv` (content to import or rewrite)

| Column | Meaning |
|---|---|
| `priority` | As in the mapping |
| `content_action` | `IMPORT` (copy, keep facts), `REWRITE_REVIEW` (thin, under 300 words, or missing author or date: check before publishing), `IMPORT_FROM_EXPORT` (app-shell page: take the text from the database export), `IMPORT_MEDIA`, `FIND_URL` (published article whose URL wasn't found: look it up, never guess), `CREATE_OR_REDIRECT`, `REVIEW` |
| `legacy_url` | Legacy URL (empty for `FIND_URL`) |
| `keep_slug` | Slug to use in the CMS, unchanged |
| `new_path` | Where it will live (`/articles/<keep_slug>`) |
| `title` / `author` / `published_time` / `modified_time` / `category` | Preserve these: set the CMS author, `published_at` and `first_published_at` to the original dates and `source=migrated`, `original_url`, `original_slug` |
| `word_count` / `legacy_class` / `source` / `notes` | Context for the editor |

When importing into the new CMS:
- Create new articles only. Never edit an existing article to "make it match".
- Keep the original topic and facts, and record the original author and publication
  date.

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
2. **The current production database export.** In the old `TPA-backend` schema:

   ```sql
   SELECT a.id, a.slug, a.title, u.name AS author, a.published_at, a.status,
          c.slug AS category, s.slug AS section
   FROM articles a
   LEFT JOIN users u ON u.id = a.user_id
   LEFT JOIN categories c ON c.id = a.category_id
   LEFT JOIN sections s ON s.id = a.section_id
   ORDER BY a.id;
   ```

   Export the result as CSV for `--articles-csv`, and keep a full backup of the database
   and the uploaded media.
3. **From the current VPS:**
   - the Nginx (or other web server) site configuration, for any existing redirects
     and rewrite rules
   - 90 days of access logs, for URLs that real visitors and bots request
   - the deployed frontend's route table or build, which shows how root-level article
     URLs like `/50-kindness-quotes-to-brighten-your-day` are served
   - the live `sitemap.xml` and `robots.txt` (the inventory fetches these itself)
4. **Any earlier sitemaps, Wayback Machine URL lists or old analytics exports,** passed
   as extra `--seeds`.
