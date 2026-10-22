from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

USER_STATUSES = ("active", "disabled")


class Role(db.Model):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class UserRole(db.Model):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    assigned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    role: Mapped[Role] = relationship(lazy="joined")


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"status IN {USER_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lower-cased; uniqueness is therefore case-insensitive.
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Incremented to invalidate every outstanding access token (password change, disable).
    session_version: Mapped[int] = mapped_column(default=1, nullable=False)

    role_links: Mapped[list[UserRole]] = relationship(
        foreign_keys=[UserRole.user_id], cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_names(self) -> list[str]:
        return sorted(link.role.name for link in self.role_links)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class RefreshToken(db.Model):
    """Server-side record of each issued refresh token (enables rotation and revocation)."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_active", "user_id", "revoked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    replaced_by_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)


TOKEN_PURPOSES = ("invitation", "password_reset")


class AccountToken(db.Model):
    """Single-use, time-limited account tokens (invitations and password resets).

    Only a SHA-256 hash of the random token is stored; the token itself exists
    only in the delivered link.
    """

    __tablename__ = "account_tokens"
    __table_args__ = (
        CheckConstraint(f"purpose IN {TOKEN_PURPOSES}", name="purpose_valid"),
        Index("ix_account_tokens_purpose_email", "purpose", "email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    roles: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivery: Mapped[str] = mapped_column(String(30), default="", nullable=False)

    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    def status(self, now: datetime | None = None) -> str:
        now = now or utcnow()
        if self.revoked_at:
            return "revoked"
        if self.used_at:
            return "accepted" if self.purpose == "invitation" else "used"
        if self.expires_at <= now:
            return "expired"
        return "pending"
