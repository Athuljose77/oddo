from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SubscriptionStatus = Literal["draft", "quotation", "confirmed", "active", "paused", "closed"]


class SubscriptionLineIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal | None = Field(None, ge=0)  # None -> product base price + variant delta
    tax_rule_id: int | None = None


class SubscriptionLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    variant_id: int | None
    description: str | None
    quantity: int
    unit_price: Decimal
    tax_rule_id: int | None
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal
    product_name: str | None = None


class SubscriptionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: str | None
    to_status: str
    actor_id: int | None
    actor_name: str | None = None
    note: str | None
    created_at: datetime


class SubscriptionCreateIn(BaseModel):
    customer_id: int
    plan_id: int
    start_date: date | None = None  # default: today (BILLING_TZ)
    expiry_date: date | None = None
    payment_terms: str | None = Field(None, max_length=50)
    lines: list[SubscriptionLineIn] = Field(min_length=1)


class SubscriptionPatchIn(BaseModel):
    start_date: date | None = None
    expiry_date: date | None = None
    payment_terms: str | None = Field(None, max_length=50)
    lines: list[SubscriptionLineIn] | None = None  # replace-all when present


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    customer_id: int
    customer_name: str | None = None
    plan_id: int
    plan_name: str | None = None
    quotation_id: int | None
    start_date: date
    anchor_date: date
    expiry_date: date | None
    payment_terms: str | None
    next_billing_date: date | None
    last_billing_date: date | None
    status: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    paused_at: datetime | None
    pause_reason: str | None
    closed_at: datetime | None
    close_reason: str | None
    lines: list[SubscriptionLineOut] = []
    events: list[SubscriptionEventOut] = []


class PauseIn(BaseModel):
    reason: str | None = Field(None, max_length=255)


class CloseIn(BaseModel):
    reason: str | None = Field(None, max_length=255)
    early: bool = False  # informational; the server validates against expiry_date


class RenewIn(BaseModel):
    new_expiry_date: date | None = None  # default: extend one cycle
    reason: str | None = Field(None, max_length=255)
