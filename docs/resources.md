# Premium resources, media library and secure delivery (Batch 08)

Think Positive Always sells and gives away **written** digital resources. Courses, when
they arrive, will also be text-based: lessons, chapters, exercises, quizzes, reading
material and optional written downloads. There are no video uploads, video fields or
video hosting integrations anywhere in the system.

## 1. What a resource is

A premium resource **is a commerce product** with file delivery. There is no second
product table and no second checkout: prices, carts, Paystack, guest checkout,
entitlements, refunds, receipts and the download log are the ones described in
`docs/commerce.md`.

| Need                                                                                                                 | Where it lives                                                    |
| -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Title, description, slug, cover, author, categories, tags, SEO                                                       | Product content (draft → publish)                                 |
| Type: eBook, workbook, journal, planner, worksheet, guide, template, checklist, written learning pack, resource pack | `product_type` (`app/commerce/product_types.py`)                  |
| Free or premium                                                                                                      | `pricing_model` (`free`: claim with an account; `paid`: checkout) |
| Pricing                                                                                                              | product prices (one per currency, promotions), unchanged          |
| Several downloadable files, each with versions                                                                       | product files and file versions                                   |
| Draft / published / archived                                                                                         | product status                                                    |
| Related resources                                                                                                    | `product_related` (ordered, part of the published snapshot)       |
| Access rules                                                                                                         | `access_days`, `download_limit`, `membership_eligible` (see §3)   |

Admins work from **Commerce → Premium Resources** (a resource-focused list: type,
free/premium, access period, files and formats, status) and edit in the product editor,
which now has an **Access & related** tab. Bundles keep their own page.

The public **Resource library** (`/resources`, prerendered, in the sitemap) lists
published resources with type and free/premium filters; each resource has its page at
`/shop/<slug>` showing formats, file list, access terms ("Lifetime access · unlimited
downloads", "365-day access · 5 downloads") and related resources.

## 2. Media library: images and premium files

**Media → Media library** is the single place for files:

- **Images** (public): JPG, PNG, WebP, AVIF and GIF uploads are validated (content
  sniffing, pixel limits against decompression bombs, no SVG/animation), stripped of
  metadata and optimised into responsive WebP/AVIF/JPEG sizes. Categories (general,
  articles, resource covers, pages, branding, people, marketing) for filtering; search;
  sizes and formats; upload progress; preview; replacement with version history;
  archiving; usage tracking; deletion only when unused. URLs are unchanged:
  `/media/<id>/v<n>/<name>-<width>.<format>`.
- **Premium files** (protected): every resource file across all resources, with
  resource, category folder, format, size, number of versions, downloads and status;
  search and filters (format, category, status) and sorting (recent, title, size,
  downloads). Upload a file to a resource (with progress), upload a new version (the
  previous ones are kept), archive/restore, or delete, but only when allowed (below). No
  preview is shown: premium files never get a public address. Administrators can
  download any version to check it.

### Accepted premium formats

PDF, EPUB, **DOCX** and **XLSX** (new), and ZIP resource packs, configurable with
`RESOURCE_FILE_FORMATS`. Every upload is checked by content, not by name:

- PDFs with JavaScript, launch actions, embedded files or rich media are refused;
  truncated PDFs are refused.
- DOCX/XLSX must have their required parts; macros (`vbaProject.bin`, macro-enabled
  content types), ActiveX controls and embedded OLE objects are refused, even if a
  `.docm` is renamed `.docx`.
- ZIP/EPUB/Office containers: entry count, total uncompressed size and compression ratio
  limits (zip bombs), no path traversal, symlinks, encryption, executables or nested
  archives in packs.
- An optional malware scanner (`PRODUCT_FILES_SCAN_COMMAND`, e.g. ClamAV) runs in the
  worker; files are not delivered until they are marked clean.

### Versions and safe deletion

Replacing a file adds version _n+1_; buyers always get the newest version **and** keep
the exact version they received. Deletion is restricted:

- a version can be deleted only if it is not the current one, no purchase recorded it and
  it was never authorised or downloaded (the download log keeps pointing at it);
- a whole file can be deleted only if no purchase ever included it and it was never
  downloaded; otherwise **archive** it (buyers keep access, new buyers don't get it).

The reason is shown next to anything that can't be deleted.

## 3. Access rules

Set per resource in **Access & related** (needs _Manage prices_, like other commercial
terms). They are applied when access is granted; existing buyers keep what they got.

| Rule                 | Effect                                                                                                                                                                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Access period (days) | The entitlement gets `expires_at`; afterwards the library shows "expired", new download links are refused and links already issued stop working. Empty = lifetime. A free resource can be claimed again after it expires; an expired purchase can be bought again. |
| Downloads per buyer  | Overrides the store-wide `payments.download_limit` for this resource.                                                                                                                                                                                              |
| Membership eligible  | Lets a future membership unlock the resource (no effect until memberships exist).                                                                                                                                                                                  |

## 4. Secure delivery

Unchanged in principle, extended for expiry:

1. The buyer (signed in, guest order page, or guest access link) asks for a file. The
   server checks the entitlement: owned by them (guest purchases only after the account
   email is confirmed), **active, not expired**, file/version allowed, deliverable (scan),
   download limit. It then issues a random, short-lived (`DOWNLOAD_LINK_TTL_SECONDS`),
   few-use (`DOWNLOAD_LINK_MAX_USES`) link; only its hash is stored.
2. Following the link re-checks everything, including revocation, refund and expiry,
   and the session for account downloads.
3. Flask either streams the file or answers with `X-Accel-Redirect:
/_protected_downloads/<category>/<id>/v<n>/<random>.<ext>`; Nginx serves it from the
   `internal` location. Files are `attachment`, `private, no-store`, `noindex`, sandboxed.

Every authorisation, served download and refusal (with its reason: revoked, expired,
limit reached, link expired or used up, wrong session, version not allowed) is recorded
in `download_events`. **Download Entitlements → Download activity** shows the last 30
days (served, links issued, refused), the most downloaded resources, why requests were
refused, and the log filtered by resource.

## 5. Storage and health

See `docs/hostinger-vps.md` §5 for the folder layout and permissions. Summary:

- Premium files: `PRODUCT_FILES_ROOT/<ebooks|workbooks|templates|courses|downloads>/…`,
  random keys, never derived from the uploaded name, outside every web root.
- Uploads are received in `UPLOAD_TEMP_ROOT` (request bodies too), validated, then moved
  atomically; abandoned temp files are removed hourly.
- **Administration → Storage Health** (_View storage health_): disk usage per area,
  folder permissions (including "Nginx can't read premium files"), missing/orphaned
  files, abandoned uploads, backup status, rate-limit storage, limits and recent upload
  errors (refused files and storage failures, for images and premium files).

## 6. Future courses and memberships

`app/services/commerce/access.py` is the interface future modules use. Everything still
ends in an `Entitlement`, so downloads, revocation, expiry, the download log and the
customer library work the same:

```python
access.grant(customer, product, source="membership", reference="membership:42",
             expires_at=period_end)          # join or renew (same reference = extend)
access.grant(customer, product, source="course", reference="course:7")
access.revoke("membership", "membership:42", "Membership cancelled")
access.can_download(customer, product)       # any usable entitlement, any source
```

- Entitlement sources `membership` and `course` are reserved in the database (migration
  `c3e8d1f20b47`).
- Memberships can unlock only resources marked _membership eligible_.
- Courses will be text: their data model will hold lessons, chapters, exercises, quizzes
  and reading material, and can list resources as written downloads that enrolment
  unlocks through `access.grant(..., source="course")`. No video fields are needed or
  planned.

## 7. Limitations

- No inline preview of premium files in the admin (by design: no public URL). Admins
  download a version to check it.
- Category folders apply to files uploaded from Batch 08 on; earlier files keep their
  original keys (still valid).
- The access period is measured from when access is granted; changing it doesn't change
  existing entitlements.
- On SQLite (development only) the new positive-number checks on `download_limit` and
  `access_days` are enforced by the application, not the database; PostgreSQL has them as
  constraints.
- Memberships and courses are not implemented yet; only the access interface and the
  reserved entitlement sources exist.
