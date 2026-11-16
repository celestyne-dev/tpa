"""Instagram API with Unified Login (Facebook Login for Business, ``config_id``).

Meta apps created now cannot use the older "API setup with Instagram login"
(www.instagram.com/oauth/authorize, graph.instagram.com). They sign in through a Facebook
Login for Business *configuration*; the permissions (``instagram_basic``,
``instagram_content_publish``) are part of that configuration, so no ``scope`` is sent.

Endpoints used, all on graph.facebook.com:
- GET  https://www.facebook.com/<v>/dialog/oauth     consent (client_id, config_id,
                                                      redirect_uri, response_type=code, state)
- GET  /oauth/access_token                            code -> access token
- GET  /debug_token                                   token type, expiry, granted permissions
- GET  /oauth/access_token (fb_exchange_token)        only for *user* tokens that expire
- GET  /me/assigned_instagram_accounts                the Instagram account(s) granted
- GET  /me/accounts?fields=instagram_business_account fallback: Page-linked account
- GET  /<IG_ID>?fields=id,username                    verify the account is readable
- GET  /<IG_ID>/media, /<media id>                    the account's own media
- POST /<IG_ID>/media, GET /<container>?fields=status_code, POST /<IG_ID>/media_publish
- GET  /<IG_ID>/content_publishing_limit

Token: a configuration of type "system-user access token" yields a Business Integration
System User token that does not expire (``expires_at`` 0); it is never refreshed. If the
configuration yields a user token instead, it is exchanged for a long-lived one and renewed
with ``fb_exchange_token`` before it expires. The retired graph.instagram.com refresh
endpoint is not used.

Nothing here logs or returns a code, secret or token; see ``http`` for error sanitising.
See docs/social-publishing.md for what could not be verified without a live authorisation.
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Any

from flask import current_app

from . import http

DIALOG = "https://www.facebook.com"
GRAPH = "https://graph.facebook.com"
# Granted through the Unified Login configuration (shown to administrators; not sent).
SCOPES = ("instagram_basic", "instagram_content_publish")
MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,username"
# A user token with less than this left is exchanged for a long-lived one at connection.
_SHORT_LIVED = 7 * 24 * 3600


def _version() -> str:
    return current_app.config.get("INSTAGRAM_GRAPH_VERSION") or "v27.0"


def _graph(path: str) -> str:
    return f"{GRAPH}/{_version()}{path}"


def _id(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _message(res: http.Response) -> str | None:
    body = res.json()
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("error_user_msg") or error.get("message")
    else:
        message = body.get("error_description") or body.get("error_message") or error
    return str(message) if message else None


def _error_code(res: http.Response) -> int | None:
    error = res.json().get("error")
    if isinstance(error, dict):
        try:
            return int(error.get("code"))
        except (TypeError, ValueError):
            return None
    return None


def _call(
    method: str,
    path: str,
    token: str,
    *,
    params: dict | None = None,
    form: dict | None = None,
    creating: bool = False,
) -> dict:
    if method == "GET":
        res = http.send("GET", _graph(path), params={**(params or {}), "access_token": token})
    else:
        res = http.send(method, _graph(path), params={"access_token": token}, form=form or {})
    code = _error_code(res)
    if code == 190 or res.status == 401:  # OAuthException: invalid, expired or revoked token
        raise http.SocialError(
            "The Instagram connection has expired or was revoked. Reconnect the account.",
            status=res.status,
            reconnect=True,
        )
    if res.status in (400, 403) and code in (3, 10, 200, 294):  # permission / capability
        raise http.SocialError(
            "Meta refused this request: the app is missing a permission or the Instagram "
            f"account is not eligible ({_message(res) or 'permission error'}).",
            status=res.status,
            permission=True,
        )
    if code in (4, 17, 32, 613, 80002) or (code == 9 and res.status == 400):  # rate limits
        raise http.SocialError(
            "Instagram's rate limit was reached; it will be retried later.",
            status=res.status,
            transient=True,
            retry_after=3600,
        )
    http.check(res, _message(res), creating=creating)
    return res.json()


# ---- OAuth --------------------------------------------------------------------------------


def authorize_url(state: str, redirect_uri: str) -> str:
    cfg = current_app.config
    query = {
        "client_id": cfg["INSTAGRAM_CLIENT_ID"],
        "config_id": cfg["INSTAGRAM_CONFIG_ID"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if cfg.get("INSTAGRAM_OVERRIDE_RESPONSE_TYPE"):
        query["override_default_response_type"] = "true"
    return f"{DIALOG}/{_version()}/dialog/oauth?{urllib.parse.urlencode(query)}"


def _app_token() -> str:
    cfg = current_app.config
    return f"{cfg['INSTAGRAM_CLIENT_ID']}|{cfg['INSTAGRAM_CLIENT_SECRET']}"


def _token_request(params: dict[str, str]) -> http.Response:
    cfg = current_app.config
    return http.send(
        "GET",
        _graph("/oauth/access_token"),
        params={
            "client_id": cfg["INSTAGRAM_CLIENT_ID"],
            "client_secret": cfg["INSTAGRAM_CLIENT_SECRET"],
            **params,
        },
    )


def _refused(res: http.Response) -> http.SocialError:
    detail = (_message(res) or "").strip()[:200]
    return http.SocialError(
        "Meta refused the authorisation (expired or already-used code, or the app id, app "
        "secret or redirect address do not match the Meta app)"
        + (f": {detail}" if detail else "."),
        status=res.status,
        reconnect=True,
    )


def inspect_token(token: str) -> dict[str, Any] | None:
    """What Meta says about a token (type, expiry, permissions), or None if it won't say."""
    try:
        res = http.send(
            "GET",
            _graph("/debug_token"),
            params={"input_token": token, "access_token": _app_token()},
        )
    except http.SocialError:
        return None
    data = res.json().get("data")
    if res.status != 200 or not isinstance(data, dict):
        return None
    return data


def _expires_in(info: dict[str, Any] | None, body: dict[str, Any]) -> int | None:
    """Seconds until the token expires; None when it does not expire."""
    if info is not None and "expires_at" in info:
        try:
            expires_at = int(info["expires_at"] or 0)
        except (TypeError, ValueError):
            expires_at = 0
        return max(1, expires_at - int(time.time())) if expires_at > 0 else None
    try:
        seconds = int(body.get("expires_in") or 0)
    except (TypeError, ValueError):
        seconds = 0
    return seconds if seconds > 0 else None


def _target_ids(info: dict[str, Any] | None) -> list[str]:
    """Instagram account ids named in the token's granular permissions."""
    out: list[str] = []
    for entry in (info or {}).get("granular_scopes") or []:
        if not isinstance(entry, dict) or not str(entry.get("scope") or "").startswith(
            "instagram_"
        ):
            continue
        for target in entry.get("target_ids") or []:
            if str(target).isdigit() and str(target) not in out:
                out.append(str(target))
    return out


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """Authorisation code -> token. Returns access_token, expires_in (None: never),
    kind (Meta's token type, lower case, or None), scopes (list, or None when unknown) and
    target_ids (Instagram account ids named by the grant)."""
    res = _token_request({"code": code, "redirect_uri": redirect_uri})
    if res.status == 400 and "redirect_uri" in (_message(res) or "").lower():
        # Business-integration exchanges are documented without redirect_uri; a failed
        # exchange does not consume the code.
        res = _token_request({"code": code})
    if res.status in (400, 401):
        raise _refused(res)
    http.check(res, _message(res))
    body = res.json()
    token = body.get("access_token")
    if not token:
        raise http.SocialError("Meta did not return an access token.")
    info = inspect_token(token)
    if info is not None:
        if info.get("is_valid") is False:
            raise http.SocialError("Meta reports the new token as invalid.", reconnect=True)
        app_id = str(info.get("app_id") or "")
        if app_id and app_id != str(current_app.config["INSTAGRAM_CLIENT_ID"]):
            raise http.SocialError("The token was issued for a different Meta app.")
    kind = str(info.get("type") or "").lower() or None if info else None
    expires_in = _expires_in(info, body)
    if kind == "user" and expires_in is not None and expires_in < _SHORT_LIVED:
        try:
            longer = extend(token)
        except http.SocialError:
            longer = None  # keep the short-lived token; the account will ask to reconnect
        if longer:
            token, expires_in = longer["access_token"], longer.get("expires_in")
    scopes = None
    if info is not None and isinstance(info.get("scopes"), list):
        scopes = [str(s) for s in info["scopes"]]
    return {
        "access_token": token,
        "expires_in": expires_in,
        "kind": kind,
        "scopes": scopes,
        "target_ids": _target_ids(info),
    }


def extend(token: str) -> dict[str, Any]:
    """Renew an expiring *user* token (about 60 days). Never used for system-user tokens."""
    res = _token_request({"grant_type": "fb_exchange_token", "fb_exchange_token": token})
    if _error_code(res) == 190 or res.status == 401:
        raise http.SocialError(
            "The Instagram connection has expired. Reconnect the account.",
            status=res.status,
            reconnect=True,
        )
    http.check(res, _message(res))
    body = res.json()
    if not body.get("access_token"):
        raise http.SocialError("Meta did not return a renewed token.")
    try:
        seconds = int(body.get("expires_in") or 0)
    except (TypeError, ValueError):
        seconds = 0
    return {"access_token": body["access_token"], "expires_in": seconds or None}


# ---- which Instagram account --------------------------------------------------------------


def _listed(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in body.get("data") or [] if isinstance(row, dict)]


def _candidates(token: str, target_ids: list[str]) -> list[str]:
    """Instagram account ids the token may act for, most authoritative source first."""
    ids: list[str] = []

    def add(value: Any) -> None:
        if value and str(value).isdigit() and str(value) not in ids:
            ids.append(str(value))

    try:
        body = _call(
            "GET", "/me/assigned_instagram_accounts", token, params={"fields": "id,username"}
        )
        for row in _listed(body):
            add(row.get("id"))
    except http.SocialError as exc:
        if exc.reconnect or exc.transient:
            raise
    for target in target_ids:
        add(target)
    if not ids:
        try:
            body = _call(
                "GET",
                "/me/accounts",
                token,
                params={"fields": "instagram_business_account{id,username}", "limit": 50},
            )
            for row in _listed(body):
                add((row.get("instagram_business_account") or {}).get("id"))
        except http.SocialError as exc:
            if exc.reconnect or exc.transient:
                raise
    return ids


def profile(ig_id: str, token: str) -> dict[str, Any]:
    """The Instagram professional account as the token sees it (id, username, name)."""
    return _call("GET", f"/{_id(ig_id)}", token, params={"fields": "id,username,name"})


def discover_account(
    token: str, target_ids: list[str] | None = None, prefer: list[str] | None = None
) -> dict[str, str]:
    """Find and verify the one Instagram account this connection is for.

    ``prefer``: ids or usernames to choose when several accounts were granted (the
    configured ``INSTAGRAM_ACCOUNT_ID``, then the account already connected). A configured
    numeric id is also tried directly when Meta lists nothing.
    """
    wanted = [str(p).strip().lstrip("@").lower() for p in (prefer or []) if str(p).strip()]
    ids = _candidates(token, target_ids or [])
    if not ids:
        ids = [w for w in wanted[:1] if w.isdigit()]
    readable: list[dict[str, str]] = []
    for ig_id in ids[:10]:
        try:
            row = profile(ig_id, token)
        except http.SocialError as exc:
            if exc.reconnect or exc.transient:
                raise
            continue  # listed but not readable with this token: not usable
        if str(row.get("id") or "") == ig_id:
            readable.append({"id": ig_id, "username": str(row.get("username") or "")})
    if not readable:
        raise http.SocialError(
            "Meta did not grant access to an Instagram professional account. In the Meta "
            "sign-in window choose the Instagram Business or Creator account, and while the "
            "app is in development make sure that account has accepted its tester "
            "invitation.",
            permission=True,
        )
    for want in wanted:
        for row in readable:
            if want in (row["id"], row["username"].lower()):
                return row
    if len(readable) == 1:
        return readable[0]
    names = ", ".join("@" + (r["username"] or r["id"]) for r in readable[:5])
    raise http.SocialError(
        f"Meta granted access to several Instagram accounts ({names}). Choose only one in "
        "the Meta sign-in window, or set INSTAGRAM_ACCOUNT_ID on the server."
    )


# ---- media --------------------------------------------------------------------------------


def media(ig_id: str, token: str, after: str | None = None, limit: int = 24) -> dict[str, Any]:
    params: dict[str, Any] = {"fields": MEDIA_FIELDS, "limit": limit}
    if after:
        params["after"] = after
    body = _call("GET", f"/{_id(ig_id)}/media", token, params=params)
    cursors = (body.get("paging") or {}).get("cursors") or {}
    has_next = bool((body.get("paging") or {}).get("next"))
    return {"items": _listed(body), "after": cursors.get("after") if has_next else None}


def media_item(token: str, media_id: str) -> dict[str, Any]:
    return _call("GET", f"/{_id(media_id)}", token, params={"fields": MEDIA_FIELDS})


# ---- publishing (single-image feed posts) -------------------------------------------------


def create_container(ig_id: str, token: str, image_url: str, caption: str) -> str:
    body = _call(
        "POST",
        f"/{_id(ig_id)}/media",
        token,
        form={"image_url": image_url, "caption": caption},
    )
    if not body.get("id"):
        raise http.SocialError("Instagram did not return a media container id.")
    return str(body["id"])


def container_status(container_id: str, token: str) -> str:
    body = _call("GET", f"/{_id(container_id)}", token, params={"fields": "status_code"})
    return str(body.get("status_code") or "")


def publish_container(ig_id: str, token: str, container_id: str) -> str:
    body = _call(
        "POST",
        f"/{_id(ig_id)}/media_publish",
        token,
        form={"creation_id": container_id},
        creating=True,
    )
    if not body.get("id"):
        raise http.SocialError("Instagram did not return the new post's id.", uncertain=True)
    return str(body["id"])


def permalink(media_id: str, token: str) -> str | None:
    try:
        body = _call("GET", f"/{_id(media_id)}", token, params={"fields": "permalink"})
    except http.SocialError:
        return None
    link = body.get("permalink")
    return str(link) if isinstance(link, str) and link.startswith("https://") else None


def publishing_quota(ig_id: str, token: str) -> tuple[int, int] | None:
    """(used, total) for the last 24 hours, or None when the platform does not say."""
    try:
        body = _call(
            "GET",
            f"/{_id(ig_id)}/content_publishing_limit",
            token,
            params={"fields": "quota_usage,config"},
        )
    except http.SocialError as exc:
        if exc.reconnect:
            raise
        return None
    rows = body.get("data") or []
    if not rows or not isinstance(rows[0], dict):
        return None
    try:
        used = int(rows[0].get("quota_usage") or 0)
        total = int((rows[0].get("config") or {}).get("quota_total") or 0)
    except (TypeError, ValueError):
        return None
    return (used, total) if total else None
