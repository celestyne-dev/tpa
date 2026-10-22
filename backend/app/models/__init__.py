"""SQLAlchemy models.

Batch 01 serves sample content from app/data via the content repository.
Database tables (users, roles, articles, topics, products, orders...) are
introduced in Batch 02 and must be imported here so Flask-Migrate detects them.
"""

from .base import TimestampMixin

__all__ = ["TimestampMixin"]
