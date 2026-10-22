"""Role records and assignment rules."""

from __future__ import annotations

from sqlalchemy import func, select

from ..extensions import db
from ..models import Role, User, UserRole
from ..utils.errors import ConflictError, ValidationError
from .permissions import ROLE_DESCRIPTIONS, RoleName


def sync_roles() -> int:
    """Ensure the four built-in roles exist. Idempotent; returns how many were created."""
    existing = set(db.session.scalars(select(Role.name)))
    created = 0
    for role in RoleName:
        if role.value not in existing:
            db.session.add(Role(name=role.value, description=ROLE_DESCRIPTIONS[role]))
            created += 1
    if created:
        db.session.flush()
    return created


def get_roles(names: list[str]) -> list[Role]:
    unknown = set(names) - {r.value for r in RoleName}
    if unknown:
        raise ValidationError(details={"roles": [f"Unknown role(s): {', '.join(sorted(unknown))}"]})
    roles = list(db.session.scalars(select(Role).where(Role.name.in_(names))))
    if len(roles) != len(set(names)):
        raise ValidationError("Roles are not initialised. Run `flask admin sync-roles`.")
    return roles


def active_super_admin_count(exclude_user_id: int | None = None) -> int:
    stmt = (
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.name == RoleName.SUPER_ADMIN.value, User.status == "active")
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.session.scalar(stmt) or 0


def set_user_roles(user: User, names: list[str], *, assigned_by: User | None) -> None:
    roles = get_roles(sorted(set(names)))
    wanted = {r.id for r in roles}
    removing_super = (
        RoleName.SUPER_ADMIN.value in user.role_names
        and RoleName.SUPER_ADMIN.value not in {r.name for r in roles}
    )
    if removing_super and user.is_active and active_super_admin_count(user.id) == 0:
        raise ConflictError("The last active super administrator cannot lose that role.")
    user.role_links = [link for link in user.role_links if link.role_id in wanted]
    current = {link.role_id for link in user.role_links}
    for role in roles:
        if role.id not in current:
            user.role_links.append(
                UserRole(role=role, assigned_by_id=assigned_by.id if assigned_by else None)
            )
