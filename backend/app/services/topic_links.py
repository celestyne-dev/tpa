"""Links to topic pages (/topics/<slug>) that always lead to a real, published topic.

Topics are created and renamed in the admin, so a topic URL written into a menu can stop
working. This module keeps those links honest:

* ``TopicLinkResolver`` checks a link against the active topics and the redirect table:
  a link to an active topic is kept, a link whose topic moved (a 301 from the old slug)
  is rewritten to the new address, and anything else is reported as dead.
* ``retarget_topic_links`` runs when a topic's slug changes: it adds the permanent
  redirect from the old URL and updates saved menu links, so the old address keeps
  working and the menus use the new one.
* ``default_topic_links`` gives the built-in menus links to topics that actually exist,
  instead of slugs written into the code.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from ..extensions import db
from ..models import NavigationItem, Redirect, Topic, User
from . import audit_service

PREFIX = "/topics/"
_TOPIC_PATH = re.compile(r"^/topics/([^/?#]+)(/[^?#]*)?([?#].*)?$")
MAX_HOPS = 5


def topic_path(slug: str) -> str:
    return f"{PREFIX}{slug}"


def topic_slug(url: str | None) -> str | None:
    """The slug of a /topics/<slug>[/page/N][?…][#…] link, or None for any other link."""
    if not url:
        return None
    m = _TOPIC_PATH.match(url)
    return m.group(1) if m else None


def active_topic_slugs() -> set[str]:
    return set(db.session.scalars(select(Topic.slug).where(Topic.status == "active")))


class TopicLinkResolver:
    """Resolve topic links against the live topics and redirects (two queries, then cached)."""

    def __init__(self) -> None:
        self.slugs = active_topic_slugs()
        self.redirects = {
            r.source_path: r.destination
            for r in db.session.scalars(
                select(Redirect).where(
                    Redirect.is_active.is_(True), Redirect.source_path.startswith(PREFIX)
                )
            )
        }

    def resolve(self, url: str | None) -> str | None:
        """The link to use: unchanged for non-topic links and live topics, the new address
        for a topic that moved, or None when the topic does not exist (or is hidden)."""
        m = _TOPIC_PATH.match(url or "")
        if not m:
            return url
        slug, rest, suffix = m.group(1), m.group(2) or "", m.group(3) or ""
        seen = set()
        for _ in range(MAX_HOPS):
            if slug in self.slugs:
                return f"{topic_path(slug)}{rest}{suffix}"
            path = topic_path(slug)
            dest = self.redirects.get(path)
            if not dest or path in seen:
                return None
            seen.add(path)
            slug = topic_slug(dest)
            if slug is None:
                return None
        return None


def default_topic_links(limit: int) -> list[dict[str, Any]]:
    """Menu links to real topics: featured first, then in the admin's display order."""
    stmt = (
        select(Topic)
        .where(Topic.status == "active")
        .order_by(Topic.featured.desc(), Topic.display_order, Topic.name)
        .limit(limit)
    )
    return [{"label": t.name, "url": topic_path(t.slug)} for t in db.session.scalars(stmt)]


def _moved(url: str, old: str, new: str) -> str | None:
    if url == old:
        return new
    for sep in ("/", "?", "#"):
        if url.startswith(old + sep):
            return new + url[len(old) :]
    return None


def retarget_topic_links(old_slug: str, new_slug: str, actor: User | None) -> int:
    """After a topic's slug changes: 301 the old URL to the new one and point saved menu
    links at the new URL. Returns the number of menu links updated."""
    from .redirect_service import create_slug_redirect

    old, new = topic_path(old_slug), topic_path(new_slug)
    create_slug_redirect(old, new, actor, note="Created automatically when the topic slug changed.")
    updated = 0
    stmt = select(NavigationItem).where(NavigationItem.url.startswith(old))
    for item in db.session.scalars(stmt):
        moved = _moved(item.url, old, new)
        if moved:
            item.url = moved
            updated += 1
    if updated:
        db.session.flush()
        audit_service.record(
            "navigation.links_updated",
            "navigation",
            None,
            actor=actor,
            details={"from": old, "to": new, "links": updated},
        )
    return updated


def fix_topic_slug(old_slug: str, new_slug: str, actor: User | None = None) -> dict[str, Any]:
    """Move one existing topic to a corrected slug, safely and repeatably.

    The topic row is renamed in place (same id), so its articles, courses, SEO fields and
    status are untouched and no second topic is created. The old URL gets a 301 to the new
    one and saved menu links are updated. Running it again after it has worked only makes
    sure the redirect is there. It refuses when both slugs exist (merging two topics is an
    editorial decision: use "Reassign articles" in the admin) or when neither exists.
    """
    from ..utils.errors import ConflictError, NotFoundError
    from .admin.taxonomy import save_topic

    old = db.session.scalar(select(Topic).where(Topic.slug == old_slug))
    new = db.session.scalar(select(Topic).where(Topic.slug == new_slug))
    if old is not None and new is not None:
        raise ConflictError(
            f"Both /topics/{old_slug} and /topics/{new_slug} exist. Reassign the articles of "
            "one topic to the other in the admin first; nothing was changed."
        )
    if old is not None:
        save_topic(old, {"slug": new_slug}, actor)
        return {"status": "renamed", "topic_id": old.id, "path": topic_path(new_slug)}
    if new is None:
        raise NotFoundError(f"No topic has the slug '{old_slug}' or '{new_slug}'.")
    source = topic_path(old_slug)
    redirect = db.session.scalar(select(Redirect).where(Redirect.source_path == source))
    if (
        redirect is not None
        and redirect.is_active
        and redirect.destination == topic_path(new_slug)
        and redirect.status_code == 301
    ):
        added, links = False, 0
    else:
        added, links = True, retarget_topic_links(old_slug, new_slug, actor)
    return {
        "status": "already_renamed",
        "topic_id": new.id,
        "path": topic_path(new_slug),
        "redirect_added": added,
        "links_updated": links,
    }


# ---- topic groups for the recommended navigation (Batch 14) -----------------------------


def group_anchor(label: str) -> str:
    """The anchor of a navigation group on /topics: "Career & Growth" -> "career-growth"."""
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _normalise(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def grouped_topic_links(
    groups: list[tuple[str, tuple[str, ...]]], limit: int
) -> dict[str, list[dict[str, Any]]]:
    """Sort the existing active topics into the navigation groups by name.

    Each topic goes into the first group with a matching keyword (so it is listed once),
    featured topics first, then the admin's order. Only topics with published articles are
    placed, so the menus never lead to an empty topic. Nothing is created: a topic that
    matches no group is simply not placed (the admin can add it), and a group with no
    matching topic stays empty.
    """
    from .topic_service import list_topics

    topics = sorted(
        (t for t in list_topics() if t.get("article_count")),
        key=lambda t: not t.get("featured"),
    )
    out: dict[str, list[dict[str, Any]]] = {label: [] for label, _ in groups}
    for topic in topics:
        text = _normalise(f"{topic['name']} {topic['slug']}")
        for label, keywords in groups:
            if any(_normalise(k) in text for k in keywords):
                if len(out[label]) < limit:
                    out[label].append({"label": topic["name"], "url": topic_path(topic["slug"])})
                break
    return out
