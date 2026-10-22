"""CMS-managed redirects.

Redirects are served with real HTTP status codes by Nginx from a map file that
the publishing worker regenerates on every release (see deploy/nginx). The
React app also checks them on its not-found page so stale client-side links
recover, but that is a convenience, not the SEO mechanism.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import urlparse

from flask import current_app
from sqlalchemy import func, or_, select

from ..extensions import db
from ..models import Redirect, User
from ..models.publishing import REDIRECT_CODES
from ..utils.errors import ConflictError, NotFoundError, ValidationError
from . import audit_service
from .publication_service import record_public_change
from .serializers import iso

MAX_CHAIN = 5
RESERVED_PREFIXES = ("/admin", "/api", "/media", "/assets")
_PATH = re.compile(r"^/[A-Za-z0-9/_\-.~%]*$")
_SAFE_URL_CHARS = re.compile(r"^[^\s\"';<>{}\\]+$")


def normalise_source(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(details={"source_path": ["Enter the old path, e.g. /old-article."]})
    path = value.strip()
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        path = parsed.path or "/"  # accept a full old URL and keep its path
    path = path.split("?", 1)[0].split("#", 1)[0]
    if len(path) > 1:
        path = path.rstrip("/")
    if len(path) > 500 or not _PATH.match(path) or "//" in path or ".." in path:
        raise ValidationError(
            details={"source_path": ["Use a path starting with / (letters, numbers, - _ . ~ %)."]}
        )
    if path == "/" or any(path == p or path.startswith(p + "/") for p in RESERVED_PREFIXES):
        raise ValidationError(details={"source_path": ["This path cannot be redirected."]})
    return path


def _allowed_hosts() -> set[str]:
    hosts = {h.lower() for h in current_app.config.get("REDIRECT_ALLOWED_HOSTS", [])}
    site = current_app.config.get("SITE_URL") or ""
    if site:
        hosts.add((urlparse(site).hostname or "").lower())
    return {h for h in hosts if h}


def normalise_destination(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(details={"destination": ["Enter where visitors should go."]})
    dest = value.strip()
    if len(dest) > 1000 or not _SAFE_URL_CHARS.match(dest):
        raise ValidationError(
            details={"destination": ["The destination contains invalid characters."]}
        )
    if dest.startswith("/"):
        if dest.startswith("//") or not _PATH.match(dest.split("?", 1)[0].split("#", 1)[0]):
            raise ValidationError(
                details={"destination": ["Use a site path such as /articles/new-slug."]}
            )
        return dest
    parsed = urlparse(dest)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError(
            details={"destination": ["Use a site path or a full https:// address."]}
        )
    if parsed.hostname.lower() not in _allowed_hosts():
        raise ValidationError(
            details={
                "destination": [
                    "External destinations must be on an allowed host "
                    "(REDIRECT_ALLOWED_HOSTS). This prevents open redirects."
                ]
            }
        )
    return dest


def _internal_target(dest: str) -> str | None:
    if dest.startswith("/"):
        path = dest.split("?", 1)[0].split("#", 1)[0]
        return path.rstrip("/") if len(path) > 1 else path
    parsed = urlparse(dest)
    site = urlparse(current_app.config.get("SITE_URL") or "")
    if parsed.hostname and site.hostname and parsed.hostname.lower() == site.hostname.lower():
        path = parsed.path or "/"
        return path.rstrip("/") if len(path) > 1 else path
    return None


def check_chain(source: str, destination: str, *, exclude_id: int | None = None) -> None:
    """Reject loops (A -> B -> A) and chains longer than MAX_CHAIN hops."""
    active = {
        r.source_path: r.destination
        for r in db.session.scalars(select(Redirect).where(Redirect.is_active.is_(True)))
        if r.id != exclude_id
    }
    seen = {source}
    target = _internal_target(destination)
    hops = 1
    while target is not None:
        if target in seen:
            raise ValidationError(
                "This redirect would create a loop.",
                details={"destination": [f"{target} already redirects back to {source}."]},
            )
        if target not in active:
            return
        seen.add(target)
        hops += 1
        if hops > MAX_CHAIN:
            raise ValidationError(
                details={"destination": ["Too many redirects in a row; point to the final page."]}
            )
        target = _internal_target(active[target])


def redirect_dict(r: Redirect) -> dict[str, Any]:
    return {
        "id": r.id,
        "source_path": r.source_path,
        "destination": r.destination,
        "status_code": r.status_code,
        "is_active": r.is_active,
        "origin": r.origin,
        "note": r.note,
        "created_at": iso(r.created_at),
        "updated_at": iso(r.updated_at),
    }


def list_redirects(args: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stmt = select(Redirect)
    if args.get("q"):
        like = f"%{args['q'].strip()}%"
        stmt = stmt.where(or_(Redirect.source_path.ilike(like), Redirect.destination.ilike(like)))
    if args.get("active") is not None:
        stmt = stmt.where(Redirect.is_active.is_(args["active"]))
    if args.get("origin"):
        stmt = stmt.where(Redirect.origin == args["origin"])
    stmt = stmt.order_by(Redirect.updated_at.desc(), Redirect.id.desc())
    page, size = args.get("page", 1), args.get("page_size", 50)
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.session.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    pages = max(1, -(-total // size))
    return [redirect_dict(r) for r in rows], {
        "page": page,
        "page_size": size,
        "total": total,
        "total_pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def get_redirect(redirect_id: int) -> Redirect:
    r = db.session.get(Redirect, redirect_id)
    if r is None:
        raise NotFoundError("Redirect not found.")
    return r


def _validate(data: dict[str, Any], existing: Redirect | None) -> dict[str, Any]:
    source = (
        normalise_source(data["source_path"]) if "source_path" in data else existing.source_path
    )
    dest = (
        normalise_destination(data["destination"])
        if "destination" in data
        else existing.destination
    )
    code = data.get("status_code", existing.status_code if existing else 301)
    if code not in REDIRECT_CODES:
        raise ValidationError(details={"status_code": ["Use 301, 302, 307 or 308."]})
    if _internal_target(dest) == source:
        raise ValidationError(details={"destination": ["A path cannot redirect to itself."]})
    clash = db.session.scalar(
        select(Redirect.id).where(
            Redirect.source_path == source, Redirect.id != (existing.id if existing else 0)
        )
    )
    if clash:
        raise ConflictError(
            "A redirect for this path already exists.",
            details={"source_path": ["Already redirected; edit the existing entry."]},
        )
    active = data.get("is_active", existing.is_active if existing else True)
    if active:
        check_chain(source, dest, exclude_id=existing.id if existing else None)
    note = (data.get("note") if "note" in data else (existing.note if existing else "")) or ""
    return {
        "source_path": source,
        "destination": dest,
        "status_code": code,
        "is_active": bool(active),
        "note": note.strip()[:300],
    }


def _changed(actor: User | None, reason: str) -> None:
    record_public_change("redirects", None, reason, actor)


def create_redirect(data: dict[str, Any], actor: User | None, origin: str = "manual") -> Redirect:
    values = _validate(data, None)
    r = Redirect(**values, origin=origin, created_by_id=actor.id if actor else None)
    db.session.add(r)
    db.session.flush()
    audit_service.record("redirect.created", "redirect", r.id, actor=actor, details=values)
    _changed(actor, "redirect_created")
    return r


def update_redirect(r: Redirect, data: dict[str, Any], actor: User) -> Redirect:
    values = _validate(data, r)
    changes = {k: {"from": getattr(r, k), "to": v} for k, v in values.items() if getattr(r, k) != v}
    for k, v in values.items():
        setattr(r, k, v)
    if changes:
        audit_service.record("redirect.updated", "redirect", r.id, actor=actor, details=changes)
        _changed(actor, "redirect_updated")
    return r


def delete_redirect(r: Redirect, actor: User) -> None:
    audit_service.record(
        "redirect.deleted", "redirect", r.id, actor=actor, details={"source_path": r.source_path}
    )
    db.session.delete(r)
    _changed(actor, "redirect_deleted")


def create_slug_redirect(old_path: str, new_path: str, actor: User | None) -> Redirect:
    """Keep an old article URL working after a slug change (301), flattening chains."""
    # The article lives at new_path again: an older redirect from there must go.
    for r in db.session.scalars(select(Redirect).where(Redirect.source_path == new_path)):
        db.session.delete(r)
    # Anything that pointed at the old URL now points straight at the new one.
    for r in db.session.scalars(select(Redirect).where(Redirect.destination == old_path)):
        r.destination = new_path
    db.session.flush()
    existing = db.session.scalar(select(Redirect).where(Redirect.source_path == old_path))
    if existing:
        existing.destination, existing.status_code, existing.is_active = new_path, 301, True
        redirect = existing
    else:
        redirect = Redirect(
            source_path=old_path,
            destination=new_path,
            status_code=301,
            origin="slug_change",
            note="Created automatically when the article slug changed.",
            created_by_id=actor.id if actor else None,
        )
        db.session.add(redirect)
    db.session.flush()
    audit_service.record(
        "redirect.created",
        "redirect",
        redirect.id,
        actor=actor,
        details={"source_path": old_path, "destination": new_path, "origin": "slug_change"},
    )
    _changed(actor, "slug_redirect")
    return redirect


# ---- import / export / delivery --------------------------------------------------------

CSV_FIELDS = ("source_path", "destination", "status_code", "is_active", "note")


def export_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_FIELDS)
    for r in db.session.scalars(select(Redirect).order_by(Redirect.source_path)):
        writer.writerow([r.source_path, r.destination, r.status_code, int(r.is_active), r.note])
    return buf.getvalue()


def import_rows(rows: list[dict[str, Any]], actor: User, *, dry_run: bool = False) -> dict:
    """Import redirects (e.g. from the old site). Each row is validated independently."""
    created, errors = 0, []
    seen: set[str] = set()
    for index, row in enumerate(rows[:5000], start=1):
        try:
            source = normalise_source(row.get("source_path") or row.get("source") or "")
            if source in seen:
                raise ConflictError(details={"source_path": ["Duplicate path in this file."]})
            seen.add(source)
            with db.session.begin_nested():
                data = {
                    "source_path": row.get("source_path") or row.get("source") or "",
                    "destination": row.get("destination") or row.get("target") or "",
                    "status_code": int(row.get("status_code") or 301),
                    "is_active": str(row.get("is_active", "1")).strip().lower()
                    not in ("0", "false", "no"),
                    "note": row.get("note") or "Imported",
                }
                create_redirect(data, actor, origin="import")
                if dry_run:
                    raise _DryRun
            created += 1
        except _DryRun:
            created += 1
        except (ValidationError, ConflictError, ValueError) as exc:
            detail = getattr(exc, "details", None) or {}
            message = "; ".join(m for v in detail.values() for m in v) if detail else str(exc)
            errors.append({"row": index, "source_path": row.get("source_path"), "error": message})
    return {"created": created if not dry_run else 0, "valid": created, "errors": errors}


class _DryRun(Exception):
    pass


def parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


def active_redirects() -> list[dict[str, Any]]:
    return [
        {"source": r.source_path, "destination": r.destination, "status_code": r.status_code}
        for r in db.session.scalars(
            select(Redirect).where(Redirect.is_active.is_(True)).order_by(Redirect.source_path)
        )
    ]


def resolve(path: str) -> dict[str, Any] | None:
    try:
        source = normalise_source(path)
    except ValidationError:
        return None
    r = db.session.scalar(
        select(Redirect).where(Redirect.source_path == source, Redirect.is_active.is_(True))
    )
    return {"destination": r.destination, "status_code": r.status_code} if r else None
