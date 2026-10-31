"""Catalog entities: products, variants, plans, tax rules, discount rules."""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
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


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="subscription")
    sales_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )


class ProductVariant(Base):
    """e.g. attribute='Brand', value='Odoo', price_delta=560."""

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "attribute", "value", name="uq_variant_attr_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attribute: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    price_delta: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    product: Mapped[Product] = relationship(back_populates="variants")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(10), nullable=False)  # daily|weekly|monthly|yearly
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    available_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Plan-by-plan behaviour (problem statement: admin decides, plan by plan)
    auto_close: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_early_close: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_pause: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")  # active|closed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TaxRule(Base):
    __tablename__ = "tax_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)  # percent
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=10)  # lower wins
    tax_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DiscountRule(Base):
    __tablename__ = "discount_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # fixed|percentage
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    min_purchase: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    min_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[date] = mapped_column(Date, nullable=False)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # engine increments
    scope: Mapped[str] = mapped_column(String(15), nullable=False, default="subscription")
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
