"""Payment endpoints (docs/API.md §9, staff+; customers read own invoice payments).

POST /payments  — record a payment, auto-marks invoice 'paid' when settled.
GET  /payments  — list with filters.
GET  /payments/{id} — detail.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.billing import invoice_service as svc
from app.billing.invoice_schemas import (
    PaymentCreateIn,
    PaymentListOut,
    PaymentOut,
    PaymentResponseOut,
)
from app.billing.invoice_routes import _to_summary
from app.billing.models import Payment
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_staff

router = APIRouter(prefix="/api/v1", tags=["payments"])


def _payment_or_404(db, payment_id: int) -> Payment:
    from fastapi import HTTPException
    p = db.get(Payment, payment_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return p


@router.post("/payments", response_model=PaymentResponseOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreateIn,
    db: Session = Depends(get_db),
    user=Depends(require_staff),
):
    result = svc.record_payment(db, payload, recorded_by_id=user.id)
    return PaymentResponseOut(
        payment=PaymentOut.model_validate(result["payment"]),
        invoice=_to_summary(result["invoice"]),
    )


@router.get("/payments", response_model=PaymentListOut)
def list_payments(
    invoice_id: int | None = Query(None),
    method: str | None = Query(
        None,
        pattern="^(bank_transfer|card|cash|upi|cheque|other)$",
    ),
    paid_from: date | None = Query(None),
    paid_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # Customers may only view payments on their own invoices
    if user.role == "customer" and invoice_id is not None:
        inv = svc.get_invoice_or_404(db, invoice_id)
        if inv.customer_id != user.id:
            from fastapi import HTTPException
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    elif user.role == "customer" and invoice_id is None:
        # Require invoice_id scope for customers (can't list all payments)
        from fastapi import HTTPException
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Customers must filter by invoice_id",
        )

    return svc.list_payments(
        db,
        invoice_id=invoice_id,
        method=method,
        paid_from=paid_from,
        paid_to=paid_to,
        page=page,
        page_size=page_size,
    )


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    payment = _payment_or_404(db, payment_id)
    # Customer scope: ensure they own the invoice this payment is on
    if user.role == "customer":
        inv = svc.get_invoice_or_404(db, payment.invoice_id)
        if inv.customer_id != user.id:
            from fastapi import HTTPException
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return PaymentOut.model_validate(payment)
