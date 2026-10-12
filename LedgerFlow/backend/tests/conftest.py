"""Shared fixtures.

Every test runs against a database of its own in a temporary directory, built
by the real generator. Nothing is mocked: a test that passes against a fake
ledger tells you nothing about the real one.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The settings are read once at import, so the database has to be chosen
# before anything from the application is imported.
# Beside the project rather than in the system temp directory: these
# are whole generated companies, and on a machine whose system disk
# is tight they fill it up a run at a time.
_SCRATCH = BACKEND / "var" / "tests"
_SCRATCH.mkdir(parents=True, exist_ok=True)
_TEMPORARY = tempfile.mkdtemp(prefix="ledgerflow-", dir=str(_SCRATCH))
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEMPORARY, 'test.db').as_posix()}"
os.environ["LEDGERFLOW_DATA_DIR"] = _TEMPORARY

from app.db import create_all, session_scope  # noqa: E402
from app.seed import generator  # noqa: E402
from app.seed.invoices import build_batch  # noqa: E402
from app.services import pipeline  # noqa: E402


@pytest.fixture(scope="session")
def loaded() -> None:
    """One generated company, shared by every test that only reads."""
    create_all()
    with session_scope() as session:
        generator.build_demo_data(session, vendor_target=40, order_target=60)
    return None


@pytest.fixture
def session(loaded):
    """A session whose writes are thrown away when the test ends."""
    from app.db import SessionLocal

    db = SessionLocal()
    transaction = db.begin_nested()
    try:
        yield db
    finally:
        transaction.rollback()
        db.rollback()
        db.close()


@pytest.fixture
def batch(session):
    return build_batch(session)


@pytest.fixture
def processed(session, batch):
    """The whole batch, put through the real pipeline once."""
    out = {}
    for document in batch:
        invoice, _created = pipeline.receive(
            session,
            filename=document.filename,
            content=document.content,
            content_type=document.content_type,
            text=document.text,
            barcode_payload=document.barcode_payload,
            received_from=document.received_from,
            kind=document.kind,
        )
        try:
            pipeline.run(session, invoice)
        except pipeline.PipelineError:
            pass
        out[document.key] = invoice
    return out


@pytest.fixture
def client(loaded):
    """A signed-out HTTP client against the real application."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_in(client):
    """Sign in as whichever role the test asks for."""

    def sign_in(email: str = "ravi.menon@hengtai-industrial.example") -> dict[str, str]:
        response = client.post(
            "/api/auth/sign-in", json={"email": email, "password": generator.DEMO_PASSWORD}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return sign_in


@pytest.fixture
def ready_to_post(session):
    """One ordinary invoice, read and checked but deliberately not posted.

    Built on its own rather than taken from the batch, because the batch
    posts its clean invoices by itself: that is the whole point of it.
    """
    import datetime as dt

    from sqlalchemy import select

    from app.evaluation.cases import retry_cases
    from app.models import User
    from app.services import approvals

    signer = session.scalar(select(User).where(User.role == "administrator"))
    for case in retry_cases(session, count=10):
        invoice, _created = pipeline.receive(
            session,
            filename=case.filename,
            content=case.content,
            content_type="application/pdf",
            text=case.text,
            received_from=case.received_from,
        )
        pipeline.read(session, invoice)
        pipeline.check(session, invoice)
        if approvals.blocking_reasons(session, invoice):
            continue
        for approval in approvals.outstanding(session, invoice):
            approval.status = "approved"
            approval.decided_by_id = signer.id
            approval.decided_at = dt.datetime.now(dt.timezone.utc)
        session.flush()
        return invoice
    raise AssertionError("the generated data produced no invoice that could be posted")


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Take the generated database away again."""
    import shutil

    shutil.rmtree(_TEMPORARY, ignore_errors=True)
