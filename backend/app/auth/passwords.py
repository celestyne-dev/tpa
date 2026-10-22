"""Password hashing and policy (Werkzeug scrypt)."""

from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

MIN_LENGTH = 12
MAX_LENGTH = 128
HASH_METHOD = "scrypt"

# Used to keep login timing similar whether or not the email exists.
_DUMMY_HASH = generate_password_hash("timing-equaliser-not-a-real-password", method=HASH_METHOD)


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=HASH_METHOD)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        check_password_hash(_DUMMY_HASH, password)
        return False
    return check_password_hash(password_hash, password)


def password_problems(password: str, *, email: str | None = None) -> list[str]:
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Use at most {MAX_LENGTH} characters.")
    if password.strip() != password:
        problems.append("Do not start or end the password with spaces.")
    if len(set(password)) < 5:
        problems.append("Use a less repetitive password.")
    local = email.split("@")[0].lower() if email else ""
    if len(local) >= 3 and local in password.lower():
        problems.append("Do not include your email name in the password.")
    return problems
