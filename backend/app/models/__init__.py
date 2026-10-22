"""SQLAlchemy models. Import every model here so Flask-Migrate detects it."""

from .audit import AuditLog
from .base import TimestampMixin
from .cms import (
    Announcement,
    GlobalCta,
    NavigationItem,
    NavigationMenu,
    Page,
    PageRevision,
    PageSection,
    ReusableSection,
    SiteSetting,
)
from .content import (
    Article,
    ArticleRevision,
    Author,
    ContentRevision,
    MediaAsset,
    MediaVariant,
    Tag,
    Topic,
    article_tags,
    article_topics,
)
from .publishing import PublishJob, Redirect
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
    "Announcement",
    "GlobalCta",
    "PageRevision",
    "ReusableSection",
    "Article",
    "ArticleRevision",
    "MediaVariant",
    "PublishJob",
    "Redirect",
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
