"""Reusable authorization helpers used by every admin resource."""

from __future__ import annotations

from functools import wraps

from flask import current_app, request
from flask_jwt_extended import current_user, verify_jwt_in_request

from ..models import User
from ..utils.errors import ForbiddenError
from .permissions import Permission
from .rbac import effective_permissions, has_permissions

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def user_permissions(user: User) -> set[str]:
    return effective_permissions(user)


def has_permission(user: User, *perms: Permission | str) -> bool:
    return has_permissions(user, *perms)


def has_any_permission(user: User, *perms: Permission | str) -> bool:
    granted = effective_permissions(user)
    return any(str(p) in granted for p in perms)


def check_origin() -> None:
    """Reject state-changing requests from untrusted browser origins."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("Origin")
    if not origin:
        return  # Non-browser clients; CSRF tokens still apply to cookie sessions.
    allowed = set(current_app.config.get("CORS_ORIGINS", []))
    allowed.add(request.host_url.rstrip("/"))
    if origin.rstrip("/") not in allowed:
        raise ForbiddenError("Requests from this origin are not allowed.")


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        return fn(*args, **kwargs)

    return wrapper


def require_permission(*perms: Permission):
    """Require an authenticated, active administrator holding every given permission."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if not has_permission(current_user, *perms):
                raise ForbiddenError()
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(*perms: Permission):
    """Require an authenticated administrator holding at least one of the permissions."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if not has_any_permission(current_user, *perms):
                raise ForbiddenError()
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def current_admin() -> User:
    return current_user
