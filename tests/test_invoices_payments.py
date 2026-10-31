"""Tests for /invoices (API.md §8) and /payments (§9).

All tests run on SQLite via conftest — never against Supabase (_clean_db wipes per test).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.conftest import auth_header
from app.billing.models import Invoice, Payment


# ------------------------------------------------------------------ helpers

def _setup(client, make_user):
    """Admin + staff + customer, product, plan, active subscription billed once."""
    _, admin_token = make_user(role="admin")
    _, staff_token = make_user(role="staff")
    customer, customer_token = make_user(role="customer")
    h = auth_header(admin_token)
    hs = auth_header(staff_token)

    product = client.post(
        "/api/v1/products", headers=h, json={"name": "InvoicePro", "sales_price": 500.00}
    ).json()
    plan = client.post(
        "/api/v1/plans", headers=h,
        json={"name": "Inv Monthly", "billing_cycle": "monthly", "price": 500.00},
    ).json()

    payload = {
        "customer_id": customer.id,
        "plan_id": plan["id"],
        "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 500.00}],
    }
    sub = client.post("/api/v1/subscriptions", headers=hs, json=payload).json()
    client.post(f"/api/v1/subscriptions/{sub['id']}/send", headers=hs)
    client.post(f"/api/v1/subscriptions/{sub['id']}/confirm", headers=hs)
    client.post(f"/api/v1/subscriptions/{sub['id']}/activate", headers=hs)

    # Live billing run to create a real invoice
    run_r = client.post("/api/v1/billing/runs", headers=hs, json={"mode": "live"})
    assert run_r.status_code == 200, run_r.text
    assert run_r.json()["created_count"] >= 1

    return admin_token, staff_token, customer, customer_token, sub


# ------------------------------------------------------------------ invoice list / get

class TestInvoiceList:
    def test_staff_can_list_invoices(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        r = client.get("/api/v1/invoices", headers=auth_header(staff))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        item = body["items"][0]
        # Derived fields present
        assert "payment_state" in item
        assert "is_overdue" in item
        assert "outstanding" in item

    def test_customer_sees_only_own_invoices(self, client, make_user, db):
        _, staff, customer, customer_token, sub = _setup(client, make_user)
        # Second customer
        c2, c2_token = make_user(role="customer")
        r = client.get("/api/v1/invoices", headers=auth_header(customer_token))
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["customer_id"] == customer.id

    def test_filter_by_status(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        r = client.get("/api/v1/invoices?status=draft", headers=hs)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["status"] == "draft"

    def test_get_invoice_detail_includes_lines(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        invs = client.get("/api/v1/invoices", headers=hs).json()["items"]
        inv_id = invs[0]["id"]
        r = client.get(f"/api/v1/invoices/{inv_id}", headers=hs)
        assert r.status_code == 200
        body = r.json()
        assert "lines" in body
        assert "payments" in body
        assert body["outstanding"] == body["total"]  # no payments yet

    def test_customer_cannot_see_other_customer_invoice(self, client, make_user, db):
        _, staff, customer, customer_token, sub = _setup(client, make_user)
        c2, c2_token = make_user(role="customer")
        invs = client.get("/api/v1/invoices", headers=auth_header(staff)).json()["items"]
        inv_id = invs[0]["id"]
        r = client.get(f"/api/v1/invoices/{inv_id}", headers=auth_header(c2_token))
        assert r.status_code == 404  # no existence leaking

    def test_unauthenticated_get_403(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        r = client.get("/api/v1/invoices")
        assert r.status_code in (401, 403)


# ------------------------------------------------------------------ invoice transitions

class TestInvoiceTransitions:
    def test_confirm_invoice(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        invs = client.get("/api/v1/invoices?status=draft", headers=hs).json()["items"]
        assert invs, "Expected at least one draft invoice"
        inv_id = invs[0]["id"]
        r = client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=hs)
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"

    def test_cancel_draft_invoice(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        invs = client.get("/api/v1/invoices?status=draft", headers=hs).json()["items"]
        assert invs
        inv_id = invs[0]["id"]
        r = client.post(f"/api/v1/invoices/{inv_id}/cancel", headers=hs)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_cannot_cancel_confirmed_invoice(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        invs = client.get("/api/v1/invoices?status=draft", headers=hs).json()["items"]
        inv_id = invs[0]["id"]
        client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=hs)
        r = client.post(f"/api/v1/invoices/{inv_id}/cancel", headers=hs)
        assert r.status_code == 409

    def test_send_invoice_sets_sent_at_and_confirms(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        invs = client.get("/api/v1/invoices?status=draft", headers=hs).json()["items"]
        inv_id = invs[0]["id"]
        r = client.post(f"/api/v1/invoices/{inv_id}/send", headers=hs)
        assert r.status_code == 200
        body = r.json()
        assert body["sent_at"] is not None
        assert body["status"] == "confirmed"

    def test_double_confirm_409(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        invs = client.get("/api/v1/invoices?status=draft", headers=hs).json()["items"]
        inv_id = invs[0]["id"]
        client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=hs)
        r = client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=hs)
        assert r.status_code == 409


# ------------------------------------------------------------------ payments

class TestPayments:
    def _get_confirmed_invoice_id(self, client, staff_token):
        hs = auth_header(staff_token)
        invs = client.get("/api/v1/invoices?status=draft", headers=hs).json()["items"]
        assert invs
        inv_id = invs[0]["id"]
        client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=hs)
        return inv_id

    def test_record_full_payment_marks_paid(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        total = client.get(f"/api/v1/invoices/{inv_id}", headers=hs).json()["total"]
        r = client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": float(total),
                  "method": "bank_transfer", "paid_at": date.today().isoformat()},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["invoice"]["status"] == "paid"
        assert body["invoice"]["payment_state"] == "paid"
        assert Decimal(str(body["invoice"]["outstanding"])) == Decimal("0.00")

    def test_partial_payment_state(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        total = Decimal(client.get(f"/api/v1/invoices/{inv_id}", headers=hs).json()["total"])
        partial = float(total / 2)
        r = client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": partial,
                  "method": "cash", "paid_at": date.today().isoformat()},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["invoice"]["payment_state"] == "partial"
        assert body["invoice"]["status"] == "confirmed"  # still open

    def test_overpayment_rejected_by_default(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        total = float(client.get(f"/api/v1/invoices/{inv_id}", headers=hs).json()["total"])
        r = client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": total + 999.00,
                  "method": "bank_transfer", "paid_at": date.today().isoformat()},
        )
        assert r.status_code == 409

    def test_zero_amount_422(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        r = client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": 0,
                  "method": "cash", "paid_at": date.today().isoformat()},
        )
        assert r.status_code == 422

    def test_payment_on_draft_invoice_409(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        invs = client.get("/api/v1/invoices?status=draft", headers=hs).json()["items"]
        inv_id = invs[0]["id"]
        r = client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": 100,
                  "method": "cash", "paid_at": date.today().isoformat()},
        )
        assert r.status_code == 409

    def test_cannot_cancel_invoice_with_payments(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        # Record a payment
        client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": 50,
                  "method": "upi", "paid_at": date.today().isoformat()},
        )
        # Attempt cancel (should 409 because of payment)
        r = client.post(f"/api/v1/invoices/{inv_id}/cancel", headers=hs)
        assert r.status_code == 409

    def test_list_payments(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": 100,
                  "method": "card", "paid_at": date.today().isoformat()},
        )
        r = client.get(f"/api/v1/payments?invoice_id={inv_id}", headers=hs)
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_get_payment_detail(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        pay_r = client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": 100,
                  "method": "cheque", "paid_at": date.today().isoformat()},
        )
        pay_id = pay_r.json()["payment"]["id"]
        r = client.get(f"/api/v1/payments/{pay_id}", headers=hs)
        assert r.status_code == 200
        assert r.json()["id"] == pay_id

    def test_customer_cannot_list_all_payments(self, client, make_user, db):
        _, staff, customer, customer_token, sub = _setup(client, make_user)
        r = client.get("/api/v1/payments", headers=auth_header(customer_token))
        assert r.status_code == 403

    def test_customer_can_view_own_payment_by_invoice(self, client, make_user, db):
        _, staff, customer, customer_token, sub = _setup(client, make_user)
        hs = auth_header(staff)
        inv_id = self._get_confirmed_invoice_id(client, staff)
        client.post(
            "/api/v1/payments",
            headers=hs,
            json={"invoice_id": inv_id, "amount": 50,
                  "method": "upi", "paid_at": date.today().isoformat()},
        )
        # Customer can filter their own invoice payments
        r = client.get(
            f"/api/v1/payments?invoice_id={inv_id}",
            headers=auth_header(customer_token),
        )
        assert r.status_code == 200
        assert r.json()["total"] >= 1


# ------------------------------------------------------------------ reports

class TestReports:
    def test_summary_endpoint(self, client, make_user, db):
        _, staff, customer, _, sub = _setup(client, make_user)
        r = client.get("/api/v1/reports/summary", headers=auth_header(staff))
        assert r.status_code == 200
        body = r.json()
        assert "active_subscriptions" in body
        assert "mrr" in body
        assert "overdue_count" in body

    def test_mrr_endpoint(self, client, make_user, db):
        _, staff, _, _, _ = _setup(client, make_user)
        r = client.get("/api/v1/reports/mrr?months=3", headers=auth_header(staff))
        assert r.status_code == 200
        body = r.json()
        assert "current_mrr" in body
        assert "arr" in body
        assert "series" in body

    def test_overdue_endpoint(self, client, make_user, db):
        _, staff, _, _, _ = _setup(client, make_user)
        r = client.get("/api/v1/reports/overdue", headers=auth_header(staff))
        assert r.status_code == 200
        assert "items" in r.json()

    def test_risk_endpoint(self, client, make_user, db):
        _, staff, _, _, _ = _setup(client, make_user)
        r = client.get("/api/v1/insights/risk", headers=auth_header(staff))
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body

    def test_forecast_endpoint(self, client, make_user, db):
        _, staff, _, _, _ = _setup(client, make_user)
        r = client.get("/api/v1/insights/forecast?horizon=3", headers=auth_header(staff))
        assert r.status_code == 200
        body = r.json()
        assert "method" in body
        assert "points" in body

    def test_reports_require_staff(self, client, make_user, db):
        _, _, customer, customer_token, _ = _setup(client, make_user)
        r = client.get("/api/v1/reports/summary", headers=auth_header(customer_token))
        assert r.status_code == 403


class TestInvoicePdf:
    def test_staff_can_download_invoice_pdf(self, client, make_user, db):
        _, staff, customer, _, _ = _setup(client, make_user)
        inv = db.scalars(select(Invoice).where(Invoice.customer_id == customer.id)).first()
        assert inv is not None
        assert inv.last_printed_at is None

        r = client.get(f"/api/v1/invoices/{inv.id}/pdf", headers=auth_header(staff))
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF-")

        db.refresh(inv)
        assert inv.last_printed_at is not None

    def test_customer_can_download_own_pdf(self, client, make_user, db):
        _, _, customer, customer_token, _ = _setup(client, make_user)
        inv = db.scalars(select(Invoice).where(Invoice.customer_id == customer.id)).first()
        r = client.get(f"/api/v1/invoices/{inv.id}/pdf", headers=auth_header(customer_token))
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"

    def test_customer_cannot_download_other_customer_pdf(self, client, make_user, db):
        _, _, customer, _, _ = _setup(client, make_user)
        other_cust, other_token = make_user(role="customer")
        inv = db.scalars(select(Invoice).where(Invoice.customer_id == customer.id)).first()

        r = client.get(f"/api/v1/invoices/{inv.id}/pdf", headers=auth_header(other_token))
        assert r.status_code == 404
