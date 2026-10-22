"""Shared validators for plain-text content, slugs and links."""

from __future__ import annotations

import re
from urllib.parse import urlparse

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HTML_TAG = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INTERNAL_PATH = re.compile(r"^/(?!/)[A-Za-z0-9\-._~/%?=&#+]*$")
_EMAIL = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


def slugify(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:200]


def plain_text_problem(value: str) -> str | None:
    """Content is plain text rendered without HTML: reject tags and control characters."""
    if _CONTROL.search(value):
        return "Contains invalid control characters."
    if _HTML_TAG.search(value):
        return "HTML is not allowed. Use plain text."
    return None


def is_internal_path(value: str) -> bool:
    return bool(_INTERNAL_PATH.match(value))


def is_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc) and " " not in value


def is_email(value: str) -> bool:
    return len(value) <= 254 and bool(_EMAIL.match(value))
