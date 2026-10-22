"""Database-backed, validated site settings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..auth.permissions import Permission as P
from ..auth.rbac import effective_permissions
from ..cms.settings_registry import SETTINGS, SETTINGS_BY_KEY, SettingDef, validate_setting
from ..extensions import db
from ..models import SiteSetting, User
from ..utils.errors import ForbiddenError, ValidationError
from . import audit_service
from .publication_service import record_public_change
from .serializers import iso


def get_values() -> dict[str, Any]:
    stored = {s.key: s.value for s in db.session.scalars(select(SiteSetting))}
    values = {}
    for definition in SETTINGS:
        value = stored.get(definition.key)
        values[definition.key] = definition.default() if value is None else value
    return values


# Settings groups managed by a dedicated permission; everything else needs settings.manage.
GROUP_PERMISSIONS = {"SEO defaults": P.SEO_MANAGE}


def setting_permission(definition: SettingDef) -> P:
    return GROUP_PERMISSIONS.get(definition.group, P.SETTINGS_MANAGE)


def editable_by(user: User, definition: SettingDef) -> bool:
    return setting_permission(definition).value in effective_permissions(user)


def admin_payload(user: User | None = None) -> dict[str, Any]:
    stored = {s.key: s for s in db.session.scalars(select(SiteSetting))}
    values = get_values()
    groups: dict[str, list[dict[str, Any]]] = {}
    for d in SETTINGS:
        if user is not None and not editable_by(user, d):
            continue
        record = stored.get(d.key)
        groups.setdefault(d.group, []).append(
            {
                "key": d.key,
                "label": d.label,
                "type": d.type,
                "max_length": d.max_length,
                "help": d.help,
                "value": values[d.key],
                "is_default": record is None or record.value is None,
                "updated_at": iso(record.updated_at) if record else None,
            }
        )
    return {"groups": [{"name": name, "settings": items} for name, items in groups.items()]}


def update_values(changes: dict[str, Any], actor: User) -> dict[str, Any]:
    if not isinstance(changes, dict) or not changes:
        raise ValidationError(details={"values": ["Provide at least one setting to update."]})
    errors: dict[str, list[str]] = {}
    clean: dict[str, Any] = {}
    for key, value in changes.items():
        definition = SETTINGS_BY_KEY.get(key)
        if definition is None:
            errors[key] = ["Unknown setting."]
            continue
        if not editable_by(actor, definition):
            raise ForbiddenError("You cannot change one or more of these settings.")
        cleaned, error = validate_setting(definition, value)
        if error:
            errors[key] = [error]
        else:
            clean[key] = cleaned
    if errors:
        raise ValidationError("Some settings are invalid.", details=errors)

    before = get_values()
    changed = {}
    for key, value in clean.items():
        if before.get(key) == value:
            continue
        record = db.session.get(SiteSetting, key)
        if record is None:
            record = SiteSetting(key=key)
            db.session.add(record)
        record.value = value
        record.updated_by_id = actor.id
        changed[key] = {"from": before.get(key), "to": value}
    if changed:
        audit_service.record("settings.updated", "site_settings", actor=actor, details=changed)
        if any(SETTINGS_BY_KEY[k].public for k in changed):
            record_public_change("site_settings", None, "settings_updated", actor)
    return {"changed": sorted(changed)}
