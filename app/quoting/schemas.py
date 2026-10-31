from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QuotationStatus = Literal["draft", "sent", "confirmed", "expired", "cancelled"]


# ------------------------------------------------------ templates
class TemplateLineIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rule_id: int | None = None


class TemplateLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    tax_rule_id: int | None


class TemplateCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    validity_days: int = Field(default=7, ge=1, le=365)
    payment_terms: str | None = Field(None, max_length=50)
    plan_id: int | None = None
    lines: list[TemplateLineIn] = Field(default_factory=list)


class TemplatePatchIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    validity_days: int | None = Field(None, ge=1, le=365)
    payment_terms: str | None = Field(None, max_length=50)
    plan_id: int | None = None
    is_active: bool | None = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    validity_days: int
    payment_terms: str | None
    plan_id: int | None
    is_active: bool
    lines: list[TemplateLineOut] = []


# ------------------------------------------------------ quotations
class QuotationLineIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal | None = Field(None, ge=0)  # None -> product base price + variant delta
    tax_rule_id: int | None = None


class QuotationLineOut(BaseModel):
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


class QuotationCreateIn(BaseModel):
    customer_id: int
    template_id: int | None = None
    plan_id: int | None = None
    start_date: date | None = None
    payment_terms: str | None = Field(None, max_length=50)
    validity_days: int | None = Field(None, ge=1, le=365)
    notes: str | None = None
    lines: list[QuotationLineIn] | None = None  # None -> take template lines (template required)


class QuotationPatchIn(BaseModel):
    plan_id: int | None = None
    start_date: date | None = None
    payment_terms: str | None = Field(None, max_length=50)
    validity_days: int | None = Field(None, ge=1, le=365)
    notes: str | None = None
    lines: list[QuotationLineIn] | None = None  # replace-all when present


class QuotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    customer_id: int
    customer_name: str | None = None
    plan_id: int | None
    plan_name: str | None = None
    template_id: int | None
    valid_until: date | None
    payment_terms: str | None
    start_date: date | None
    status: str
    subscription_id: int | None
    notes: str | None
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    lines: list[QuotationLineOut] = []
