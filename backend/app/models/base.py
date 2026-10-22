from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from .types import UTCDateTime, utcnow


class TimestampMixin:
    """Created/updated timestamps (timezone-aware UTC)."""

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
