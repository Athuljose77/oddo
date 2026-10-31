"""Admin area: staff creation (admin-only) and customer management."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.models import User
from app.auth.schemas import RegisterIn, StaffCreateIn, UserOut, UserPatchIn
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_staff

router = APIRouter(prefix="/api/v1", tags=["admin"])


def _staff_query(db: Session):
    return select(User).where(User.role == "staff").order_by(User.id)


@router.get("/admin/staff", response_model=list[UserOut])
def list_staff(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return db.scalars(_staff_query(db)).all()


@router.post("/admin/staff", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Only the admin can add a member of staff."""
    return service.create_staff(db, payload)


@router.patch("/admin/staff/{user_id}", response_model=UserOut)
def patch_staff(
    user_id: int,
    payload: UserPatchIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None or user.role != "staff":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------- customers

CustomerOut = UserOut  # customers are users with role='customer'


@router.get("/customers", response_model=list[UserOut])
def list_customers(
    q: str | None = Query(None, min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(User).where(User.role == "customer")
    if user.role == "customer":  # defensive: scoped to self
        stmt = stmt.where(User.id == user.id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
    stmt = stmt.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    return db.scalars(stmt).all()


@router.get("/customers/{customer_id}", response_model=UserOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    customer = db.get(User, customer_id)
    if customer is None or customer.role != "customer":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    # Other customers' records → 404 (no existence leaking)
    if user.role == "customer" and user.id != customer.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


@router.post("/customers", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: RegisterIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return service.register_customer(db, payload)


@router.patch("/customers/{customer_id}", response_model=UserOut)
def patch_customer(
    customer_id: int,
    payload: UserPatchIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    customer = db.get(User, customer_id)
    if customer is None or customer.role != "customer":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    if payload.name is not None:
        customer.name = payload.name.strip()
    if payload.is_active is not None:
        customer.is_active = payload.is_active
    db.commit()
    db.refresh(customer)
    return customer


# count helper used by M2's reports later; keep query import warm
_ = func
