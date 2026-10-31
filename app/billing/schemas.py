"""Wire shapes for /billing (docs/API.md §7). Money fields are Decimal -> JSON strings."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

RunMode = Literal["dry_run", "live"]
AttemptStatus = Literal["created", "skipped", "failed"]


class RunCreateIn(BaseModel):
    run_date: date | None = None  # default: today (Asia/Kolkata)
    mode: RunMode = "dry_run"


class RetryIn(BaseModel):
    attempt_ids: list[int] | None = None  # None -> all failed attempts in the run


class CatchupOut(BaseModel):
    subscriptions: int
    max_periods: int


class ProjectedOut(BaseModel):
    invoices: int
    subtotal: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal


class AnomalyOut(BaseModel):
    subscription_id: int
    subscription_number: str
    customer_name: str | None
    previous_total: Decimal
    projected_total: Decimal
    change_amount: Decimal
    change_pct: Decimal
    reason: str
    severity: Literal["info", "review"]
    action: str | None


class PreviewRow(BaseModel):
    subscription: str
    period_start: date
    period_end: date
    total: Decimal
    discount_rule: str | None
    reason: str | None


class RunOut(BaseModel):
    """POST /billing/runs, GET /billing/runs/{id}, POST /{id}/retry."""

    run_id: int
    run_date: date
    mode: RunMode
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int
    selected_count: int
    created_count: int
    skipped_count: int
    failed_count: int
    catchup: CatchupOut
    projected: ProjectedOut
    anomalies: list[AnomalyOut] = []
    preview: list[PreviewRow] = []


class RunSummaryOut(BaseModel):
    """List rows (GET /billing/runs) — anomalies/preview are per-run, not listed."""

    model_config = {"from_attributes": True}

    run_id: int
    run_date: date
    mode: RunMode
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int
    selected_count: int
    created_count: int
    skipped_count: int
    failed_count: int
    projected_subtotal: Decimal
    projected_tax: Decimal
    projected_discount: Decimal
    projected_total: Decimal


class RunListOut(BaseModel):
    items: list[RunSummaryOut]
    total: int
    page: int
    page_size: int


class AttemptOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    subscription_id: int
    subscription_number: str | None = None
    period_start: date
    period_end: date
    status: AttemptStatus
    reason: str | None
    invoice_id: int | None
    discount_rule_name: str | None
    projected_total: Decimal | None
    actual_total: Decimal | None
    error_message: str | None
    retry_count: int
    duration_ms: int


class AttemptListOut(BaseModel):
    items: list[AttemptOut]
    total: int
    page: int
    page_size: int