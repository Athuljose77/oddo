"""Quotation logic: template prefill, line computation, lifecycle helpers.

Conversion to a subscription (confirm) lands together with the subscriptions
module — until then confirm returns 501 and API.md marks it not implemented.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.billing.tax_engine import compute_line_amounts, get_applicable_tax
from app.catalog.models import Product, ProductVariant, TaxRule
from app.core.config import get_settings
from app.core.sequences import next_number
from app.quoting.models import Quotation, QuotationLine, QuoteTemplate
from app.quoting.schemas import QuotationLineIn

settings = get_settings()
TWO_PLACES = Decimal("0.01")


def today() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(settings.billing_tz)).date()


def default_validity_days() -> int:
    return 7


def resolve_lines(db: Session, raw_lines: list[QuotationLineIn]) -> list[dict]:
    """Validate raw line input and compute tax/totals for each line."""
    if not raw_lines:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "A quotation needs at least one line")

    resolved = []
    for raw in raw_lines:
        product = db.get(Product, raw.product_id)
        if product is None or not product.is_active:
            raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, f"Product {raw.product_id} not found or inactive")

        # Price: explicit -> product base + variant delta (problem statement: Odoo +560)
        unit_price = raw.unit_price
        if unit_price is None:
            unit_price = Decimal(str(product.sales_price))
            if raw.variant_id is not None:
                variant = db.get(ProductVariant, raw.variant_id)
                if variant is None or variant.product_id != product.id:
                    raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "Variant does not belong to the product")
                unit_price += Decimal(str(variant.price_delta))

        tax_rule = None
        if raw.tax_rule_id is not None:
            tax_rule = db.get(TaxRule, raw.tax_rule_id)
            if tax_rule is None:
                raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "Tax rule not found")
        else:
            tax_rule = get_applicable_tax(db, product.id)

        amounts = compute_line_amounts(raw.quantity, Decimal(unit_price), tax_rule)
        resolved.append(
            {
                "product_id": product.id,
                "variant_id": raw.variant_id,
                "description": product.name,
                "quantity": raw.quantity,
                "unit_price": Decimal(unit_price).quantize(TWO_PLACES),
                "tax_rule_id": tax_rule.id if tax_rule else None,
                "tax_rate": amounts["tax_rate"],
                "tax_amount": amounts["tax_amount"],
                "line_total": amounts["total"],
            }
        )
    return resolved


def compute_totals(lines: list[QuotationLine]) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = sum((Decimal(str(l.line_total)) - Decimal(str(l.tax_amount))) for l in lines)
    tax_total = sum(Decimal(str(l.tax_amount)) for l in lines)
    total = sum(Decimal(str(l.line_total)) for l in lines)
    return (
        subtotal.quantize(TWO_PLACES),
        tax_total.quantize(TWO_PLACES),
        total.quantize(TWO_PLACES),
    )


def replace_lines(db: Session, quotation: Quotation, resolved: list[dict]) -> None:
    quotation.lines.clear()
    db.flush()
    for data in resolved:
        quotation.lines.append(QuotationLine(**data))
    db.flush()
    subtotal, tax_total, total = compute_totals(quotation.lines)
    quotation.subtotal = subtotal
    quotation.tax_total = tax_total
    quotation.total = total


def effective_status(quotation: Quotation) -> str:
    """Sent quotations whose validity passed read as 'expired' (lazy, no write-on-read)."""
    if quotation.status == "sent" and quotation.valid_until and quotation.valid_until < today():
        return "expired"
    return quotation.status


def ensure_convertible(quotation: Quotation) -> None:
    eff = effective_status(quotation)
    if quotation.subscription_id is not None:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Quotation has already been converted")
    if eff == "expired":
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Quotation has expired")
    if eff not in ("draft", "sent"):
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Cannot confirm a {eff} quotation")


def send_quotation(db: Session, quotation: Quotation, validity_days: int | None = None) -> Quotation:
    if quotation.status != "draft":
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Cannot send a {quotation.status} quotation")
    days = validity_days
    if days is None:
        template = db.get(QuoteTemplate, quotation.template_id) if quotation.template_id else None
        days = template.validity_days if template else default_validity_days()
    quotation.status = "sent"
    if quotation.valid_until is None:
        quotation.valid_until = today() + timedelta(days=days)
    db.commit()
    db.refresh(quotation)
    return quotation


def create_quotation_number(db: Session) -> str:
    return next_number(db, "QUO")


def quotation_to_subscription(_db: Session, _quotation: Quotation) -> None:
    """Placeholder until the subscriptions module exists (M1, next block)."""
    raise HTTPException(
        http_status.HTTP_501_NOT_IMPLEMENTED,
        "Subscription conversion lands with the subscriptions module — see docs/API.md status table",
    )
