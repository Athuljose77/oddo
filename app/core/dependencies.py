"""Shared FastAPI dependencies: DB session, current user, role guards.

Every permission check happens HERE and in route handlers — never only in the UI.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> "User":
    from app.auth.models import User  # local import to avoid circulars

    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or disabled")
    return user


def require_roles(*roles: str):
    """Dependency factory: e.g. Depends(require_roles('admin')) or ('admin','staff')."""

    def checker(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker


# Convenience guards used across modules
require_staff = require_roles("admin", "staff")
require_admin = require_roles("admin")


def get_owned_or_404(owner_id: int, current_user, resource_label: str = "record"):
    """Customer-scope helper: customers may only access their own records.

    Returns 404 (not 403) for other customers' records — no existence leaking.
    """
    if current_user.role == "customer" and current_user.id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{resource_label} not found")
