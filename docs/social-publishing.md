# Social publishing: Pinterest and Instagram

Admin › Integrations connects the site's own Pinterest and Instagram accounts.
Admin › Social publishing sends Media Library images to them, now or on a schedule.
Nothing is posted automatically: publishing an article or a quote collection on TPA never
creates a Pin or an Instagram post. Every post is created by a person with the
"Publish to Pinterest and Instagram" permission.

Automated tests replace every platform call with a fake. **Publishing, importing and
connecting have not been exercised against the live Pinterest or Instagram APIs.** Treat
each as unconfirmed until the real-account checks at the end of this page pass.

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
| `INSTAGRAM_CLIENT_ID`         | Instagram app id (from the Meta app's "Instagram" product, not the Meta app id) |
| `INSTAGRAM_CLIENT_SECRET`     | Instagram app secret                                                    |
| `INSTAGRAM_REDIRECT_URI`      | Optional. Default `{ADMIN_BASE_URL}/admin/integrations/instagram/callback` |
| `INSTAGRAM_GRAPH_VERSION`     | Optional. Default `v27.0`                                               |
| `SOCIAL_HTTP_TIMEOUT`         | Optional. Seconds, default 20                                           |
| `SOCIAL_IMPORT_MAX_BYTES`     | Optional. Largest Instagram image imported, default 15 MB               |

Generate the key once:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Losing or changing the key without keeping the old one in the list makes stored tokens
unreadable; the accounts then show "Reconnect needed". Until the settings exist, Integrations
shows which names are missing and the rest of the CMS works normally.

The release also needs `pip install -r requirements.txt` (adds `cryptography`) and
`flask db upgrade` (migration `f2b6d8e0a314`).

## Pinterest developer setup

1. The Pinterest account must be a **business** account (apps registered after
   14 September 2026 are refused for personal accounts).
2. At developers.pinterest.com create an app and request access. New apps get **Trial
   access**; request **Standard access** before relying on it. With Trial access, set
   `PINTEREST_API_BASE` to the sandbox address, or Pins created are only visible to the
   account itself.
3. Add the redirect address shown on the Integrations page, exactly.
4. Scopes requested: `user_accounts:read`, `boards:read`, `pins:read`, `pins:write`.
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

## Meta (Instagram) developer setup

1. The Instagram account must be a **professional** (Business or Creator) account. A
   Facebook Page is not required for Instagram Login.
2. At developers.facebook.com create a Business-type app, add the **Instagram** product and
   choose **API setup with Instagram login**.
3. Under Business login settings add the redirect address shown on the Integrations page.
4. Permissions: `instagram_business_basic` and `instagram_business_content_publish`.
5. While the app is in Development mode, only Instagram accounts added as testers
   (App roles › Instagram testers, then accepted in the Instagram app) can connect. For any
   other account both permissions need **App Review** with Advanced Access, and the app
   must be Live with business verification.
6. Put the Instagram app id and secret in the server settings.

Tokens: the 60-day long-lived token is renewed automatically while the account stays
connected.

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
3. Connect Instagram; import one image; publish one feed post; schedule one.
4. Leave both connected for a few days and confirm no "Reconnect needed" appears.
