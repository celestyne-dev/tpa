"""CMS navigation menus. Menus not yet saved in the database fall back to defaults."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..cms.defaults import DEFAULT_MENUS
from ..extensions import db
from ..models import NavigationItem, NavigationMenu, User
from ..utils.errors import NotFoundError, ValidationError
from ..utils.validation import is_https_url, is_internal_path, plain_text_problem
from . import audit_service
from .publication_service import record_public_change

MAX_ITEMS = 40


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
            }
            if parent_id is None:
                node["children"] = build(item.id)
            out.append(node)
        return out

    return build(None)


def _tree_from_defaults(key: str) -> list[dict[str, Any]]:
    def norm(item: dict[str, Any], top: bool) -> dict[str, Any]:
        node = {
            "label": item["label"],
            "link_type": item.get("link_type", "internal"),
            "url": item.get("url"),
            "open_in_new_tab": False,
            "is_visible": True,
        }
        if top:
            node["children"] = [norm(c, False) for c in item.get("children", [])]
        return node

    return [norm(i, True) for i in DEFAULT_MENUS[key]["items"]]


def menu_tree(key: str, *, visible_only: bool = True) -> list[dict[str, Any]]:
    menu = _menu(key)
    return _tree_from_db(menu, visible_only=visible_only) if menu else _tree_from_defaults(key)


def public_navigation() -> dict[str, Any]:
    def link(node: dict[str, Any]) -> dict[str, Any]:
        return {
            "label": node["label"],
            "url": node["url"],
            "external": node["link_type"] == "external",
            "open_in_new_tab": node["open_in_new_tab"],
        }

    primary = [link(n) for n in menu_tree("primary") if n["link_type"] != "heading"]
    footer = [
        {
            "title": n["label"],
            "items": [link(c) for c in n["children"] if c["link_type"] != "heading"],
        }
        for n in menu_tree("footer")
        if n["link_type"] == "heading"
    ]
    return {"primary": primary, "footer": [g for g in footer if g["items"]]}


def admin_menus() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "name": spec["name"],
            "is_default": _menu(key) is None,
            "allows_groups": key == "footer",
            "items": menu_tree(key, visible_only=False),
        }
        for key, spec in DEFAULT_MENUS.items()
    ]


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
            problems.append("Group headings are only allowed at the top level of the footer.")
        url = None
    elif link_type == "internal" and not (url and is_internal_path(url)):
        problems.append("Internal links must start with / (e.g. /articles).")
    elif link_type == "external" and not (url and is_https_url(url)):
        problems.append("External links must be full https:// URLs.")
    children = item.get("children") or []
    if children and not (top and link_type == "heading"):
        problems.append("Only group headings can contain links.")
    if problems:
        errors[path] = problems
    return {
        "label": label,
        "link_type": link_type,
        "url": url,
        "open_in_new_tab": bool(item.get("open_in_new_tab", False)),
        "is_visible": bool(item.get("is_visible", True)),
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
    clean = [
        _validate_item(item, str(i), top=True, allow_groups=key == "footer", errors=errors)
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
                    display_order=child_order,
                )
            )
    audit_service.record(
        "navigation.updated", "navigation_menu", key, actor=actor, details={"items": total}
    )
    record_public_change("navigation_menu", key, "navigation_updated", actor)
    db.session.flush()
    return menu_tree(key, visible_only=False)
