"""Test fixtures.

Each run gets its own SQLite file and its own copy of the demonstration data,
so tests never see each other's rows and can be run in any order.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The database is chosen before the application is imported.
_TEMP_DIR = tempfile.mkdtemp(prefix="quoteagent-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEMP_DIR, 'test.db').as_posix()}"
os.environ["MODEL_API_KEY"] = ""

from app.db import create_all, session_scope  # noqa: E402
from app.seed import generator  # noqa: E402
from app.services import matching  # noqa: E402

PRODUCT_TARGET = 600
CUSTOMER_TARGET = 25


@pytest.fixture(scope="session", autouse=True)
def demo_data() -> Iterator[None]:
    create_all()
    with session_scope() as session:
        generator.build_demo_data(
            session, product_target=PRODUCT_TARGET, customer_target=CUSTOMER_TARGET
        )
    matching.reset_index()
    yield


@pytest.fixture()
def session() -> Iterator:
    with session_scope() as handle:
        yield handle


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    from app.routers import cases as cases_router

    cases_router.clear_sample_cache()
    return TestClient(app)


@pytest.fixture()
def signed_in(client):
    """A client signed in as the administrator, who can do everything."""

    def sign_in(email: str = "admin@hengtai-industrial.example") -> object:
        response = client.post(
            "/api/auth/sign-in", json={"email": email, "password": generator.DEMO_PASSWORD}
        )
        assert response.status_code == 200, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        return client

    return sign_in
