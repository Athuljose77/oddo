"""Invoice & payment service functions (docs/API.md §8–9).

All writes go through here; routes are thin (docs/CONVENTIONS.md).

Key rules:
- Money is Decimal throughout — never float in returned dicts.
- payment_state / is_overdue / outstanding are derived at read time.
- Invoices auto-advance to 'paid' when paid_amount >= total (inside payment tx).
- Cancellation requires zero payments (409 otherwise).
- ALLOW_OVERPAYMENT env flag controls whether payment > outstanding is accepted.
"""
from datetime import date, datetime, UTC
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.billing.models import Invoice, Payment
from app.core.config import get_settings

settings = get_settings()
TODAY = date.today


# ------------------------------------------------------------------ helpers

def _today() -> date:
    """Isolated so tests can monkeypatch."""
    return date.today()


def _payment_state(invoice: Invoice) -> str:
    """Derive payment_state from paid_amount vs total."""
    total = Decimal(str(invoice.total))
    paid = Decimal(str(invoice.paid_amount))
    if paid <= 0:
        return "unpaid"
    if paid >= total:
        return "overpaid" if paid > total else "paid"
    return "partial"


def _is_overdue(invoice: Invoice, today: date | None = None) -> bool:
    today = today or _today()
    if invoice.status not in ("confirmed",):
        return False
    return invoice.due_date < today and Decimal(str(invoice.paid_amount)) < Decimal(str(invoice.total))


def _days_overdue(invoice: Invoice, today: date | None = None) -> int:
    today = today or _today()
    if not _is_overdue(invoice, today):
        return 0
    return (today - invoice.due_date).days


def _outstanding(invoice: Invoice) -> Decimal:
    return max(Decimal("0"), Decimal(str(invoice.total)) - Decimal(str(invoice.paid_amount)))


def enrich(invoice: Invoice, today: date | None = None) -> dict:
    """Return the invoice ORM object augmented with derived fields as a dict
    that Pydantic can validate via from_attributes=True after we inject extras.
    """
    today = today or _today()
    # We can't set attributes on the mapped object easily, so we build a shim.
    invoice._payment_state = _payment_state(invoice)
    invoice._is_overdue = _is_overdue(invoice, today)
    invoice._days_overdue = _days_overdue(invoice, today)
    invoice._outstanding = _outstanding(invoice)
    return invoice


# ------------------------------------------------------------------ invoice reads

def get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return inv


def list_invoices(
    db: Session,
    *,
    inv_status: str | None = None,
    payment_status: str | None = None,
    overdue: bool | None = None,
    customer_id: int | None = None,
    subscription_id: int | None = None,
    issued_from: date | None = None,
    issued_to: date | None = None,
    q: str | None = None,
    sort: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user=None,
) -> dict:
    from app.core.pagination import paginate

    stmt = select(Invoice)

    # Customer scope: customers see only their own invoices
    if current_user and current_user.role == "customer":
        stmt = stmt.where(Invoice.customer_id == current_user.id)
    elif customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)

    if subscription_id:
        stmt = stmt.where(Invoice.subscription_id == subscription_id)
    if inv_status:
        stmt = stmt.where(Invoice.status == inv_status)
    if issued_from:
        stmt = stmt.where(Invoice.issue_date >= issued_from)
    if issued_to:
        stmt = stmt.where(Invoice.issue_date <= issued_to)

    today = _today()

    if overdue is True:
        stmt = stmt.where(
            Invoice.status == "confirmed",
            Invoice.due_date < today,
        )

    stmt = stmt.order_by(Invoice.id.desc())
    result = paginate(db, stmt, page, page_size)

    enriched = [enrich(inv, today) for inv in result["items"]]

    # Post-filter payment_state (derived — can't SQL-filter easily)
    if payment_status:
        enriched = [i for i in enriched if _payment_state(i) == payment_status]

    return {**result, "items": enriched}


# ------------------------------------------------------------------ invoice transitions

def confirm_invoice(db: Session, invoice_id: int) -> Invoice:
    inv = get_invoice_or_404(db, invoice_id)
    if inv.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Invoice is '{inv.status}', expected 'draft'")
    inv.status = "confirmed"
    db.commit()
    db.refresh(inv)
    return enrich(inv)


def cancel_invoice(db: Session, invoice_id: int) -> Invoice:
    inv = get_invoice_or_404(db, invoice_id)
    if inv.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Invoice is '{inv.status}', expected 'draft'")
    if inv.payments:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot cancel invoice with recorded payments")
    inv.status = "cancelled"
    db.commit()
    db.refresh(inv)
    return enrich(inv)


def send_invoice(db: Session, invoice_id: int) -> Invoice:
    inv = get_invoice_or_404(db, invoice_id)
    if inv.status not in ("draft", "confirmed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Invoice is '{inv.status}'; can only send draft or confirmed invoices",
        )
    inv.sent_at = datetime.now(UTC)
    if inv.status == "draft":
        inv.status = "confirmed"
    db.commit()
    db.refresh(inv)
    return enrich(inv)


# ------------------------------------------------------------------ payments

def record_payment(db: Session, payload, recorded_by_id: int) -> dict:
    """Create a payment and update invoice.paid_amount; auto-mark paid when settled."""
    from app.billing.invoice_schemas import PaymentCreateIn

    inv = get_invoice_or_404(db, payload.invoice_id)

    if inv.status not in ("confirmed",):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Invoice is '{inv.status}'; payments can only be recorded against confirmed invoices",
        )

    amount = Decimal(str(payload.amount))
    outstanding = _outstanding(inv)

    allow_overpayment = getattr(settings, "allow_overpayment", False)
    if amount > outstanding and not allow_overpayment:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Payment amount {amount} exceeds outstanding {outstanding}. "
            "Set ALLOW_OVERPAYMENT=true to allow.",
        )

    payment = Payment(
        invoice_id=inv.id,
        amount=amount,
        method=payload.method,
        paid_at=payload.paid_at,
        note=payload.note,
        recorded_by=recorded_by_id,
    )
    db.add(payment)

    new_paid = Decimal(str(inv.paid_amount)) + amount
    inv.paid_amount = new_paid
    if new_paid >= Decimal(str(inv.total)):
        inv.status = "paid"

    db.commit()
    db.refresh(payment)
    db.refresh(inv)

    return {"payment": payment, "invoice": enrich(inv)}


def list_payments(
    db: Session,
    *,
    invoice_id: int | None = None,
    method: str | None = None,
    paid_from: date | None = None,
    paid_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    from app.core.pagination import paginate

    stmt = select(Payment)
    if invoice_id:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    if method:
        stmt = stmt.where(Payment.method == method)
    if paid_from:
        stmt = stmt.where(Payment.paid_at >= paid_from)
    if paid_to:
        stmt = stmt.where(Payment.paid_at <= paid_to)
    stmt = stmt.order_by(Payment.id.desc())
    return paginate(db, stmt, page, page_size)
