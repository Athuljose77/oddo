from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.models import User
from app.auth.schemas import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    UserOut,
)
from app.core.database import get_db
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """Public registration always creates a customer account."""
    return service.register_customer(db, payload)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = service.authenticate(db, payload.email, payload.password)
    return service.issue_token(user)


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
def forgot_password(payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    service.request_password_reset(db, payload.email)
    # Always the same response — never reveal whether the email exists
    return {"detail": "If the email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    service.reset_password(db, payload.token, payload.new_password)
    return {"detail": "Password has been reset."}


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    payload: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.change_password(db, user, payload.current_password, payload.new_password)
    return {"detail": "Password changed."}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
