"""Instagram API with Instagram Login (professional accounts; not the retired Basic Display API).

Documented endpoints used (https://developers.facebook.com/docs/instagram-platform/):
- GET  https://www.instagram.com/oauth/authorize       consent (client_id, redirect_uri,
                                                         response_type=code, scope, state)
- POST https://api.instagram.com/oauth/access_token    code -> short-lived token (1 hour)
- GET  graph.instagram.com/access_token                 -> long-lived token (60 days)
       (grant_type=ig_exchange_token)
- GET  graph.instagram.com/refresh_access_token         renew a long-lived token
       (grant_type=ig_refresh_token; token at least 24 hours old and not expired)
- GET  /me?fields=user_id,username,account_type         connected account
- GET  /me/media?fields=...                             the account's own media
- GET  /<media id>?fields=...                           one of the account's media
- POST /<IG_ID>/media (image_url, caption)              image container
- GET  /<container id>?fields=status_code               FINISHED / IN_PROGRESS / ERROR / ...
- POST /<IG_ID>/media_publish (creation_id)              publish the container
- GET  /<IG_ID>/content_publishing_limit                24-hour publishing quota

Scopes: instagram_business_basic (profile and media) and instagram_business_content_publish
(publishing). Only single-image feed posts are supported (JPEG, from a public URL).
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from flask import current_app

from . import http

AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
SCOPES = ("instagram_business_basic", "instagram_business_content_publish")
MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,username"


def _version() -> str:
    return current_app.config.get("INSTAGRAM_GRAPH_VERSION") or "v27.0"


def _message(res: http.Response) -> str | None:
    body = res.json()
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("error_user_msg") or error.get("message")
    else:
        message = body.get("error_message") or error
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
    query = {**(params or {}), "access_token": token}
    url = f"{GRAPH}/{_version()}{path}"
    if method == "GET":
        res = http.send("GET", url, params=query)
    else:
        res = http.send(method, url, params={"access_token": token}, form=form or {})
    code = _error_code(res)
    if res.status == 400 and code == 190:  # OAuthException: invalid or expired token
        raise http.SocialError(
            "The Instagram connection has expired or was revoked. Reconnect the account.",
            status=400,
            reconnect=True,
        )
    if res.status in (400, 403) and code in (10, 200, 3):  # permission / capability errors
        raise http.SocialError(
            "Instagram refused this request: the app is missing a permission or the account "
            f"is not eligible ({_message(res) or 'permission error'}).",
            status=res.status,
            permission=True,
        )
    if code in (4, 17, 32, 613) or (code == 9 and res.status == 400):  # rate limits
        raise http.SocialError(
            "Instagram's rate limit was reached; it will be retried later.",
            status=res.status,
            transient=True,
            retry_after=3600,
        )
    http.check(res, _message(res), creating=creating)
    return res.json()


def authorize_url(state: str, redirect_uri: str) -> str:
    query = {
        "client_id": current_app.config["INSTAGRAM_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(query)}"


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """Code -> long-lived token. Returns access_token, user_id, permissions, expires_in."""
    res = http.send(
        "POST",
        TOKEN_URL,
        form={
            "client_id": current_app.config["INSTAGRAM_CLIENT_ID"],
            "client_secret": current_app.config["INSTAGRAM_CLIENT_SECRET"],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if res.status == 400:
        raise http.SocialError(
            "Instagram refused the authorisation (expired or already-used code, or the app "
            "credentials / redirect URI do not match).",
            status=400,
            reconnect=True,
        )
    http.check(res, _message(res))
    body = res.json()
    if isinstance(body.get("data"), list) and body["data"]:
        body = body["data"][0]
    short = body.get("access_token")
    if not short:
        raise http.SocialError("Instagram did not return an access token.")
    permissions = body.get("permissions") or []
    if isinstance(permissions, str):
        permissions = [p.strip() for p in permissions.split(",") if p.strip()]
    long_res = http.send(
        "GET",
        f"{GRAPH}/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": current_app.config["INSTAGRAM_CLIENT_SECRET"],
            "access_token": short,
        },
    )
    http.check(long_res, _message(long_res))
    long_body = long_res.json()
    if not long_body.get("access_token"):
        raise http.SocialError("Instagram did not return a long-lived token.")
    return {
        "access_token": long_body["access_token"],
        "expires_in": long_body.get("expires_in"),
        "user_id": str(body.get("user_id") or ""),
        "permissions": [str(p) for p in permissions],
    }


def refresh(token: str) -> dict[str, Any]:
    res = http.send(
        "GET",
        f"{GRAPH}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
    )
    if res.status == 400 and _error_code(res) == 190:
        raise http.SocialError(
            "The Instagram connection has expired. Reconnect the account.",
            status=400,
            reconnect=True,
        )
    http.check(res, _message(res))
    body = res.json()
    if not body.get("access_token"):
        raise http.SocialError("Instagram did not return a refreshed token.")
    return body


def me(token: str) -> dict[str, Any]:
    return _call(
        "GET",
        "/me",
        token,
        params={"fields": "user_id,username,account_type,profile_picture_url"},
    )


def media(token: str, after: str | None = None, limit: int = 24) -> dict[str, Any]:
    params: dict[str, Any] = {"fields": MEDIA_FIELDS, "limit": limit}
    if after:
        params["after"] = after
    body = _call("GET", "/me/media", token, params=params)
    cursors = (body.get("paging") or {}).get("cursors") or {}
    has_next = bool((body.get("paging") or {}).get("next"))
    return {
        "items": [m for m in body.get("data") or [] if isinstance(m, dict)],
        "after": cursors.get("after") if has_next else None,
    }


def media_item(token: str, media_id: str) -> dict[str, Any]:
    return _call(
        "GET", f"/{urllib.parse.quote(media_id, safe='')}", token, params={"fields": MEDIA_FIELDS}
    )


def create_container(ig_id: str, token: str, image_url: str, caption: str) -> str:
    body = _call(
        "POST",
        f"/{urllib.parse.quote(ig_id, safe='')}/media",
        token,
        form={"image_url": image_url, "caption": caption},
    )
    if not body.get("id"):
        raise http.SocialError("Instagram did not return a media container id.")
    return str(body["id"])


def container_status(container_id: str, token: str) -> str:
    body = _call(
        "GET",
        f"/{urllib.parse.quote(container_id, safe='')}",
        token,
        params={"fields": "status_code"},
    )
    return str(body.get("status_code") or "")


def publish_container(ig_id: str, token: str, container_id: str) -> str:
    body = _call(
        "POST",
        f"/{urllib.parse.quote(ig_id, safe='')}/media_publish",
        token,
        form={"creation_id": container_id},
        creating=True,
    )
    if not body.get("id"):
        raise http.SocialError("Instagram did not return the new post's id.", uncertain=True)
    return str(body["id"])


def permalink(media_id: str, token: str) -> str | None:
    try:
        body = _call(
            "GET",
            f"/{urllib.parse.quote(media_id, safe='')}",
            token,
            params={"fields": "permalink"},
        )
    except http.SocialError:
        return None
    link = body.get("permalink")
    return str(link) if isinstance(link, str) and link.startswith("https://") else None


def publishing_quota(ig_id: str, token: str) -> tuple[int, int] | None:
    """(used, total) for the last 24 hours, or None when the platform does not say."""
    try:
        body = _call(
            "GET",
            f"/{urllib.parse.quote(ig_id, safe='')}/content_publishing_limit",
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
