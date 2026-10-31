"""Billing engine: runs, attempts, invoices, catch-up, idempotency (brief §5-§7).

Contract guarantees (docs/CONVENTIONS.md § billing idempotency — do not weaken):
- One run at a time: partial UNIQUE(status) WHERE running (+ pre-check -> 409).
- Each subscription PERIOD commits in its own transaction; on failure the period
  rolls back, the attempt records `failed`, that subscription STOPS advancing,
  the run continues with the next subscription.
- Invoices UNIQUE(subscription_id, period_start): a duplicate insert surfaces as
  IntegrityError -> attempt `skipped(already_invoiced)` — never a second invoice.
- dry_run: attempts + run rows only. NO invoices, NO used_count, NO pointer advance.
- Catch-up: all missed periods <= run_date, capped at MAX_CATCHUP_PERIODS (366).
- Retries UPDATE the failed attempt in place (retry_count++, error appended),
  never insert a second attempt row for the same period.
"""
import re
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.billing.date_calculator import first_index_on_or_after, period_end, period_start, today
from app.billing.discount_engine import allocate_discount, redeem, select_discount
from app.billing.models import BillingAttempt, BillingRun, Invoice, InvoiceLine
from app.billing.tax_engine import amounts_on_base, get_applicable_tax
from app.catalog.models import TaxRule
from app.core.config import get_settings
from app.core.sequences import next_number
from app.subscriptions.models import Subscription

TWO_PLACES = Decimal("0.01")
settings = get_settings()


# ---------------------------------------------------------------- helpers
def _terms_days(payment_terms: str | None) -> int:
    """'Net 30' -> 30. No terms -> due on issue."""
    if not payment_terms:
        return 0
    m = re.search(r"\d+", payment_terms)
    return int(m.group()) if m else 0


def _lock_subscription(db: Session, subscription_id: int) -> Subscription | None:
    """Load the subscription for the period transaction.

    Runs are serialized at the run level by the partial unique index on
    billing_runs(status), so a per-row FOR UPDATE lock is not needed (and would
    fail on Postgres when combined with the plan's outer join).
    """
    return db.get(Subscription, subscription_id)


def reap_stale_runs(db: Session) -> int:
    """Interrupted runs: `running` rows older than STALE_RUN_MINUTES (15).

    Called at startup and before every new run so a crashed process can never
    wedge the billing pipeline. Returns rows reaped.
    """
    cutoff_dt = datetime.now(UTC) - timedelta(minutes=settings.stale_run_minutes)
    stale = list(
        db.scalars(
            select(BillingRun).where(
                BillingRun.status == "running", BillingRun.started_at < cutoff_dt
            )
        ).all()
    )
    for run in stale:
        run.status = "interrupted"
    if stale:
        db.commit()
    return len(stale)


def due_subscriptions(
    db: Session, run_date, subscription_id: int | None = None
) -> list[Subscription]:
    stmt = (
        select(Subscription)
        .where(
            Subscription.status == "active",
            Subscription.next_billing_date.is_not(None),
            Subscription.next_billing_date <= run_date,
        )
        .order_by(Subscription.id)
    )
    if subscription_id is not None:
        stmt = stmt.where(Subscription.id == subscription_id)
    return list(db.scalars(stmt).all())


def catchup_stats(db: Session, subs: list[Subscription], run_date) -> tuple[int, int]:
    """(subscriptions needing >1 period, max periods any subscription needs)."""
    needing = 0
    max_periods = 0
    cap = settings.max_catchup_periods
    for sub in subs:
        # first period starting AFTER run_date, minus where we are now
        first_after, _ = first_index_on_or_after(
            sub.anchor_date, sub.plan.billing_cycle, run_date + timedelta(days=1)
        )
        periods = min(max(first_after - sub.period_index, 0), cap)
        if periods > 1:
            needing += 1
        max_periods = max(max_periods, periods)
    return needing, max_periods


# ---------------------------------------------------------------- one period
def _quote_period(
    db: Session, sub: Subscription, idx: int, run_date
) -> dict:
    """Price one period: lines, discount (best single rule), tax AFTER discount.

    Pure computation — no inserts, no used_count. Shared by live + dry_run so the
    projected and actual numbers can never diverge.
    """
    cycle = sub.plan.billing_cycle
    p_start = period_start(sub.anchor_date, cycle, idx)
    p_end = period_end(sub.anchor_date, cycle, idx)

    resolved = []  # (line, tax_rule) in line order
    grosses: list[Decimal] = []
    product_gross: dict[int, Decimal] = {}
    total_qty = 0
    for line in sub.lines:
        gross = (Decimal(line.quantity) * Decimal(str(line.unit_price))).quantize(TWO_PLACES)
        grosses.append(gross)
        product_gross[line.product_id] = product_gross.get(line.product_id, Decimal("0.00")) + gross
        total_qty += line.quantity
        tax_rule = (
            db.get(TaxRule, line.tax_rule_id)
            if line.tax_rule_id
            else get_applicable_tax(db, line.product_id)
        )
        resolved.append((line, tax_rule))
    invoice_subtotal = sum(grosses, Decimal("0.00"))

    rule, discount, _base = select_discount(
        db,
        run_date,
        invoice_subtotal=invoice_subtotal,
        total_qty=total_qty,
        product_gross=product_gross,
    )
    # Allocate within the rule's scope (subscription: all lines; product: that product only)
    if rule is not None and rule.scope == "product":
        scope_grosses = [
            g if line.product_id == rule.product_id else Decimal("0.00")
            for (line, _), g in zip(resolved, grosses)
        ]
    else:
        scope_grosses = grosses
    shares = allocate_discount(discount, scope_grosses)

    tax_total = Decimal("0.00")
    grand_total = Decimal("0.00")
    line_rows = []  # (line, tax_rule, gross, share, amounts)
    for (line, tax_rule), gross, share in zip(resolved, grosses, shares):
        amounts = amounts_on_base(gross - share, tax_rule)
        tax_total += amounts["tax_amount"]
        grand_total += amounts["total"]
        line_rows.append((line, tax_rule, gross, share, amounts))

    return {
        "p_start": p_start,
        "p_end": p_end,
        "line_rows": line_rows,
        "subtotal": invoice_subtotal,
        "discount": sum(shares, Decimal("0.00")),
        "tax": tax_total,
        "total": grand_total,
        "rule": rule,
    }


def _persist_invoice(
    db: Session, run: BillingRun, sub: Subscription, quote: dict, run_date
) -> Invoice:
    """Insert invoice + lines + redemption from a quote. Caller owns the tx."""
    invoice = Invoice(
        number=next_number(db, "INV"),
        subscription_id=sub.id,
        customer_id=sub.customer_id,
        run_id=run.id,
        period_start=quote["p_start"],
        period_end=quote["p_end"],
        issue_date=run_date,
        due_date=run_date + timedelta(days=_terms_days(sub.payment_terms)),
        status="draft",
        subtotal=quote["subtotal"],
        discount_total=quote["discount"],
        tax_total=quote["tax"],
        total=quote["total"],
        paid_amount=Decimal("0.00"),
    )
    db.add(invoice)
    db.flush()  # invoice.id for lines + redemption
    for line, tax_rule, _gross, share, amounts in quote["line_rows"]:
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                product_id=line.product_id,
                variant_id=line.variant_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_amount=share,
                tax_rule_id=tax_rule.id if tax_rule else None,
                tax_rate=amounts["tax_rate"],
                tax_amount=amounts["tax_amount"],
                line_total=amounts["total"],
            )
        )
    if quote["rule"] is not None:
        redeem(db, quote["rule"], invoice, quote["discount"], live=True)
    return invoice


def _process_period(
    db: Session,
    run: BillingRun,
    sub_id: int,
    idx: int,
    run_date,
    live: bool,
    timer_start: float,
    attempt: BillingAttempt | None = None,
) -> BillingAttempt:
    """One subscription period, one transaction.

    `attempt` (retry path): UPDATE this failed attempt in place instead of
    inserting — UNIQUE(run_id, subscription_id, period_start) forbids a second row.
    """
    try:
        sub = _lock_subscription(db, sub_id)
        if sub is None:
            raise RuntimeError("subscription disappeared")
        cycle = sub.plan.billing_cycle
        p_start = period_start(sub.anchor_date, cycle, idx)
        p_end = period_end(sub.anchor_date, cycle, idx)

        def _row(**kw) -> BillingAttempt:
            row = attempt if attempt is not None else BillingAttempt(
                run_id=run.id, subscription_id=sub_id, period_start=p_start, period_end=p_end
            )
            for k, v in kw.items():
                setattr(row, k, v)
            row.duration_ms = int((time.perf_counter() - timer_start) * 1000)
            db.add(row)
            return row

        # Status may have changed since selection (paused/closed mid-run)
        if sub.status != "active":
            row = _row(status="skipped", reason=sub.status)
            db.commit()
            return row

        # Idempotency: invoice already exists for this period?
        existing = db.scalar(
            select(Invoice).where(
                Invoice.subscription_id == sub_id, Invoice.period_start == p_start
            )
        )
        if existing is not None:
            # Reconcile the pointer forward — but NEVER move it backward: a later
            # run may already have billed past this period.
            if sub.period_index == idx:
                sub.period_index = idx + 1
                sub.next_billing_date = period_start(sub.anchor_date, cycle, idx + 1)
                sub.last_billing_date = p_start
            row = _row(
                status="skipped",
                reason="already_invoiced",
                invoice_id=existing.id,
                projected_total=Decimal(str(existing.total)),
                actual_total=Decimal(str(existing.total)),
            )
            db.commit()
            return row

        quote = _quote_period(db, sub, idx, run_date)
        if live:
            invoice = _persist_invoice(db, run, sub, quote, run_date)
            # Advance the billing pointer inside the SAME transaction as the
            # invoice — but never move it backward (a backfilled old period
            # on retry must not rewind a pointer that already passed it).
            if sub.period_index == idx:
                sub.period_index = idx + 1
                sub.next_billing_date = period_start(sub.anchor_date, cycle, idx + 1)
                sub.last_billing_date = p_start
            row = _row(
                status="created",
                invoice_id=invoice.id,
                discount_rule_name=quote["rule"].name if quote["rule"] else None,
                projected_subtotal=quote["subtotal"],
                projected_tax=quote["tax"],
                projected_discount=quote["discount"],
                projected_total=quote["total"],
                actual_total=quote["total"],
            )
        else:
            # dry_run: compute the would-be invoice WITHOUT persisting it
            row = _row(
                status="created",
                discount_rule_name=quote["rule"].name if quote["rule"] else None,
                projected_subtotal=quote["subtotal"],
                projected_tax=quote["tax"],
                projected_discount=quote["discount"],
                projected_total=quote["total"],
            )
        db.commit()
        return row

    except IntegrityError as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc))
        if "uq_invoice_subscription_period" in msg or "invoices.subscription_id" in msg:
            # Race: another writer inserted this period first -> skipped, never a 2nd invoice
            anchor = _scalar_where(db, Subscription.anchor_date, sub_id)
            cycle = _cycle_of(db, sub_id)
            row = BillingAttempt(
                run_id=run.id,
                subscription_id=sub_id,
                period_start=period_start(anchor, cycle, idx),
                period_end=period_end(anchor, cycle, idx),
                status="skipped",
                reason="already_invoiced",
            )
            db.add(row)
            db.commit()
            return row
        return _fail_attempt(db, run, sub_id, idx, msg, timer_start, attempt)
    except HTTPException as exc:
        db.rollback()
        return _fail_attempt(db, run, sub_id, idx, str(exc.detail), timer_start, attempt)
    except Exception as exc:  # noqa: BLE001 — any period error must not kill the run
        db.rollback()
        return _fail_attempt(db, run, sub_id, idx, str(exc), timer_start, attempt)


def _scalar_where(db: Session, column, sub_id: int):
    return db.scalar(select(column).where(Subscription.id == sub_id))


def _cycle_of(db: Session, sub_id: int) -> str:
    from app.catalog.models import Plan

    return db.scalar(
        select(Plan.billing_cycle)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(Subscription.id == sub_id)
    )


def _fail_attempt(
    db: Session,
    run: BillingRun,
    sub_id: int,
    idx: int,
    message: str,
    timer_start: float,
    attempt: BillingAttempt | None = None,
) -> BillingAttempt:
    """Period rolled back; record the failure and STOP advancing this subscription."""
    anchor = _scalar_where(db, Subscription.anchor_date, sub_id)
    cycle = _cycle_of(db, sub_id)
    if attempt is not None:
        # Retry of an existing attempt: keep its identity, append the new error.
        # retry_count was already incremented (committed) by retry_run.
        attempt.status = "failed"
        attempt.reason = "error"
        attempt.error_message = _append_error(
            attempt.error_message, retry_n=attempt.retry_count, error=message
        )
        attempt.duration_ms = int((time.perf_counter() - timer_start) * 1000)
        db.commit()
        return attempt
    row = BillingAttempt(
        run_id=run.id,
        subscription_id=sub_id,
        period_start=period_start(anchor, cycle, idx),
        period_end=period_end(anchor, cycle, idx),
        status="failed",
        reason="error",
        error_message=message[:2000],
        duration_ms=int((time.perf_counter() - timer_start) * 1000),
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------- anomalies
def anomalies_for(db: Session, created_attempts: list[BillingAttempt]) -> list[dict]:
    """Flag material total changes vs the subscription's previous invoice (brief §7).

    One anomaly per subscription (earliest new period). |change| >= 10% -> review.
    """
    seen: set[int] = set()
    out: list[dict] = []
    for attempt in sorted(created_attempts, key=lambda a: (a.subscription_id, a.period_start)):
        if attempt.subscription_id in seen:
            continue
        seen.add(attempt.subscription_id)
        sub = attempt.subscription
        prev = db.scalar(
            select(Invoice)
            .where(Invoice.subscription_id == sub.id, Invoice.period_start < attempt.period_start)
            .order_by(Invoice.period_start.desc())
            .limit(1)
        )
        if prev is None:
            continue
        prev_total = Decimal(str(prev.total))
        new_total = Decimal(str(attempt.projected_total or 0))
        change = new_total - prev_total
        if change == 0:
            continue
        pct = (
            (change / prev_total * 100).quantize(Decimal("0.01"))
            if prev_total
            else Decimal("100.00")
        )
        if prev.discount_total and not (attempt.projected_discount or 0):
            reason = "Previous discount expired"
        elif Decimal(str(prev.subtotal)) != Decimal(str(attempt.projected_subtotal or 0)):
            reason = "Line pricing changed"
        else:
            reason = "Total changed since previous invoice"
        review = abs(pct) >= Decimal("10.00")
        out.append(
            {
                "subscription_id": sub.id,
                "subscription_number": sub.number,
                "customer_name": sub.customer_name,
                "previous_total": prev_total,
                "projected_total": new_total,
                "change_amount": change,
                "change_pct": pct,
                "reason": reason,
                "severity": "review" if review else "info",
                "action": "Review the invoice before sending" if review else None,
            }
        )
    return out


# ---------------------------------------------------------------- run driver
def run_billing(
    db: Session,
    run_date=None,
    mode: str = "dry_run",
    user: User | None = None,
    subscription_id: int | None = None,
) -> dict:
    """Execute a billing run synchronously -> run response (docs/API.md §7)."""
    run_date = run_date or today()
    if mode not in ("dry_run", "live"):
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "mode must be dry_run or live")
    if mode == "live" and run_date > today():
        # dry_run may simulate future dates (the SIMULATE step of the brief); live money may not
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            "run_date cannot be in the future for a live run",
        )

    reap_stale_runs(db)

    run = BillingRun(
        run_date=run_date,
        mode=mode,
        subscription_id=subscription_id,
        triggered_by=user.id if user else None,
        status="running",
    )
    db.add(run)
    try:
        db.commit()  # the partial unique index enforces one running run
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, "Another billing run is already in progress"
        )

    t0 = time.perf_counter()
    subs = due_subscriptions(db, run_date, subscription_id)
    run.selected_count = len(subs)
    needing, max_periods = catchup_stats(db, subs, run_date)
    run.catchup_subscriptions = needing
    run.catchup_max_periods = max_periods
    db.commit()

    live = mode == "live"
    cap = settings.max_catchup_periods
    for sub in subs:
        sub_id = sub.id
        idx = sub.period_index
        periods_done = 0
        while periods_done < cap:
            # Re-read the pointer: live billing advances it every period
            fresh = db.get(Subscription, sub_id)
            if fresh is None or fresh.status != "active":
                break
            anchor, cycle = fresh.anchor_date, fresh.plan.billing_cycle
            if period_start(anchor, cycle, idx) > run_date:
                break
            # Term end: auto-close at expiry; keep billing when plan.auto_close=false
            if (
                fresh.expiry_date is not None
                and period_start(anchor, cycle, idx) > fresh.expiry_date
                and fresh.plan.auto_close
            ):
                from app.subscriptions import service as sub_service

                sub_service.transition(db, fresh, "closed", user, reason="Auto-closed at expiry")
                break
            attempt = _process_period(db, run, sub_id, idx, run_date, live, time.perf_counter())
            if attempt.status == "failed":
                break  # stop advancing THIS subscription; run continues with the next
            idx += 1
            periods_done += 1

    _finalize_run(db, run, t0)
    return build_run_response(db, run)


def _finalize_run(db: Session, run: BillingRun, t0: float) -> None:
    """Counts + projected sums from the attempts actually recorded."""
    created = list(
        db.scalars(
            select(BillingAttempt).where(
                BillingAttempt.run_id == run.id, BillingAttempt.status == "created"
            )
        ).all()
    )
    run.created_count = len(created) if run.mode == "live" else 0  # live counts real invoices
    run.skipped_count = (
        db.scalar(
            select(func.count(BillingAttempt.id)).where(
                BillingAttempt.run_id == run.id, BillingAttempt.status == "skipped"
            )
        )
        or 0
    )
    run.failed_count = (
        db.scalar(
            select(func.count(BillingAttempt.id)).where(
                BillingAttempt.run_id == run.id, BillingAttempt.status == "failed"
            )
        )
        or 0
    )
    # Attempts carry projected components in BOTH modes, so the sums are uniform
    run.projected_subtotal = sum(Decimal(str(a.projected_subtotal or 0)) for a in created)
    run.projected_tax = sum(Decimal(str(a.projected_tax or 0)) for a in created)
    run.projected_discount = sum(Decimal(str(a.projected_discount or 0)) for a in created)
    run.projected_total = sum(Decimal(str(a.projected_total or 0)) for a in created)
    run.status = "completed_with_errors" if run.failed_count else "completed"
    run.finished_at = datetime.now(UTC)
    run.duration_ms = int((time.perf_counter() - t0) * 1000)
    db.commit()


# ---------------------------------------------------------------- response
def build_run_response(db: Session, run: BillingRun) -> dict:
    """The documented run shape (POST /billing/runs, GET /{id}, POST /{id}/retry)."""
    attempts = list(
        db.scalars(
            select(BillingAttempt)
            .where(BillingAttempt.run_id == run.id)
            .order_by(BillingAttempt.id)
        ).all()
    )
    created = [a for a in attempts if a.status == "created"]
    subtotal = sum(Decimal(str(a.projected_subtotal or 0)) for a in created)
    tax = sum(Decimal(str(a.projected_tax or 0)) for a in created)
    discount = sum(Decimal(str(a.projected_discount or 0)) for a in created)
    total = sum(Decimal(str(a.projected_total or 0)) for a in created)

    preview = [
        {
            "subscription": a.subscription.number if a.subscription else str(a.subscription_id),
            "period_start": a.period_start,
            "period_end": a.period_end,
            "total": Decimal(str(a.projected_total)),
            "discount_rule": a.discount_rule_name,
            "reason": None,
        }
        for a in created[:50]  # sample; full detail via GET /billing/runs/{id}/attempts
    ]
    return {
        "run_id": run.id,
        "run_date": run.run_date,
        "mode": run.mode,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": run.duration_ms,
        "selected_count": run.selected_count,
        "created_count": run.created_count,
        "skipped_count": run.skipped_count,
        "failed_count": run.failed_count,
        "catchup": {"subscriptions": run.catchup_subscriptions, "max_periods": run.catchup_max_periods},
        "projected": {
            "invoices": len(created),
            "subtotal": subtotal,
            "tax": tax,
            "discount": discount,
            "total": total,
        },
        "anomalies": anomalies_for(db, created),
        "preview": preview,
    }


# ---------------------------------------------------------------- retry
def retry_run(db: Session, run: BillingRun, attempt_ids: list[int] | None = None) -> dict:
    """Reprocess FAILED attempts only. Increments retry_count; appends to (never
    overwrites) error_message; idempotency-safe. Works on interrupted runs too.
    """
    reap_stale_runs(db)  # a stale `running` run becomes `interrupted` and is retryable
    if run.status == "running":
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Run is still in progress")

    stmt = select(BillingAttempt).where(
        BillingAttempt.run_id == run.id, BillingAttempt.status == "failed"
    )
    if attempt_ids:
        stmt = stmt.where(BillingAttempt.id.in_(attempt_ids))
    targets = list(db.scalars(stmt.order_by(BillingAttempt.id)).all())

    live = run.mode == "live"
    for attempt in targets:
        timer = time.perf_counter()
        # Increment retry_count in place BEFORE processing, committed, so even a
        # period rollback cannot lose it (docs/API.md §7 retry contract)
        attempt.retry_count += 1
        db.commit()
        sub = db.get(Subscription, attempt.subscription_id)
        if sub is None:
            attempt.error_message = _append_error(
                attempt.error_message, retry_n=attempt.retry_count, error="subscription missing"
            )
            db.commit()
            continue
        # Recover the period index the attempt refers to
        idx, _ = first_index_on_or_after(
            sub.anchor_date, sub.plan.billing_cycle, attempt.period_start
        )
        # UPDATE the failed attempt in place — never insert a duplicate period row
        _process_period(db, run, attempt.subscription_id, idx, run.run_date, live, timer, attempt=attempt)

    _recount_run(db, run)
    db.commit()
    return build_run_response(db, run)


def _recount_run(db: Session, run: BillingRun) -> None:
    """Recompute counts + status after retries (attempts are the source of truth)."""
    created_count = (
        db.scalar(
            select(func.count(BillingAttempt.id)).where(
                BillingAttempt.run_id == run.id, BillingAttempt.status == "created"
            )
        )
        or 0
    )
    run.created_count = created_count if run.mode == "live" else 0
    run.skipped_count = (
        db.scalar(
            select(func.count(BillingAttempt.id)).where(
                BillingAttempt.run_id == run.id, BillingAttempt.status == "skipped"
            )
        )
        or 0
    )
    run.failed_count = (
        db.scalar(
            select(func.count(BillingAttempt.id)).where(
                BillingAttempt.run_id == run.id, BillingAttempt.status == "failed"
            )
        )
        or 0
    )
    created = list(
        db.scalars(
            select(BillingAttempt).where(
                BillingAttempt.run_id == run.id, BillingAttempt.status == "created"
            )
        ).all()
    )
    run.projected_subtotal = sum(Decimal(str(a.projected_subtotal or 0)) for a in created)
    run.projected_tax = sum(Decimal(str(a.projected_tax or 0)) for a in created)
    run.projected_discount = sum(Decimal(str(a.projected_discount or 0)) for a in created)
    run.projected_total = sum(Decimal(str(a.projected_total or 0)) for a in created)
    run.status = "completed_with_errors" if run.failed_count else "completed"


def _append_error(previous: str | None, *, retry_n: int, error: str | None) -> str | None:
    """History-preserving: retry failures APPEND, the original error stays."""
    if not error:
        return previous
    if not previous:
        return f"retry {retry_n}: {error}"
    return f"{previous} | retry {retry_n}: {error}"[:2000]