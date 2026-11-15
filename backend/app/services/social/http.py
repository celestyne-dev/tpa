"""Outbound HTTP for the Pinterest and Instagram clients.

Everything goes through :func:`send` (tests replace it with a fake; CI never calls a real
platform). Redirects are never followed, responses are size-limited, and errors carry a
short, sanitised message: no URL (Instagram puts the token in the query string), no request
body and no token is ever put in an exception, a log line or an API response.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from flask import current_app

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # API responses (JSON)


class SocialError(Exception):
    """A failed platform call.

    - ``transient``: worth retrying later (rate limit, platform outage, network).
    - ``uncertain``: the request may have been carried out (timeout or 5xx on a create call);
      check the platform before sending it again.
    - ``reconnect``: the authorisation is invalid or expired; an administrator must reconnect.
    - ``permission``: the app or account lacks a permission / feature (setup or app review).
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        transient: bool = False,
        uncertain: bool = False,
        reconnect: bool = False,
        permission: bool = False,
        retry_after: int | None = None,
        code: str | None = None,
    ):
        super().__init__(message)
        self.message = message[:300]
        self.status = status
        self.transient = transient
        self.uncertain = uncertain
        self.reconnect = reconnect
        self.permission = permission
        self.retry_after = retry_after
        self.code = code


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        try:
            data = json.loads(self.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {"data": data}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None  # a 3xx is returned as-is and treated as an error


_OPENER = urllib.request.build_opener(_NoRedirect)


def _timeout() -> int:
    return int(current_app.config.get("SOCIAL_HTTP_TIMEOUT", 20))


def send(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> Response:
    """Make one request. Raises :class:`SocialError` for network failures only; HTTP error
    statuses are returned (see :func:`check`)."""
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
    data = None
    hdrs = {"Accept": "application/json", "User-Agent": "ThinkPositiveAlways-CMS/1.0"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    request = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with _OPENER.open(request, timeout=_timeout()) as res:  # noqa: S310 (https only)
            body = res.read(max_bytes + 1)
            status, res_headers = res.status, dict(res.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_RESPONSE_BYTES) if exc.fp else b""
        status, res_headers = exc.code, dict(exc.headers.items()) if exc.headers else {}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        host = urllib.parse.urlparse(url).hostname
        logger.warning("social http %s %s failed: %s", method, host, type(exc).__name__)
        raise SocialError(
            "The platform could not be reached (network error or timeout).",
            transient=True,
            uncertain=method != "GET",
        ) from None
    if len(body) > max_bytes:
        raise SocialError("The platform's response was too large.", status=status)
    return Response(status=status, body=body, headers=res_headers)


def _retry_after(headers: dict[str, str]) -> int | None:
    for name, value in headers.items():
        if name.lower() == "retry-after":
            try:
                return max(1, min(86400, int(value)))
            except ValueError:
                return None
    return None


def check(res: Response, platform_message: str | None, *, creating: bool = False) -> None:
    """Raise a classified :class:`SocialError` for a non-2xx response."""
    if 200 <= res.status < 300:
        return
    detail = (platform_message or "").strip()[:200]
    suffix = f" ({detail})" if detail else ""
    if res.status in (401,):
        raise SocialError(
            "The connection has expired or was revoked. Reconnect the account." + suffix,
            status=401,
            reconnect=True,
        )
    if res.status == 403:
        raise SocialError(
            "The platform refused this request: the app or account is missing a permission "
            "or feature (see Admin › Integrations for setup)." + suffix,
            status=403,
            permission=True,
        )
    if res.status == 429:
        raise SocialError(
            "The platform's rate limit was reached; it will be retried later." + suffix,
            status=429,
            transient=True,
            retry_after=_retry_after(res.headers) or 900,
        )
    if res.status >= 500:
        raise SocialError(
            "The platform had a temporary problem." + suffix,
            status=res.status,
            transient=True,
            uncertain=creating,
        )
    if 300 <= res.status < 400:
        raise SocialError("The platform returned an unexpected redirect.", status=res.status)
    raise SocialError(
        ("The platform rejected the request" + suffix) if detail else "The request was rejected.",
        status=res.status,
    )


# ---- downloading images from Instagram (SSRF protection) ----------------------------------

# Instagram serves media from Meta's CDNs. Anything else is refused.
MEDIA_HOST_SUFFIXES = (".cdninstagram.com", ".fbcdn.net")
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def media_url_problem(url: str) -> str | None:
    """Why a media URL may not be fetched, or None when it is acceptable."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return "The media address is invalid."
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return "Only https media addresses are accepted."
    if parsed.port not in (None, 443):
        return "The media address uses an unexpected port."
    if not any(host.endswith(suffix) for suffix in MEDIA_HOST_SUFFIXES):
        return "The media is not hosted by Instagram."
    return None


def _resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]


def _public_host(host: str) -> bool:
    try:
        addresses = _resolve(host)
    except OSError:
        return False
    if not addresses:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global or ip.is_multicast:
            return False
    return True


def download_image(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Fetch an Instagram image (https, Meta CDN host, public address, no redirects, size
    and content type checked). Returns (bytes, content type)."""
    if problem := media_url_problem(url):
        raise SocialError(problem)
    host = urllib.parse.urlparse(url).hostname or ""
    if not _public_host(host):
        raise SocialError("The media host did not resolve to a public address.")
    res = send("GET", url, headers={"Accept": "image/*"}, max_bytes=max_bytes)
    if res.status != 200:
        check(res, None)
        raise SocialError("The image could not be downloaded.", status=res.status)
    content_type = ""
    for name, value in res.headers.items():
        if name.lower() == "content-type":
            content_type = value.split(";", 1)[0].strip().lower()
    if content_type not in IMAGE_TYPES:
        raise SocialError("The file is not a JPEG, PNG or WebP image.")
    if not res.body:
        raise SocialError("The image was empty.")
    return res.body, content_type
