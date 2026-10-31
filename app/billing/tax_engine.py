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
    return amounts_on_base(gross, tax_rule)


def amounts_on_base(base: Decimal, tax_rule: TaxRule | None) -> dict:
    """Tax math on an already-discounted base (billing engine: price -> discount -> tax).

    `base` = line gross minus its allocated discount (tax-exclusive net, or
    tax-inclusive gross when the rule includes tax).
    """
    base = base.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if tax_rule is None:
        return {
            "subtotal": base,
            "tax_amount": Decimal("0.00"),
            "total": base,
            "tax_rate": Decimal("0.00"),
            "tax_included": False,
        }

    rate = Decimal(str(tax_rule.rate)) / Decimal("100")
    if tax_rule.tax_included:
        # base already contains tax: tax = base * rate / (1 + rate)
        tax = (base * rate / (Decimal("1") + rate)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        subtotal = (base - tax).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total = base
    else:
        subtotal = base
        tax = (base * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total = base + tax

    return {
        "subtotal": subtotal,
        "tax_amount": tax,
        "total": total,
        "tax_rate": Decimal(str(tax_rule.rate)),
        "tax_included": tax_rule.tax_included,
    }
