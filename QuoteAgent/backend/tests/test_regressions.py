"""Faults that reached a person, each pinned so it cannot come back."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_session, session_scope
from app.models import Product
from app.seed import generator
from app.services import matching

ADMIN = "admin@hengtai-industrial.example"


# ---------------------------------------------------------------------------
# "Try a line" on the catalogue worked once, then failed until a restart
# ---------------------------------------------------------------------------
def _parts_with_a_supplier(count: int) -> list[str]:
    with session_scope() as session:
        return list(
            session.scalars(
                select(Product.sku)
                .where(Product.is_active.is_(True), Product.supplier_id.is_not(None))
                .order_by(Product.id)
                .limit(count)
            )
        )


def test_trying_a_line_works_every_time_not_just_the_first(signed_in):
    """The catalogue index is cached between requests, and the parts it held
    belonged to the request that built it. Once that request had finished,
    showing a matched part's supplier raised DetachedInstanceError, so every
    check after the first was a server error."""
    client = signed_in("amy.chen@hengtai-industrial.example")
    matching.reset_index()  # the first check builds it, as after a restart

    skus = _parts_with_a_supplier(3)
    assert len(skus) == 3
    for sku in skus:
        response = client.post("/api/catalogue/match", json={"text": sku})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "matched"
        assert body["product"]["sku"] == sku
        assert body["product"]["supplier"]["name"]


def test_a_matched_part_belongs_to_the_session_that_asked():
    with session_scope() as session:
        matching.get_index(session, rebuild=True)
    sku = _parts_with_a_supplier(1)[0]

    with session_scope() as session:
        result = matching.match_line(session, sku)
        assert result.product is not None
        assert result.product in session
        assert result.product.supplier is not None


# ---------------------------------------------------------------------------
# The first run could not be reached on an empty database
# ---------------------------------------------------------------------------
@pytest.fixture()
def empty_database(tmp_path) -> Iterator[sessionmaker]:
    """Point every request at a brand new, empty database for one test."""
    from app.main import app

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'empty.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def empty_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = empty_session
    try:
        yield factory
    finally:
        app.dependency_overrides.pop(get_session, None)
        matching.reset_index()  # it was built from the empty database's parts
        engine.dispose()


def test_the_first_run_loads_without_signing_in_then_the_demo_account_works(
    client, empty_database
):
    """On a brand new database there are no accounts, so a load that needed a
    signed-in administrator could never be started. The README's first run is
    load first, then sign in."""
    status = client.get("/api/system/status").json()
    assert status["data_loaded"] is False
    assert status["counts"]["users"] == 0

    refused = client.post(
        "/api/auth/sign-in", json={"email": ADMIN, "password": generator.DEMO_PASSWORD}
    )
    assert refused.status_code == 401

    loaded = client.post(
        "/api/system/load-demo-data-now",
        json={"product_target": 200, "customer_target": 10},
    )
    assert loaded.status_code == 200, loaded.text
    assert client.get("/api/system/status").json()["data_loaded"] is True

    signed_in = client.post(
        "/api/auth/sign-in", json={"email": ADMIN, "password": generator.DEMO_PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["role"] == "administrator"

    # Once anything exists the open door is shut again.
    again = client.post(
        "/api/system/load-demo-data-now",
        json={"product_target": 200, "customer_target": 10},
    )
    assert again.status_code == 401


def test_the_load_button_starts_without_signing_in_on_an_empty_database(
    client, empty_database, monkeypatch
):
    """The route the first-run screen calls. The background load itself is
    replaced, so nothing is written to the database the other tests share."""
    from app.routers import system

    started: list[tuple[int, int]] = []

    def pretend_load(product_target: int, customer_target: int) -> None:
        started.append((product_target, customer_target))
        with system.LOAD_STATE.lock:
            system.LOAD_STATE.running = False

    monkeypatch.setattr(system, "_load", pretend_load)
    response = client.post(
        "/api/system/load-demo-data", json={"product_target": 2000, "customer_target": 150}
    )
    assert response.status_code == 200, response.text
    assert response.json()["started"] is True

    for _ in range(200):
        if started:
            break
        time.sleep(0.01)
    assert started == [(2000, 150)]


@pytest.mark.parametrize("route", ["/api/system/load-demo-data", "/api/system/load-demo-data-now"])
def test_loading_over_existing_data_still_needs_an_administrator(client, signed_in, route):
    anonymous = client.post(route, json={"product_target": 200, "customer_target": 10})
    assert anonymous.status_code == 401

    engineer = signed_in("amy.chen@hengtai-industrial.example")
    refused = engineer.post(route, json={"product_target": 200, "customer_target": 10})
    assert refused.status_code == 403
