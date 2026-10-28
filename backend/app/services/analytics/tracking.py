"""Page-view ingestion (``POST /api/v1/analytics/collect``).

Privacy and data minimisation:
- cookieless: the browser sends no identifier; nothing is stored in the browser;
- never stored: IP address, user agent, query string (except allow-listed UTM values),
  fragment, account or session ids;
- the visitor hash is SHA-256 of (truncated IP, user agent, random daily salt), cut to
  16 hex characters. The salt is replaced every day and the old one deleted, so hashes
  can't be reversed or linked across days: unique visitors are estimated per day only;
- private, transactional and token-bearing routes are never recorded;
- ``DNT: 1`` / ``Sec-GPC: 1`` are honoured (``ANALYTICS_RESPECT_DNT``).

Exclusions: bots and automation (user agent), admin and API paths, prerendering
(headless browsers), cross-site requests, repeated hits of the same page by the same
visitor within ``DUPLICATE_WINDOW``.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlparse

from flask import current_app, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import AnalyticsPageView, AnalyticsSalt, Article, Topic

MAX_BODY = 2048
DUPLICATE_WINDOW = timedelta(seconds=30)
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
_UTM_VALUE = re.compile(r"[^a-z0-9._+\- ]")
# Routes that are private, transactional or may carry tokens: never recorded.
EXCLUDED_PREFIXES = (
    "/admin",
    "/api",
    "/account",
    "/checkout",
    "/cart",
    "/purchases",
    "/learn",
    "/certificates",
    "/login",
    "/register",
    "/verify-email",
    "/forgot-password",
    "/reset-password",
    "/newsletter/confirm",
    "/newsletter/preferences",
    "/newsletter/unsubscribe",
    "/resources/access",
)
_BOT = re.compile(
    r"bot|crawl|spider|slurp|scrap|headless|phantom|puppeteer|playwright|selenium|"
    r"lighthouse|pagespeed|gtmetrix|pingdom|uptime|monitor|preview|fetch|curl|wget|"
    r"python|java/|go-http|axios|node-fetch|okhttp|facebookexternalhit|embedly|"
    r"whatsapp|telegrambot|discordbot|slackbot|bingpreview|prerender",
    re.I,
)
_HEX_TOKEN = re.compile(r"^[0-9a-fA-F]{32,}$")
_OPAQUE_TOKEN = re.compile(r"^(?=.*[A-Z])(?=.*[0-9])[A-Za-z0-9_\-]{20,}$")
SEARCH_HOSTS = (
    "google.",
    "bing.com",
    "duckduckgo.com",
    "search.yahoo.",
    "yandex.",
    "baidu.com",
    "ecosia.org",
    "search.brave.com",
    "startpage.com",
)
SOCIAL_HOSTS = (
    "facebook.com",
    "fb.me",
    "instagram.com",
    "t.co",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "lnkd.in",
    "pinterest.",
    "reddit.com",
    "youtube.com",
    "tiktok.com",
    "threads.net",
    "whatsapp.com",
)
EMAIL_HOSTS = ("mail.google.com", "outlook.live.com", "outlook.office.com", "mail.yahoo.com")
_salt_cache: dict[date, str] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def enabled() -> bool:
    return current_app.config.get("ANALYTICS_TRACKING", "enabled") == "enabled"


# ---- normalisation --------------------------------------------------------------------


def normalise_path(raw: Any) -> str | None:
    """A recordable path, or None. Query strings and fragments are always dropped."""
    if not isinstance(raw, str) or not raw.startswith("/") or len(raw) > 600:
        return None
    path = raw.split("?", 1)[0].split("#", 1)[0]
    if any(ord(c) < 33 for c in path) or "@" in path or "\\" in path:
        return None
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1:
        path = path.rstrip("/")
    if len(path) > 300:
        return None
    lowered = path.lower()
    if any(lowered == p or lowered.startswith(p + "/") for p in EXCLUDED_PREFIXES):
        return None
    if any(_HEX_TOKEN.match(seg) or _OPAQUE_TOKEN.match(seg) for seg in path.split("/")):
        return None  # looks like a token or opaque id (slugs are lowercase words)
    return path


def classify_path(path: str) -> tuple[str, str | None]:
    """(page_type, slug of the content it shows)."""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "home", None
    head = parts[0]
    if head == "articles":
        return ("article", parts[1]) if len(parts) == 2 else ("article_index", None)
    if head == "topics" and len(parts) == 2:
        return "topic", parts[1]
    if head == "shop":
        return ("product", parts[1]) if len(parts) == 2 else ("shop", None)
    if head == "courses":
        return "course", parts[1] if len(parts) == 2 else None
    if head == "membership":
        return "membership", None
    if head in ("resources", "free-resources"):
        return "resource", None
    return "page", None


def _utm(query: Any) -> dict[str, str]:
    out = {k: "" for k in UTM_KEYS}
    if not isinstance(query, str) or not query:
        return out
    for key, value in parse_qsl(query.lstrip("?")[:1000], keep_blank_values=False):
        if key in out and not out[key]:
            clean = _UTM_VALUE.sub("", value.strip().lower())[:100].strip()
            if "@" not in value:  # never store something that looks like an email
                out[key] = clean
    return out


def _host(url: Any) -> str:
    if not isinstance(url, str) or not url:
        return ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _site_hosts() -> set[str]:
    hosts = {_host(current_app.config.get("SITE_URL", "")), _host(request.host_url)}
    return {h for h in hosts if h}


def _host_matches(host: str, pattern: str) -> bool:
    """``google.`` matches any Google country domain; ``x.com`` matches it and subdomains."""
    if pattern.endswith("."):
        return host.startswith(pattern) or f".{pattern}" in f".{host}"
    return host == pattern or host.endswith("." + pattern)


def classify_source(referrer_host: str, utm: dict[str, str], spa: bool) -> str:
    if utm["utm_source"] or utm["utm_campaign"]:
        return "campaign"
    if spa or (referrer_host and referrer_host in _site_hosts()):
        return "internal"
    if not referrer_host:
        return "direct"

    def matches(hosts):
        return any(_host_matches(referrer_host, h) for h in hosts)

    if referrer_host in EMAIL_HOSTS:
        return "email"
    if matches(SEARCH_HOSTS):
        return "search"
    if matches(SOCIAL_HOSTS):
        return "social"
    return "referral"


# ---- visitor estimate -----------------------------------------------------------------


def _salt(day: date) -> str:
    cached = _salt_cache.get(day)
    if cached:
        return cached
    row = db.session.get(AnalyticsSalt, day)
    if row is None:
        row = AnalyticsSalt(day=day, salt=secrets.token_hex(32))
        try:
            with db.session.begin_nested():
                db.session.add(row)
                db.session.flush()
        except IntegrityError:  # another worker created it
            row = db.session.get(AnalyticsSalt, day)
    _salt_cache.clear()
    _salt_cache[day] = row.salt
    return row.salt


def _ip_prefix(remote: str | None) -> str:
    """Truncated network (IPv4 /24, IPv6 /48); the full address is never used or kept."""
    try:
        ip = ipaddress.ip_address(remote or "")
    except ValueError:
        return ""
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False).network_address)


def visitor_hash(day: date, user_agent: str) -> str:
    material = f"{_salt(day)}|{_ip_prefix(request.remote_addr)}|{user_agent[:300]}"
    return hashlib.sha256(material.encode()).hexdigest()[:16]


# ---- ingestion ------------------------------------------------------------------------


def _ignored(reason: str) -> dict[str, Any]:
    return {"recorded": False, "reason": reason}


def _request_problem() -> str | None:
    headers = request.headers
    ua = headers.get("User-Agent", "")
    if not ua or _BOT.search(ua):
        return "bot"
    if current_app.config.get("ANALYTICS_RESPECT_DNT", True) and (
        headers.get("DNT") == "1" or headers.get("Sec-GPC") == "1"
    ):
        return "do_not_track"
    if headers.get("Sec-Fetch-Site") in ("cross-site",):
        return "cross_site"
    origin = headers.get("Origin")
    if origin:
        allowed = {_host(o) for o in current_app.config.get("CORS_ORIGINS", [])} | _site_hosts()
        if _host(origin) not in allowed:
            return "cross_site"
    if headers.get("Purpose") == "prefetch" or headers.get("Sec-Purpose", "").startswith(
        "prefetch"
    ):
        return "prefetch"
    return None


def _content(page_type: str, slug: str | None) -> tuple[str, int | None]:
    if not slug:
        return "", None
    if page_type == "article":
        found = db.session.scalar(
            select(Article.id).where(Article.slug == slug, Article.status == "published")
        )
        return ("article", found) if found else ("", None)
    if page_type == "topic":
        found = db.session.scalar(select(Topic.id).where(Topic.slug == slug))
        return ("topic", found) if found else ("", None)
    return "", None


def collect(raw_body: bytes) -> dict[str, Any]:
    """Record one page view if it qualifies. Never raises for bad input (the endpoint
    always answers 204 so it can't be used to probe)."""
    if not enabled():
        return _ignored("disabled")
    if len(raw_body) > MAX_BODY:
        return _ignored("too_large")
    problem = _request_problem()
    if problem:
        return _ignored(problem)
    try:
        data = json.loads(raw_body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return _ignored("malformed")
    if not isinstance(data, dict):
        return _ignored("malformed")
    path = normalise_path(data.get("path"))
    if path is None:
        return _ignored("path")
    page_type, slug = classify_path(path)
    spa = data.get("spa") is True
    utm = _utm(data.get("search"))
    referrer_host = "" if spa else _host(data.get("referrer"))
    now = _now()
    day = now.date()
    vhash = visitor_hash(day, request.headers.get("User-Agent", ""))
    recent = db.session.scalar(
        select(AnalyticsPageView.id).where(
            AnalyticsPageView.visitor_hash == vhash,
            AnalyticsPageView.occurred_at >= now - DUPLICATE_WINDOW,
            AnalyticsPageView.path == path,
        )
    )
    if recent:
        return _ignored("duplicate")
    content_type, content_id = _content(page_type, slug)
    db.session.add(
        AnalyticsPageView(
            occurred_at=now,
            day=day,
            path=path,
            page_type=page_type,
            content_type=content_type,
            content_id=content_id,
            source=classify_source(referrer_host, utm, spa),
            referrer_host=referrer_host[:255],
            visitor_hash=vhash,
            **utm,
        )
    )
    return {"recorded": True}
