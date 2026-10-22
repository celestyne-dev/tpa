"""Central permission definitions and the role registry.

Roles are stored in the database and assigned per user; what each role may do
is defined here in code so permissions cannot be widened by editing data. The
frontend receives each user's resolved permission list and never hardcodes
role names. To add a specialised role later (e.g. "newsletter_manager"), add
a RoleDefinition below and a data migration inserting the role row.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    DASHBOARD_VIEW = "dashboard.view"
    ANALYTICS_VIEW = "analytics.view"
    CONTENT_READ = "content.read"
    CONTENT_WRITE = "content.write"
    CONTENT_PUBLISH = "content.publish"
    CONTENT_MODERATE = "content.moderate"
    TAXONOMY_MANAGE = "taxonomy.manage"
    PAGES_READ = "pages.read"
    PAGES_WRITE = "pages.write"
    NAVIGATION_MANAGE = "navigation.manage"
    SETTINGS_MANAGE = "settings.manage"
    USERS_MANAGE = "users.manage"
    ROLES_ASSIGN = "roles.assign"
    AUDIT_READ = "audit.read"


PERMISSION_DESCRIPTIONS: dict[Permission, str] = {
    Permission.DASHBOARD_VIEW: "Open the admin dashboard",
    Permission.ANALYTICS_VIEW: "View content analytics and reports",
    Permission.CONTENT_READ: "View articles, drafts and editorial records",
    Permission.CONTENT_WRITE: "Create and edit articles",
    Permission.CONTENT_PUBLISH: "Publish and schedule articles",
    Permission.CONTENT_MODERATE: "Unpublish and archive articles",
    Permission.TAXONOMY_MANAGE: "Create, edit and remove topics, tags and authors",
    Permission.PAGES_READ: "View CMS pages and sections",
    Permission.PAGES_WRITE: "Edit CMS pages and sections",
    Permission.NAVIGATION_MANAGE: "Edit website navigation menus",
    Permission.SETTINGS_MANAGE: "Edit sensitive website settings",
    Permission.USERS_MANAGE: "Create, invite, disable and reset administrator accounts",
    Permission.ROLES_ASSIGN: "Assign and change administrator roles",
    Permission.AUDIT_READ: "Read the audit log",
}


class RoleName(StrEnum):
    SUPER_ADMIN = "super_admin"
    EDITOR = "editor"
    MODERATOR = "moderator"
    ANALYST = "analyst"


@dataclass(frozen=True)
class RoleDefinition:
    name: RoleName
    label: str
    description: str
    permissions: frozenset[Permission]


ROLE_DEFINITIONS: dict[RoleName, RoleDefinition] = {
    RoleName.SUPER_ADMIN: RoleDefinition(
        RoleName.SUPER_ADMIN,
        "Super admin",
        "Full administrative access, including users, roles and settings.",
        frozenset(Permission),
    ),
    RoleName.EDITOR: RoleDefinition(
        RoleName.EDITOR,
        "Editor",
        "Creates, edits and publishes editorial content, taxonomy and pages.",
        frozenset(
            {
                Permission.DASHBOARD_VIEW,
                Permission.CONTENT_READ,
                Permission.CONTENT_WRITE,
                Permission.CONTENT_PUBLISH,
                Permission.CONTENT_MODERATE,
                Permission.TAXONOMY_MANAGE,
                Permission.PAGES_READ,
                Permission.PAGES_WRITE,
            }
        ),
    ),
    RoleName.MODERATOR: RoleDefinition(
        RoleName.MODERATOR,
        "Moderator",
        "Reviews content and can take published content offline.",
        frozenset(
            {
                Permission.DASHBOARD_VIEW,
                Permission.CONTENT_READ,
                Permission.CONTENT_MODERATE,
                Permission.PAGES_READ,
            }
        ),
    ),
    RoleName.ANALYST: RoleDefinition(
        RoleName.ANALYST,
        "Analyst",
        "Read-only access to the dashboard, content listings and analytics.",
        frozenset({Permission.DASHBOARD_VIEW, Permission.ANALYTICS_VIEW, Permission.CONTENT_READ}),
    ),
}

# Backwards-compatible views used across the codebase.
ROLE_PERMISSIONS: dict[RoleName, frozenset[Permission]] = {
    name: role.permissions for name, role in ROLE_DEFINITIONS.items()
}
ROLE_DESCRIPTIONS: dict[RoleName, str] = {
    name: role.description for name, role in ROLE_DEFINITIONS.items()
}


def role_permissions(name: str) -> frozenset[Permission]:
    try:
        return ROLE_DEFINITIONS[RoleName(name)].permissions
    except ValueError:
        return frozenset()  # Unknown role names grant nothing.


def permissions_for_roles(role_names: list[str] | set[str]) -> set[Permission]:
    granted: set[Permission] = set()
    for name in role_names:
        granted |= role_permissions(name)
    return granted


def can_grant_roles(actor_permissions: set[Permission], role_names: list[str]) -> bool:
    """An administrator may only grant roles whose permissions they already hold."""
    if Permission.ROLES_ASSIGN not in actor_permissions:
        return False
    return all(role_permissions(name) <= actor_permissions for name in role_names)
