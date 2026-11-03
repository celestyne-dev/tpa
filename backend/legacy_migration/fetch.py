"""Read-only HTTP: GET only, redirects recorded hop by hop (never followed blindly), hosts
restricted, bodies capped. Also the HTML, sitemap and robots.txt parsers."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib import robotparser
from urllib.parse import urljoin
from xml.etree import ElementTree

from . import __version__
from .core import clean_url, same_site

USER_AGENT = f"TPA-legacy-inventory/{__version__} (read-only SEO migration check)"
MAX_BODY = 3 * 1024 * 1024
MAX_HOPS = 10
REDIRECT_CODES = (301, 302, 303, 307, 308)


@dataclass
class Hop:
    url: str
    status: int
    location: str = ""


@dataclass
class Response:
    url: str
    status: int  # first response's status (0 = network error)
    final_url: str = ""
    final_status: int = 0
    hops: list[Hop] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)  # of the final response
    body: bytes = b""
    error: str = ""
    elapsed_ms: int = 0

    @property
    def redirect_count(self) -> int:
        return sum(1 for h in self.hops if h.status in REDIRECT_CODES)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    def text(self) -> str:
        charset = "utf-8"
        match = re.search(r"charset=([\w-]+)", self.headers.get("content-type", ""), re.I)
        if match:
            charset = match.group(1)
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def chain_text(self) -> str:
        return " | ".join(f"{h.status} {h.url}" for h in self.hops)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None  # surface 3xx as HTTPError so every hop is recorded


class Fetcher:
    """GET-only client. ``hosts`` limits where requests (and followed redirects) may go."""

    def __init__(
        self,
        hosts: list[str],
        *,
        delay: float = 1.0,
        timeout: float = 20.0,
        user_agent: str = USER_AGENT,
        opener=None,
    ):
        self.hosts = list(hosts)
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.user_agent = user_agent
        self._opener = opener or urllib.request.build_opener(_NoRedirect)
        self._last = 0.0
        self.requests = 0

    def _wait(self) -> None:
        pause = self._last + self.delay - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        self._last = time.monotonic()

    def _one(self, url: str, *, read_body: bool) -> tuple[int, dict[str, str], bytes, str]:
        self._wait()
        self.requests += 1
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                body = resp.read(MAX_BODY + 1) if read_body else b""
                return resp.status, headers, _decode(body, headers), ""
        except urllib.error.HTTPError as exc:
            headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
            body = b""
            if read_body and exc.code not in REDIRECT_CODES:
                try:
                    body = exc.read(MAX_BODY + 1)
                except OSError:
                    body = b""
            return exc.code, headers, _decode(body, headers), ""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return 0, {}, b"", f"{type(exc).__name__}: {reason}"[:200]

    def get(self, url: str, *, follow: bool = True, read_body: bool = True) -> Response:
        """GET ``url``; with ``follow`` walk redirects (allowed hosts only, max 10 hops)."""
        start = time.monotonic()
        result = Response(url=url, status=0)
        current, seen = url, set()
        for _ in range(MAX_HOPS + 1):
            if not same_site(current, self.hosts):
                result.final_url, result.final_status = current, 0
                result.error = result.error or "redirects off-site (not requested)"
                break
            status, headers, body, error = self._one(current, read_body=read_body)
            location = headers.get("location", "")
            result.hops.append(Hop(current, status, location))
            if len(result.hops) == 1:
                result.status = status
            result.final_url, result.final_status = current, status
            result.headers, result.body, result.error = headers, body, error
            if status not in REDIRECT_CODES or not location or not follow:
                break
            nxt = clean_url(location, current)
            if nxt is None:
                result.error = "unusable Location header"
                break
            if nxt in seen or nxt == current:
                result.error = "redirect loop"
                result.final_url = nxt
                break
            seen.add(current)
            current = nxt
        else:
            result.error = "too many redirects"
        result.elapsed_ms = int((time.monotonic() - start) * 1000)
        return result


def _decode(body: bytes, headers: dict[str, str]) -> bytes:
    if body[:2] == b"\x1f\x8b" or headers.get("content-encoding", "").lower() == "gzip":
        with contextlib.suppress(OSError):  # not actually gzip: keep the raw bytes
            body = gzip.decompress(body)
    return body[:MAX_BODY]


def fingerprint(response: Response) -> str:
    """Identifies an identical HTML shell (SPA index.html or a themed 404 page)."""
    text = re.sub(r"\s+", " ", response.text())
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


# ---- HTML ------------------------------------------------------------------------------


class PageParser(HTMLParser):
    """Title, meta, canonical, links, images, h1, JSON-LD and visible word count."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, anchor text)
        self.images: list[str] = []
        self.h1 = ""
        self.jsonld: list[str] = []
        self.words = 0
        self._stack: list[str] = []
        self._anchor: list[str] | None = None
        self._href = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("title", "h1", "script", "style", "noscript"):
            self._stack.append(tag)
            self._buf = []
            if tag == "script" and "ld+json" not in a.get("type", ""):
                self._stack[-1] = "skip"
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if key and key not in self.meta:
                self.meta[key] = a.get("content", "").strip()
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            if "canonical" in rel and a.get("href"):
                self.canonicals.append(a["href"].strip())
        elif tag == "a" and a.get("href"):
            self._href, self._anchor = a["href"].strip(), []
        elif tag in ("img", "source"):
            src = a.get("src") or (a.get("srcset", "").split(" ", 1)[0])
            if src:
                self.images.append(src.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor is not None:
            self.links.append((self._href, " ".join("".join(self._anchor).split())[:200]))
            self._anchor = None
        if self._stack and (
            self._stack[-1] == tag or (tag == "script" and self._stack[-1] == "skip")
        ):
            kind = self._stack.pop()
            text = "".join(self._buf)
            if kind == "title" and not self.title:
                self.title = " ".join(text.split())
            elif kind == "h1" and not self.h1:
                self.h1 = " ".join(text.split())[:300]
            elif kind == "script":
                self.jsonld.append(text)
            self._buf = []

    def handle_data(self, data):
        if self._stack:
            self._buf.append(data)
            if self._stack[-1] in ("script", "style", "noscript", "skip", "title"):
                return
        if self._anchor is not None:
            self._anchor.append(data)
        self.words += len(re.findall(r"\w+", data))


def parse_page(html: str, base_url: str) -> dict:
    parser = PageParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed markup: keep what was parsed
        pass
    meta = parser.meta
    ld = _jsonld_facts(parser.jsonld)
    canonical = clean_url(parser.canonicals[0], base_url) if parser.canonicals else None
    return {
        "title": parser.title[:300],
        "meta_description": meta.get("description", "")[:500],
        "robots_meta": ", ".join(v for k, v in meta.items() if k in ("robots", "googlebot") and v),
        "canonical": canonical or "",
        "canonical_count": len(parser.canonicals),
        "og_type": meta.get("og:type", ""),
        "og_title": meta.get("og:title", "")[:300],
        "og_image": clean_url(meta.get("og:image", ""), base_url) or "",
        "published_time": meta.get("article:published_time") or ld.get("datePublished", ""),
        "modified_time": meta.get("article:modified_time") or ld.get("dateModified", ""),
        "author": meta.get("author") or meta.get("article:author") or ld.get("author", ""),
        "schema_type": ld.get("type", ""),
        "section": meta.get("article:section", ""),
        "h1": parser.h1,
        "word_count": parser.words,
        "links": [(clean_url(h, base_url), t) for h, t in parser.links if _linkable(h)],
        "images": [u for u in (clean_url(i, base_url) for i in parser.images) if u],
    }


def _linkable(href: str) -> bool:
    return not href.lower().startswith(("mailto:", "tel:", "javascript:", "data:", "#"))


def _jsonld_facts(blocks: list[str]) -> dict[str, str]:
    facts: dict[str, str] = {}

    def visit(node):
        if isinstance(node, list):
            for n in node:
                visit(n)
            return
        if not isinstance(node, dict):
            return
        if "@graph" in node:
            visit(node["@graph"])
        kind = node.get("@type")
        kind = kind[0] if isinstance(kind, list) and kind else kind
        if kind in ("Article", "BlogPosting", "NewsArticle", "WebPage", "CollectionPage"):
            if not facts.get("type") or kind != "WebPage":
                facts["type"] = str(kind)
            for key in ("datePublished", "dateModified"):
                if node.get(key) and not facts.get(key):
                    facts[key] = str(node[key])
            author = node.get("author")
            if isinstance(author, list) and author:
                author = author[0]
            if isinstance(author, dict):
                author = author.get("name")
            if author and not facts.get("author"):
                facts["author"] = str(author)

    for block in blocks:
        try:
            visit(json.loads(block))
        except (ValueError, TypeError):
            continue
    return facts


def is_noindex(robots_meta: str, x_robots_tag: str) -> bool:
    return "noindex" in f"{robots_meta},{x_robots_tag}".lower().replace(" ", "")


# ---- sitemaps and robots.txt -----------------------------------------------------------


def parse_sitemap(body: bytes) -> tuple[list[tuple[str, str]], list[str]]:
    """(urlset entries as (loc, lastmod), nested sitemap URLs)."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return [], []
    urls, nested = [], []
    for el in root:
        tag = el.tag.rsplit("}", 1)[-1]
        values = {c.tag.rsplit("}", 1)[-1]: (c.text or "").strip() for c in el}
        if not values.get("loc"):
            continue
        if tag == "sitemap":
            nested.append(values["loc"])
        elif tag == "url":
            urls.append((values["loc"], values.get("lastmod", "")))
    return urls, nested


def parse_robots(text: str, robots_url: str) -> tuple[robotparser.RobotFileParser, list[str]]:
    parser = robotparser.RobotFileParser(robots_url)
    parser.parse(text.splitlines())
    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lower().startswith("sitemap:")
    ]
    return parser, [urljoin(robots_url, s) for s in sitemaps if s]
