"""Quotation templates and actual quotation records (separate entities, per spec)."""
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class QuoteTemplate(Base):
    __tablename__ = "quote_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    payment_terms: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lines: Mapped[list["QuoteTemplateLine"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", lazy="selectin"
    )


class QuoteTemplateLine(Base):
    __tablename__ = "quote_template_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("quote_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rule_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rules.id"), nullable=True)

    template: Mapped[QuoteTemplate] = relationship(back_populates="lines")


class Quotation(Base):
    __tablename__ = "quotations"
    __table_args__ = (UniqueConstraint("subscription_id", name="uq_quotation_subscription"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # QUO-2026-0001
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("quote_templates.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    # draft | sent | confirmed | expired | cancelled   (expired is lazily derived from valid_until)
    subscription_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set once, UQ
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines: Mapped[list["QuotationLine"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", lazy="selectin"
    )
    customer = relationship("User", foreign_keys=[customer_id], lazy="joined")

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer else None

    @property
    def plan_name(self) -> str | None:
        return self.plan.name if self.plan else None

    plan = relationship("Plan", foreign_keys=[plan_id], lazy="joined")


class QuotationLine(Base):
    __tablename__ = "quotation_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True
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

    quotation: Mapped[Quotation] = relationship(back_populates="lines")
    product = relationship("Product", lazy="joined")

    @property
    def product_name(self) -> str | None:
        return self.product.name if self.product else None
