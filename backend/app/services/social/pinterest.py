"""Pinterest API v5 client (OAuth 2.0 authorization-code flow, boards, image Pins).

Documented endpoints used (https://developers.pinterest.com/docs/api/v5/):
- GET  https://www.pinterest.com/oauth/          user consent (client_id, redirect_uri,
                                                 response_type=code, scope, state)
- POST /v5/oauth/token                            code -> access + refresh token (HTTP Basic
                                                 client_id:client_secret); also refresh_token
- GET  /v5/user_account                           connected account
- GET  /v5/boards                                 boards (bookmark pagination)
- POST /v5/pins                                   create an image Pin from a public image URL
- GET  /v5/boards/{board_id}/pins                 recent Pins (duplicate check after a timeout)

Scopes requested: user_accounts:read, boards:read, boards:write, pins:read, pins:write.
An account connected before boards:write was added keeps working; it shows the missing
permission until it is reconnected.
"""

from __future__ import annotations

import base64
import urllib.parse
from typing import Any

from flask import current_app

from . import http

AUTHORIZE_URL = "https://www.pinterest.com/oauth/"
SCOPES = ("user_accounts:read", "boards:read", "boards:write", "pins:read", "pins:write")


def _base() -> str:
    return current_app.config.get("PINTEREST_API_BASE", "https://api.pinterest.com").rstrip("/")


def _message(res: http.Response) -> str | None:
    body = res.json()
    message = body.get("message") or body.get("error_description") or body.get("error")
    return str(message) if message else None


def _call(method: str, path: str, token: str, *, creating: bool = False, **kw) -> dict:
    res = http.send(method, f"{_base()}{path}", headers={"Authorization": f"Bearer {token}"}, **kw)
    http.check(res, _message(res), creating=creating)
    return res.json()


def authorize_url(state: str, redirect_uri: str) -> str:
    query = {
        "client_id": current_app.config["PINTEREST_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(query)}"


def _token_request(form: dict[str, str]) -> dict[str, Any]:
    cfg = current_app.config
    creds = f"{cfg['PINTEREST_CLIENT_ID']}:{cfg['PINTEREST_CLIENT_SECRET']}"
    res = http.send(
        "POST",
        f"{_base()}/v5/oauth/token",
        form=form,
        headers={"Authorization": "Basic " + base64.b64encode(creds.encode()).decode()},
    )
    if res.status in (400, 401):
        raise http.SocialError(
            "Pinterest refused the authorisation (expired or already-used code, or the app "
            "credentials / redirect URI do not match).",
            status=res.status,
            reconnect=True,
        )
    http.check(res, _message(res))
    body = res.json()
    if not body.get("access_token"):
        raise http.SocialError("Pinterest did not return an access token.")
    return body


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            # Older apps get a refresh token that is renewed on every refresh only when asked.
            "continuous_refresh": "true",
        }
    )


def refresh(refresh_token: str) -> dict[str, Any]:
    return _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})


def user_account(token: str) -> dict[str, Any]:
    return _call("GET", "/v5/user_account", token)


def boards(token: str, max_pages: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    bookmark = None
    for _ in range(max_pages):
        params: dict[str, Any] = {"page_size": 100}
        if bookmark:
            params["bookmark"] = bookmark
        body = _call("GET", "/v5/boards", token, params=params)
        for board in body.get("items") or []:
            if isinstance(board, dict) and board.get("id"):
                out.append(
                    {
                        "id": str(board["id"]),
                        "name": str(board.get("name") or "")[:200],
                        "privacy": board.get("privacy"),
                    }
                )
        bookmark = body.get("bookmark")
        if not bookmark:
            break
    return out


def create_pin(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = _call("POST", "/v5/pins", token, json_body=payload, creating=True)
    if not body.get("id"):
        raise http.SocialError("Pinterest did not return the new Pin's id.", uncertain=True)
    return body


def board_pins(token: str, board_id: str) -> list[dict[str, Any]]:
    path = f"/v5/boards/{urllib.parse.quote(board_id, safe='')}/pins"
    body = _call("GET", path, token, params={"page_size": 50})
    return [p for p in body.get("items") or [] if isinstance(p, dict)]


def pin_url(pin_id: str) -> str:
    return f"https://www.pinterest.com/pin/{urllib.parse.quote(str(pin_id), safe='')}/"
