"""Password hashing, JWT issue/verify, reset-token hashing.

- Passwords: bcrypt (never plaintext).
- Reset tokens: raw token sent via link, only its SHA-256 hash is stored.
"""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()

SPECIAL_CHAR_MESSAGE = "Password must be more than 8 characters and include an uppercase letter, a lowercase letter and a special character."


def validate_password_strength(password: str) -> str:
    """Enforce the problem-statement password rules. Returns error text or ''."""
    if len(password) <= 8:
        return SPECIAL_CHAR_MESSAGE
    if not any(c.isupper() for c in password):
        return SPECIAL_CHAR_MESSAGE
    if not any(c.islower() for c in password):
        return SPECIAL_CHAR_MESSAGE
    if not any(not c.isalnum() for c in password):
        return SPECIAL_CHAR_MESSAGE
    return ""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
