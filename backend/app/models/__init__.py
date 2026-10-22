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
from .user import RefreshToken, Role, User, UserRole

__all__ = [
    "Article",
    "AuditLog",
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
