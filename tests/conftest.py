"""Test bootstrap: isolated SQLite DB, app fixtures, auth helpers.

Note: tests create schema via Base.metadata.create_all() for speed; production
schema changes only via Alembic (see docs/CONVENTIONS.md).
"""
import os
import tempfile
from itertools import count

# Must run before app imports so settings pick up the test database
_TEST_DB = os.path.join(tempfile.gettempdir(), "brightloop_test.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["MAILER_MODE"] = "log"

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)


@pytest.fixture(autouse=True)
def _clean_db(db):
    """Wipe all rows before EVERY test — tests must not leak data into each other."""
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


_user_seq = count(1)  # session-unique emails — never collide between tests


@pytest.fixture()
def make_user(db):
    """Create a user directly in the DB and return (user, token)."""
    from app.core.security import create_access_token, hash_password
    from app.auth.models import User

    counter = _user_seq

    def _make(role: str = "customer", email: str | None = None, password: str = "Valid!Pass123"):
        email = email or f"{role}{next(counter)}@test.io"
        user = User(
            email=email,
            name=f"Test {role.title()}",
            role=role,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, create_access_token(user.id, user.role)

    return _make


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
