"""Invoice endpoints (docs/API.md §8, staff+; customers read their own).

Lifecycle: draft → confirmed → paid  (+  cancelled from draft only)
payment_state / is_overdue / outstanding are derived at read time, never stored.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.billing import invoice_service as svc
from app.billing.invoice_schemas import (
    InvoiceListOut,
    InvoiceOut,
    InvoiceSummaryOut,
    PaymentCreateIn,
    PaymentListOut,
    PaymentOut,
    PaymentResponseOut,
)
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_staff

router = APIRouter(prefix="/api/v1", tags=["invoices"])


def _to_invoice_out(inv) -> InvoiceOut:
    """Convert enriched Invoice ORM + derived attrs → InvoiceOut."""
    return InvoiceOut(
        id=inv.id,
        number=inv.number,
        subscription_id=inv.subscription_id,
        customer_id=inv.customer_id,
        run_id=inv.run_id,
        period_start=inv.period_start,
        period_end=inv.period_end,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        status=inv.status,
        payment_state=inv._payment_state,
        is_overdue=inv._is_overdue,
        days_overdue=inv._days_overdue,
        subtotal=inv.subtotal,
        tax_total=inv.tax_total,
        discount_total=inv.discount_total,
        total=inv.total,
        paid_amount=inv.paid_amount,
        outstanding=inv._outstanding,
        sent_at=inv.sent_at,
        last_printed_at=inv.last_printed_at,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        lines=inv.lines,
        payments=inv.payments,
    )


def _to_summary(inv) -> InvoiceSummaryOut:
    return InvoiceSummaryOut(
        id=inv.id,
        number=inv.number,
        subscription_id=inv.subscription_id,
        customer_id=inv.customer_id,
        run_id=inv.run_id,
        period_start=inv.period_start,
        period_end=inv.period_end,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        status=inv.status,
        payment_state=inv._payment_state,
        is_overdue=inv._is_overdue,
        days_overdue=inv._days_overdue,
        subtotal=inv.subtotal,
        tax_total=inv.tax_total,
        discount_total=inv.discount_total,
        total=inv.total,
        paid_amount=inv.paid_amount,
        outstanding=inv._outstanding,
    )


# ------------------------------------------------------------------ list

@router.get("/invoices", response_model=InvoiceListOut)
def list_invoices(
    inv_status: str | None = Query(None, alias="status", pattern="^(draft|confirmed|paid|cancelled)$"),
    payment_status: str | None = Query(None, pattern="^(unpaid|partial|paid|overpaid)$"),
    overdue: bool | None = Query(None),
    customer_id: int | None = Query(None),
    subscription_id: int | None = Query(None),
    issued_from: date | None = Query(None),
    issued_to: date | None = Query(None),
    q: str | None = Query(None),
    sort: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    result = svc.list_invoices(
        db,
        inv_status=inv_status,
        payment_status=payment_status,
        overdue=overdue,
        customer_id=customer_id,
        subscription_id=subscription_id,
        issued_from=issued_from,
        issued_to=issued_to,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
        current_user=user,
    )
    return {
        **result,
        "items": [_to_summary(i) for i in result["items"]],
    }


# ------------------------------------------------------------------ detail

@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    inv = svc.get_invoice_or_404(db, invoice_id)
    # Customer scope: 404 on other customers' invoices (no existence leaking)
    if user.role == "customer" and inv.customer_id != user.id:
        from fastapi import HTTPException
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return _to_invoice_out(svc.enrich(inv))


# ------------------------------------------------------------------ transitions

@router.post("/invoices/{invoice_id}/confirm", response_model=InvoiceOut)
def confirm_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    return _to_invoice_out(svc.confirm_invoice(db, invoice_id))


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    return _to_invoice_out(svc.cancel_invoice(db, invoice_id))


@router.post("/invoices/{invoice_id}/send", response_model=InvoiceOut)
def send_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_staff),
):
    return _to_invoice_out(svc.send_invoice(db, invoice_id))


@router.get("/invoices/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from datetime import datetime, timezone
    from fastapi import HTTPException, Response
    from app.core.pdf import generate_invoice_pdf

    inv = svc.get_invoice_or_404(db, invoice_id)
    if user.role == "customer" and inv.customer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")

    enriched = svc.enrich(inv)
    inv.last_printed_at = datetime.now(timezone.utc)
    db.commit()

    pdf_bytes = generate_invoice_pdf(enriched)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{inv.number}.pdf"'},
    )
