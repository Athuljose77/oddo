from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BillingCycle = Literal["daily", "weekly", "monthly", "yearly"]
DiscountType = Literal["fixed", "percentage"]
DiscountScope = Literal["product", "subscription"]


# ------------------------------------------------------------------ products
class VariantCreateIn(BaseModel):
    attribute: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=120)
    price_delta: Decimal = Decimal("0")


class VariantPatchIn(BaseModel):
    attribute: str | None = Field(None, min_length=1, max_length=80)
    value: str | None = Field(None, min_length=1, max_length=120)
    price_delta: Decimal | None = None


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    attribute: str
    value: str
    price_delta: Decimal


class ProductCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    type: str = Field(default="subscription", min_length=1, max_length=50)
    sales_price: Decimal = Field(default=Decimal("0"), ge=0)
    cost_price: Decimal | None = Field(None, ge=0)
    notes: str | None = None


class ProductPatchIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    type: str | None = Field(None, min_length=1, max_length=50)
    sales_price: Decimal | None = Field(None, ge=0)
    cost_price: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    sales_price: Decimal
    cost_price: Decimal | None
    notes: str | None
    is_active: bool
    variants: list[VariantOut] = []


# --------------------------------------------------------------------- plans
class PlanCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    billing_cycle: BillingCycle
    price: Decimal = Field(default=Decimal("0"), ge=0)
    min_quantity: int = Field(default=1, ge=1)
    available_from: date | None = None
    available_to: date | None = None
    auto_close: bool = True
    allow_early_close: bool = True
    allow_pause: bool = True
    allow_renew: bool = True

    @model_validator(mode="after")
    def _dates_ordered(self):
        if self.available_from and self.available_to and self.available_from > self.available_to:
            raise ValueError("available_from must be on or before available_to")
        return self


class PlanPatchIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    billing_cycle: BillingCycle | None = None
    price: Decimal | None = Field(None, ge=0)
    min_quantity: int | None = Field(None, ge=1)
    available_from: date | None = None
    available_to: date | None = None
    auto_close: bool | None = None
    allow_early_close: bool | None = None
    allow_pause: bool | None = None
    allow_renew: bool | None = None


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    billing_cycle: BillingCycle
    price: Decimal
    min_quantity: int
    available_from: date | None
    available_to: date | None
    auto_close: bool
    allow_early_close: bool
    allow_pause: bool
    allow_renew: bool
    status: str


# ---------------------------------------------------------------- tax rules
class TaxRuleCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rate: Decimal = Field(ge=0, le=100)
    product_id: int | None = None
    priority: int = Field(default=10, ge=0)
    tax_included: bool = False
    is_active: bool = True


class TaxRulePatchIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    rate: Decimal | None = Field(None, ge=0, le=100)
    product_id: int | None = None
    priority: int | None = Field(None, ge=0)
    is_active: bool | None = None
    # tax_included intentionally absent: fixed at creation (docs/API.md)


class TaxRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rate: Decimal
    product_id: int | None
    priority: int
    tax_included: bool
    is_active: bool


# ----------------------------------------------------------- discount rules
class DiscountRuleCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: DiscountType
    value: Decimal = Field(gt=0)
    min_purchase: Decimal | None = Field(None, ge=0)
    min_quantity: int | None = Field(None, ge=1)
    starts_at: date
    ends_at: date | None = None
    usage_limit: int | None = Field(None, ge=1)
    scope: DiscountScope = "subscription"
    product_id: int | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _validate(self):
        if self.type == "percentage" and self.value > 100:
            raise ValueError("percentage discount cannot exceed 100")
        if self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must be on or after starts_at")
        if self.scope == "product" and self.product_id is None:
            raise ValueError("product_id is required for product-scoped discounts")
        return self


class DiscountRulePatchIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    value: Decimal | None = Field(None, gt=0)
    min_purchase: Decimal | None = Field(None, ge=0)
    min_quantity: int | None = Field(None, ge=1)
    starts_at: date | None = None
    ends_at: date | None = None
    usage_limit: int | None = Field(None, ge=1)
    is_active: bool | None = None
    # used_count is engine-owned: never client-settable


class DiscountRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: DiscountType
    value: Decimal
    min_purchase: Decimal | None
    min_quantity: int | None
    starts_at: date
    ends_at: date | None
    usage_limit: int | None
    used_count: int
    scope: DiscountScope
    product_id: int | None
    is_active: bool
