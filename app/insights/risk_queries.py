"""Real-data risk scoring: one aggregate SQL query, then the rule-based score."""
import time
from datetime import date, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.billing.models import Invoice, Payment
from app.insights.risk import risk_score
from app.subscriptions.models import Subscription
from app.catalog.models import Plan, Product, ProductVariant, TaxRule  # noqa: F401  (registers models)
from app.quoting.models import Quotation  # noqa: F401  (registers models)


def _compute_all(db: Session, today: date) -> list[dict]:
    six_months_ago = today - timedelta(days=183)

    owed = Invoice.total - Invoice.paid_amount
    inv = (
        select(
            Invoice.subscription_id.label("sid"),
            func.count(Invoice.id)
            .filter(and_(Invoice.status == "confirmed", Invoice.due_date < today, owed > 0))
            .label("overdue"),
            func.coalesce(
                func.sum(owed).filter(and_(Invoice.status == "confirmed", owed > 0)), 0
            ).label("outstanding"),
        )
        .group_by(Invoice.subscription_id)
        .subquery()
    )

    late = (
        select(Invoice.subscription_id.label("sid"), func.count(Payment.id).label("late_count"))
        .join(Payment, Payment.invoice_id == Invoice.id)
        .where(Payment.paid_at > Invoice.due_date, Payment.paid_at >= six_months_ago)
        .group_by(Invoice.subscription_id)
        .subquery()
    )

    stmt = (
        select(
            Subscription.id,
            User.name,
            Subscription.expiry_date,
            func.coalesce(inv.c.overdue, 0),
            func.coalesce(inv.c.outstanding, 0),
            func.coalesce(late.c.late_count, 0),
        )
        .join(User, User.id == Subscription.customer_id)
        .outerjoin(inv, inv.c.sid == Subscription.id)
        .outerjoin(late, late.c.sid == Subscription.id)
        .where(Subscription.status.in_(("active", "paused")))
    )

    items = []
    for sub_id, name, expiry, overdue, outstanding, late_count in db.execute(stmt).all():
        days_to_expiry = (expiry - today).days if expiry else None
        result = risk_score(int(overdue), int(late_count), float(outstanding), days_to_expiry)
        items.append({"subscription_id": sub_id, "customer_name": name, **result})

    items.sort(key=lambda i: (-i["score"], i["subscription_id"]))
    return items


_CACHE: dict = {"key": None, "at": 0.0, "items": []}
CACHE_SECONDS = 60


def _all_scored(db: Session, today: date) -> list[dict]:
    """Scored list, cached for 60s so paging/filtering is instant."""
    now = time.monotonic()
    if (_CACHE["key"] == today and now - _CACHE["at"] < CACHE_SECONDS
            and _CACHE["items"]):
        return _CACHE["items"]
    items = _compute_all(db, today)
    _CACHE.update(key=today, at=now, items=items)
    return items


def risk_list(db: Session, band: str | None = None, page: int = 1,
              page_size: int = 20, today: date | None = None) -> dict:
    items = _all_scored(db, today or date.today())
    if band:
        items = [i for i in items if i["band"] == band]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items),
            "page": page, "page_size": page_size}


if __name__ == "__main__":
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        t = time.perf_counter()
        everything = _compute_all(db, date.today())
        print(f"risk: {time.perf_counter() - t:.2f}s for {len(everything)} subscriptions")
        for b in ("high", "medium", "low"):
            print(b, sum(1 for i in everything if i["band"] == b))
        print("overdue invoices counted:",
              sum(f["value"] for i in everything for f in i["factors"]
                  if f["name"] == "outstanding_invoices"))
        print("top 3:", [(i["customer_name"], i["score"]) for i in everything[:3]])