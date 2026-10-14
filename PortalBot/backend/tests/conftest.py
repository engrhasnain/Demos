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
_TEMPORARY = tempfile.mkdtemp(prefix="portalbot-", dir=str(_SCRATCH))
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEMPORARY, 'test.db').as_posix()}"
os.environ["PORTALBOT_DATA_DIR"] = _TEMPORARY

from app.db import SessionLocal, create_all, session_scope  # noqa: E402
from app.seed import generator  # noqa: E402
from app.seed.generator import Builder  # noqa: E402
from app.systems.carrier import Behaviour, CarrierPortal  # noqa: E402


@pytest.fixture(scope="session")
def loaded() -> None:
    create_all()
    with session_scope() as session:
        generator.build_demo_data(session, shipment_target=60)
    return None


@pytest.fixture
def session(loaded):
    """A session whose writes are thrown away when the test ends.

    The shipments are put back to pending first. The HTTP tests run the
    bot for real and commit, so without this a unit test would see
    whatever the last one happened to leave, and the order of the file
    would decide whether it passed.
    """
    from sqlalchemy import delete, update

    from app.models import Challenge, Run, ScriptFlag, Shipment, Step

    db = SessionLocal()
    transaction = db.begin_nested()
    try:
        db.execute(delete(Step))
        db.execute(delete(Challenge))
        db.execute(delete(ScriptFlag))
        db.execute(
            update(Shipment).values(
                state="pending",
                consignment="",
                tracking_number="",
                carrier="",
                label_url="",
                booked_at=None,
                written_back_at=None,
                attempts=0,
                exception_kind="",
                exception_detail="",
                run_id=None,
            )
        )
        db.execute(delete(Run))
        db.flush()
        yield db
    finally:
        transaction.rollback()
        db.rollback()
        db.close()


@pytest.fixture
def carrier():
    """A portal behaving itself, unless a test says otherwise."""
    return CarrierPortal(behaviour=Behaviour(tracking_delay_seconds=0))


@pytest.fixture
def legacy(session):
    return Builder.legacy_for(session)


@pytest.fixture
def client(loaded):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_in(client):
    def sign_in(email: str = "tomas.reyes@hengtai-industrial.example") -> dict[str, str]:
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
