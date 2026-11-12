"""CMS navigation menus. Menus not yet saved in the database fall back to defaults."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..cms.defaults import DEFAULT_MENUS, TOPIC_GROUPS, TOPICS_PER_GROUP
from ..extensions import db
from ..models import NavigationItem, NavigationMenu, User
from ..utils.errors import NotFoundError, ValidationError
from ..utils.validation import is_https_url, is_internal_path, plain_text_problem
from . import audit_service
from .publication_service import record_public_change
from .topic_links import (
    TopicLinkResolver,
    default_topic_links,
    group_anchor,
    grouped_topic_links,
    topic_slug,
)

MAX_ITEMS = 40
VISIBILITY = ("all", "desktop", "mobile")


def _menu(key: str) -> NavigationMenu | None:
    return db.session.scalar(select(NavigationMenu).where(NavigationMenu.key == key))


def _tree_from_db(menu: NavigationMenu, *, visible_only: bool) -> list[dict[str, Any]]:
    items = [i for i in menu.items if i.is_visible or not visible_only]
    by_parent: dict[int | None, list[NavigationItem]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)

    def build(parent_id: int | None) -> list[dict[str, Any]]:
        out = []
        for item in sorted(by_parent.get(parent_id, []), key=lambda i: i.display_order):
            node = {
                "label": item.label,
                "link_type": item.link_type,
                "url": item.url,
                "open_in_new_tab": item.open_in_new_tab,
                "is_visible": item.is_visible,
                "visibility": item.visibility or "all",
            }
            if parent_id is None:
                node["children"] = build(item.id)
            out.append(node)
        return out

    return build(None)


ALL_ARTICLES = {"label": "All articles", "url": "/articles"}


def _tree_from_defaults(key: str) -> list[dict[str, Any]]:
    def norm(item: dict[str, Any], top: bool) -> dict[str, Any]:
        node = {
            "label": item["label"],
            "link_type": item.get("link_type", "internal"),
            "url": item.get("url"),
            "open_in_new_tab": False,
            "is_visible": True,
            "visibility": "all",
        }
        if top:
            children = list(item.get("children", []))
            if item.get("topic_links"):
                children += default_topic_links(item["topic_links"])
            if item.get("topic_group") and groups[item["topic_group"]]:
                children += [*groups[item["topic_group"]], ALL_ARTICLES]
            if item.get("group_links"):
                children += [
                    {"label": label, "url": f"/topics#{group_anchor(label)}"}
                    for label, _k in TOPIC_GROUPS
                    if groups[label]
                ]
            node["children"] = [norm(c, False) for c in children]
        return node

    groups = grouped_topic_links(TOPIC_GROUPS, TOPICS_PER_GROUP)
    items = [norm(i, True) for i in DEFAULT_MENUS[key]["items"]]
    # A topic group with no matching topics is left out rather than shown empty.
    return [
        i
        for i, spec in zip(items, DEFAULT_MENUS[key]["items"], strict=True)
        if not (spec.get("topic_group") and not i["children"])
    ]


def menu_tree(key: str, *, visible_only: bool = True) -> list[dict[str, Any]]:
    menu = _menu(key)
    return _tree_from_db(menu, visible_only=visible_only) if menu else _tree_from_defaults(key)


# Website areas that can be switched off until they are ready (Settings › Website sections).
AREA_PREFIXES = {
    "visibility.shop_public": ("/shop", "/cart"),
    "visibility.courses_public": ("/courses",),
}


def hidden_prefixes() -> tuple[str, ...]:
    from .settings_service import get_values

    values = get_values()
    return tuple(p for key, ps in AREA_PREFIXES.items() if not values.get(key) for p in ps)


def is_hidden_destination(url: str | None, prefixes: tuple[str, ...]) -> bool:
    """An internal link into a switched-off area: /shop, /shop/..., /courses, ... (The
    pages stay reachable; they are only left out of menus and promotions.)"""
    if not url or not url.startswith("/"):
        return False
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/"
    return any(path == p or path.startswith(p + "/") for p in prefixes)


def unpublished_policy_paths() -> set[str]:
    """Policy addresses still served by their built-in draft (no published CMS page)."""
    from ..cms.routing import OVERRIDABLE_PATHS
    from ..cms.templates import POLICY_PATHS
    from ..models import Page

    live = db.session.scalars(
        select(Page.published_path).where(
            Page.status == "published", Page.published_path.in_(POLICY_PATHS)
        )
    )
    assert POLICY_PATHS <= OVERRIDABLE_PATHS
    return set(POLICY_PATHS) - set(live)


def _path_only(url: str | None) -> str | None:
    if not url or not url.startswith("/"):
        return None
    return url.split("#", 1)[0].split("?", 1)[0].rstrip("/") or "/"


# App pages that answer without a CMS record (and aren't in the sitemap), so links to them
# are never treated as missing.
APP_PREFIXES = (
    "/search",
    "/articles/page/",
    "/authors/",
    "/account",
    "/learn",
    "/certificates/",
    "/newsletter/",
    "/resources/access",
    "/checkout",
    "/verify-email",
    "/forgot-password",
    "/reset-password",
    "/admin",
)


def _unavailable_paths():
    """A check for internal menu links that lead nowhere yet (an unpublished CMS page, a
    removed article); links into the app's own pages always count as available."""
    from .seo_service import _known_paths, broken_links

    known = _known_paths()

    def check(url: str | None) -> bool:
        path = _path_only(url)
        if path is None or path == "/" or topic_slug(url):
            return False  # external, home, or a topic link (handled by the topic resolver)
        if any(path == p.rstrip("/") or path.startswith(p) for p in APP_PREFIXES):
            return False
        return bool(broken_links([path], known))

    return check


def _with_featured_topics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add featured topics that aren't linked anywhere in the default header menu.

    The default topic groups are filled by keyword (at most a few per group), so a new
    topic whose name matches no keyword never reached the header. A topic marked
    **Featured** in Admin › Topics, active and with published articles, is added to the
    matching topic group
    (by the group's keywords; otherwise the group with the fewest topics), after the
    group's topic links and in the topics' display order. Other topics are not added, and
    a topic already linked anywhere in the menu is not repeated.
    """
    from .topic_links import _normalise, topic_path
    from .topic_service import list_topics

    groups = [i for i in items if any(topic_slug(c.get("url")) for c in i.get("children") or [])]
    if not groups:
        return items
    linked = {
        topic_slug(node.get("url")) for i in items for node in [i, *(i.get("children") or [])]
    }
    keywords = dict(TOPIC_GROUPS)
    for topic in list_topics(featured=True):
        if not topic.get("article_count") or topic["slug"] in linked:
            continue
        text = _normalise(f"{topic['name']} {topic['slug']}")
        target = next(
            (g for g in groups if any(_normalise(k) in text for k in keywords.get(g["label"], ()))),
            None,
        ) or min(groups, key=lambda g: sum(1 for c in g["children"] if topic_slug(c["url"])))
        children = target["children"]
        after = max(i for i, c in enumerate(children) if topic_slug(c["url"])) + 1
        children.insert(
            after,
            {
                "label": topic["name"],
                "url": topic_path(topic["slug"]),
                "external": False,
                "open_in_new_tab": False,
                "visibility": "all",
            },
        )
        linked.add(topic["slug"])
    return items


def public_navigation() -> dict[str, Any]:
    hidden = hidden_prefixes()
    topics = TopicLinkResolver()
    drafts = unpublished_policy_paths()
    unavailable = _unavailable_paths()

    def shown(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for n in nodes:
            if is_hidden_destination(n.get("url"), hidden):
                continue
            if _path_only(n.get("url")) in drafts:
                # A policy that is still a built-in draft is not advertised in the menus.
                continue
            if n["link_type"] == "internal" and unavailable(n.get("url")):
                # Only valid destinations: e.g. a page that hasn't been published yet.
                continue
            if n["link_type"] == "internal" and topic_slug(n.get("url")):
                # A topic that was renamed is linked at its new address; a topic that does
                # not exist (or is hidden) is left out instead of sending readers to a 404.
                url = topics.resolve(n["url"])
                if url is None:
                    continue
                n = {**n, "url": url}
            out.append(n)
        return out

    def link(node: dict[str, Any]) -> dict[str, Any]:
        return {
            "label": node["label"],
            "url": node["url"],
            "external": node["link_type"] == "external",
            "open_in_new_tab": node["open_in_new_tab"],
            "visibility": node.get("visibility", "all"),
        }

    def header_items(key: str) -> list[dict[str, Any]]:
        out = []
        for n in shown(menu_tree(key)):
            if n["link_type"] == "heading":
                children = [link(c) for c in shown(n["children"])]
                if children:
                    out.append(
                        {
                            "label": n["label"],
                            "url": None,
                            "visibility": n.get("visibility", "all"),
                            "children": children,
                        }
                    )
            else:
                out.append(link(n))
        return out

    primary = header_items("primary")
    if _menu("primary") is None:  # a menu saved in Admin › Navigation is shown as arranged
        primary = _with_featured_topics(primary)
    mobile = header_items("mobile") if _menu("mobile") is not None else []
    footer = [
        {
            "title": n["label"],
            "items": [link(c) for c in shown(n["children"]) if c["link_type"] != "heading"],
        }
        for n in menu_tree("footer")
        if n["link_type"] == "heading"
    ]
    legal = [link(n) for n in shown(menu_tree("legal")) if n["link_type"] != "heading"]
    return {
        "primary": primary,
        "mobile": mobile or None,
        "footer": [g for g in footer if g["items"]],
        "legal": legal,
    }


def link_warnings(items: list[dict[str, Any]]) -> list[str]:
    """Internal links that do not point to a published page (warnings, not errors)."""
    from .seo_service import broken_links

    hrefs = []
    for item in items:
        if item.get("link_type") == "internal" and item.get("url"):
            hrefs.append(item["url"])
        hrefs += [c["url"] for c in item.get("children") or [] if c.get("link_type") == "internal"]
    broken = broken_links(hrefs)
    warnings = [f"{href} does not point to a published page yet." for href in dict.fromkeys(broken)]
    drafts = unpublished_policy_paths()
    for href in dict.fromkeys(hrefs):
        if _path_only(href) in drafts:
            warnings.append(
                f"{href} is still a draft policy, so it stays hidden from the menu until its "
                "page is published under Pages."
            )
    topics = TopicLinkResolver()
    for href in dict.fromkeys(hrefs):
        if href in broken or not topic_slug(href):
            continue
        moved = topics.resolve(href)
        if moved is None:
            warnings.append(f"{href} is not a published topic, so it is hidden from the menu.")
        elif moved != href:
            warnings.append(f"{href} has moved: readers are sent to {moved}. Update the link.")
    return warnings


def admin_menus() -> list[dict[str, Any]]:
    out = []
    for key, spec in DEFAULT_MENUS.items():
        items = menu_tree(key, visible_only=False)
        out.append(
            {
                "key": key,
                "name": spec["name"],
                "help": spec.get("help", ""),
                "is_default": _menu(key) is None,
                "allows_groups": spec.get("allows_groups", False),
                "items": items,
                # The recommended structure from the defaults, built from today's topics:
                # the editor can load it for review; nothing changes until it is saved.
                "recommended": _tree_from_defaults(key),
                "warnings": link_warnings(items),
            }
        )
    return out


def _validate_item(item: Any, path: str, *, top: bool, allow_groups: bool, errors: dict) -> dict:
    problems: list[str] = []
    if not isinstance(item, dict):
        errors[path] = ["Each item must be an object."]
        return {}
    label = str(item.get("label", "")).strip()
    link_type = item.get("link_type", "internal")
    url = (item.get("url") or "").strip() or None
    if not label or len(label) > 80:
        problems.append("Label is required (max 80 characters).")
    elif problem := plain_text_problem(label):
        problems.append(problem)
    if link_type not in ("internal", "external", "heading"):
        problems.append("Link type must be internal, external or heading.")
    if link_type == "heading":
        if not (top and allow_groups):
            problems.append("Groups are only allowed at the top level of this menu.")
        url = None
    elif link_type == "internal" and not (url and is_internal_path(url)):
        problems.append("Internal links must start with / (e.g. /articles).")
    elif link_type == "external" and not (url and is_https_url(url)):
        problems.append("External links must be full https:// URLs.")
    children = item.get("children") or []
    if children and not (top and link_type == "heading"):
        problems.append("Only group headings can contain links.")
    visibility = item.get("visibility") or "all"
    if visibility not in VISIBILITY:
        problems.append(f"Visibility must be one of: {', '.join(VISIBILITY)}.")
    if problems:
        errors[path] = problems
    return {
        "label": label,
        "link_type": link_type,
        "url": url,
        "open_in_new_tab": bool(item.get("open_in_new_tab", False)),
        "is_visible": bool(item.get("is_visible", True)),
        "visibility": visibility if visibility in VISIBILITY else "all",
        "children": [
            _validate_item(c, f"{path}.{i}", top=False, allow_groups=allow_groups, errors=errors)
            for i, c in enumerate(children)
        ]
        if top
        else [],
    }


def replace_menu(key: str, items: Any, actor: User) -> list[dict[str, Any]]:
    if key not in DEFAULT_MENUS:
        raise NotFoundError("Menu not found.")
    if not isinstance(items, list):
        raise ValidationError(details={"items": ["Items must be a list."]})
    total = len(items) + sum(len(i.get("children") or []) for i in items if isinstance(i, dict))
    if total > MAX_ITEMS:
        raise ValidationError(details={"items": [f"A menu can have at most {MAX_ITEMS} links."]})
    errors: dict[str, list[str]] = {}
    allow_groups = DEFAULT_MENUS[key].get("allows_groups", False)
    clean = [
        _validate_item(item, str(i), top=True, allow_groups=allow_groups, errors=errors)
        for i, item in enumerate(items)
    ]
    if errors:
        raise ValidationError("Some menu items are invalid.", details=errors)

    menu = _menu(key)
    if menu is None:
        menu = NavigationMenu(key=key, name=DEFAULT_MENUS[key]["name"])
        db.session.add(menu)
    menu.items.clear()
    db.session.flush()
    for order, node in enumerate(clean):
        parent = NavigationItem(
            label=node["label"],
            link_type=node["link_type"],
            url=node["url"],
            open_in_new_tab=node["open_in_new_tab"],
            is_visible=node["is_visible"],
            visibility=node["visibility"],
            display_order=order,
        )
        menu.items.append(parent)
        db.session.flush()
        for child_order, child in enumerate(node["children"]):
            menu.items.append(
                NavigationItem(
                    parent_id=parent.id,
                    label=child["label"],
                    link_type=child["link_type"],
                    url=child["url"],
                    open_in_new_tab=child["open_in_new_tab"],
                    is_visible=child["is_visible"],
                    visibility=child["visibility"],
                    display_order=child_order,
                )
            )
    audit_service.record(
        "navigation.updated", "navigation_menu", key, actor=actor, details={"items": total}
    )
    record_public_change("navigation_menu", key, "navigation_updated", actor)
    db.session.flush()
    return menu_tree(key, visible_only=False)
