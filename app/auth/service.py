"""Auth business logic. Routes stay thin; rules live here."""
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.schemas import RegisterIn, StaffCreateIn
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)

settings = get_settings()
RESET_TOKEN_TTL_MINUTES = 60


def _email_taken(db: Session, email: str) -> bool:
    return db.scalar(select(User).where(User.email == email)) is not None


def register_customer(db: Session, payload: RegisterIn) -> User:
    """Public registration — ALWAYS creates a customer (#6)."""
    email = payload.email.lower()
    if _email_taken(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email,
        name=payload.name,
        role="customer",  # forced server-side; never read from the client
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    db.refresh(user)
    return user


def create_staff(db: Session, payload: StaffCreateIn) -> User:
    """Admin-only staff creation."""
    email = payload.email.lower()
    if _email_taken(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email,
        name=payload.name,
        role="staff",
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    # Same error for unknown email and wrong password — no user enumeration
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    return user


def issue_token(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id, user.role),
        "token_type": "bearer",
        "user": user,
    }


def request_password_reset(db: Session, email: str) -> None:
    """Always returns without error; email may not exist (no enumeration)."""
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active:
        return
    from app.core.mailer import send_password_reset_email

    raw_token = generate_reset_token()
    user.reset_token_hash = hash_reset_token(raw_token)  # store HASH only (#5)
    user.reset_token_expires_at = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    user.reset_sent_at = datetime.now(UTC)
    db.commit()
    send_password_reset_email(user.email, raw_token)


def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    token_hash = hash_reset_token(raw_token)
    user = db.scalar(select(User).where(User.reset_token_hash == token_hash))
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")
    expires = user.reset_token_expires_at
    if expires is None or expires.replace(tzinfo=UTC) < datetime.now(UTC):
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")

    user.password_hash = hash_password(new_password)
    user.reset_token_hash = None  # single-use: token is consumed
    user.reset_token_expires_at = None
    db.commit()


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    user.password_hash = hash_password(new_password)
    db.commit()


def bootstrap_admin(db: Session) -> None:
    """Create the first admin from env on startup — the only non-API admin path."""
    if not settings.admin_email or not settings.admin_password:
        return
    if db.scalar(select(User).where(User.role == "admin")) is not None:
        return
    from app.core.security import validate_password_strength

    if validate_password_strength(settings.admin_password):
        print("[bootstrap] ADMIN_PASSWORD does not meet password rules; admin not created")
        return
    email = settings.admin_email.lower()
    if _email_taken(db, email):
        return
    db.add(
        User(
            email=email,
            name="Administrator",
            role="admin",
            password_hash=hash_password(settings.admin_password),
        )
    )
    db.commit()
    print(f"[bootstrap] admin account created: {email}")
