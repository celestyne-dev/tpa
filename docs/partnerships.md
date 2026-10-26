# Sponsorships, advertising, affiliates and the media kit (Batch 07)

Nothing in this module is automatic: revenue, commissions and audience figures exist only
when someone records them. The system never contacts partners, issues invoices, takes
payments, joins affiliate programs or invents numbers.

## Partners and inquiries

- **`/partner-with-us`** shows the inquiry form (also available as the _Partnership inquiry
  form_ page-builder section). It asks for organisation, name, business email, website,
  collaboration type, an optional budget range, objectives, a message and confirmation of
  the privacy notice.
  - Validated on the server. Rate limited per IP (`RATELIMIT_PARTNERSHIP_INQUIRY`) and per
    address (3 per hour). A hidden honeypot field and a minimum fill time stop bots.
  - "Received" (HTTP 201 with a reference) is only returned after the inquiry is committed.
    Spam gets a neutral 202 and is not stored.
  - The team is notified at `PARTNERSHIP_NOTIFY_EMAIL` (falls back to `PARTNERSHIPS_EMAIL`)
    only when `MAIL_BACKEND` really sends. The outcome is stored on the inquiry
    (`no_recipient`, `not_configured`, `failed` or the backend name). The email never contains the
    sender's contact details.
- **`/admin/partnership-inquiries`**: review, mark reviewed/declined/spam, or **convert**
  (creates the partner and an opportunity).
- **`/admin/partners`**: organisation, website, logo (media library), industry, country,
  type, status, source, owner, description, confidential notes and work contacts
  (name, business email, role). No other personal data is collected.

## Pipeline and campaigns (`/admin/sponsorships`)

- **Opportunities** move through: new inquiry → qualification → proposal ⇄ negotiation →
  approved → contracted → active → completed, or lost (reason required) / cancelled.
  Invalid moves are refused. Interactions (call, email, meeting, note) and follow-up dates
  are recorded in the history. The expected value is an estimate and is reported as
  pipeline, never as revenue.
- **Campaigns**: draft → internal review → sponsor review → approved → scheduled → active →
  completed. Approval needs `sponsorships.approve`, start and end dates and a disclosure.
  "Scheduled" needs a future start, and "active" is only allowed within the dates. Editing an
  approved or scheduled campaign sends it back to draft. "Sponsor review" is an internal
  record: sponsors never get admin access.

## Inventory, rate cards and bookings

- **Placements** (homepage sponsor, article sponsor, in-article banner, sidebar, footer,
  newsletter sponsor, sponsored article, brand spotlight, landing page) have a key, channel,
  dimensions, formats, capacity/exclusivity, pricing model, currency, restrictions and an
  active flag. CPM pricing is refused unless the placement is marked as having reliable
  impression measurement (nothing measures impressions yet).
- **Rate cards** are indicative, stored in integer minor units with their currency, and
  shown publicly only when marked public and within their validity dates.
- **Bookings**: placement, partner, campaign, dates (UTC), agreed fee, creative (headline,
  text, image, https link). Status: pending → approved ⇄ paused → stopped, or cancelled.
  - Exclusive placements (capacity 1) cannot hold overlapping approved or paused bookings.
    Saving or approving one returns 409. Overlaps with pending bookings show a warning.
  - Only **approved** bookings whose window includes "now" are rendered. Pending, paused,
    stopped, cancelled and expired bookings never appear.
  - Material edits to an approved booking return it to pending. Every change is in the
    booking history and the audit log.
  - The publishing worker rebuilds the static site at booking start/end boundaries, and the
    browser hides an expired creative immediately after hydration.

## Sponsored articles (article editor → Sponsorship tab)

- Sponsor name, label (must say sponsored/paid; default "Sponsored Content"), disclosure,
  partner, campaign, dates, paid outbound links, sponsor media and approval notes.
- Review: draft → internal review → sponsor review → **Approve** (Editor-in-Chief,
  `sponsorships.approve`). Material edits after approval go back to internal review, and a
  scheduled article is returned to draft.
- Publishing (immediate or scheduled) is refused until the disclosure is set and the
  sponsorship is approved. A sponsorship can't be removed once the article has been published.
- Readers see the label and sponsor name directly under the title, plus the disclosure, in both
  the React app and the prerendered HTML. List cards carry the label too. Links listed as paid get
  `rel="sponsored noopener noreferrer"`; other links stay organic (`noopener noreferrer`).
  Canonicals, redirects and SEO fields are unchanged.

## Newsletter sponsorship

In the newsletter editor, users with `sponsorships.manage` can set a sponsor and
disclosure. The disclosure is added at the top of the HTML and plain-text email. A sponsored
edition can't be approved without the disclosure or without `sponsorships.approve`.
Unsubscribe links and consent rules are unchanged.

## Affiliates

- **Programs** (`/admin/affiliates`): merchant, network, category, commission model, rate (only once
  confirmed), currency, payout threshold, account status, terms URL, last verified date.
  Account identifiers and notes are visible only with `affiliates.manage`.
- **Links** (`/admin/affiliate-links`): https destinations only. The following are rejected:
  `javascript:`, `data:`, plain http, embedded credentials, localhost and private IPs, and this
  site's `/admin` and `/api`. Readers use `/api/v1/go/<slug>`, which redirects only to the stored, re-validated
  destination (plus UTM tags). Query parameters can't change the target. Inactive or expired
  links return 404.
- **Clicks** are stored only as daily counts per link and source page. Nothing identifies the visitor,
  and no third-party scripts are used. Clicks are never treated as purchases or earnings.
- **Commissions** come only from CSV imports (`reference,date,amount,currency[,status,link]`;
  duplicate references per program are skipped) or manual entries with written evidence.
- **Disclosure**: edited on the Affiliates page and required (40–400 characters, mentioning
  affiliate links or commission). The _Affiliate recommendations_ section always shows it
  next to the links, which carry `rel="sponsored"`.

## Media kit (`/admin/media-kit`, public at `/advertise`)

- Draft and published versions: about, editorial focus, audience summary and geography, content
  categories, formats, guidelines, sponsorship policy, contact button, brand assets, and switches for
  placements, the public rate card and measurements. Publishing queues a site rebuild. A published
  CMS page at `/advertise` replaces the built-in page.
- **Audience measurements** need a type, value, platform, source and measurement date (not in the
  future), and record who entered them. Only figures marked verified can be made public. They are always shown as
  "Measured <date>. Source: …", and social followers are labelled as social, never as
  website traffic. Nothing is fetched automatically. HTML only; there is no PDF export.

## Reports (`/admin/partnership-reports`)

Per currency, never converted:

- pipeline (expected);
- contracted;
- completed campaigns;
- invoiced (manual records);
- received, verified and unverified separately;
- outstanding (contracted minus verified received);
- affiliate commissions, reported and paid.

The report also shows campaigns by status, bookings by state and placement utilisation.

You can filter by date, partner, campaign, status, channel and currency. CSV export needs
`partnership_reports.export` and is audited.

## Permissions

| Permission                                                                        | Purpose                                                  |
| --------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `partnerships.view` / `partnerships.manage`                                       | Partners, contacts, inquiries, opportunities             |
| `sponsorships.view` / `sponsorships.manage` / `sponsorships.approve`              | Campaigns, article and newsletter sponsorships, approval |
| `advertising.view`, `advertising.manage_inventory`, `advertising.manage_bookings` | Placements and rates; bookings                           |
| `media_kit.manage`                                                                | Media kit and audience measurements                      |
| `affiliates.view` / `affiliates.manage` / `affiliates.manage_links`               | Programs (private IDs with manage), links                |
| `partnership_finance.view` / `partnership_finance.manage`                         | Invoiced/received records, commission entries            |
| `partnership_reports.export`                                                      | CSV export                                               |

Templates: Partnership Manager (relationships, inquiries, opportunities, campaigns, bookings,
inventory, media kit); Marketing Manager (campaigns, bookings, affiliate links);
Affiliate Manager (affiliates); Editor-in-Chief (view + approve sponsorships); Finance Manager
(view + finance + export); Administrator (all except finance management); Super Admin
(everything). Content writers get none. Money fields are hidden from roles without commercial rights.

## Manual setup checklist

1. Set `PARTNERSHIP_NOTIFY_EMAIL` and a real `MAIL_BACKEND` if you want inquiry emails.
2. Create placements and (optionally) public rate cards.
3. Enter audience measurements from your own analytics exports, then verify them.
4. Write and publish the media kit.
5. Record affiliate programs only after you've actually joined them, then create links and set the disclosure.
6. Add page-builder sections (sponsor logos, sponsored banner, brand spotlight, affiliate
   recommendations, media kit block, inquiry form) where needed.
