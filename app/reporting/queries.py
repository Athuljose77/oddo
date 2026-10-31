"""Reporting queries (aggregate SQL, server-side pagination). Money is Decimal.

MRR rules (docs/API.md section 10): daily*365/12, weekly*52/12, monthly*1, yearly/12;
paused and closed excluded from current MRR; tax excluded (uses qty * unit_price only).
Pass `db` = a SQLAlchemy Session or Connection.

Check on the real DB:  python -m app.reporting.queries
"""
import time
from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, case, func, or_, select

import app.auth.models  # noqa: F401  (registers tables)
import app.billing.models  # noqa: F401
import app.catalog.models  # noqa: F401
import app.subscriptions.models  # noqa: F401
from app.core.database import Base
from app.insights.forecast import forecast_series

T = Base.metadata.tables
S, P, L = T["subscriptions"], T["plans"], T["subscription_lines"]
INV, PAY, U = T["invoices"], T["payments"], T["users"]
MAX_PAGE_SIZE = 100


def q2(x):
    return Decimal(x or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _factor():
    c = func.lower(P.c.billing_cycle)
    return case((c.like("d%"), Decimal(365) / 12), (c.like("w%"), Decimal(52) / 12),
                (c.like("m%"), Decimal(1)), else_=Decimal(1) / 12)


def _sub_mrr():
    base = (select(L.c.subscription_id.label("sid"), func.sum(L.c.quantity * L.c.unit_price).label("base"))
            .group_by(L.c.subscription_id).subquery())
    return (select(S.c.id, S.c.status, S.c.start_date, S.c.closed_at, S.c.paused_at,
                   (base.c.base * _factor()).label("mrr"))
            .join(P, P.c.id == S.c.plan_id).join(base, base.c.sid == S.c.id)
            .where(S.c.status.in_(("active", "paused", "closed"))).subquery())


def current_mrr(db):
    m = _sub_mrr()
    return q2(db.execute(select(func.coalesce(func.sum(m.c.mrr), 0)).where(m.c.status == "active")).scalar_one())


def _series_and_current(db, months=24, as_of=None):
    """ONE aggregate query: MRR live at the end of each month + today's active MRR."""
    as_of = as_of or date.today()
    m = _sub_mrr()
    ends = []
    for i in range(months - 1, -1, -1):
        t = as_of.year * 12 + (as_of.month - 1) - i
        y, mo = divmod(t, 12)
        mo += 1
        ends.append(min(date(y, mo, monthrange(y, mo)[1]), as_of))
    cols = []
    for i, e in enumerate(ends):
        live = and_(m.c.start_date <= e,
                    or_(m.c.closed_at.is_(None), func.date(m.c.closed_at) > e),
                    or_(m.c.paused_at.is_(None), func.date(m.c.paused_at) > e))
        cols.append(func.coalesce(func.sum(case((live, m.c.mrr), else_=0)), 0).label(f"m{i}"))
    cols.append(func.coalesce(func.sum(case((m.c.status == "active", m.c.mrr), else_=0)), 0).label("cur"))
    row = db.execute(select(*cols)).one()
    series = [(f"{e.year:04d}-{e.month:02d}", q2(v)) for e, v in zip(ends, row[:-1])]
    cur = q2(row[-1])
    series[-1] = (series[-1][0], cur)  # current month = today's real MRR
    return series, cur


def mrr_actual_series(db, months=24, as_of=None):
    return _series_and_current(db, months, as_of)[0]


def mrr_report(db, months=24, horizon=3, as_of=None):
    actual, cur = _series_and_current(db, months, as_of)
    fc = forecast_series([v for _, v in actual], actual[-1][0], horizon)
    series = [{"month": mo, "mrr": v, "kind": "actual"} for mo, v in actual]
    series += [{"month": p["month"], "mrr": p["value"], "kind": "projection"} for p in fc["points"]]
    return {"current_mrr": cur, "arr": q2(cur * 12),
            "normalization": {"daily": "price*365/12", "weekly": "price*52/12", "monthly": "price", "yearly": "price/12"},
            "series": series}


def forecast_report(db, horizon=3, as_of=None):
    actual, _ = _series_and_current(db, 24, as_of)
    return forecast_series([v for _, v in actual], actual[-1][0], horizon)


def _open_invoices():
    return and_(INV.c.status == "confirmed", INV.c.total - INV.c.paid_amount > 0)


def summary(db, date_from=None, date_to=None, today=None):
    today = today or date.today()
    to = date_to or today
    frm = date_from or (to - timedelta(days=30))
    open_inv = _open_invoices()
    owed = INV.c.total - INV.c.paid_amount
    m = _sub_mrr()
    row = db.execute(select(
        select(func.count()).select_from(S).where(S.c.status == "active").scalar_subquery(),
        select(func.coalesce(func.sum(PAY.c.amount), 0)).where(PAY.c.paid_at >= frm, PAY.c.paid_at <= to).scalar_subquery(),
        select(func.coalesce(func.sum(owed), 0)).where(open_inv).scalar_subquery(),
        select(func.count()).select_from(INV).where(open_inv, INV.c.due_date < today).scalar_subquery(),
        select(func.coalesce(func.sum(owed), 0)).where(open_inv, INV.c.due_date < today).scalar_subquery(),
        select(func.coalesce(func.sum(case((m.c.status == "active", m.c.mrr), else_=0)), 0)).select_from(m).scalar_subquery(),
    )).one()
    recent = db.execute(
        select(PAY.c.id, PAY.c.invoice_id, INV.c.number, U.c.name, PAY.c.amount, PAY.c.method, PAY.c.paid_at)
        .join(INV, INV.c.id == PAY.c.invoice_id).join(U, U.c.id == INV.c.customer_id)
        .order_by(PAY.c.paid_at.desc(), PAY.c.id.desc()).limit(5)).all()
    return {"active_subscriptions": row[0], "mrr": q2(row[5]), "revenue_collected": q2(row[1]),
            "outstanding": q2(row[2]), "overdue_count": row[3], "overdue_amount": q2(row[4]),
            "recent_payments": [{"id": r[0], "invoice_id": r[1], "invoice_number": r[2], "customer_name": r[3],
                                 "amount": q2(r[4]), "method": r[5], "paid_at": r[6]} for r in recent]}


def overdue(db, page=1, page_size=20, today=None):
    today = today or date.today()
    page, page_size = max(1, page), min(max(1, page_size), MAX_PAGE_SIZE)
    where = and_(_open_invoices(), INV.c.due_date < today)
    total = db.execute(select(func.count()).select_from(INV).where(where)).scalar_one()
    rows = db.execute(
        select(INV.c.id, INV.c.number, INV.c.subscription_id, S.c.number, INV.c.customer_id, U.c.name,
               INV.c.due_date, INV.c.total, INV.c.paid_amount)
        .join(S, S.c.id == INV.c.subscription_id).join(U, U.c.id == INV.c.customer_id)
        .where(where).order_by(INV.c.due_date.asc(), INV.c.id.asc())
        .limit(page_size).offset((page - 1) * page_size)).all()
    items = [{"invoice_id": r[0], "invoice_number": r[1], "subscription_id": r[2], "subscription_number": r[3],
              "customer_id": r[4], "customer_name": r[5], "due_date": r[6], "total": q2(r[7]),
              "outstanding": q2(Decimal(r[7]) - Decimal(r[8])), "days_overdue": (today - r[6]).days} for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


if __name__ == "__main__":
    from app.core.database import engine

    def timed(name, fn):
        t = time.time()
        out = fn()
        print(f"{name}: {time.time() - t:.2f}s")
        return out

    with engine.connect() as db:
        s = timed("summary", lambda: summary(db))
        print({k: v for k, v in s.items() if k != "recent_payments"})
        r = timed("mrr", lambda: mrr_report(db))
        print("current_mrr", r["current_mrr"], "arr", r["arr"])
        print("last 5 points:", [(p["month"], str(p["mrr"]), p["kind"]) for p in r["series"][-6:]])
        o = timed("overdue", lambda: overdue(db))
        print("overdue total", o["total"], "| most overdue:", o["items"][0]["invoice_number"], o["items"][0]["days_overdue"], "days")
        f = timed("forecast", lambda: forecast_report(db))
        print(f["method"], f["confidence"], "|", f["note"])
