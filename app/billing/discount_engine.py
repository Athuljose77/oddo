"""Discount selection + application (docs/CONVENTIONS.md § discount concurrency).

Eligibility (docs/API.md §3): is_active ∧ starts_at ≤ run_date ≤ ends_at ∧
(usage_limit is null ∨ used_count < usage_limit) ∧ min_purchase ∧ min_quantity met.

Contract per statement: ONE best rule per invoice (largest discount wins; tie -> lower id).
scope=subscription discounts the whole invoice; scope=product only that product's lines.
Tax is ALWAYS computed after the discount (price -> discount -> tax).
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.models import DiscountRedemption, Invoice
from app.catalog.models import DiscountRule

TWO_PLACES = Decimal("0.01")


def rule_eligible(rule: DiscountRule, on_date: date, subtotal: Decimal, total_qty: int) -> bool:
    if not rule.is_active or rule.starts_at > on_date:
        return False
    if rule.ends_at is not None and on_date > rule.ends_at:
        return False
    if rule.usage_limit is not None and rule.used_count >= rule.usage_limit:
        return False
    if rule.min_purchase is not None and subtotal < Decimal(str(rule.min_purchase)):
        return False
    if rule.min_quantity is not None and total_qty < rule.min_quantity:
        return False
    return True


def discount_amount(rule: DiscountRule, base: Decimal) -> Decimal:
    """Discount value against `base` (the taxable amount of the rule's scope)."""
    if rule.type == "percentage":
        raw = (base * Decimal(str(rule.value)) / Decimal("100")).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
    else:
        raw = min(Decimal(str(rule.value)), base)  # fixed: never exceeds the base
    return max(raw, Decimal("0.00"))


def select_discount(
    db: Session,
    on_date: date,
    *,
    invoice_subtotal: Decimal,
    total_qty: int,
    product_gross: dict[int, Decimal],
) -> tuple[DiscountRule | None, Decimal, Decimal]:
    """Pick the best eligible rule for one invoice.

    Returns (rule, amount, base) where base is the amount the rule applied to
    (whole invoice for scope=subscription, that product's gross for scope=product).
    Rules are read in id order so the (amount, -id) max is deterministic.
    """
    rules = list(db.scalars(select(DiscountRule).order_by(DiscountRule.id)).all())
    best: tuple[Decimal, int, DiscountRule, Decimal] | None = None  # (-amount, id, rule, base)
    for rule in rules:
        if not rule_eligible(rule, on_date, invoice_subtotal, total_qty):
            continue
        if rule.scope == "product":
            base = product_gross.get(rule.product_id or -1, Decimal("0.00"))
        else:
            base = invoice_subtotal
        if base <= 0:
            continue
        amount = discount_amount(rule, base)
        if amount <= 0:
            continue
        candidate = (-amount, rule.id, rule, base)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        return None, Decimal("0.00"), Decimal("0.00")
    _, _, rule, base = best
    return rule, discount_amount(rule, base), base


def allocate_discount(discount: Decimal, line_grosses: list[Decimal]) -> list[Decimal]:
    """Split a scope-level discount across its lines proportionally (largest remainder).

    Allocations SUM EXACTLY to `discount` — no cents lost to rounding.
    """
    total = sum(line_grosses, Decimal("0.00"))
    if discount <= 0 or total <= 0:
        return [Decimal("0.00")] * len(line_grosses)
    discount = min(discount, total)  # never allocate more than the lines hold

    raw = [(discount * g / total) for g in line_grosses]
    shares = [r.quantize(TWO_PLACES, rounding=ROUND_HALF_UP) for r in raw]
    remainder = discount - sum(shares, Decimal("0.00"))
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - shares[i], -i), reverse=True)
    i = 0
    while remainder >= TWO_PLACES and order:
        shares[order[i % len(order)]] += TWO_PLACES
        remainder -= TWO_PLACES
        i += 1
        if i > len(raw) * 4:
            break
    return shares


def redeem(
    db: Session, rule: DiscountRule, invoice: Invoice, amount: Decimal, *, live: bool
) -> None:
    """Increment usage + record redemption — LIVE only (dry_run must not mutate).

    The rule row is locked FOR UPDATE inside the period transaction so concurrent
    usage cannot overshoot usage_limit (CONVENTIONS § discount concurrency).
    """
    if not live:
        return
    locked = db.scalar(
        select(DiscountRule)
        .where(DiscountRule.id == rule.id)
        .order_by(DiscountRule.id)
        .with_for_update()
    )
    if locked.usage_limit is not None and locked.used_count >= locked.usage_limit:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Discount '{rule.name}' reached its usage limit during billing",
        )
    locked.used_count += 1
    db.add(DiscountRedemption(discount_rule_id=rule.id, invoice_id=invoice.id, amount=amount))