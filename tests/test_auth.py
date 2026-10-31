"""Auth acceptance tests — brief §21 Authentication."""
from tests.conftest import auth_header

VALID_PW = "Bright!Loop99"


class TestRegistration:
    def test_register_creates_customer(self, client):
        r = client.post(
            "/api/v1/auth/register",
            json={"email": "owner@brightloop.io", "password": VALID_PW, "name": "Asha"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["role"] == "customer"
        assert "password" not in str(body).lower() or "password_hash" not in body

    def test_register_ignores_role_field(self, client):
        """A crafted payload can never create staff/admin accounts (#6)."""
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "evil@test.io",
                "password": VALID_PW,
                "name": "Evil",
                "role": "admin",
                "is_admin": True,
            },
        )
        assert r.status_code == 201
        assert r.json()["role"] == "customer"

    def test_duplicate_email_rejected(self, client):
        payload = {"email": "dup@test.io", "password": VALID_PW, "name": "Dup"}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201
        assert client.post("/api/v1/auth/register", json=payload).status_code == 409

    def test_email_is_case_normalized(self, client):
        r = client.post(
            "/api/v1/auth/register",
            json={"email": "Mixed@Case.IO", "password": VALID_PW, "name": "MC"},
        )
        assert r.status_code == 201
        assert r.json()["email"] == "mixed@case.io"

    def test_weak_passwords_rejected(self, client):
        # Rules: >8 chars, ≥1 upper, ≥1 lower, ≥1 special (digits NOT required)
        weak = ["short1!", "alllowercase1!", "ALLUPPERCASE1!", "NoSpecial123", "MoreThan8Chars"]
        for i, pw in enumerate(weak):
            r = client.post(
                "/api/v1/auth/register",
                json={"email": f"weak{i}@test.io", "password": pw, "name": "W"},
            )
            assert r.status_code == 422, f"password accepted: {pw}"


class TestLogin:
    def test_login_success_and_me(self, client):
        client.post(
            "/api/v1/auth/register",
            json={"email": "login@test.io", "password": VALID_PW, "name": "L"},
        )
        r = client.post(
            "/api/v1/auth/login", json={"email": "login@test.io", "password": VALID_PW}
        )
        assert r.status_code == 200
        token = r.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers=auth_header(token))
        assert me.status_code == 200
        assert me.json()["email"] == "login@test.io"

    def test_login_wrong_password_401(self, client):
        client.post(
            "/api/v1/auth/register",
            json={"email": "wrong@test.io", "password": VALID_PW, "name": "W"},
        )
        r = client.post("/api/v1/auth/login", json={"email": "wrong@test.io", "password": "Nope!12345"})
        assert r.status_code == 401

    def test_login_unknown_email_same_401(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "ghost@test.io", "password": "Whatever!1"})
        assert r.status_code == 401

    def test_me_requires_token(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_me_rejects_garbage_token(self, client):
        assert (
            client.get("/api/v1/auth/me", headers=auth_header("not.a.jwt")).status_code == 401
        )


class TestPasswordReset:
    def test_forgot_always_200(self, client):
        r = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@test.io"})
        assert r.status_code == 200

    def test_reset_flow_single_use(self, client, monkeypatch):
        from sqlalchemy import select

        from app.auth.models import User
        from app.core.database import SessionLocal
        from app.core.security import hash_reset_token

        client.post(
            "/api/v1/auth/register",
            json={"email": "reset@test.io", "password": VALID_PW, "name": "R"},
        )
        captured = {}

        def fake_send(to, raw_token):
            captured["token"] = raw_token

        # service imports the mailer lazily inside the function — patch where it lands
        import app.core.mailer as mailer

        monkeypatch.setattr(mailer, "send_password_reset_email", fake_send)

        assert client.post("/api/v1/auth/forgot-password", json={"email": "reset@test.io"}).status_code == 200
        assert "token" in captured, "reset token was not generated"

        # DB must store the HASH, never the raw token (#5)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == "reset@test.io"))
            assert user.reset_token_hash is not None
            assert user.reset_token_hash != captured["token"]
            assert user.reset_token_hash == hash_reset_token(captured["token"])
        finally:
            db.close()

        new_pw = "Rotated!Pass1"
        r = client.post(
            "/api/v1/auth/reset-password",
            json={"token": captured["token"], "new_password": new_pw},
        )
        assert r.status_code == 200

        # Single-use: replaying the same token fails
        r = client.post(
            "/api/v1/auth/reset-password",
            json={"token": captured["token"], "new_password": "Another!Pass1"},
        )
        assert r.status_code == 400

        # Old password dead, new one works
        assert (
            client.post("/api/v1/auth/login", json={"email": "reset@test.io", "password": VALID_PW}).status_code
            == 401
        )
        assert (
            client.post("/api/v1/auth/login", json={"email": "reset@test.io", "password": new_pw}).status_code
            == 200
        )

    def test_reset_invalid_token_400(self, client):
        r = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "a" * 43, "new_password": VALID_PW},
        )
        assert r.status_code == 400


class TestChangePassword:
    def test_change_password(self, client, make_user):
        user, token = make_user(password=VALID_PW)
        # wrong current
        r = client.post(
            "/api/v1/auth/change-password",
            headers=auth_header(token),
            json={"current_password": "Wrong!Pass1", "new_password": "New!Pass1234"},
        )
        assert r.status_code == 401
        # correct
        r = client.post(
            "/api/v1/auth/change-password",
            headers=auth_header(token),
            json={"current_password": VALID_PW, "new_password": "New!Pass1234"},
        )
        assert r.status_code == 200
        # login with new
        r = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "New!Pass1234"}
        )
        assert r.status_code == 200
