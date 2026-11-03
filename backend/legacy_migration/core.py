"""URL normalisation, path classification and CSV helpers shared by every step."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

ACTIONS = ("KEEP", "REDIRECT_301", "RETIRE_410", "REVIEW")
GONE_STATUSES = (404, 410)

# The only legacy paths that may redirect to the homepage (no blanket "/" redirects).
HOME_ALIASES = frozenset({"/", "/home", "/index.html", "/index.htm", "/index.php"})

MEDIA_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp",
    ".pdf", ".mp4", ".webm", ".mp3",
)  # fmt: skip
ASSET_EXTENSIONS = (".js", ".css", ".map", ".woff", ".woff2", ".ttf", ".json", ".txt")
FEED_PATHS = ("/rss.xml", "/feed", "/rss", "/atom.xml")
# Never crawled or mapped as public content (accounts, admin, APIs, carts...).
SYSTEM_SEGMENTS = frozenset(
    {
        "admin", "api", "login", "logout", "signin", "sign-in", "signup", "register",
        "account", "accounts", "auth", "oauth", "cart", "checkout", "orders",
        "wp-admin", "wp-login.php", "wp-json", "xmlrpc.php", "cdn-cgi", "preview",
        "forums/new-topic",
    }
)  # fmt: skip
ARTICLE_PATTERNS = (
    re.compile(r"^/articles?/[^/]+$"),  # /articles/<slug>, /article/<id>
    re.compile(r"^/(?:19|20)\d\d/\d\d(?:/\d\d)?/[^/]+$"),  # /2024/05/<slug>
    re.compile(r"^/(?:blog|posts?)/[^/]+$"),
)
CATEGORY_PATTERNS = (re.compile(r"^/(?:category|categories|topics?|tag|tags|section)/[^/]+$"),)


def clean_url(url: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL without fragment, default port or empty query."""
    if not url:
        return None
    url = url.strip()
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if parts.port and not (
        (parts.scheme == "http" and parts.port == 80)
        or (parts.scheme == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path or "/", parts.query, ""))


def path_of(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


def path_key(path: str) -> str:
    """Matching key for a path: no query or fragment, no trailing slash (except "/")."""
    path = (path or "/").split("#", 1)[0].split("?", 1)[0] or "/"
    if not path.startswith("/"):
        path = urlsplit(path).path or "/"
    return path.rstrip("/") or "/"


def bare_host(host: str) -> str:
    host = (host or "").lower().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, hosts: Iterable[str]) -> bool:
    """www and the apex domain count as one site."""
    host = bare_host(urlsplit(url).hostname or "")
    return bool(host) and host in {bare_host(h) for h in hosts}


def last_segment(path: str) -> str:
    return path_key(path).rsplit("/", 1)[-1]


def classify_path(path: str) -> str:
    """A first guess from the path alone; page evidence (og:type, JSON-LD) can refine it."""
    key = path_key(path)
    low = key.lower()
    if key == "/" or low in HOME_ALIASES:
        return "home"
    if low.endswith(MEDIA_EXTENSIONS):
        return "media"
    if low.endswith(ASSET_EXTENSIONS) or low.startswith(("/assets/", "/static/")):
        return "asset"
    if low in FEED_PATHS or low.endswith(("/feed", ".rss")):
        return "feed"
    if low.endswith(".xml"):
        return "sitemap"
    segments = low.strip("/").split("/")
    if segments[0] in SYSTEM_SEGMENTS or "/".join(segments[:2]) in SYSTEM_SEGMENTS:
        return "system"
    if segments[0] == "search":
        return "search"
    if any(p.match(key) for p in ARTICLE_PATTERNS):
        return "article"
    if any(p.match(key) for p in CATEGORY_PATTERNS):
        return "category"
    if segments[0] in ("forums", "forum"):
        return "forum"
    if segments[0] == "shop":
        return "shop"
    return "page"


# ---- CSV -------------------------------------------------------------------------------

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value) -> str:
    """Scraped titles are untrusted: never let a cell start a spreadsheet formula."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else ""
    text = str(value)
    if text.startswith(_FORMULA_START) and not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return "'" + text
    return text


def write_csv(path: str | Path, fields: Iterable[str], rows: Iterable[dict]) -> int:
    fields = list(fields)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(row.get(k)) for k in fields})
            count += 1
    return count


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [_strip_guard(row) for row in csv.DictReader(fh)]


def read_csv_text(text: str) -> list[dict[str, str]]:
    return [_strip_guard(row) for row in csv.DictReader(io.StringIO(text))]


def _strip_guard(row: dict) -> dict[str, str]:
    out = {}
    for key, value in row.items():
        if key is None:
            continue
        value = (value or "").strip()
        if value.startswith("'") and value[1:2] in _FORMULA_START:
            value = value[1:]
        out[key.strip().lower()] = value
    return out


def as_int(value, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "yes", "y", "true", "approved", "x"}


def chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
