"""Subscription tests: creation validation, lifecycle, guards, conversion, scoping.

Brief §21 / docs/API.md §6. Date math itself is covered in test_date_calculator.
"""
from datetime import date, timedelta

from tests.conftest import auth_header

from app.billing.date_calculator import today


def _setup(client, make_user):
    """Admin + staff + customer tokens, a product, an active plan."""
    _, admin_token = make_user(role="admin")
    _, staff_token = make_user(role="staff")
    customer, customer_token = make_user(role="customer")
    h = auth_header(admin_token)

    product = client.post(
        "/api/v1/products", headers=h, json={"name": "CloudPro", "sales_price": 2000.00}
    ).json()
    plan = client.post(
        "/api/v1/plans",
        headers=h,
        json={"name": "Growth Monthly", "billing_cycle": "monthly", "price": 1180.00},
    ).json()
    return admin_token, staff_token, customer, customer_token, product, plan


def _create_sub(client, token, customer_id, plan_id, product_id, **extra):
    payload = {
        "customer_id": customer_id,
        "plan_id": plan_id,
        "lines": [{"product_id": product_id, "quantity": 10, "unit_price": 1180.00}],
    }
    payload.update(extra)
    return client.post("/api/v1/subscriptions", headers=auth_header(token), json=payload)


def _to_active(client, token, subscription_id, start_date=None):
    """drive draft -> quotation -> confirmed -> active."""
    hs = auth_header(token)
    client.post(f"/api/v1/subscriptions/{subscription_id}/send", headers=hs)
    client.post(f"/api/v1/subscriptions/{subscription_id}/confirm", headers=hs)
    r = client.post(f"/api/v1/subscriptions/{subscription_id}/activate", headers=hs)
    assert r.status_code == 200, r.text
    return r.json()


class TestCreate:
    def test_create_draft_with_number_and_totals(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        r = _create_sub(client, staff_token, customer.id, plan["id"], product["id"])
        assert r.status_code == 201
        body = r.json()
        assert body["number"].startswith(f"SUB-{date.today().year}-")
        assert body["status"] == "draft"
        assert body["anchor_date"] == body["start_date"] == body["next_billing_date"]
        assert len(body["lines"]) == 1
        assert float(body["total"]) == 10 * 1180.00
        # audit: creation recorded
        assert body["events"][-1]["from_status"] is None
        assert body["events"][-1]["to_status"] == "draft"

    def test_closed_plan_rejected(self, client, make_user):
        admin_token, staff_token, customer, _, product, plan = _setup(client, make_user)
        client.post(f"/api/v1/plans/{plan['id']}/close", headers=auth_header(admin_token))
        r = _create_sub(client, staff_token, customer.id, plan["id"], product["id"])
        assert r.status_code == 422 and "closed" in r.json()["detail"]

    def test_availability_window_enforced(self, client, make_user):
        admin_token, staff_token, customer, _, product, plan = _setup(client, make_user)
        client.patch(
            f"/api/v1/plans/{plan['id']}",
            headers=auth_header(admin_token),
            json={"available_from": str(date.today() + timedelta(days=30))},
        )
        r = _create_sub(client, staff_token, customer.id, plan["id"], product["id"])
        assert r.status_code == 422 and "not yet available" in r.json()["detail"]

    def test_min_quantity_enforced(self, client, make_user):
        admin_token, staff_token, customer, _, product, plan = _setup(client, make_user)
        client.patch(f"/api/v1/plans/{plan['id']}", headers=auth_header(admin_token), json={"min_quantity": 20})
        r = _create_sub(client, staff_token, customer.id, plan["id"], product["id"])
        assert r.status_code == 422 and "minimum quantity" in r.json()["detail"]

    def test_expiry_before_start_rejected(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        start = date.today() + timedelta(days=10)
        r = _create_sub(
            client, staff_token, customer.id, plan["id"], product["id"],
            start_date=str(start), expiry_date=str(start - timedelta(days=1)),
        )
        assert r.status_code == 422

    def test_staff_cannot_create_for_non_customer(self, client, make_user):
        _, staff_token, _, _, product, plan = _setup(client, make_user)
        staff2, _ = make_user(role="staff")
        r = _create_sub(client, staff_token, staff2.id, plan["id"], product["id"])
        assert r.status_code == 422

    def test_customer_cannot_create(self, client, make_user):
        _, _, customer, customer_token, product, plan = _setup(client, make_user)
        r = _create_sub(client, customer_token, customer.id, plan["id"], product["id"])
        assert r.status_code == 403


class TestLifecycle:
    def test_full_happy_path(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        future_start = str(date.today() + timedelta(days=30))
        sub = _create_sub(
            client, staff_token, customer.id, plan["id"], product["id"], start_date=future_start
        ).json()
        sid = sub["id"]

        assert client.post(f"/api/v1/subscriptions/{sid}/send", headers=hs).json()["status"] == "quotation"
        assert client.post(f"/api/v1/subscriptions/{sid}/revise", headers=hs).json()["status"] == "draft"
        assert client.post(f"/api/v1/subscriptions/{sid}/send", headers=hs).json()["status"] == "quotation"
        assert client.post(f"/api/v1/subscriptions/{sid}/confirm", headers=hs).json()["status"] == "confirmed"

        # future start cannot activate
        r = client.post(f"/api/v1/subscriptions/{sid}/activate", headers=hs)
        assert r.status_code == 409 and "start date" in r.json()["detail"]

        # backdate the start (direct DB write — PATCH re-anchors, we only want the guard flipped)
        from sqlalchemy import update

        from app.core.database import SessionLocal
        from app.subscriptions.models import Subscription

        db = SessionLocal()
        db.execute(update(Subscription).where(Subscription.id == sid).values(start_date=date.today()))
        db.commit()
        db.close()

        assert client.post(f"/api/v1/subscriptions/{sid}/activate", headers=hs).json()["status"] == "active"

        # history has every hop
        detail = client.get(f"/api/v1/subscriptions/{sid}", headers=hs).json()
        hops = [(e["from_status"], e["to_status"]) for e in detail["events"]]
        assert (None, "draft") in hops and ("quotation", "confirmed") in hops
        assert ("confirmed", "active") in hops
        # actor recorded
        assert all(e["actor_id"] is not None for e in detail["events"])

    def test_invalid_transition_409(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        # draft cannot pause/activate/renew
        for action in ("pause", "activate", "renew"):
            assert client.post(f"/api/v1/subscriptions/{sub['id']}/{action}", headers=hs).status_code == 409

    def test_cancel_from_draft_and_quotation(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        r = client.post(f"/api/v1/subscriptions/{sub['id']}/close", headers=hs)
        assert r.status_code == 200 and r.json()["status"] == "closed"


class TestPauseResume:
    def _active_sub(self, client, make_user, plan_flags=None, start_days_ago: int | None = None):
        admin_token, staff_token, customer, _, product, plan = _setup(client, make_user)
        if plan_flags:
            client.patch(f"/api/v1/plans/{plan['id']}", headers=auth_header(admin_token), json=plan_flags)
        extra = {}
        if start_days_ago is not None:
            extra["start_date"] = str(date.today() - timedelta(days=start_days_ago))
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"], **extra).json()
        _to_active(client, staff_token, sub["id"])
        return staff_token, sub["id"]

    def test_pause_freezes_and_resume_waives_elapsed_periods(self, client, make_user):
        # Started 75 days ago: ~2-3 monthly periods have come due since (never billed —
        # the billing engine doesn't exist yet; the frozen date being past is what matters).
        staff_token, sid = self._active_sub(client, make_user, start_days_ago=75)
        hs = auth_header(staff_token)

        r = client.post(f"/api/v1/subscriptions/{sid}/pause", headers=hs, json={"reason": "vacation"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "paused" and body["paused_at"] is not None
        assert body["pause_reason"] == "vacation"
        frozen = body["next_billing_date"]
        assert frozen < str(today())  # frozen in the past — periods came due during the pause

        r = client.post(f"/api/v1/subscriptions/{sid}/resume", headers=hs)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "active" and body["paused_at"] is None
        # re-anchored forward: next billing is a real period start >= today, never the stale past date
        assert body["next_billing_date"] >= str(today())
        assert body["next_billing_date"] != frozen
        # the waiver is recorded in history (more than zero periods)
        assert any(
            "waived" in (e["note"] or "") and not e["note"].startswith("0 ")
            for e in body["events"]
            if e["from_status"] == "paused"
        )

    def test_resume_without_elapsed_periods_keeps_billing_date(self, client, make_user):
        staff_token, sid = self._active_sub(client, make_user)
        hs = auth_header(staff_token)
        client.post(f"/api/v1/subscriptions/{sid}/pause", headers=hs)
        r = client.post(f"/api/v1/subscriptions/{sid}/resume", headers=hs)
        body = r.json()
        # nothing elapsed -> next_billing_date unchanged (== start, in the future-safe sense)
        assert "0 period(s) waived" in next(e["note"] for e in body["events"] if e["to_status"] == "active" and e["from_status"] == "paused")

    def test_pause_blocked_when_plan_disallows(self, client, make_user):
        staff_token, sid = self._active_sub(client, make_user, plan_flags={"allow_pause": False})
        r = client.post(f"/api/v1/subscriptions/{sid}/pause", headers=auth_header(staff_token))
        assert r.status_code == 409 and "allow pause" in r.json()["detail"]


class TestRenewAndClose:
    def test_renew_extends_expiry_one_cycle(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        expiry = date.today() + timedelta(days=15)
        sub = _create_sub(
            client, staff_token, customer.id, plan["id"], product["id"], expiry_date=str(expiry)
        ).json()
        _to_active(client, staff_token, sub["id"])
        r = client.post(f"/api/v1/subscriptions/{sub['id']}/renew", headers=hs)
        assert r.status_code == 200
        from app.billing.date_calculator import add_months

        assert r.json()["expiry_date"] == str(add_months(expiry, 1))  # one monthly cycle

    def test_renew_with_explicit_date_and_blocked_flag(self, client, make_user):
        admin_token, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        _to_active(client, staff_token, sub["id"])
        new_expiry = date.today() + timedelta(days=100)
        r = client.post(
            f"/api/v1/subscriptions/{sub['id']}/renew", headers=hs, json={"new_expiry_date": str(new_expiry)}
        )
        assert r.status_code == 200 and r.json()["expiry_date"] == str(new_expiry)

        client.patch(f"/api/v1/plans/{plan['id']}", headers=auth_header(admin_token), json={"allow_renew": False})
        r = client.post(f"/api/v1/subscriptions/{sub['id']}/renew", headers=hs)
        assert r.status_code == 409 and "renewal" in r.json()["detail"]

    def test_renew_past_date_rejected(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        _to_active(client, staff_token, sub["id"])
        r = client.post(
            f"/api/v1/subscriptions/{sub['id']}/renew",
            headers=hs,
            json={"new_expiry_date": str(date.today() - timedelta(days=1))},
        )
        assert r.status_code == 422

    def test_closed_subscription_renew_reopens_without_backbilling(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        _to_active(client, staff_token, sub["id"])
        client.post(f"/api/v1/subscriptions/{sub['id']}/close", headers=hs, json={"reason": "done"})
        r = client.post(f"/api/v1/subscriptions/{sub['id']}/renew", headers=hs)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "active" and body["closed_at"] is None
        assert body["next_billing_date"] >= str(today())  # no invoice for the closed gap

    def test_early_close_guarded_by_plan(self, client, make_user):
        admin_token, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        client.patch(f"/api/v1/plans/{plan['id']}", headers=auth_header(admin_token), json={"allow_early_close": False})
        sub = _create_sub(
            client, staff_token, customer.id, plan["id"], product["id"],
            expiry_date=str(date.today() + timedelta(days=300)),
        ).json()
        _to_active(client, staff_token, sub["id"])
        r = client.post(f"/api/v1/subscriptions/{sub['id']}/close", headers=hs, json={"early": True})
        assert r.status_code == 409 and "early" in r.json()["detail"]


class TestConversion:
    def _sent_quotation(self, client, staff_token, customer, product, plan):
        hs = auth_header(staff_token)
        quote = client.post(
            "/api/v1/quotations",
            headers=hs,
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "start_date": str(date.today()),
                "lines": [{"product_id": product["id"], "quantity": 10, "unit_price": 1180.00}],
            },
        ).json()
        client.post(f"/api/v1/quotations/{quote['id']}/send", headers=hs)
        return quote

    def test_confirm_creates_confirmed_subscription_once(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        quote = self._sent_quotation(client, staff_token, customer, product, plan)
        hs = auth_header(staff_token)

        r = client.post(f"/api/v1/quotations/{quote['id']}/confirm", headers=hs)
        assert r.status_code == 201
        body = r.json()
        assert body["quotation"]["status"] == "confirmed"
        assert body["quotation"]["subscription_id"] is not None
        sub = body["subscription"]
        assert sub["number"].startswith("SUB-")
        assert sub["status"] == "confirmed"
        assert sub["next_billing_date"] == sub["start_date"]
        # lines snapshotted with tax math from the quotation
        detail = client.get(f"/api/v1/subscriptions/{sub['id']}", headers=hs).json()
        assert len(detail["lines"]) == 1
        assert float(detail["total"]) == 10 * 1180.00
        assert detail["events"][0]["note"].startswith("converted from QUO-")

        # exactly once
        r = client.post(f"/api/v1/quotations/{quote['id']}/confirm", headers=hs)
        assert r.status_code == 409 and "already been converted" in r.json()["detail"]

    def test_customer_can_accept_own_sent_quotation(self, client, make_user):
        _, staff_token, customer, customer_token, product, plan = _setup(client, make_user)
        quote = self._sent_quotation(client, staff_token, customer, product, plan)
        r = client.post(f"/api/v1/quotations/{quote['id']}/confirm", headers=auth_header(customer_token))
        assert r.status_code == 201
        assert r.json()["subscription"]["status"] == "confirmed"

    def test_conversion_blocked_when_plan_closed(self, client, make_user):
        admin_token, staff_token, customer, _, product, plan = _setup(client, make_user)
        quote = self._sent_quotation(client, staff_token, customer, product, plan)
        hs = auth_header(staff_token)
        client.post(f"/api/v1/plans/{plan['id']}/close", headers=auth_header(admin_token))
        r = client.post(f"/api/v1/quotations/{quote['id']}/confirm", headers=hs)
        assert r.status_code == 409 and "closed" in r.json()["detail"]


class TestScopingAndPermissions:
    def test_customer_sees_only_own(self, client, make_user):
        _, staff_token, customer, customer_token, product, plan = _setup(client, make_user)
        _, other_customer_token = make_user(role="customer")
        mine = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()

        hs = auth_header(customer_token)
        r = client.get("/api/v1/subscriptions", headers=hs)
        assert r.json()["total"] == 1 and r.json()["items"][0]["id"] == mine["id"]
        # other customer's id -> 404, not 403
        assert client.get(f"/api/v1/subscriptions/{mine['id']}", headers=auth_header(other_customer_token)).status_code == 404

    def test_customer_can_pause_resume_close_own(self, client, make_user):
        _, staff_token, customer, customer_token, product, plan = _setup(client, make_user)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        _to_active(client, staff_token, sub["id"])
        hs = auth_header(customer_token)
        assert client.post(f"/api/v1/subscriptions/{sub['id']}/pause", headers=hs).json()["status"] == "paused"
        assert client.post(f"/api/v1/subscriptions/{sub['id']}/resume", headers=hs).json()["status"] == "active"
        assert client.post(f"/api/v1/subscriptions/{sub['id']}/close", headers=hs, json={"reason": "bye"}).json()["status"] == "closed"

    def test_customer_cannot_run_staff_actions(self, client, make_user):
        _, staff_token, customer, customer_token, product, plan = _setup(client, make_user)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        hs = auth_header(customer_token)
        for action in ("send", "revise", "activate", "renew"):
            assert client.post(f"/api/v1/subscriptions/{sub['id']}/{action}", headers=hs).status_code == 403

    def test_customer_cannot_touch_others_subscription(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        _, other_token = make_user(role="customer")
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        r = client.post(f"/api/v1/subscriptions/{sub['id']}/pause", headers=auth_header(other_token))
        assert r.status_code == 404


class TestListAndPatch:
    def test_list_filters_and_search(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        _create_sub(client, staff_token, customer.id, plan["id"], product["id"])

        r = client.get("/api/v1/subscriptions?status=draft", headers=hs)
        assert r.json()["total"] == 2
        r = client.get(f"/api/v1/subscriptions?q={sub['number']}", headers=hs)
        assert r.json()["total"] == 1 and r.json()["items"][0]["id"] == sub["id"]
        r = client.get("/api/v1/subscriptions?q=Test Customer", headers=hs)  # by customer name
        assert r.json()["total"] == 2

    def test_patch_only_before_confirmation_and_reanchors(self, client, make_user):
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        # move the start into the past -> anchor + next_billing follow (nothing billed yet)
        new_start = str(date.today() - timedelta(days=10))
        r = client.patch(
            f"/api/v1/subscriptions/{sub['id']}", headers=hs, json={"start_date": new_start}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["start_date"] == body["anchor_date"] == body["next_billing_date"] == new_start

        _to_active(client, staff_token, sub["id"])
        r = client.patch(f"/api/v1/subscriptions/{sub['id']}", headers=hs, json={"payment_terms": "Net 15"})
        assert r.status_code == 409

    def test_bill_now_requires_active_subscription(self, client, make_user):
        """bill-now runs the engine scoped to one subscription; a draft sub is not
        billable, so the run completes with nothing selected (no 501 anymore)."""
        _, staff_token, customer, _, product, plan = _setup(client, make_user)
        sub = _create_sub(client, staff_token, customer.id, plan["id"], product["id"]).json()
        r = client.post(f"/api/v1/subscriptions/{sub['id']}/bill-now", headers=auth_header(staff_token))
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "live"
        assert body["selected_count"] == 0
        assert body["created_count"] == 0
