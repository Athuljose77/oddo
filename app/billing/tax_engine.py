"""Shared tax calculation — used by quotations now and the billing engine later.

Rules (docs/CONVENTIONS.md):
- Product-specific tax rule beats global; within a pool the LOWEST priority wins.
- Calculation order: price -> discount -> tax.
- Decimal + HALF_UP rounding at the line level.
- tax_included=false -> tax added on top; true -> extracted from the gross.
"""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import TaxRule

TWO_PLACES = Decimal("0.01")


def get_applicable_tax(db: Session, product_id: int | None) -> TaxRule | None:
    if product_id is None:
        return None
    rules = list(db.scalars(select(TaxRule).where(TaxRule.is_active.is_(True))).all())
    product_rules = [r for r in rules if r.product_id == product_id]
    pool = product_rules or [r for r in rules if r.product_id is None]
    if not pool:
        return None
    return sorted(pool, key=lambda r: (r.priority, r.id))[0]


def compute_line_amounts(
    quantity: int, unit_price: Decimal, tax_rule: TaxRule | None
) -> dict:
    """Return subtotal / tax_amount / total / tax_rate / tax_included for one line."""
    gross = (Decimal(quantity) * unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if tax_rule is None:
        return {
            "subtotal": gross,
            "tax_amount": Decimal("0.00"),
            "total": gross,
            "tax_rate": Decimal("0.00"),
            "tax_included": False,
        }

    rate = Decimal(str(tax_rule.rate)) / Decimal("100")
    if tax_rule.tax_included:
        # gross already contains tax: tax = gross * rate / (1 + rate)
        tax = (gross * rate / (Decimal("1") + rate)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        subtotal = (gross - tax).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total = gross
    else:
        subtotal = gross
        tax = (gross * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total = gross + tax

    return {
        "subtotal": subtotal,
        "tax_amount": tax,
        "total": total,
        "tax_rate": Decimal(str(tax_rule.rate)),
        "tax_included": tax_rule.tax_included,
    }
