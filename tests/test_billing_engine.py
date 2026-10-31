"""Billing engine tests: dry-run purity, live billing, idempotency, catch-up,
retry, discounts, anomalies, expiry auto-close (brief §5-§7 / docs/API.md §7).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.conftest import auth_header

from app.billing import engine
from app.billing.date_calculator import add_months, period_start, today
from app.billing.models import BillingAttempt, BillingRun, DiscountRedemption, Invoice
from app.catalog.models import DiscountRule
from app.subscriptions.models import Subscription


# ---------------------------------------------------------------- helpers
def _setup(client, make_user, plan_extra=None):
    """Admin + staff + customer, a product, an active monthly plan."""
    _, admin_token = make_user(role="admin")
    _, staff_token = make_user(role="staff")
    customer, customer_token = make_user(role="customer")
    h = auth_header(admin_token)

    product = client.post(
        "/api/v1/products", headers=h, json={"name": "CloudPro", "sales_price": 2000.00}
    ).json()
    plan_payload = {"name": "Growth Monthly", "billing_cycle": "monthly", "price": 1180.00}
    plan_payload.update(plan_extra or {})
    plan = client.post("/api/v1/plans", headers=h, json=plan_payload).json()
    return admin_token, staff_token, customer, customer_token, product, plan


def _active_sub(client, token, customer_id, plan_id, product_id, start_date=None, **extra):
    """Create + drive to active. start_date backdates the anchor for catch-up tests."""
    payload = {
        "customer_id": customer_id,
        "plan_id": plan_id,
        "lines": [{"product_id": product_id, "quantity": 10, "unit_price": 1180.00}],
    }
    if start_date is not None:
        payload["start_date"] = start_date.isoformat()
    payload.update(extra)
    hs = auth_header(token)
    sub = client.post("/api/v1/subscriptions", headers=hs, json=payload).json()
    client.post(f"/api/v1/subscriptions/{sub['id']}/send", headers=hs)
    client.post(f"/api/v1/subscriptions/{sub['id']}/confirm", headers=hs)
    r = client.post(f"/api/v1/subscriptions/{sub['id']}/activate", headers=hs)
    assert r.status_code == 200, r.text
    return r.json()


def _run(client, token, **payload):
    return client.post("/api/v1/billing/runs", headers=auth_header(token), json=payload)


def _invoices(db, subscription_id):
    return list(
        db.scalars(
            select(Invoice)
            .where(Invoice.subscription_id == subscription_id)
            .order_by(Invoice.period_start)
        ).all()
    )


def _reset_pointer(db, sub_id):
    """Simulate pointer drift (admin rewind): the period is billed but the
    subscription says it's due again — rerun must skip, never double-bill."""
    sub = db.get(Subscription, sub_id)
    sub.period_index = 0
    sub.next_billing_date = sub.anchor_date
    db.commit()


# ---------------------------------------------------------------- dry run
class TestDryRun:
    def test_dry_run_persists_run_and_attempts_but_nothing_else(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        r = _run(client, staff, mode="dry_run")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "dry_run"
        assert body["status"] == "completed"
        assert body["selected_count"] == 1
        assert body["created_count"] == 0  # dry run never counts invoices
        assert body["projected"]["invoices"] == 1
        assert Decimal(body["projected"]["total"]) == Decimal("11800.00")

        # run + attempt rows persist for audit
        assert db.get(BillingRun, body["run_id"]) is not None
        attempts = db.scalars(
            select(BillingAttempt).where(BillingAttempt.run_id == body["run_id"])
        ).all()
        assert len(attempts) == 1
        assert attempts[0].status == "created"
        assert Decimal(str(attempts[0].projected_total)) == Decimal("11800.00")
        assert attempts[0].invoice_id is None

        # NO invoices, pointer untouched
        assert _invoices(db, sub["id"]) == []
        fresh = db.get(Subscription, sub["id"])
        assert fresh.next_billing_date == date.today()
        assert fresh.period_index == 0

    def test_dry_run_projects_discount_without_redeeming(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(client, make_user)
        client.post(
            "/api/v1/discount-rules",
            headers=auth_header(admin),
            json={
                "name": "LAUNCH10",
                "type": "percentage",
                "value": 10,
                "starts_at": "2020-01-01",
            },
        )
        _active_sub(client, staff, customer.id, plan["id"], product["id"])
        body = _run(client, staff, mode="dry_run").json()
        assert Decimal(body["projected"]["discount"]) == Decimal("1180.00")
        assert Decimal(body["projected"]["total"]) == Decimal("10620.00")
        assert body["preview"][0]["discount_rule"] == "LAUNCH10"
        # no redemption, no used_count
        assert db.scalars(select(DiscountRedemption)).all() == []
        rule = db.scalars(select(DiscountRule)).first()
        assert rule.used_count == 0

    def test_dry_run_future_date_allowed_live_rejected(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        _active_sub(client, staff, customer.id, plan["id"], product["id"])
        future = today() + timedelta(days=45)
        r = _run(client, staff, mode="dry_run", run_date=future.isoformat())
        assert r.status_code == 200
        # a monthly sub 45 days out has 2 due periods (idx 0, 1) — projection works
        assert r.json()["projected"]["invoices"] >= 1

        r = _run(client, staff, mode="live", run_date=future.isoformat())
        assert r.status_code == 422
        assert "future" in r.json()["detail"]


# ---------------------------------------------------------------- live run
class TestLiveRun:
    def test_live_run_creates_invoice_and_advances_pointer(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        body = _run(client, staff, mode="live").json()
        assert body["status"] == "completed"
        assert body["created_count"] == 1

        invoices = _invoices(db, sub["id"])
        assert len(invoices) == 1
        inv = invoices[0]
        assert inv.number.startswith(f"INV-{date.today().year}-")
        assert inv.status == "draft"
        assert Decimal(str(inv.subtotal)) == Decimal("11800.00")
        assert Decimal(str(inv.total)) == Decimal("11800.00")
        assert len(inv.lines) == 1
        assert inv.lines[0].quantity == 10

        # pointer advanced exactly one period, anchored math
        fresh = db.get(Subscription, sub["id"])
        assert fresh.period_index == 1
        assert fresh.next_billing_date == period_start(fresh.anchor_date, "monthly", 1)
        assert fresh.last_billing_date == fresh.anchor_date

        # attempt links the invoice
        attempt = db.scalars(
            select(BillingAttempt).where(BillingAttempt.run_id == body["run_id"])
        ).first()
        assert attempt.invoice_id == inv.id
        assert Decimal(str(attempt.actual_total)) == Decimal("11800.00")

    def test_due_date_follows_payment_terms(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(
            client, staff, customer.id, plan["id"], product["id"], payment_terms="Net 30"
        )
        _run(client, staff, mode="live")
        inv = _invoices(db, sub["id"])[0]
        assert inv.due_date == inv.issue_date + timedelta(days=30)

    def test_tax_computed_after_discount(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(client, make_user)
        h = auth_header(admin)
        client.post("/api/v1/tax-rules", headers=h, json={"name": "GST18", "rate": 18})
        client.post(
            "/api/v1/discount-rules",
            headers=h,
            json={
                "name": "LAUNCH10",
                "type": "percentage",
                "value": 10,
                "starts_at": "2020-01-01",
            },
        )
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        _run(client, staff, mode="live")
        inv = _invoices(db, sub["id"])[0]
        # subtotal 11800, -10% = 10620 base, 18% tax on the DISCOUNTED base
        assert Decimal(str(inv.subtotal)) == Decimal("11800.00")
        assert Decimal(str(inv.discount_total)) == Decimal("1180.00")
        assert Decimal(str(inv.tax_total)) == Decimal("1911.60")
        # contract: total = subtotal - discount + tax
        assert Decimal(str(inv.total)) == Decimal("12531.60")
        line = inv.lines[0]
        assert Decimal(str(line.discount_amount)) == Decimal("1180.00")
        assert Decimal(str(line.tax_amount)) == Decimal("1911.60")


# ---------------------------------------------------------------- idempotency
class TestIdempotency:
    def test_rerun_same_day_skips_billed_period(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        _run(client, staff, mode="live")

        # drift the pointer back (simulates a missed advance) -> rerun must NOT double bill
        _reset_pointer(db, sub["id"])
        body = _run(client, staff, mode="live").json()
        assert body["created_count"] == 0
        assert body["skipped_count"] == 1
        assert len(_invoices(db, sub["id"])) == 1
        attempt = db.scalars(
            select(BillingAttempt).where(
                BillingAttempt.run_id == body["run_id"], BillingAttempt.status == "skipped"
            )
        ).first()
        assert attempt.reason == "already_invoiced"
        # pointer reconciled forward again
        assert db.get(Subscription, sub["id"]).period_index == 1

    def test_unique_invoice_is_the_hard_backstop(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        _run(client, staff, mode="live")
        inv = _invoices(db, sub["id"])[0]
        with pytest.raises(IntegrityError):
            db.add(
                Invoice(
                    number="INV-1999-0001",
                    subscription_id=sub["id"],
                    customer_id=customer.id,
                    period_start=inv.period_start,
                    period_end=inv.period_end,
                    issue_date=date.today(),
                    due_date=date.today(),
                )
            )
            db.commit()
        db.rollback()

    def test_invoice_number_sequence_increments(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(
            client, staff, customer.id, plan["id"], product["id"], start_date=add_months(today(), -1)
        )
        _run(client, staff, mode="live")
        numbers = [i.number for i in _invoices(db, sub["id"])]
        assert len(numbers) == 2
        assert numbers[0] < numbers[1]  # INV-YYYY-0001 then 0002


# ---------------------------------------------------------------- catch-up
class TestCatchUp:
    def test_all_missed_periods_billed_in_one_run(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        start = add_months(today(), -2)  # 3 monthly periods due
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        body = _run(client, staff, mode="live").json()
        assert body["created_count"] == 3
        assert body["catchup"] == {"subscriptions": 1, "max_periods": 3}

        invoices = _invoices(db, sub["id"])
        assert [i.period_start for i in invoices] == [
            period_start(start, "monthly", 0),
            period_start(start, "monthly", 1),
            period_start(start, "monthly", 2),
        ]
        fresh = db.get(Subscription, sub["id"])
        assert fresh.period_index == 3
        assert fresh.next_billing_date == period_start(start, "monthly", 3)

    def test_catchup_cap_stops_at_max_periods(self, client, make_user, db, monkeypatch):
        monkeypatch.setattr(engine.settings, "max_catchup_periods", 2)
        _, staff, customer, _, product, plan = _setup(client, make_user)
        start = add_months(today(), -5)  # 6 periods due, capped at 2
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        body = _run(client, staff, mode="live").json()
        assert body["created_count"] == 2
        assert len(_invoices(db, sub["id"])) == 2
        # the rest stays due for the next run
        assert db.get(Subscription, sub["id"]).next_billing_date <= today()

    def test_paused_and_closed_subscriptions_never_billed(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        start = add_months(today(), -2)
        paused = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        closed = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        hs = auth_header(staff)
        client.post(f"/api/v1/subscriptions/{paused['id']}/pause", headers=hs, json={})
        client.post(f"/api/v1/subscriptions/{closed['id']}/close", headers=hs, json={})
        body = _run(client, staff, mode="live").json()
        assert body["selected_count"] == 0
        assert _invoices(db, paused["id"]) == []
        assert _invoices(db, closed["id"]) == []


# ---------------------------------------------------------------- guards
class TestGuards:
    def test_second_run_conflicts_while_running(self, client, make_user, db):
        _, staff, *_ = _setup(client, make_user)
        db.add(BillingRun(run_date=date.today(), mode="live", status="running"))
        db.commit()
        r = _run(client, staff, mode="live")
        assert r.status_code == 409
        assert r.json()["detail"] == "Another billing run is already in progress"

    def test_customers_cannot_run_billing(self, client, make_user):
        _, _, _, customer_token, _, _ = _setup(client, make_user)
        r = _run(client, customer_token, mode="dry_run")
        assert r.status_code == 403

    def test_invalid_mode_rejected(self, client, make_user):
        _, staff, *_ = _setup(client, make_user)
        r = client.post(
            "/api/v1/billing/runs", headers=auth_header(staff), json={"mode": "banana"}
        )
        assert r.status_code == 422


# ---------------------------------------------------------------- reaper + retry
class TestReaperAndRetry:
    def test_stale_running_run_reaped_at_next_run(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        stale = BillingRun(
            run_date=date.today(),
            mode="live",
            status="running",
            started_at=datetime.now(ZoneInfo("UTC")) - timedelta(minutes=30),
        )
        db.add(stale)
        db.commit()

        _active_sub(client, staff, customer.id, plan["id"], product["id"])
        body = _run(client, staff, mode="live").json()
        assert body["status"] == "completed"  # not blocked by the wedged run
        db.refresh(stale)
        assert stale.status == "interrupted"

    def test_interrupted_run_with_no_failures_is_retry_noop(self, client, make_user, db):
        _, staff, *_ = _setup(client, make_user)
        run = BillingRun(run_date=date.today(), mode="live", status="interrupted")
        db.add(run)
        db.commit()
        r = client.post(f"/api/v1/billing/runs/{run.id}/retry", headers=auth_header(staff), json={})
        assert r.status_code == 200
        assert r.json()["failed_count"] == 0

    def test_failed_attempt_then_successful_retry(self, client, make_user, db, monkeypatch):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])

        real = engine._persist_invoice
        boom_ids = {sub["id"]}

        def flaky(db_, run, sub_, quote, run_date):
            if sub_.id in boom_ids:
                raise RuntimeError("disk full")
            return real(db_, run, sub_, quote, run_date)

        monkeypatch.setattr(engine, "_persist_invoice", flaky)
        body = _run(client, staff, mode="live").json()
        assert body["status"] == "completed_with_errors"
        assert body["failed_count"] == 1
        assert _invoices(db, sub["id"]) == []
        # subscription stopped advancing
        assert db.get(Subscription, sub["id"]).period_index == 0

        attempt_id = body["run_id"]
        attempts = db.scalars(
            select(BillingAttempt).where(BillingAttempt.run_id == attempt_id)
        ).all()
        failed = attempts[0]
        assert failed.status == "failed"
        assert "disk full" in failed.error_message
        failed_attempt_id = failed.id

        # fix the fault and retry
        monkeypatch.setattr(engine, "_persist_invoice", real)
        r = client.post(
            f"/api/v1/billing/runs/{attempt_id}/retry",
            headers=auth_header(staff),
            json={"attempt_ids": [failed_attempt_id]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["created_count"] == 1
        assert body["failed_count"] == 0

        # same attempt row updated in place: retry_count, preserved error history
        db.expire_all()
        retried = db.get(BillingAttempt, failed_attempt_id)
        assert retried.status == "created"
        assert retried.retry_count == 1
        assert retried.invoice_id is not None
        assert "disk full" in retried.error_message  # history preserved
        assert len(_invoices(db, sub["id"])) == 1  # exactly one invoice, no duplicates
        assert db.get(Subscription, sub["id"]).period_index == 1

    def test_repeated_failure_appends_to_error_history(self, client, make_user, db, monkeypatch):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])

        def always_broken(*args, **kwargs):
            raise RuntimeError("gateway timeout")

        monkeypatch.setattr(engine, "_persist_invoice", always_broken)
        body = _run(client, staff, mode="live").json()
        run_id = body["run_id"]

        for expected_retry in (1, 2):
            r = client.post(
                f"/api/v1/billing/runs/{run_id}/retry", headers=auth_header(staff), json={}
            )
            assert r.status_code == 200
            assert r.json()["failed_count"] == 1
            db.expire_all()
            attempt = db.scalars(
                select(BillingAttempt).where(BillingAttempt.run_id == run_id)
            ).first()
            assert attempt.retry_count == expected_retry
            assert f"retry {expected_retry}" in attempt.error_message
        # original error still present at the head of the history
        assert attempt.error_message.startswith("gateway timeout")
        assert attempt.error_message.count("gateway timeout") == 3  # original + 2 retries


# ---------------------------------------------------------------- discounts
class TestDiscounts:
    def test_live_run_redeems_discount_exactly_once(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(client, make_user)
        rule = client.post(
            "/api/v1/discount-rules",
            headers=auth_header(admin),
            json={
                "name": "LAUNCH10",
                "type": "percentage",
                "value": 10,
                "starts_at": "2020-01-01",
                "usage_limit": 5,
            },
        ).json()
        start = add_months(today(), -1)  # two periods
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        body = _run(client, staff, mode="live").json()
        assert body["created_count"] == 2
        redemptions = db.scalars(select(DiscountRedemption)).all()
        assert len(redemptions) == 2  # one per invoice
        db.expire_all()
        assert db.get(DiscountRule, rule["id"]).used_count == 2
        for inv in _invoices(db, sub["id"]):
            assert Decimal(str(inv.discount_total)) == Decimal("1180.00")
            assert Decimal(str(inv.total)) == Decimal("10620.00")

    def test_usage_limit_stops_further_redemption(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(client, make_user)
        rule = client.post(
            "/api/v1/discount-rules",
            headers=auth_header(admin),
            json={
                "name": "ONCEONLY",
                "type": "fixed",
                "value": 500,
                "starts_at": "2020-01-01",
                "usage_limit": 1,
            },
        ).json()
        # exhaust the limit up front
        r = db.get(DiscountRule, rule["id"])
        r.used_count = 1
        db.commit()

        start = add_months(today(), -1)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        body = _run(client, staff, mode="live").json()
        assert body["created_count"] == 2
        for inv in _invoices(db, sub["id"]):
            assert Decimal(str(inv.discount_total)) == Decimal("0.00")  # limit reached
            assert Decimal(str(inv.total)) == Decimal("11800.00")
        assert db.scalars(select(DiscountRedemption)).all() == []

    def test_largest_discount_wins_single_rule(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(client, make_user)
        h = auth_header(admin)
        client.post(
            "/api/v1/discount-rules",
            headers=h,
            json={"name": "SMALL500", "type": "fixed", "value": 500, "starts_at": "2020-01-01"},
        )
        client.post(
            "/api/v1/discount-rules",
            headers=h,
            json={"name": "BIG10", "type": "percentage", "value": 10, "starts_at": "2020-01-01"},
        )
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        body = _run(client, staff, mode="live").json()
        assert body["projected"]["discount"] == "1180.00"  # 10% beats 500 fixed
        inv = _invoices(db, sub["id"])[0]
        assert Decimal(str(inv.discount_total)) == Decimal("1180.00")
        redemption = db.scalars(select(DiscountRedemption)).first()
        assert redemption.discount_rule_id == 2  # BIG10

    def test_tie_breaks_to_lower_id(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(client, make_user)
        h = auth_header(admin)
        for name in ("TIE_A", "TIE_B"):
            client.post(
                "/api/v1/discount-rules",
                headers=h,
                json={"name": name, "type": "fixed", "value": 500, "starts_at": "2020-01-01"},
            )
        _active_sub(client, staff, customer.id, plan["id"], product["id"])
        _run(client, staff, mode="live")
        redemption = db.scalars(select(DiscountRedemption)).first()
        assert redemption.discount_rule_id == 1  # lower id wins the tie

    def test_min_purchase_gate_respected(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(client, make_user)
        client.post(
            "/api/v1/discount-rules",
            headers=auth_header(admin),
            json={
                "name": "WHALES",
                "type": "percentage",
                "value": 20,
                "min_purchase": 99999,
                "starts_at": "2020-01-01",
            },
        )
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        _run(client, staff, mode="live")
        inv = _invoices(db, sub["id"])[0]
        assert Decimal(str(inv.discount_total)) == Decimal("0.00")


# ---------------------------------------------------------------- anomalies
class TestAnomalies:
    def test_expired_discount_flagged_for_review(self, client, make_user, db):
        admin, staff, customer, _, product, plan = _setup(
            client, make_user, plan_extra={"billing_cycle": "daily"}
        )
        h = auth_header(admin)
        rule = client.post(
            "/api/v1/discount-rules",
            headers=h,
            json={
                "name": "HALFPRICE",
                "type": "fixed",
                "value": 2000,
                "starts_at": "2020-01-01",
            },
        ).json()
        start = today() - timedelta(days=2)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)

        # first run bills days 1-2 WITH the discount
        first = _run(client, staff, mode="live", run_date=(today() - timedelta(days=1)).isoformat()).json()
        assert first["created_count"] == 2
        assert Decimal(first["projected"]["discount"]) == Decimal("4000.00")

        # discount expires; today's run bills at full price -> anomaly vs previous invoice
        client.patch(
            f"/api/v1/discount-rules/{rule['id']}",
            headers=h,
            json={"ends_at": (today() - timedelta(days=1)).isoformat()},
        )
        second = _run(client, staff, mode="live").json()
        assert second["created_count"] == 1
        anomalies = second["anomalies"]
        assert len(anomalies) == 1  # one per subscription, earliest new period only
        a = anomalies[0]
        assert a["subscription_id"] == sub["id"]
        assert a["reason"] == "Previous discount expired"
        assert a["severity"] == "review"  # 11800 vs 9800 = +20.4%
        assert Decimal(a["change_pct"]) > Decimal("10")
        assert a["action"] == "Review the invoice before sending"

    def test_first_invoice_produces_no_anomaly(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        _active_sub(client, staff, customer.id, plan["id"], product["id"])
        body = _run(client, staff, mode="live").json()
        assert body["anomalies"] == []


# ---------------------------------------------------------------- expiry auto-close
class TestExpiryAutoClose:
    def test_auto_close_closes_subscription_at_term_end(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        start = add_months(today(), -1)
        expiry = start + timedelta(days=20)  # before the 2nd period start
        sub = _active_sub(
            client, staff, customer.id, plan["id"], product["id"],
            start_date=start, expiry_date=expiry.isoformat(),
        )
        body = _run(client, staff, mode="live").json()
        assert body["created_count"] == 1  # 2nd period starts after expiry
        db.expire_all()
        fresh = db.get(Subscription, sub["id"])
        assert fresh.status == "closed"
        assert fresh.close_reason == "Auto-closed at expiry"

    def test_no_auto_close_keeps_billing_past_expiry(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(
            client, make_user, plan_extra={"auto_close": False}
        )
        start = add_months(today(), -1)
        expiry = start + timedelta(days=20)
        sub = _active_sub(
            client, staff, customer.id, plan["id"], product["id"],
            start_date=start, expiry_date=expiry.isoformat(),
        )
        body = _run(client, staff, mode="live").json()
        assert body["created_count"] == 2  # keeps billing past the term
        db.expire_all()
        assert db.get(Subscription, sub["id"]).status == "active"


# ---------------------------------------------------------------- bill-now + endpoints
class TestBillNowAndEndpoints:
    def test_bill_now_scopes_to_one_subscription(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        start = add_months(today(), -1)
        a = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        b = _active_sub(client, staff, customer.id, plan["id"], product["id"], start_date=start)
        r = client.post(f"/api/v1/subscriptions/{a['id']}/bill-now", headers=auth_header(staff))
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "live"
        assert body["selected_count"] == 1
        assert body["created_count"] == 2  # catch-up for A only
        assert len(_invoices(db, a["id"])) == 2
        assert _invoices(db, b["id"]) == []  # B untouched
        assert db.get(Subscription, b["id"]).period_index == 0

    def test_attempts_endpoint_filters_by_status(self, client, make_user, db):
        _, staff, customer, _, product, plan = _setup(client, make_user)
        sub = _active_sub(client, staff, customer.id, plan["id"], product["id"])
        body = _run(client, staff, mode="live").json()
        hs = auth_header(staff)

        r = client.get(f"/api/v1/billing/runs/{body['run_id']}/attempts", headers=hs)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["subscription_number"] == sub["number"]
        assert items[0]["status"] == "created"
        assert items[0]["invoice_id"] is not None
        assert Decimal(items[0]["projected_total"]) == Decimal("11800.00")

        r = client.get(
            f"/api/v1/billing/runs/{body['run_id']}/attempts?status=failed", headers=hs
        )
        assert r.json()["total"] == 0

    def test_run_listing_filters_by_mode(self, client, make_user):
        _, staff, *_ = _setup(client, make_user)
        _run(client, staff, mode="dry_run")
        _run(client, staff, mode="live")
        hs = auth_header(staff)
        assert client.get("/api/v1/billing/runs", headers=hs).json()["total"] == 2
        assert client.get("/api/v1/billing/runs?mode=live", headers=hs).json()["total"] == 1
        assert client.get("/api/v1/billing/runs?mode=dry_run", headers=hs).json()["total"] == 1

    def test_run_detail_matches_post_shape(self, client, make_user):
        _, staff, *_ = _setup(client, make_user)
        posted = _run(client, staff, mode="dry_run").json()
        hs = auth_header(staff)
        r = client.get(f"/api/v1/billing/runs/{posted['run_id']}", headers=hs)
        assert r.status_code == 200
        body = r.json()
        for key in ("run_id", "run_date", "mode", "status", "catchup", "projected", "preview"):
            assert body[key] == posted[key]

    def test_unknown_run_404(self, client, make_user):
        _, staff, *_ = _setup(client, make_user)
        hs = auth_header(staff)
        assert client.get("/api/v1/billing/runs/9999", headers=hs).status_code == 404
        assert client.post("/api/v1/billing/runs/9999/retry", headers=hs, json={}).status_code == 404
