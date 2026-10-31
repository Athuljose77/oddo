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

from sqlalchemy import String, func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.billing.invoice_service import _is_overdue, _outstanding, _today
from app.billing.models import Invoice, Payment
from app.catalog.models import Plan
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


def _live_mrr(db: Session) -> Decimal:
    plans = {p.id: p for p in db.scalars(select(Plan)).all()}
    counts = db.execute(
        select(Subscription.plan_id, func.count(Subscription.id))
        .where(Subscription.status == "active")
        .group_by(Subscription.plan_id)
    ).all()
    cycle_map = {
        "daily": Decimal("365") / 12,
        "weekly": Decimal("52") / 12,
        "monthly": Decimal("1"),
        "yearly": Decimal("1") / 12,
    }
    total = ZERO
    for plan_id, count in counts:
        p = plans.get(plan_id)
        if not p:
            continue
        price = Decimal(str(p.price))
        factor = cycle_map.get(p.billing_cycle, Decimal("1"))
        total += Decimal(count) * (price * factor)
    return total.quantize(TWO)


# ------------------------------------------------------------------ summary

def get_summary(db: Session, from_date: date | None = None, to_date: date | None = None) -> dict:
    today = _today()

    active_count = db.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == "active")
    ) or 0
    mrr = _live_mrr(db)

    # revenue collected (sum of confirmed payments in window)
    pay_stmt = select(func.sum(Payment.amount))
    if from_date:
        pay_stmt = pay_stmt.where(Payment.paid_at >= from_date)
    if to_date:
        pay_stmt = pay_stmt.where(Payment.paid_at <= to_date)
    revenue_collected = Decimal(str(db.scalar(pay_stmt) or 0))

    # outstanding & unsettled across confirmed invoices in 1 instant query
    confirmed_stats = db.execute(
        select(
            func.count(Invoice.id),
            func.sum(Invoice.total - Invoice.paid_amount)
        ).where(Invoice.status == "confirmed")
    ).first()
    unsettled_count = (confirmed_stats[0] or 0) if confirmed_stats else 0
    outstanding_total = (
        Decimal(str(confirmed_stats[1] or 0))
        if (confirmed_stats and confirmed_stats[1] is not None)
        else ZERO
    )

    overdue_stats = db.execute(
        select(
            func.count(Invoice.id),
            func.sum(Invoice.total - Invoice.paid_amount)
        ).where(
            Invoice.status == "confirmed",
            Invoice.due_date < today,
            Invoice.paid_amount < Invoice.total
        )
    ).first()
    overdue_count = (overdue_stats[0] or 0) if overdue_stats else 0
    overdue_amount = (
        Decimal(str(overdue_stats[1] or 0))
        if (overdue_stats and overdue_stats[1] is not None)
        else ZERO
    )

    # recent payments (last 5)
    recent_payments = list(
        db.scalars(
            select(Payment).order_by(Payment.id.desc()).limit(5)
        ).all()
    )

    return {
        "active_subscriptions": active_count,
        "mrr": mrr,
        "arr": (mrr * 12).quantize(TWO),
        "revenue_collected": revenue_collected,
        "outstanding": outstanding_total,
        "unsettled_total": outstanding_total,
        "unsettled_invoices_count": unsettled_count,
        "overdue_count": overdue_count,
        "overdue_invoices_count": overdue_count,
        "overdue_amount": overdue_amount,
        "overdue_total": overdue_amount,
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

    # Fast SQL aggregation by year-month
    month_col = func.substr(func.cast(Invoice.issue_date, String), 1, 7)
    rows = db.execute(
        select(month_col, func.sum(Invoice.subtotal))
        .where(Invoice.status.in_(["confirmed", "paid"]))
        .group_by(month_col)
    ).all()

    monthly_revenue: dict[str, Decimal] = {
        str(ym): Decimal(str(val or 0)) for ym, val in rows
    }

    live_mrr_val = _live_mrr(db)

    # Produce series starting from (months) ago
    series = []
    for delta in range(months - 1, -1, -1):
        m = _month_offset(current_month, -delta)
        key = m.strftime("%Y-%m")
        if m < current_month:
            val = monthly_revenue.get(key, ZERO).quantize(TWO)
        else:
            val = live_mrr_val.quantize(TWO)
        series.append({
            "month": key,
            "period": key,
            "mrr": val,
            "growth_pct": 0.0,
            "kind": "actual",
            "type": "Historical" if m < current_month else "Current",
        })

    # Calculate month-over-month growth_pct
    for i in range(1, len(series)):
        prev_mrr = series[i - 1]["mrr"]
        curr_mrr = series[i]["mrr"]
        if prev_mrr > 0:
            growth = round(float((curr_mrr - prev_mrr) / prev_mrr * 100), 1)
            series[i]["growth_pct"] = growth

    # Append simple linear projection for next 3 months
    recent_actuals = [row["mrr"] for row in series if row["kind"] == "actual"]
    if len(recent_actuals) >= 2:
        trend = (recent_actuals[-1] - recent_actuals[0]) / max(1, len(recent_actuals) - 1)
        for i in range(1, 4):
            m = _month_offset(current_month, i)
            key = m.strftime("%Y-%m")
            projected = max(ZERO, (recent_actuals[-1] + trend * i).quantize(TWO))
            prev_val = series[-1]["mrr"]
            growth = round(float((projected - prev_val) / prev_val * 100), 1) if prev_val > 0 else 0.0
            series.append({
                "month": key,
                "period": key,
                "mrr": projected,
                "growth_pct": growth,
                "kind": "projection",
                "type": "Projected",
            })

    return {
        "current_mrr": live_mrr_val.quantize(TWO),
        "arr": (live_mrr_val * 12).quantize(TWO),
        "normalization": {
            "daily": "price*365/12",
            "weekly": "price*52/12",
            "monthly": "price",
            "yearly": "price/12",
        },
        "series": series,
    }


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
        "customer_id": sub.customer_id,
        "customer_name": sub.customer_name,
        "score": raw_score,
        "risk_score": raw_score,
        "band": band,
        "risk_level": band,
        "factors": factors,
        "reasons": [f["name"].replace("_", " ") for f in factors],
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
    prev_val = Decimal(str(round(level, 2)))
    for i in range(1, horizon + 1):
        m = _month_offset(current_month, i)
        value = max(0.0, level + i * trend)
        dec_val = Decimal(str(round(value, 2)))
        growth = round(float((dec_val - prev_val) / prev_val * 100), 1) if prev_val > 0 else 0.0
        prev_val = dec_val
        points.append({
            "month": m.strftime("%Y-%m"),
            "period": m.strftime("%Y-%m"),
            "value": dec_val,
            "mrr": dec_val,
            "growth_pct": growth,
        })

    confidence = "high" if len(history) >= 12 else ("medium" if len(history) >= 6 else "low")

    return {
        "method": "holt_linear",
        "baseline_method": "naive_last",
        "points": points,
        "confidence": confidence,
        "note": "Projection, not collected revenue",
    }
