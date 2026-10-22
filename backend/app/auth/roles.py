"""Role records and assignment rules."""

from __future__ import annotations

from sqlalchemy import func, select

from ..extensions import db
from ..models import Role, User, UserRole
from ..utils.errors import ConflictError, ValidationError
from .permissions import RoleName
from .rbac import sync_rbac


def sync_roles() -> int:
    """Ensure permissions, system roles and templates exist (idempotent)."""
    return sync_rbac()["roles_created"]


def get_roles(names: list[str], *, require_active: bool = True) -> list[Role]:
    names = sorted(set(names))
    roles = list(db.session.scalars(select(Role).where(Role.name.in_(names))))
    unknown = set(names) - {r.name for r in roles}
    if unknown:
        raise ValidationError(details={"roles": [f"Unknown role(s): {', '.join(sorted(unknown))}"]})
    inactive = [r.label or r.name for r in roles if not r.is_active]
    if require_active and inactive:
        raise ValidationError(details={"roles": [f"Inactive role(s): {', '.join(inactive)}"]})
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
    current_names = set(user.role_names)
    wanted_names = set(names)
    # Roles the user already holds may stay even if since deactivated; new ones must be active.
    get_roles(sorted(wanted_names - current_names))
    roles = get_roles(sorted(wanted_names), require_active=False)
    wanted = {r.id for r in roles}
    removing_super = (
        RoleName.SUPER_ADMIN.value in current_names
        and RoleName.SUPER_ADMIN.value not in wanted_names
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
