"""SQLAlchemy models. Import every model here so Flask-Migrate detects it."""

from .audit import AuditLog
from .base import TimestampMixin
from .cms import NavigationItem, NavigationMenu, Page, PageSection, SiteSetting
from .content import (
    Article,
    Author,
    ContentRevision,
    MediaAsset,
    Tag,
    Topic,
    article_tags,
    article_topics,
)
from .user import (
    AccountToken,
    PermissionDefinition,
    RefreshToken,
    Role,
    User,
    UserRole,
    role_permissions,
)

__all__ = [
    "AccountToken",
    "Article",
    "AuditLog",
    "PermissionDefinition",
    "role_permissions",
    "Author",
    "ContentRevision",
    "MediaAsset",
    "NavigationItem",
    "NavigationMenu",
    "Page",
    "PageSection",
    "RefreshToken",
    "Role",
    "SiteSetting",
    "Tag",
    "TimestampMixin",
    "Topic",
    "User",
    "UserRole",
    "article_tags",
    "article_topics",
]
