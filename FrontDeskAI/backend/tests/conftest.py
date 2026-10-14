"""Shared fixtures."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Beside the project rather than in the system temp directory: these
# are whole generated companies, and on a machine whose system disk
# is tight they fill it up a run at a time.
_SCRATCH = BACKEND / "var" / "tests"
_SCRATCH.mkdir(parents=True, exist_ok=True)
_TEMPORARY = tempfile.mkdtemp(prefix="frontdesk-", dir=str(_SCRATCH))
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEMPORARY, 'test.db').as_posix()}"
os.environ["FRONTDESK_DATA_DIR"] = _TEMPORARY
os.environ["LINE_CHANNEL_SECRET"] = "a-test-secret"

from app.db import SessionLocal, create_all, session_scope  # noqa: E402
from app.models import Conversation, Order  # noqa: E402
from app.seed import generator  # noqa: E402
from app.services import identity  # noqa: E402


@pytest.fixture(scope="session")
def loaded() -> None:
    create_all()
    with session_scope() as session:
        generator.build_demo_data(session, customer_target=120, order_target=400)
    return None


@pytest.fixture
def session(loaded):
    db = SessionLocal()
    transaction = db.begin_nested()
    try:
        yield db
    finally:
        transaction.rollback()
        db.rollback()
        db.close()


@pytest.fixture
def conversation(session):
    """A fresh, unverified web conversation."""
    import uuid

    row = Conversation(
        reference=f"T-{uuid.uuid4().hex[:10]}", channel="web", status="open"
    )
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def orders(session):
    """Two orders belonging to two different customers."""
    from sqlalchemy import select

    mine = session.scalar(
        select(Order).where(Order.status == "delivered").order_by(Order.id).limit(1)
    )
    theirs = session.scalar(
        select(Order).where(Order.customer_id != mine.customer_id).order_by(Order.id).limit(1)
    )
    return mine, theirs


@pytest.fixture
def verified(session, conversation, orders):
    """A conversation that has proved who it is."""
    mine, _ = orders
    contact = mine.customer.contacts[0]
    result = identity.verify(
        session, conversation, order_number=mine.number, email=contact.email
    )
    assert result.ok
    return conversation


@pytest.fixture
def client(loaded):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_in(client):
    def sign_in(email: str = "yuki.sato@hengtai-industrial.example") -> dict[str, str]:
        response = client.post(
            "/api/auth/sign-in",
            json={"email": email, "password": generator.DEMO_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return sign_in


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Take the generated database away again."""
    import shutil

    shutil.rmtree(_TEMPORARY, ignore_errors=True)
