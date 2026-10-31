"""Reports and intelligence service (docs/API.md §10).

/reports/summary  — KPI dashboard
/reports/mrr      — MRR time series (actual + projection)
/reports/overdue  — chase list (confirmed invoices past due)
/insights/risk    — rule-based churn-risk scoring per subscription
/insights/forecast — Holt linear trend on monthly revenue

MRR normalisation (excludes paused, excludes tax, net of subscription-scope discounts):
  daily   → price * 365 / 12
  weekly  → price * 52  / 12
  monthly → price
  yearly  → price / 12
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.billing.invoice_service import _is_overdue, _outstanding, _today
from app.billing.models import Invoice, Payment
from app.subscriptions.models import Subscription

ZERO = Decimal("0")
TWO = Decimal("0.01")


# ------------------------------------------------------------------ helpers

def _mrr_contribution(sub: Subscription) -> Decimal:
    """Monthly-normalised plan price (no tax, no discount for simplicity)."""
    cycle_map = {"daily": Decimal("365") / 12, "weekly": Decimal("52") / 12,
                 "monthly": Decimal("1"), "yearly": Decimal("1") / 12}
    price = Decimal(str(sub.plan.price))
    factor = cycle_map.get(sub.plan.billing_cycle, Decimal("1"))
    return (price * factor).quantize(TWO)


# ------------------------------------------------------------------ summary

def get_summary(db: Session, from_date: date | None = None, to_date: date | None = None) -> dict:
    today = _today()

    # active subscription count + MRR
    active_subs = list(
        db.scalars(select(Subscription).where(Subscription.status == "active")).all()
    )
    active_count = len(active_subs)
    mrr = sum((_mrr_contribution(s) for s in active_subs), ZERO)

    # revenue collected (sum of confirmed payments in window)
    pay_stmt = select(func.sum(Payment.amount))
    if from_date:
        pay_stmt = pay_stmt.where(Payment.paid_at >= from_date)
    if to_date:
        pay_stmt = pay_stmt.where(Payment.paid_at <= to_date)
    revenue_collected = Decimal(str(db.scalar(pay_stmt) or 0))

    # outstanding across non-cancelled, non-draft invoices
    confirmed_invs = list(
        db.scalars(
            select(Invoice).where(Invoice.status.in_(["confirmed"]))
        ).all()
    )
    outstanding_total = sum((_outstanding(i) for i in confirmed_invs), ZERO)

    overdue_invs = [i for i in confirmed_invs if _is_overdue(i, today)]
    overdue_count = len(overdue_invs)
    overdue_amount = sum((_outstanding(i) for i in overdue_invs), ZERO)

    # recent payments (last 5)
    recent_payments = list(
        db.scalars(
            select(Payment).order_by(Payment.id.desc()).limit(5)
        ).all()
    )

    return {
        "active_subscriptions": active_count,
        "mrr": mrr,
        "revenue_collected": revenue_collected,
        "outstanding": outstanding_total,
        "overdue_count": overdue_count,
        "overdue_amount": overdue_amount,
        "recent_payments": [
            {
                "id": p.id,
                "invoice_id": p.invoice_id,
                "amount": Decimal(str(p.amount)),
                "method": p.method,
                "paid_at": p.paid_at,
            }
            for p in recent_payments
        ],
    }


# ------------------------------------------------------------------ MRR series

def get_mrr(db: Session, months: int = 24) -> dict:
    today = _today()
    current_month = today.replace(day=1)

    # Build a map month_str → collected_revenue from confirmed invoices
    # (issue_date used as the reporting month)
    rows = db.execute(
        select(Invoice.issue_date, Invoice.subtotal).where(
            Invoice.status.in_(["confirmed", "paid"])
        )
    ).all()

    monthly_revenue: dict[str, Decimal] = defaultdict(Decimal)
    for issue_date, subtotal in rows:
        key = issue_date.strftime("%Y-%m")
        monthly_revenue[key] += Decimal(str(subtotal))

    # Produce series starting from (months) ago
    series = []
    for delta in range(months - 1, -1, -1):
        m = _month_offset(current_month, -delta)
        key = m.strftime("%Y-%m")
        if m < current_month:
            series.append({
                "month": key,
                "mrr": monthly_revenue.get(key, ZERO).quantize(TWO),
                "kind": "actual",
            })
        else:
            # current month — use live MRR
            series.append({
                "month": key,
                "mrr": _live_mrr(db).quantize(TWO),
                "kind": "actual",
            })

    # Append simple linear projection for next 3 months
    recent_actuals = [row["mrr"] for row in series if row["kind"] == "actual"]
    if len(recent_actuals) >= 2:
        trend = (recent_actuals[-1] - recent_actuals[0]) / max(1, len(recent_actuals) - 1)
        for i in range(1, 4):
            m = _month_offset(current_month, i)
            projected = (recent_actuals[-1] + trend * i).quantize(TWO)
            series.append({
                "month": m.strftime("%Y-%m"),
                "mrr": max(ZERO, projected),
                "kind": "projection",
            })

    current_mrr = _live_mrr(db)
    return {
        "current_mrr": current_mrr.quantize(TWO),
        "arr": (current_mrr * 12).quantize(TWO),
        "normalization": {
            "daily": "price*365/12",
            "weekly": "price*52/12",
            "monthly": "price",
            "yearly": "price/12",
        },
        "series": series,
    }


def _live_mrr(db: Session) -> Decimal:
    active = db.scalars(select(Subscription).where(Subscription.status == "active")).all()
    return sum((_mrr_contribution(s) for s in active), ZERO)


def _month_offset(base: date, delta: int) -> date:
    """Add `delta` months to `base` (first-of-month dates only)."""
    total_months = base.month + delta
    year = base.year + (total_months - 1) // 12
    month = (total_months - 1) % 12 + 1
    return base.replace(year=year, month=month, day=1)


# ------------------------------------------------------------------ overdue list

def get_overdue(db: Session, page: int = 1, page_size: int = 20) -> dict:
    from app.core.pagination import paginate
    from app.billing.invoice_service import enrich

    today = _today()
    stmt = (
        select(Invoice)
        .where(Invoice.status == "confirmed", Invoice.due_date < today)
        .order_by((today - Invoice.due_date).desc())
    )
    result = paginate(db, stmt, page, page_size)
    enriched = [enrich(i, today) for i in result["items"]]
    return {**result, "items": enriched}


# ------------------------------------------------------------------ risk scoring

def _expiry_days(sub: Subscription, today: date) -> int:
    """Days until expiry (0 when no expiry or past)."""
    if sub.expiry_date is None:
        return 0
    delta = (sub.expiry_date - today).days
    return max(0, delta) if delta <= 60 else 0


def _score_subscription(
    sub: Subscription,
    late_payments: int,
    outstanding_invoices: int,
    today: date,
) -> dict:
    factors = []
    raw_score = 0

    factor_specs = [
        ("late_payments", 30, late_payments, 3),
        ("outstanding_invoices", 25, outstanding_invoices, 3),
        ("expiry_approaching_days", 27, _expiry_days(sub, today), 60),
        ("paused_recently", 18, 1 if sub.status == "paused" else 0, 1),
    ]

    for name, weight, value, f_max in factor_specs:
        contribution = min(weight, int(value * weight / max(1, f_max)))
        raw_score += contribution
        if contribution > 0:
            factors.append({
                "name": name,
                "value": value,
                "weight": weight,
                "contribution": contribution,
            })

    band = "low" if raw_score < 30 else ("medium" if raw_score < 60 else "high")
    action = None
    if band == "high":
        action = "Contact the customer and resolve the outstanding payment before renewal"
    elif band == "medium":
        action = "Monitor closely and follow up on any outstanding invoices"

    return {
        "subscription_id": sub.id,
        "subscription_number": sub.number,
        "customer_name": sub.customer_name,
        "score": raw_score,
        "band": band,
        "factors": factors,
        "action": action,
    }


def get_risk(db: Session, band: str | None = None, page: int = 1, page_size: int = 20) -> dict:
    today = _today()

    # Pre-aggregate overdue and outstanding counts in 2 instant queries instead of 7000+ individual queries
    late_map = dict(
        db.execute(
            select(Invoice.subscription_id, func.count(Invoice.id))
            .where(Invoice.status == "confirmed", Invoice.due_date < today)
            .group_by(Invoice.subscription_id)
        ).all()
    )
    outstanding_map = dict(
        db.execute(
            select(Invoice.subscription_id, func.count(Invoice.id))
            .where(Invoice.status == "confirmed")
            .group_by(Invoice.subscription_id)
        ).all()
    )

    subs = db.scalars(
        select(Subscription).where(Subscription.status.in_(["active", "paused"]))
    ).all()

    scored = sorted(
        [
            _score_subscription(
                s,
                late_map.get(s.id, 0),
                outstanding_map.get(s.id, 0),
                today,
            )
            for s in subs
        ],
        key=lambda x: x["score"],
        reverse=True,
    )
    if band:
        scored = [s for s in scored if s["band"] == band]

    total = len(scored)
    start = (page - 1) * page_size
    return {
        "items": scored[start: start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ------------------------------------------------------------------ forecast

def get_forecast(db: Session, horizon: int = 3) -> dict:
    """Holt linear (double exponential smoothing) on monthly revenue."""
    today = _today()
    current_month = today.replace(day=1)

    # Collect last 12 months of actual monthly revenue
    history = []
    for delta in range(11, -1, -1):
        m = _month_offset(current_month, -delta)
        next_m = _month_offset(m, 1)
        revenue = db.scalar(
            select(func.sum(Payment.amount)).where(
                Payment.paid_at >= m, Payment.paid_at < next_m
            )
        ) or 0
        history.append(Decimal(str(revenue)))

    if len(history) < 2:
        return {
            "method": "naive_last",
            "baseline_method": "naive_last",
            "points": [],
            "confidence": "low",
            "note": "Insufficient data for forecasting",
        }

    # Holt linear parameters
    alpha, beta = 0.4, 0.2
    level = float(history[0])
    trend = float(history[1] - history[0])

    for obs in history[1:]:
        prev_level = level
        level = alpha * float(obs) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend

    points = []
    for i in range(1, horizon + 1):
        m = _month_offset(current_month, i)
        value = max(0.0, level + i * trend)
        points.append({
            "month": m.strftime("%Y-%m"),
            "value": Decimal(str(round(value, 2))),
        })

    confidence = "high" if len(history) >= 12 else ("medium" if len(history) >= 6 else "low")

    return {
        "method": "holt_linear",
        "baseline_method": "naive_last",
        "points": points,
        "confidence": confidence,
        "note": "Projection, not collected revenue",
    }
