"""Wire shapes for /invoices (API.md §8) and /payments (§9).

Money fields are Decimal → serialised as JSON strings per docs/CONVENTIONS.md.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator

InvoiceStatus = Literal["draft", "confirmed", "paid", "cancelled"]
PaymentState = Literal["unpaid", "partial", "paid", "overpaid"]
PaymentMethod = Literal["bank_transfer", "card", "cash", "upi", "cheque", "other"]


# ------------------------------------------------------------------ invoice lines
class InvoiceLineOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    product_id: int
    variant_id: int | None
    description: str | None
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal


# ------------------------------------------------------------------ invoice detail
class InvoiceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    number: str
    subscription_id: int
    customer_id: int
    run_id: int | None

    period_start: date
    period_end: date
    issue_date: date
    due_date: date

    status: InvoiceStatus
    payment_state: PaymentState  # derived (not stored)
    is_overdue: bool             # derived
    days_overdue: int            # derived (0 when not overdue)

    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total: Decimal
    paid_amount: Decimal
    outstanding: Decimal         # derived = total - paid_amount

    sent_at: datetime | None
    last_printed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    lines: list[InvoiceLineOut] = []
    payments: list["PaymentOut"] = []


class InvoiceSummaryOut(BaseModel):
    """Light row for list responses — no lines/payments."""
    model_config = {"from_attributes": True}

    id: int
    number: str
    subscription_id: int
    customer_id: int
    run_id: int | None

    period_start: date
    period_end: date
    issue_date: date
    due_date: date

    status: InvoiceStatus
    payment_state: PaymentState
    is_overdue: bool
    days_overdue: int

    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total: Decimal
    paid_amount: Decimal
    outstanding: Decimal


class InvoiceListOut(BaseModel):
    items: list[InvoiceSummaryOut]
    total: int
    page: int
    page_size: int


# ------------------------------------------------------------------ payment
class PaymentCreateIn(BaseModel):
    invoice_id: int
    amount: Decimal
    method: PaymentMethod
    paid_at: date
    note: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be > 0")
        return v


class PaymentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    invoice_id: int
    amount: Decimal
    method: PaymentMethod
    paid_at: date
    note: str | None
    recorded_by: int | None
    created_at: datetime


class PaymentResponseOut(BaseModel):
    """POST /payments response: the new payment + updated invoice snapshot."""
    payment: PaymentOut
    invoice: InvoiceSummaryOut


class PaymentListOut(BaseModel):
    items: list[PaymentOut]
    total: int
    page: int
    page_size: int


# allow forward ref
InvoiceOut.model_rebuild()
