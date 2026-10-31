"""Subscription logic: creation validation, central transitions, conversion.

All status changes flow through `transition()` — the state machine module owns
what is legal, this module owns the side effects (pause clock, expiry renewal,
billing re-anchor) and the audit trail.
"""
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.billing.date_calculator import (
    first_index_on_or_after,
    next_cycle_date,
    today,
)
from app.catalog.models import Plan
from app.core.sequences import next_number
from app.quoting.models import Quotation
from app.quoting.service import resolve_lines
from app.subscriptions.models import (
    Subscription,
    SubscriptionEvent,
    SubscriptionLine,
)
from app.subscriptions.schemas import (
    SubscriptionCreateIn,
    SubscriptionLineIn,
    SubscriptionPatchIn,
)
from app.subscriptions.state_machine import (
    ensure_can_close,
    ensure_transition,
    is_early_close,
)


def ensure_plan_available(plan: Plan, on_date, http_code: int = http_status.HTTP_422_UNPROCESSABLE_ENTITY) -> None:
    """Statement: the system must validate plan availability before creating a subscription."""
    if plan.status != "active":
        raise HTTPException(http_code, f"Plan '{plan.name}' is closed")
    if plan.available_from is not None and on_date < plan.available_from:
        raise HTTPException(http_code, f"Plan '{plan.name}' is not yet available (opens {plan.available_from})")
    if plan.available_to is not None and on_date > plan.available_to:
        raise HTTPException(http_code, f"Plan '{plan.name}' availability ended {plan.available_to}")


def _build_lines(subscription: Subscription, resolved: list[dict]) -> None:
    subscription.lines.clear()
    db_lines = [SubscriptionLine(**data) for data in resolved]
    for line in db_lines:
        subscription.lines.append(line)
    subscription.subtotal = sum(l.line_total - l.tax_amount for l in db_lines)
    subscription.tax_total = sum(l.tax_amount for l in db_lines)
    subscription.total = sum(l.line_total for l in db_lines)


def create_subscription(db: Session, payload: SubscriptionCreateIn, actor) -> Subscription:
    customer = db.get(User, payload.customer_id)
    if customer is None or customer.role != "customer":
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "customer_id must reference a customer")
    plan = db.get(Plan, payload.plan_id)
    if plan is None:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "plan_id not found")

    start = payload.start_date or today()
    ensure_plan_available(plan, start)
    if payload.expiry_date is not None and payload.expiry_date <= start:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "expiry_date must be after start_date")

    total_qty = sum(line.quantity for line in payload.lines)
    if total_qty < plan.min_quantity:
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Plan '{plan.name}' requires a minimum quantity of {plan.min_quantity} (got {total_qty})",
        )

    resolved = resolve_lines(db, payload.lines)

    subscription = Subscription(
        number=next_number(db, "SUB"),
        customer_id=customer.id,
        plan_id=plan.id,
        created_by=actor.id,
        start_date=start,
        anchor_date=start,  # immutable billing anchor (CONVENTIONS § billing date rules)
        expiry_date=payload.expiry_date,
        payment_terms=payload.payment_terms,
        next_billing_date=start,  # billed in advance at period start
        period_index=0,
        status="draft",
    )
    db.add(subscription)
    db.flush()
    _build_lines(subscription, resolved)
    _record_event(db, subscription, None, "draft", actor, "created")
    db.commit()
    db.refresh(subscription)
    return subscription


def patch_subscription(db: Session, subscription: Subscription, payload: SubscriptionPatchIn) -> Subscription:
    if subscription.status not in ("draft", "quotation"):
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Cannot edit a {subscription.status} subscription",
        )
    data = payload.model_dump(exclude_unset=True)
    lines_payload = data.pop("lines", None)

    if payload.start_date is not None:
        if payload.expiry_date is not None and payload.expiry_date <= payload.start_date:
            raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "expiry_date must be after start_date")
        if subscription.period_index == 0:
            # Nothing billed yet -> moving the start moves the anchor too
            subscription.start_date = payload.start_date
            subscription.anchor_date = payload.start_date
            subscription.next_billing_date = payload.start_date
    elif payload.expiry_date is not None and payload.expiry_date <= subscription.start_date:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "expiry_date must be after start_date")

    for key, value in data.items():
        setattr(subscription, key, value)

    if lines_payload is not None:
        resolved = resolve_lines(db, [SubscriptionLineIn(**line) for line in lines_payload])
        _build_lines(subscription, resolved)

    db.commit()
    db.refresh(subscription)
    return subscription


def _record_event(db: Session, subscription: Subscription, from_status, to_status: str, actor, note: str | None) -> None:
    db.add(
        SubscriptionEvent(
            subscription_id=subscription.id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor.id if actor else None,
            note=note,
        )
    )


def transition(
    db: Session,
    subscription: Subscription,
    to_status: str,
    actor,
    *,
    reason: str | None = None,
    new_expiry_date=None,
) -> Subscription:
    """The one path for every status change. Validates, applies side effects, audits."""
    plan = subscription.plan
    t = today()
    current = subscription.status
    ensure_transition(subscription, to_status, plan, t)
    note = reason

    if to_status == "paused":
        subscription.paused_at = datetime.now(UTC)
        subscription.pause_reason = reason
        note = reason or "paused"

    elif current == "paused" and to_status == "active":
        days_paused = max((t - subscription.paused_at.date()).days, 0) if subscription.paused_at else 0
        # Waive periods that began during the pause; re-anchor to the first period >= today.
        # If the frozen next_billing_date is still in the future, nothing is waived.
        idx, new_next = first_index_on_or_after(subscription.anchor_date, plan.billing_cycle, t)
        waived = 0
        if idx > subscription.period_index:
            waived = idx - subscription.period_index
            subscription.period_index = idx
            subscription.next_billing_date = new_next
        if subscription.expiry_date is not None:
            subscription.expiry_date = subscription.expiry_date + timedelta(days=days_paused)
        subscription.paused_at = None
        subscription.pause_reason = None
        note = f"resumed after {days_paused}d paused; {waived} period(s) waived"

    elif to_status == "active" and current in ("active", "closed"):
        # Renewal: extend (or replace) the expiry; reopen re-anchors without back-billing.
        if new_expiry_date is not None:
            if new_expiry_date <= t:
                raise HTTPException(
                    http_status.HTTP_422_UNPROCESSABLE_ENTITY, "new_expiry_date must be in the future"
                )
            subscription.expiry_date = new_expiry_date
        else:
            base = subscription.expiry_date if (subscription.expiry_date and subscription.expiry_date > t) else t
            subscription.expiry_date = next_cycle_date(base, plan.billing_cycle)
        if current == "closed":
            idx, new_next = first_index_on_or_after(subscription.anchor_date, plan.billing_cycle, t)
            subscription.period_index = idx
            subscription.next_billing_date = new_next
            subscription.closed_at = None
            subscription.close_reason = None
        note = reason or f"renewed; new expiry {subscription.expiry_date}"

    elif to_status == "closed":
        if current in ("active", "paused"):
            ensure_can_close(subscription, plan, t)
        subscription.closed_at = datetime.now(UTC)
        subscription.close_reason = reason
        early = is_early_close(subscription, t)
        note = reason or ("closed early" if early else "closed at term end")

    subscription.status = to_status
    _record_event(db, subscription, current, to_status, actor, note)
    db.commit()
    db.refresh(subscription)
    return subscription


def convert_quotation(db: Session, quotation: Quotation, actor) -> Subscription:
    """Quotation -> subscription, exactly once (called from the quoting confirm route).

    The new subscription starts life in `confirmed` — the quotation WAS the draft.
    Same transaction: subscription insert + quotation.subscription_id + status.
    """
    if quotation.plan_id is None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, "Quotation has no plan; create a subscription directly instead"
        )
    plan = db.get(Plan, quotation.plan_id)
    start = quotation.start_date or today()
    ensure_plan_available(plan, start, http_status.HTTP_409_CONFLICT)

    total_qty = sum(line.quantity for line in quotation.lines)
    if total_qty < plan.min_quantity:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Plan '{plan.name}' requires a minimum quantity of {plan.min_quantity} (got {total_qty})",
        )

    subscription = Subscription(
        number=next_number(db, "SUB"),
        customer_id=quotation.customer_id,
        plan_id=plan.id,
        quotation_id=quotation.id,
        created_by=actor.id,
        start_date=start,
        anchor_date=start,
        expiry_date=None,
        payment_terms=quotation.payment_terms,
        next_billing_date=start,
        period_index=0,
        status="confirmed",
        subtotal=quotation.subtotal,
        tax_total=quotation.tax_total,
        total=quotation.total,
    )
    db.add(subscription)
    db.flush()
    # Snapshot the quotation lines (already tax-resolved) onto the subscription
    for line in quotation.lines:
        subscription.lines.append(
            SubscriptionLine(
                product_id=line.product_id,
                variant_id=line.variant_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rule_id=line.tax_rule_id,
                tax_rate=line.tax_rate,
                tax_amount=line.tax_amount,
                line_total=line.line_total,
            )
        )
    _record_event(db, subscription, None, "confirmed", actor, f"converted from {quotation.number}")
    quotation.subscription_id = subscription.id
    quotation.status = "confirmed"
    db.commit()
    db.refresh(subscription)
    return subscription
