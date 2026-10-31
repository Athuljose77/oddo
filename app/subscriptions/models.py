"""Subscription entities: the subscription itself, its lines, and its audit trail.

Every status transition appends a SubscriptionEvent row (actor + timestamp) —
the "status history" shown on GET /subscriptions/{id}.
"""
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # SUB-2026-0001
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False, index=True)
    quotation_id: Mapped[int | None] = mapped_column(
        ForeignKey("quotations.id"), nullable=True, unique=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)  # immutable; = start_date
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(50), nullable=True)

    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # next period to bill

    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft", index=True)
    # draft | quotation | confirmed | active | paused | closed

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines: Mapped[list["SubscriptionLine"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list["SubscriptionEvent"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        order_by="SubscriptionEvent.id.desc()",
        lazy="selectin",
    )
    customer = relationship("User", foreign_keys=[customer_id], lazy="joined")
    plan = relationship("Plan", foreign_keys=[plan_id], lazy="joined")

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer else None

    @property
    def plan_name(self) -> str | None:
        return self.plan.name if self.plan else None


class SubscriptionLine(Base):
    __tablename__ = "subscription_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rule_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rules.id"), nullable=True)
    tax_rate: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    subscription: Mapped[Subscription] = relationship(back_populates="lines")
    product = relationship("Product", lazy="joined")

    @property
    def product_name(self) -> str | None:
        return self.product.name if self.product else None


class SubscriptionEvent(Base):
    """Status history row: who moved the subscription, when, and why."""

    __tablename__ = "subscription_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    to_status: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subscription: Mapped[Subscription] = relationship(back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id], lazy="joined")

    @property
    def actor_name(self) -> str | None:
        return self.actor.name if self.actor else None
