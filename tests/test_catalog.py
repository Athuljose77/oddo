"""Catalog acceptance tests — brief §21 Catalog + §3 permissions."""
from tests.conftest import auth_header


class TestProducts:
    def test_admin_creates_product_with_variant(self, client, make_user):
        _, admin_token = make_user(role="admin")
        h = auth_header(admin_token)

        r = client.post(
            "/api/v1/products",
            headers=h,
            json={
                "name": "CloudPro",
                "type": "subscription",
                "sales_price": 2000.00,
                "cost_price": 800.00,
                "notes": "Flagship suite",
            },
        )
        assert r.status_code == 201
        product_id = r.json()["id"]

        # Odoo brand variant adds 560 (problem statement example)
        r = client.post(
            f"/api/v1/products/{product_id}/variants",
            headers=h,
            json={"attribute": "Brand", "value": "Odoo", "price_delta": 560.00},
        )
        assert r.status_code == 201
        assert float(r.json()["price_delta"]) == 560.00

        # Duplicate variant rejected
        r = client.post(
            f"/api/v1/products/{product_id}/variants",
            headers=h,
            json={"attribute": "Brand", "value": "Odoo", "price_delta": 0},
        )
        assert r.status_code == 409

        # GET includes variants
        r = client.get(f"/api/v1/products/{product_id}", headers=h)
        assert r.status_code == 200
        assert r.json()["variants"][0]["value"] == "Odoo"

    def test_staff_can_read_but_not_write(self, client, make_user):
        _, staff_token = make_user(role="staff")
        h = auth_header(staff_token)
        assert client.get("/api/v1/products", headers=h).status_code == 200
        r = client.post(
            "/api/v1/products", headers=h, json={"name": "Nope", "sales_price": 1}
        )
        assert r.status_code == 403

    def test_customer_cannot_access_catalog(self, client, make_user):
        _, token = make_user(role="customer")
        assert client.get("/api/v1/products", headers=auth_header(token)).status_code == 403
        assert client.get("/api/v1/plans", headers=auth_header(token)).status_code == 403

    def test_negative_price_rejected(self, client, make_user):
        _, admin_token = make_user(role="admin")
        r = client.post(
            "/api/v1/products",
            headers=auth_header(admin_token),
            json={"name": "Bad", "sales_price": -5},
        )
        assert r.status_code == 422

    def test_product_list_uses_envelope_and_search(self, client, make_user):
        _, admin_token = make_user(role="admin")
        h = auth_header(admin_token)
        client.post("/api/v1/products", headers=h, json={"name": "Alpha Suite", "sales_price": 10})
        client.post("/api/v1/products", headers=h, json={"name": "Beta Suite", "sales_price": 20})
        r = client.get("/api/v1/products?q=Alpha", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert set(body) >= {"items", "total", "page", "page_size"}
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Alpha Suite"


class TestPlans:
    def _create_plan(self, client, admin_token, **overrides):
        payload = {
            "name": "Growth Monthly",
            "billing_cycle": "monthly",
            "price": 1180.00,
            "min_quantity": 1,
            "available_from": "2026-01-01",
            "available_to": "2027-12-31",
        }
        payload.update(overrides)
        return client.post("/api/v1/plans", headers=auth_header(admin_token), json=payload)

    def test_create_all_four_cycles(self, client, make_user):
        _, admin_token = make_user(role="admin")
        for cycle in ("daily", "weekly", "monthly", "yearly"):
            r = self._create_plan(client, admin_token, billing_cycle=cycle, name=f"P-{cycle}")
            assert r.status_code == 201, cycle
            assert r.json()["billing_cycle"] == cycle

    def test_invalid_cycle_rejected(self, client, make_user):
        _, admin_token = make_user(role="admin")
        r = self._create_plan(client, admin_token, billing_cycle="hourly")
        assert r.status_code == 422

    def test_availability_window_order_enforced(self, client, make_user):
        _, admin_token = make_user(role="admin")
        r = self._create_plan(
            client, admin_token, available_from="2027-01-01", available_to="2026-01-01"
        )
        assert r.status_code == 422

    def test_close_and_reopen(self, client, make_user):
        _, admin_token = make_user(role="admin")
        plan_id = self._create_plan(client, admin_token).json()["id"]
        r = client.post(f"/api/v1/plans/{plan_id}/close", headers=auth_header(admin_token))
        assert r.status_code == 200 and r.json()["status"] == "closed"
        r = client.post(f"/api/v1/plans/{plan_id}/reopen", headers=auth_header(admin_token))
        assert r.status_code == 200 and r.json()["status"] == "active"

    def test_plan_flags_survive_roundtrip(self, client, make_user):
        """auto_close / allow_pause / allow_renew / allow_early_close are per-plan."""
        _, admin_token = make_user(role="admin")
        r = self._create_plan(
            client,
            admin_token,
            auto_close=False,
            allow_pause=True,
            allow_renew=False,
            allow_early_close=True,
        )
        body = r.json()
        assert body["auto_close"] is False
        assert body["allow_pause"] is True
        assert body["allow_renew"] is False
        assert body["allow_early_close"] is True


class TestTaxesAndDiscounts:
    def test_admin_creates_global_and_product_tax(self, client, make_user):
        _, admin_token = make_user(role="admin")
        h = auth_header(admin_token)
        r = client.post(
            "/api/v1/tax-rules", headers=h, json={"name": "GST 18", "rate": 18.0, "priority": 10}
        )
        assert r.status_code == 201
        assert float(r.json()["rate"]) == 18.0

        r = client.post(
            "/api/v1/tax-rules", headers=h, json={"name": "GST 5", "rate": 5.0, "priority": 1}
        )
        assert r.status_code == 201

    def test_staff_cannot_write_tax_or_discount(self, client, make_user):
        _, staff_token = make_user(role="staff")
        h = auth_header(staff_token)
        assert (
            client.post("/api/v1/tax-rules", headers=h, json={"name": "X", "rate": 5}).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/discount-rules",
                headers=h,
                json={
                    "name": "X",
                    "type": "percentage",
                    "value": 10,
                    "starts_at": "2026-01-01",
                },
            ).status_code
            == 403
        )

    def test_admin_creates_discount_rule(self, client, make_user):
        _, admin_token = make_user(role="admin")
        h = auth_header(admin_token)
        r = client.post(
            "/api/v1/discount-rules",
            headers=h,
            json={
                "name": "SEAT-10",
                "type": "percentage",
                "value": 10.0,
                "min_quantity": 10,
                "starts_at": "2026-10-01",
                "ends_at": "2026-12-31",
                "usage_limit": 100,
                "scope": "subscription",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["used_count"] == 0  # read-only, engine-owned
        assert float(body["value"]) == 10.0

    def test_discount_validation(self, client, make_user):
        _, admin_token = make_user(role="admin")
        h = auth_header(admin_token)
        base = {"name": "D", "type": "percentage", "starts_at": "2026-01-01"}
        # >100%
        assert (
            client.post(
                "/api/v1/discount-rules", headers=h, json={**base, "value": 150}
            ).status_code
            == 422
        )
        # ends before starts
        assert (
            client.post(
                "/api/v1/discount-rules",
                headers=h,
                json={**base, "value": 10, "ends_at": "2025-12-31"},
            ).status_code
            == 422
        )
        # product scope without product
        assert (
            client.post(
                "/api/v1/discount-rules", headers=h, json={**base, "value": 10, "scope": "product"}
            ).status_code
            == 422
        )

    def test_used_count_not_client_settable(self, client, make_user):
        _, admin_token = make_user(role="admin")
        h = auth_header(admin_token)
        r = client.post(
            "/api/v1/discount-rules",
            headers=h,
            json={"name": "D", "type": "fixed", "value": 5, "starts_at": "2026-01-01"},
        )
        rule_id = r.json()["id"]
        r = client.patch(
            f"/api/v1/discount-rules/{rule_id}", headers=h, json={"used_count": 999}
        )
        assert r.status_code == 200
        assert r.json()["used_count"] == 0  # field not accepted by schema
