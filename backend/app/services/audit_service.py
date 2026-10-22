"""Audit logging with secret-free, size-limited metadata."""

from __future__ import annotations

import re
from typing import Any

from flask import has_request_context, request

from ..extensions import db
from ..models import AuditLog, User

_SENSITIVE = re.compile(r"pass(word)?|token|secret|hash|csrf|jwt|cookie|authorization", re.I)
_MAX_STRING = 300
_MAX_ITEMS = 50


def sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(k)[:80]: ("[redacted]" if _SENSITIVE.search(str(k)) else sanitize(v, depth + 1))
            for k, v in list(value.items())[:_MAX_ITEMS]
        }
    if isinstance(value, list | tuple | set):
        return [sanitize(v, depth + 1) for v in list(value)[:_MAX_ITEMS]]
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "…"
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)[:_MAX_STRING]


def record(
    action: str,
    resource_type: str,
    resource_id: Any = None,
    *,
    actor: User | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=None if resource_id is None else str(resource_id),
        details=sanitize(details or {}),
        ip_address=request.remote_addr if has_request_context() else None,
    )
    db.session.add(entry)
    return entry


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Summarise changes for the audit log (field names plus short scalar values)."""
    changes: dict[str, Any] = {}
    for key, new in after.items():
        old = before.get(key)
        if old != new:
            if isinstance(new, str | int | bool | type(None)) and len(str(new)) <= 120:
                changes[key] = {"from": old if len(str(old)) <= 120 else "…", "to": new}
            else:
                changes[key] = "changed"
    return changes
