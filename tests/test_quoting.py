"""Quotation tests — templates, tax math, lifecycle, scoping (brief §21)."""
from datetime import date, timedelta

from tests.conftest import auth_header


def _setup(client, make_user):
    """Admin + staff tokens, a product, a plan. Shared by quoting tests."""
    _, admin_token = make_user(role="admin")
    _, staff_token = make_user(role="staff")
    customer, _ = make_user(role="customer")
    h = auth_header(admin_token)

    product = client.post(
        "/api/v1/products", headers=h, json={"name": "CloudPro", "sales_price": 2000.00}
    ).json()
    plan = client.post(
        "/api/v1/plans",
        headers=h,
        json={"name": "Growth Monthly", "billing_cycle": "monthly", "price": 1180.00},
    ).json()
    return admin_token, staff_token, customer, product, plan


class TestTemplatesAndPrefill:
    def test_quotation_from_template_prefills_lines(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        h = auth_header(admin_token)

        template = client.post(
            "/api/v1/quote-templates",
            headers=h,
            json={
                "name": "Professional Plan Offer",
                "validity_days": 7,
                "payment_terms": "Net 15",
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 10, "unit_price": 1180.00}],
            },
        )
        assert template.status_code == 201

        r = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={"customer_id": customer.id, "template_id": template.json()["id"]},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["number"].startswith(f"QUO-{date.today().year}-")
        assert body["status"] == "draft"
        assert body["payment_terms"] == "Net 15"
        assert body["plan_id"] == plan["id"]
        assert len(body["lines"]) == 1
        assert body["lines"][0]["quantity"] == 10
        # tax-free: 10 × 1180
        assert float(body["subtotal"]) == 11800.00
        assert float(body["total"]) == 11800.00

    def test_variant_price_used_when_no_explicit_price(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        h = auth_header(admin_token)
        client.post(
            f"/api/v1/products/{product['id']}/variants",
            headers=h,
            json={"attribute": "Brand", "value": "Odoo", "price_delta": 560.00},
        )
        variant = client.get(f"/api/v1/products/{product['id']}", headers=h).json()["variants"][0]

        r = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "variant_id": variant["id"], "quantity": 1}],
            },
        )
        assert r.status_code == 201
        # base 2000 + Odoo 560
        assert float(r.json()["lines"][0]["unit_price"]) == 2560.00

    def test_template_requires_lines_or_template(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        r = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={"customer_id": customer.id, "plan_id": plan["id"]},
        )
        assert r.status_code == 422

    def test_sequence_numbers_increment(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        line = {"product_id": product["id"], "quantity": 1, "unit_price": 10}
        first = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={"customer_id": customer.id, "plan_id": plan["id"], "lines": [line]},
        ).json()
        second = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={"customer_id": customer.id, "plan_id": plan["id"], "lines": [line]},
        ).json()
        assert first["number"] != second["number"]
        assert int(second["number"].split("-")[-1]) == int(first["number"].split("-")[-1]) + 1


class TestTaxMath:
    def test_exclusive_tax_line_totals(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        h = auth_header(admin_token)
        client.post(
            "/api/v1/tax-rules", headers=h, json={"name": "GST 18", "rate": 18.0, "priority": 10}
        )

        r = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 10, "unit_price": 100.00}],
            },
        )
        assert r.status_code == 201
        line = r.json()["lines"][0]
        assert float(line["tax_rate"]) == 18.0
        assert float(line["tax_amount"]) == 180.00  # 1000 × 18%
        assert float(line["line_total"]) == 1180.00
        assert float(r.json()["subtotal"]) == 1000.00
        assert float(r.json()["tax_total"]) == 180.00
        assert float(r.json()["total"]) == 1180.00

    def test_tax_inclusive_extraction(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        h = auth_header(admin_token)
        client.post(
            "/api/v1/tax-rules",
            headers=h,
            json={"name": "VAT 18 incl", "rate": 18.0, "tax_included": True},
        )
        r = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 1180.00}],
            },
        )
        line = r.json()["lines"][0]
        # gross 1180 contains 18% → tax = 1180 × 18/118 = 180.00
        assert float(line["tax_amount"]) == 180.00
        assert float(line["line_total"]) == 1180.00
        assert float(r.json()["subtotal"]) == 1000.00

    def test_tax_included_is_immutable_after_creation(self, client, make_user):
        _, admin_token = make_user(role="admin")
        h = auth_header(admin_token)
        rule = client.post(
            "/api/v1/tax-rules", headers=h, json={"name": "T", "rate": 10, "tax_included": False}
        ).json()
        r = client.patch(
            f"/api/v1/tax-rules/{rule['id']}", headers=h, json={"tax_included": True}
        )
        # field not in PATCH schema → ignored, value unchanged
        assert r.status_code == 200
        assert r.json()["tax_included"] is False


class TestLifecycle:
    def test_send_sets_validity_and_status(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        quote = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 10}],
            },
        ).json()
        r = client.post(f"/api/v1/quotations/{quote['id']}/send", headers=auth_header(staff_token))
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "sent"
        assert body["valid_until"] == (date.today() + timedelta(days=7)).isoformat()
        # sending twice → 409
        assert (
            client.post(
                f"/api/v1/quotations/{quote['id']}/send", headers=auth_header(staff_token)
            ).status_code
            == 409
        )

    def test_expired_quotation_reads_expired_and_cannot_confirm(self, client, make_user, db):
        from sqlalchemy import update

        from app.quoting.models import Quotation

        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        quote = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 10}],
            },
        ).json()
        client.post(f"/api/v1/quotations/{quote['id']}/send", headers=auth_header(staff_token))
        # force expiry: validity ended yesterday
        db.execute(
            update(Quotation)
            .where(Quotation.id == quote["id"])
            .values(valid_until=date.today() - timedelta(days=1))
        )
        db.commit()

        r = client.get(f"/api/v1/quotations/{quote['id']}", headers=auth_header(staff_token))
        assert r.json()["status"] == "expired"
        r = client.post(f"/api/v1/quotations/{quote['id']}/confirm", headers=auth_header(staff_token))
        assert r.status_code == 409

    def test_confirm_returns_501_until_subscriptions_module(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        quote = client.post(
            "/api/v1/quotations",
            headers=auth_header(staff_token),
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 10}],
            },
        ).json()
        client.post(f"/api/v1/quotations/{quote['id']}/send", headers=auth_header(staff_token))
        r = client.post(f"/api/v1/quotations/{quote['id']}/confirm", headers=auth_header(staff_token))
        assert r.status_code == 501

    def test_cancel_and_edit_rules(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        hs = auth_header(staff_token)
        quote = client.post(
            "/api/v1/quotations",
            headers=hs,
            json={
                "customer_id": customer.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 2, "unit_price": 10}],
            },
        ).json()
        # patch lines recomputes totals
        r = client.patch(
            f"/api/v1/quotations/{quote['id']}",
            headers=hs,
            json={"lines": [{"product_id": product["id"], "quantity": 3, "unit_price": 100}]},
        )
        assert r.status_code == 200
        assert float(r.json()["total"]) == 300.00
        # cancel works from draft
        r = client.post(f"/api/v1/quotations/{quote['id']}/cancel", headers=hs)
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        # cancelled can't be edited
        r = client.patch(
            f"/api/v1/quotations/{quote['id']}", headers=hs, json={"notes": "x"}
        )
        assert r.status_code == 409

    def test_staff_cannot_create_template_admin_can(self, client, make_user):
        _, staff_token = make_user(role="staff")
        _, admin_token = make_user(role="admin")
        payload = {"name": "T", "validity_days": 7}
        assert (
            client.post(
                "/api/v1/quote-templates", headers=auth_header(staff_token), json=payload
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/quote-templates", headers=auth_header(admin_token), json=payload
            ).status_code
            == 201
        )


class TestCustomerScoping:
    def test_customer_sees_only_own_quotations(self, client, make_user):
        admin_token, staff_token, customer_a, product, plan = _setup(client, make_user)
        customer_b, token_b = make_user(role="customer")
        hs = auth_header(staff_token)

        qa = client.post(
            "/api/v1/quotations",
            headers=hs,
            json={
                "customer_id": customer_a.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 10}],
            },
        ).json()
        qb = client.post(
            "/api/v1/quotations",
            headers=hs,
            json={
                "customer_id": customer_b.id,
                "plan_id": plan["id"],
                "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 10}],
            },
        ).json()

        # customer B sees only B's quotation in the list
        r = client.get("/api/v1/quotations", headers=auth_header(token_b))
        ids = [item["id"] for item in r.json()["items"]]
        assert qb["id"] in ids and qa["id"] not in ids

        # customer B cannot read A's quotation directly → 404
        assert (
            client.get(f"/api/v1/quotations/{qa['id']}", headers=auth_header(token_b)).status_code
            == 404
        )
        # customer A can read own
        assert (
            client.get(f"/api/v1/quotations/{qa['id']}", headers=hs).status_code == 200
        )

    def test_customer_cannot_create_or_send(self, client, make_user):
        admin_token, staff_token, customer, product, plan = _setup(client, make_user)
        _, customer_token = make_user(role="customer")
        hc = auth_header(customer_token)
        assert (
            client.post(
                "/api/v1/quotations",
                headers=hc,
                json={"customer_id": customer.id, "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 1}]},
            ).status_code
            == 403
        )
