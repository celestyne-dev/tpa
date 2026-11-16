# Social publishing: Pinterest and Instagram

Admin › Integrations connects the site's own Pinterest and Instagram accounts.
Admin › Social publishing sends Media Library images to them, now or on a schedule.
Nothing is posted automatically: publishing an article or a quote collection on TPA never
creates a Pin or an Instagram post. Every post is created by a person with the
"Publish to Pinterest and Instagram" permission.

Automated tests replace every platform call with a fake. **The Instagram connection
(Unified Login), importing and publishing have not been exercised against Meta's live API
from the development environment.** Treat them as unconfirmed until the real-account checks
at the end of this page pass.

## Permissions

| Permission       | Allows                                                        | Default roles                               |
| ---------------- | ------------------------------------------------------------- | ------------------------------------------- |
| `social.view`    | See accounts, boards and posts                                | Super Admin, Administrator, Marketing Manager, Editor-in-Chief |
| `social.publish` | Create, schedule, retry and cancel posts; import from Instagram (also needs `media.upload`) | Super Admin, Administrator, Marketing Manager |
| `social.connect` | Connect and disconnect accounts (sensitive)                   | Super Admin only                            |

## Server settings (names only; never commit values)

| Name                          | Purpose                                                                 |
| ----------------------------- | ----------------------------------------------------------------------- |
| `SOCIAL_TOKEN_ENCRYPTION_KEY` | Fernet key that encrypts stored tokens. Comma-separated keys rotate (first encrypts, all decrypt). |
| `PINTEREST_CLIENT_ID`         | Pinterest app id                                                        |
| `PINTEREST_CLIENT_SECRET`     | Pinterest app secret                                                    |
| `PINTEREST_REDIRECT_URI`      | Optional. Default `{ADMIN_BASE_URL}/admin/integrations/pinterest/callback` |
| `PINTEREST_API_BASE`          | Optional. `https://api-sandbox.pinterest.com` while the app has trial access |
| `INSTAGRAM_CLIENT_ID`         | The **Meta App ID** (App settings › Basic)                              |
| `INSTAGRAM_CLIENT_SECRET`     | The **Meta App Secret** (App settings › Basic)                          |
| `INSTAGRAM_CONFIG_ID`         | The Unified Login configuration id (Facebook Login for Business)        |
| `INSTAGRAM_REDIRECT_URI`      | Optional. Default `{ADMIN_BASE_URL}/admin/integrations/instagram/callback` |
| `INSTAGRAM_ACCOUNT_ID`        | Optional. Instagram account id or username to use when Meta grants several, or when Meta lists none |
| `INSTAGRAM_OVERRIDE_RESPONSE_TYPE` | Optional, default `false`. See "Not verified against Meta" below   |
| `INSTAGRAM_GRAPH_VERSION`     | Optional. Default `v27.0`                                               |
| `SOCIAL_HTTP_TIMEOUT`         | Optional. Seconds, default 20                                           |
| `SOCIAL_IMPORT_MAX_BYTES`     | Optional. Largest Instagram image imported, default 15 MB               |

Generate the key once:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Losing or changing the key without keeping the old one in the list makes stored tokens
unreadable; the accounts then show "Reconnect needed". Until the settings exist, Integrations
shows which names are missing and the rest of the CMS works normally.

The release that introduced social publishing needs `pip install -r requirements.txt` (adds
`cryptography`) and `flask db upgrade` (migration `f2b6d8e0a314`). The Unified Login update
adds no migration and no dependency: deploy the code, add `INSTAGRAM_CONFIG_ID` (and set
`INSTAGRAM_CLIENT_ID` / `INSTAGRAM_CLIENT_SECRET` to the Meta app's id and secret), restart
the backend, then reconnect Instagram and, for `boards:write`, Pinterest.

## Pinterest developer setup

1. The Pinterest account must be a **business** account (apps registered after
   14 September 2026 are refused for personal accounts).
2. At developers.pinterest.com create an app and request access. New apps get **Trial
   access**; request **Standard access** before relying on it. With Trial access, set
   `PINTEREST_API_BASE` to the sandbox address, or Pins created are only visible to the
   account itself.
3. Add the redirect address shown on the Integrations page, exactly.
4. Scopes requested: `user_accounts:read`, `boards:read`, `boards:write`, `pins:read`,
   `pins:write`. An account connected before `boards:write` was added keeps working and
   keeps its scheduled posts; Integrations lists `boards:write` as a missing permission
   until a Super Admin presses **Reconnect Pinterest** and approves it.
5. Put the app id and secret in the server settings.

Tokens: the access token lasts 30 days and is renewed automatically with the refresh token
(60 days, itself renewed on each refresh). If both lapse, the account shows
"Reconnect needed".

### Claiming the website

The tag `<meta name="p:domain_verify" content="…">` is written into the `<head>` of every
prerendered page from Settings › Technical › Pinterest verification code (default: the code
supplied for thinkpositivealways.com). Only the code is stored; pasted tags are reduced to
their code and anything else is refused. In Pinterest: Settings › Claimed accounts ›
Websites › Claim › Add HTML tag › Verify. The CMS cannot see whether Pinterest approved it.

## Meta (Instagram) developer setup: Instagram API with Unified Login

Meta apps created now cannot use "API setup with Instagram login". They use **Unified
Login**: Facebook Login for Business with a configuration (`config_id`), the
`graph.facebook.com` host, and the permissions `instagram_basic` and
`instagram_content_publish`. The CMS only supports this flow.

1. The Instagram account must be a **professional** (Business or Creator) account.
2. In the Meta app (Business type, in a business portfolio) open Instagram › **API setup
   with Unified login** and create a configuration with `instagram_basic` and
   `instagram_content_publish`. Choose the **system-user access token** type with the
   token set to **never expire** if the dashboard offers the choice.
3. Add the redirect address shown on the Integrations page to the configuration / Facebook
   Login for Business settings, exactly:
   `https://thinkpositivealways.com/admin/integrations/instagram/callback`.
4. While the app is in Development mode, the Instagram account must be an accepted
   **Instagram tester** of the app. For other accounts both permissions need App Review
   (Advanced Access) and the app must be Live.
5. Server settings for thinkpositivealways.com:

       INSTAGRAM_CLIENT_ID=1462765242713469
       INSTAGRAM_CONFIG_ID=1147246304946068
       INSTAGRAM_CLIENT_SECRET=<Meta App Secret; never commit it>

   The App ID and configuration ID are identifiers, not secrets. The App Secret is.

### How the connection works

- **Sign-in**: `https://www.facebook.com/<version>/dialog/oauth` with `client_id`,
  `config_id`, `redirect_uri`, `response_type=code` and a signed `state` (valid 10 minutes,
  bound to the platform and to the Super Admin who started it). No `scope` is sent: the
  permissions come from the configuration.
- **Code exchange**: `GET graph.facebook.com/<version>/oauth/access_token` with the app id,
  app secret, code and redirect address.
- **Token**: Meta is asked (`/debug_token`) what was issued. A system-user token with no
  expiry is stored as non-expiring and is **never refreshed**; Integrations shows
  "Does not expire". If Meta issues a user token instead, it is exchanged for a long-lived
  one (about 60 days) and renewed with `fb_exchange_token` before it expires; a renewal
  that fails temporarily does not stop scheduled posts while the token is still valid. The
  old `graph.instagram.com/refresh_access_token` endpoint is not called at all.
- **Which account**: `GET /me/assigned_instagram_accounts`, then the account ids named in
  the token's granular permissions, then an account linked to a Facebook Page
  (`/me/accounts`). Every candidate is read back (`GET /<id>?fields=id,username,name`) and
  only readable accounts count. Exactly one must remain; with several, set
  `INSTAGRAM_ACCOUNT_ID` or choose one account in Meta's window. The old `/me` profile
  response is not used.
- **Media and publishing** use the same account id on `graph.facebook.com`:
  `/<id>/media`, `/<id>/content_publishing_limit`, `POST /<id>/media`,
  `GET /<container>?fields=status_code`, `POST /<id>/media_publish`.
- Codes, the App Secret and tokens are never written to logs, the audit log or API
  responses. The audit log records only the username, the kind of grant and whether it expires.

An Instagram account connected with the previous Instagram Login flow (if any) stops
working after this release and shows "Reconnect needed"; reconnect it once.

### Not verified against Meta

None of this could be run against Meta from the development environment (no App Secret and
no interactive sign-in), and Meta's Unified Login pages could not be opened from it; the
flow follows Facebook Login for Business and what other projects report for Unified Login.
The tests use a stand-in for `graph.facebook.com`. Check these on the first real connection:

1. **Sign-in address**. If Meta's window rejects the request, set
   `INSTAGRAM_OVERRIDE_RESPONSE_TYPE=true` (adds `override_default_response_type=true`,
   which Facebook Login for Business documents for system-user configurations) and retry.
2. **`state`**. Facebook Login returns `state` unchanged; this is assumed for Unified Login.
   If it is not returned, the callback reports "The connection request is invalid".
3. **Code exchange**. The redirect address is sent; if Meta's error mentions
   `redirect_uri` the exchange is repeated once without it.
4. **Token type and expiry**. Read from `/debug_token`. If Integrations shows a renewal date
   instead of "Does not expire", the configuration is issuing a user token: change the
   configuration to a non-expiring system-user token and reconnect.
5. **Account discovery**. Some projects report `/me/assigned_instagram_accounts` returning
   an empty list although the account was granted. The fallbacks above cover that; if all
   are empty, set `INSTAGRAM_ACCOUNT_ID` to the numeric Instagram account id and reconnect.
6. **Permissions**. The granted permissions come from `/debug_token`. If Meta does not
   report them, the account connects and a missing publish permission only shows up as a
   "Failed" post with Meta's message.
7. **Media fields**. `media_url`, `permalink`, `timestamp` and `username` are requested on
   `/<id>/media`; a field Meta refuses for this token type would surface as an error when
   listing posts to import.
8. **Graph version**. `v27.0` is the default; change `INSTAGRAM_GRAPH_VERSION` if Meta's
   dashboard shows a different current version for the app.

## Connecting in the CMS (Super Admin)

1. Admin › Integrations. If a card lists missing server settings, add them first.
2. Press **Connect Pinterest** or **Connect Instagram**, approve on the platform, and you
   are returned to the CMS. The card then shows the account name.
3. **Disconnect** removes the stored tokens. Scheduled posts for that account fail until it
   is connected again.

## Publishing

Admin › Social publishing: choose the platform and image, optionally the related article or
quote collection, fill in the text, then **publish now** or **schedule**.

- **Pinterest**: title, description, optional alt text, board, destination link. When a
  related article or quote collection is chosen the Pin always links to its canonical page
  (for example `/quotes/<slug>`); otherwise the link must be an https page on this website,
  never an image file or admin page.
- **Instagram**: single-image feed posts only (JPEG, between 4:5 and 1.91:1). Captions may
  contain hashtags; links in captions are not clickable, so there is no destination field.
- The Media Library image dialog and the image block in the article / Quotes editor have
  **Send to Pinterest**, **Publish to Instagram**, **Schedule social post** and
  **View social posts** links that open the composer with the image (and the collection)
  already selected. The public "Save to Pinterest" button on quote pages is unrelated.
- Scheduled posts are sent by the existing `flask content publish-due` timer, which also
  renews tokens. No new service or timer is needed.

### Failures and duplicates

- Rate limits and platform outages are retried automatically with a growing delay.
- If a request may have reached the platform (timeout, server error), the post moves to
  "Checking": the board or account is searched for it before anything is sent again.
- A definite refusal ends in "Failed" with the reason; **Retry** is available after the
  cause is fixed. An expired authorisation marks the account "Reconnect needed".
- The same image cannot be queued twice for the same account (and board), and publishing an
  image that was already published asks for confirmation.
- Connections, posts, failures, retries, cancellations and imports are in the audit log.
  Tokens and secrets are never logged or returned to the browser.

## Importing from Instagram

Admin › Integrations › Import images from Instagram lists the connected account's own
posts. Single images can be previewed and imported after confirming ownership and adding alt
text. The file is copied into the Media Library (caption kept, credit "@account on
Instagram", source = the post's permalink) and pages serve the copy. Each Instagram post can
be imported once. Downloads are limited to https addresses on Instagram's own CDN hosts.

## Real-account checks before relying on it

1. Claim the website in Pinterest and confirm it shows as verified.
2. Connect Pinterest; confirm boards load; publish one Pin; confirm its link opens the
   canonical page; schedule one Pin and confirm it goes out.
3. Connect Instagram as `thinkpositivealways.com1`; confirm the card shows the username
   and "Does not expire"; list posts; import one image; publish one feed post; schedule one
   and confirm the timer sends it.
4. Leave both connected for a few days and confirm no "Reconnect needed" appears.
