"""Central permission definitions and role-to-permission mapping.

Roles are stored in the database (and assigned per user); what each role is
allowed to do is defined here in code so that permissions cannot be widened
by editing data. The frontend receives the resolved permission list and never
hardcodes role names.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    DASHBOARD_VIEW = "dashboard.view"
    REPORTS_READ = "reports.read"
    CONTENT_READ = "content.read"
    CONTENT_WRITE = "content.write"
    CONTENT_PUBLISH = "content.publish"
    CONTENT_MODERATE = "content.moderate"
    PAGES_READ = "pages.read"
    PAGES_WRITE = "pages.write"
    NAVIGATION_MANAGE = "navigation.manage"
    SETTINGS_MANAGE = "settings.manage"
    USERS_MANAGE = "users.manage"
    AUDIT_READ = "audit.read"


class RoleName(StrEnum):
    SUPER_ADMIN = "super_admin"
    EDITOR = "editor"
    MODERATOR = "moderator"
    ANALYST = "analyst"


ROLE_DESCRIPTIONS: dict[RoleName, str] = {
    RoleName.SUPER_ADMIN: "Full administrative access, including users, roles and settings.",
    RoleName.EDITOR: "Creates, edits and publishes editorial content and pages.",
    RoleName.MODERATOR: "Reviews content and can take published content offline.",
    RoleName.ANALYST: "Read-only access to the dashboard, content listings and reports.",
}

ROLE_PERMISSIONS: dict[RoleName, frozenset[Permission]] = {
    RoleName.SUPER_ADMIN: frozenset(Permission),
    RoleName.EDITOR: frozenset(
        {
            Permission.DASHBOARD_VIEW,
            Permission.CONTENT_READ,
            Permission.CONTENT_WRITE,
            Permission.CONTENT_PUBLISH,
            Permission.CONTENT_MODERATE,
            Permission.PAGES_READ,
            Permission.PAGES_WRITE,
        }
    ),
    RoleName.MODERATOR: frozenset(
        {
            Permission.DASHBOARD_VIEW,
            Permission.CONTENT_READ,
            Permission.CONTENT_MODERATE,
            Permission.PAGES_READ,
        }
    ),
    RoleName.ANALYST: frozenset(
        {Permission.DASHBOARD_VIEW, Permission.REPORTS_READ, Permission.CONTENT_READ}
    ),
}


def permissions_for_roles(role_names: list[str] | set[str]) -> set[Permission]:
    granted: set[Permission] = set()
    for name in role_names:
        try:
            granted |= ROLE_PERMISSIONS[RoleName(name)]
        except ValueError:
            continue  # Unknown role names grant nothing.
    return granted
