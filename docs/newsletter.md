# The Positive Reset — newsletter, email marketing and lead magnets (Batch 06)

## What exists

| Area                                                         | Where                                                                                                                                                                            |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Subscribers, segments, tags, suppression list, import/export | `/admin/subscribers`                                                                                                                                                             |
| Campaigns and templates                                      | `/admin/newsletters`                                                                                                                                                             |
| Automations                                                  | `/admin/email-automations`                                                                                                                                                       |
| Lead magnets (free resources)                                | `/admin/lead-magnets`                                                                                                                                                            |
| Sending settings (Super Admin)                               | `/admin/email-settings`                                                                                                                                                          |
| Public pages                                                 | signup forms on the homepage, footer, `/newsletter`, articles and CMS sections; `/newsletter/confirm`, `/newsletter/preferences`, `/newsletter/unsubscribe`, `/resources/access` |

Backend code lives in `app/services/newsletter/`, `app/api/newsletter.py` and `app/api/admin/newsletter.py`; models in `app/models/newsletter.py`.

## Consent and safeguards

- **Double opt-in.** Every signup is `pending` until the person clicks the confirmation link. Only `subscribed` and confirmed people receive marketing.
- **Consent evidence.** Each subscription records the time, the exact consent wording and version, the source, and a hashed IP address. Changing the wording requires a new consent version.
- **Separate from accounts.** Registering or buying never subscribes anyone. Product announcements go only to subscribers who chose "New digital products".
- **No enumeration.** Public signup and resource requests always return the same "check your inbox" response.
- **Spam protection.** Signups and resource requests are protected by a honeypot field, a minimum fill time, and rate limits per IP and per address.
- **Unsubscribing** is immediate:
  - via a link in every email, and RFC 8058 one-click (`List-Unsubscribe` and `List-Unsubscribe-Post` headers);
  - it cancels queued mail, exits automations, adds the address to the suppression list and is audited.
- **Re-subscribing** needs fresh consent and a new confirmation.
- **Bounces and complaints** suppress permanently. The suppression list stores only SHA-256 hashes, so it survives erasure.
- **Self-service erasure** is on the preferences page (staff can also erase). Delivery records keep an anonymised address.
- **Imports are quarantined** (never mailed) unless the importer attests to recorded opt-in consent and each row has a consent date. Quarantined contacts can be sent a confirmation request.

## Sending

Sending mode (`/admin/email-settings`):

- `disabled` (default): nothing is sent and forms stay hidden.
- `test`: mail reaches only `NEWSLETTER_TEST_RECIPIENTS`; everyone else is recorded as skipped.
- `live`: needs every readiness check:
  - `NEWSLETTER_LIVE_ALLOWED=true`;
  - a real SMTP provider;
  - a sender address;
  - consent wording;
  - a postal address;
  - four Super Admin confirmations (DNS authentication, provider verified, test email checked, privacy policy reviewed).

Campaign workflow:

1. Draft (`newsletters.create`/`edit`).
2. Approve (`newsletters.publish`). Any later edit withdraws the approval, and approval is refused while starter-template `[guidance]` remains.
3. Schedule (`newsletters.schedule`) or send (`newsletters.send`).

Previews render in a sandboxed frame and send nothing. Test emails go only to the requester or a configured test recipient, and never change a campaign.

The **email worker** (`flask --app wsgi newsletter worker`, systemd `tpa-email-worker`) does all the heavy work outside web requests:

- starts due schedules;
- freezes each campaign (content snapshot and recipient list, inserted idempotently);
- expands automation triggers;
- sends in rate-limited batches with retries and exponential backoff;
- re-checks consent and suppression before every message;
- recovers after interruption. A message whose send had already started is marked `unknown` and **not** resent automatically (staff can retry it), so nobody gets a duplicate.

Reports count only evidence:

- eligible, queued, attempted;
- **accepted by the provider**: SMTP acceptance is not delivery;
- delivered, bounced and complained, only from signed provider feedback;
- failed, suppressed, skipped (test mode), cancelled, and unsubscribes from the campaign.

There is no open or click tracking.

**Provider feedback.** `POST /api/v1/email/feedback` takes a body `{"events": [{"type": "bounced|complained|delivered", "message_id"?, "email"?, "bounce_type"?: "hard|soft"}]}` with these headers:

- `X-TPA-Timestamp`: Unix seconds, within 5 minutes;
- `X-TPA-Signature`: hex HMAC-SHA256 of `"<timestamp>.<raw body>"`, keyed with `EMAIL_FEEDBACK_SECRET`.

A small adapter is needed to translate your provider's webhook format into this shape.

## Automations

Six starters are added as **drafts**:

- confirmed welcome;
- welcome sequence;
- lead magnet follow-up;
- new article;
- product announcement;
- re-engagement.

Activation is refused while starter guidance remains. Each automation has a trigger, an optional segment, a required preference, ordered emails with delays and an exit tag.

- Enrolment is unique per subscriber and trigger context, so nobody receives the same sequence twice.
- Article and product announcements fire once per item; products only when actually purchasable.
- Re-engagement exits as soon as the subscriber engages.

## Lead magnets

A lead magnet wraps a **published free product with real private files** (Batch 05). Nothing is invented.

- Requests send a secure link (`/resources/access#token=…`); only a hash of the token is stored. The link expires after `LEAD_MAGNET_LINK_TTL_HOURS` or `LEAD_MAGNET_MAX_DOWNLOADS`.
- Each download uses a 5-minute signed URL streamed through the private-file path.
- Newsletter opt-in is a separate, unticked checkbox. "Required" mode is allowed only with a clear notice and always records consent through double opt-in.
- Connect a lead magnet in the page builder with the **Free resource signup** section, or the optional field on **Newsletter signup**.

## Configuration (backend/.env)

See `backend/.env.example`:

- `NEWSLETTER_MAIL_BACKEND`, `NEWSLETTER_FROM_EMAIL`, `NEWSLETTER_SMTP_*`;
- `NEWSLETTER_SEND_RATE_PER_MINUTE`, `NEWSLETTER_BATCH_SIZE`, `NEWSLETTER_MAX_ATTEMPTS`, `NEWSLETTER_STALE_CLAIM_MINUTES`;
- `NEWSLETTER_TEST_RECIPIENTS`, `NEWSLETTER_CONFIRM_TTL_HOURS`, `NEWSLETTER_LIVE_ALLOWED`;
- `EMAIL_FEEDBACK_SECRET`, `LEAD_MAGNET_LINK_TTL_HOURS`, `LEAD_MAGNET_MAX_DOWNLOADS`, `RATELIMIT_NEWSLETTER_SIGNUP`.

Production refuses `console` and `memory` backends.

### SPF, DKIM and DMARC

Bulk mail must not be sent until the sending domain is authenticated for the provider you actually use. Use the exact records that provider gives you (no records are invented here).

1. **SPF**: one TXT record on the sending domain that includes the provider's SPF mechanism. Only one SPF record per domain.
2. **DKIM**: the CNAME/TXT keys the provider generates for your domain.
3. **DMARC**: a TXT record at `_dmarc.<domain>`. Start with `p=none` and a reporting address, then tighten to `quarantine`/`reject` once reports show SPF/DKIM alignment.
4. Check with the provider's verification page and by sending a test (headers should show `spf=pass`, `dkim=pass`, `dmarc=pass`).
5. Then tick the confirmations in `/admin/email-settings`.

## Permissions

| Permission                                                                  | Allows                                                                                 |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `subscribers.view` / `subscribers.manage` / `subscribers.export`            | View; tags, segments, imports, unsubscribes, suppressions, erasure; audited CSV export |
| `newsletters.view` / `create` / `edit`                                      | See, create and edit drafts (and send test emails to yourself)                         |
| `newsletters.publish` / `schedule` / `send`                                 | Approve; schedule or cancel a schedule; send or stop                                   |
| `newsletters.reports`                                                       | Delivery reports and per-recipient records                                             |
| `email_templates.manage`, `email_automations.manage`, `lead_magnets.manage` | Templates, automations, lead magnets                                                   |
| `email_settings.manage` (sensitive)                                         | Sending mode, sender, consent wording, attestations: Super Admin only                  |

`newsletters.manage` (planned since Batch 02) is superseded and stays unavailable.

Template grants:

- **Newsletter Manager:** everything except email settings.
- **Administrator:** everything except export and settings.
- **Marketing Manager:** view, create, edit, reports, subscribers.view and lead magnets; no approve or send.
- **Editorial roles:** nothing.

Customers never hold admin permissions.

## Known limitations

- SMTP gives no delivery, bounce or complaint data on its own. Those need a provider webhook adapter posting to the feedback endpoint. Only SMTP is implemented; API providers plug into `services/newsletter/providers.py`.
- There is no open or click tracking (by design), so engagement signals are confirmation, preference updates and resource claims.
- Segment preference and interest filters run in Python over confirmed subscribers. That is fine for tens of thousands; very large lists would need JSON-indexed SQL.
- Automations have no visual builder; steps are edited as an ordered list.
- Signup forms are prerendered: settings changes queue a site rebuild, and forms re-check status in the browser.
