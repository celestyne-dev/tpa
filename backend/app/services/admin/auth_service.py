from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from ...auth.decorators import user_permissions
from ...auth.passwords import hash_password, password_problems, verify_password
from ...extensions import db
from ...models import User
from ...utils.errors import ValidationError
from ..serializers import iso

GENERIC_LOGIN_ERROR = "Invalid email or password."


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def authenticate(email: str, password: str) -> User | None:
    """Return the user for valid credentials; None otherwise (never says which part failed)."""
    user = db.session.scalar(select(User).where(User.email == normalise_email(email)))
    valid = verify_password(user.password_hash if user else None, password or "")
    if user is None or not valid or not user.is_active:
        return None
    user.last_login_at = datetime.now(UTC)
    return user


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "status": user.status,
        "roles": user.role_names,
        "permissions": sorted(p.value for p in user_permissions(user)),
        "last_login_at": iso(user.last_login_at),
        "email_verified_at": iso(user.email_verified_at),
        "created_at": iso(user.created_at),
    }


def change_password(user: User, current: str, new: str) -> None:
    if not verify_password(user.password_hash, current or ""):
        raise ValidationError(details={"current_password": ["The current password is incorrect."]})
    problems = password_problems(new or "", email=user.email)
    if verify_password(user.password_hash, new or ""):
        problems.append("Choose a password different from the current one.")
    if problems:
        raise ValidationError(details={"new_password": problems})
    user.password_hash = hash_password(new)
