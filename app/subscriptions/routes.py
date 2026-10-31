"""Subscription endpoints. Staff manage all; customers self-serve on their own.

Customer-allowed actions (docs/API.md §6): view, confirm, pause, resume, close
— own subscriptions only, same plan guards as staff.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_staff
from app.core.pagination import paginate
from app.subscriptions import service
from app.subscriptions.models import Subscription
from app.subscriptions.schemas import (
    CloseIn,
    PauseIn,
    RenewIn,
    SubscriptionCreateIn,
    SubscriptionOut,
    SubscriptionPatchIn,
)

router = APIRouter(prefix="/api/v1", tags=["subscriptions"])

# The subset of transitions a customer may trigger on their OWN subscription
CUSTOMER_ACTIONS = {"confirm", "pause", "resume", "close"}


def _subscription_visible(db: Session, subscription_id: int, user) -> Subscription:
    """Staff see everything; customers see only their own (404 otherwise)."""
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    if user.role == "customer" and sub.customer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    return sub


def _ensure_customer_action(user, action: str) -> None:
    if user.role == "customer" and action not in CUSTOMER_ACTIONS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")


@router.get("/subscriptions")
def list_subscriptions(
    sub_status: str | None = Query(None, alias="status"),
    plan_id: int | None = None,
    customer_id: int | None = None,
    q: str | None = Query(None, min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = select(Subscription)
    if user.role == "customer":
        stmt = stmt.where(Subscription.customer_id == user.id)  # forced server-side scope
    elif customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    if sub_status:
        stmt = stmt.where(Subscription.status == sub_status)
    if plan_id:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if q:
        from app.auth.models import User

        stmt = stmt.join(Subscription.customer).where(
            or_(Subscription.number.ilike(f"%{q}%"), User.name.ilike(f"%{q}%"))
        )
    return paginate(db, stmt.order_by(Subscription.id.desc()), page, page_size)


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: SubscriptionCreateIn,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    return service.create_subscription(db, payload, user)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionOut)
def get_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return _subscription_visible(db, subscription_id, user)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionOut)
def patch_subscription(
    subscription_id: int,
    payload: SubscriptionPatchIn,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    subscription = _subscription_visible(db, subscription_id, user)
    return service.patch_subscription(db, subscription, payload)


@router.post("/subscriptions/{subscription_id}/send", response_model=SubscriptionOut)
def send_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(db, subscription, "quotation", user)


@router.post("/subscriptions/{subscription_id}/revise", response_model=SubscriptionOut)
def revise_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(db, subscription, "draft", user)


@router.post("/subscriptions/{subscription_id}/confirm", response_model=SubscriptionOut)
def confirm_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_customer_action(user, "confirm")
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(db, subscription, "confirmed", user)


@router.post("/subscriptions/{subscription_id}/activate", response_model=SubscriptionOut)
def activate_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(db, subscription, "active", user)


@router.post("/subscriptions/{subscription_id}/pause", response_model=SubscriptionOut)
def pause_subscription(
    subscription_id: int,
    payload: PauseIn | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_customer_action(user, "pause")
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(db, subscription, "paused", user, reason=payload.reason if payload else None)


@router.post("/subscriptions/{subscription_id}/resume", response_model=SubscriptionOut)
def resume_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_customer_action(user, "resume")
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(db, subscription, "active", user)


@router.post("/subscriptions/{subscription_id}/renew", response_model=SubscriptionOut)
def renew_subscription(
    subscription_id: int,
    payload: RenewIn | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(
        db,
        subscription,
        "active",
        user,
        reason=payload.reason if payload else None,
        new_expiry_date=payload.new_expiry_date if payload else None,
    )


@router.post("/subscriptions/{subscription_id}/close", response_model=SubscriptionOut)
def close_subscription(
    subscription_id: int,
    payload: CloseIn | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_customer_action(user, "close")
    subscription = _subscription_visible(db, subscription_id, user)
    return service.transition(db, subscription, "closed", user, reason=payload.reason if payload else None)


@router.post("/subscriptions/{subscription_id}/bill-now")
def bill_subscription_now(
    subscription_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    _subscription_visible(db, subscription_id, user)
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Single-subscription billing lands with the billing engine — see docs/API.md status table",
    )
