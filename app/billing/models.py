"""Billing engine tables: runs, attempts, invoices, lines, discount redemptions, payments.

Idempotency (docs/CONVENTIONS.md § billing idempotency — do not weaken):
- invoices: UNIQUE(subscription_id, period_start) — the hard guarantee.
- billing_runs: partial UNIQUE(status) WHERE status='running' — one run at a time.
- billing_attempts: UNIQUE(run_id, subscription_id, period_start) — one attempt per
  period; retries UPDATE the row in place (retry_count++), never insert a second.
"""
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

RUNNING_GUARD = text("status = 'running'")


class BillingRun(Base):
    __tablename__ = "billing_runs"
    __table_args__ = (
        Index(
            "uq_billing_runs_one_running",
            "status",
            unique=True,
            postgresql_where=RUNNING_GUARD,
            sqlite_where=RUNNING_GUARD,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)  # dry_run | live
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    # running | completed | completed_with_errors | interrupted
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )  # set when triggered via bill-now (scoped run)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Stored for GET /billing/runs/{id} (projected_* = what the run WOULD bill / did bill)
    projected_subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    projected_tax: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    projected_discount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    projected_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    catchup_subscriptions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catchup_max_periods: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def run_id(self) -> int:
        """Wire name for the run's id (docs/API.md §7 uses run_id everywhere)."""
        return self.id


class BillingAttempt(Base):
    __tablename__ = "billing_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "subscription_id", "period_start", name="uq_attempt_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("billing_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # created | skipped | failed
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # already_invoiced | expired | paused | closed | error
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    discount_rule_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    projected_subtotal: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    projected_tax: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    projected_discount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    projected_total: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_total: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subscription = relationship("app.subscriptions.models.Subscription", lazy="joined")
    invoice = relationship("Invoice", lazy="joined")

    @property
    def subscription_number(self) -> str | None:
        return self.subscription.number if self.subscription else None


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("subscription_id", "period_start", name="uq_invoice_subscription_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # INV-2026-0001
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("billing_runs.id"), nullable=True, index=True)

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")
    # draft | confirmed | paid | cancelled

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rule_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rules.id"), nullable=True)
    tax_rate: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class DiscountRedemption(Base):
    """One row per (rule, invoice) — UNIQUE is the usage-count backstop."""

    __tablename__ = "discount_redemptions"
    __table_args__ = (
        UniqueConstraint("discount_rule_id", "invoice_id", name="uq_redemption_rule_invoice"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discount_rule_id: Mapped[int] = mapped_column(
        ForeignKey("discount_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Payment(Base):
    """Lands with the payments block — table here so invoices can relate."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # bank_transfer|card|cash|upi|cheque|other
    paid_at: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    invoice: Mapped[Invoice] = relationship(back_populates="payments")