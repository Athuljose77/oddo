"""RBAC and customer data-isolation tests — brief §21 Admin + Customer portal."""
from tests.conftest import auth_header


class TestStaffManagement:
    def test_only_admin_can_create_staff(self, client, make_user):
        _, admin_token = make_user(role="admin")
        _, staff_token = make_user(role="staff")
        payload = {
            "email": "rep@brightloop.io",
            "password": "Staff!Pass1",
            "name": "Ravi",
            "role": "staff",
        }
        # anonymous
        assert client.post("/api/v1/admin/staff", json=payload).status_code == 401
        # staff cannot create staff
        assert (
            client.post("/api/v1/admin/staff", json=payload, headers=auth_header(staff_token)).status_code
            == 403
        )
        # admin can
        r = client.post("/api/v1/admin/staff", json=payload, headers=auth_header(admin_token))
        assert r.status_code == 201
        assert r.json()["role"] == "staff"

    def test_staff_cannot_create_admin(self, client, make_user):
        _, admin_token = make_user(role="admin")
        r = client.post(
            "/api/v1/admin/staff",
            headers=auth_header(admin_token),
            json={
                "email": "wannabe@brightloop.io",
                "password": "Admin!Pass1",
                "name": "X",
                "role": "admin",
            },
        )
        assert r.status_code == 422  # role field rejects anything but 'staff'

    def test_list_staff_admin_only(self, client, make_user):
        _, staff_token = make_user(role="staff")
        _, admin_token = make_user(role="admin")
        assert (
            client.get("/api/v1/admin/staff", headers=auth_header(staff_token)).status_code == 403
        )
        assert client.get("/api/v1/admin/staff", headers=auth_header(admin_token)).status_code == 200

    def test_deactivate_staff(self, client, make_user):
        _, admin_token = make_user(role="admin")
        staff, _ = make_user(role="staff")
        r = client.patch(
            f"/api/v1/admin/staff/{staff.id}",
            headers=auth_header(admin_token),
            json={"is_active": False},
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False


class TestCustomerIsolation:
    def test_customer_sees_only_self_in_list(self, client, make_user):
        """Directory endpoint: customers receive their own record only."""
        cust_a, token_a = make_user(role="customer")
        make_user(role="customer")  # another customer exists
        r = client.get("/api/v1/customers", headers=auth_header(token_a))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == cust_a.id

    def test_customer_cannot_read_other_customer(self, client, make_user):
        _, token_a = make_user(role="customer")
        cust_b, _ = make_user(role="customer")
        # other customer's record → 404 (no existence leak)
        r = client.get(f"/api/v1/customers/{cust_b.id}", headers=auth_header(token_a))
        assert r.status_code == 404
        # own record → 200
        cust_a = client.get("/api/v1/auth/me", headers=auth_header(token_a)).json()
        r = client.get(f"/api/v1/customers/{cust_a['id']}", headers=auth_header(token_a))
        assert r.status_code == 200

    def test_staff_can_read_customers(self, client, make_user):
        _, token = make_user(role="staff")
        r = client.get("/api/v1/customers", headers=auth_header(token))
        assert r.status_code == 200
        assert all(c["role"] == "customer" for c in r.json()["items"])

    def test_admin_manages_customers(self, client, make_user):
        _, admin_token = make_user(role="admin")
        r = client.post(
            "/api/v1/customers",
            headers=auth_header(admin_token),
            json={"email": "b2b@acme.io", "password": "Temp!Pass123", "name": "Acme Ltd"},
        )
        assert r.status_code == 201
        customer_id = r.json()["id"]
        r = client.patch(
            f"/api/v1/customers/{customer_id}",
            headers=auth_header(admin_token),
            json={"name": "Acme Ltd (Renamed)"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Acme Ltd (Renamed)"

    def test_staff_cannot_create_customers(self, client, make_user):
        _, staff_token = make_user(role="staff")
        r = client.post(
            "/api/v1/customers",
            headers=auth_header(staff_token),
            json={"email": "nope@test.io", "password": "Temp!Pass123", "name": "N"},
        )
        assert r.status_code == 403


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
