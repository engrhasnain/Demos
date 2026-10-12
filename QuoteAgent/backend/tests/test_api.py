"""The product end to end, through its own HTTP routes."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Case, QuoteVersion, TariffTable
from app.services import casestate
from app.services.casestate import IllegalTransition, assert_can_move, can_move


# ---------------------------------------------------------------------------
# The case lifecycle refuses moves that are not on the map
# ---------------------------------------------------------------------------
def test_a_received_case_cannot_jump_straight_to_sent():
    assert not can_move(casestate.RECEIVED, casestate.SENT)
    with pytest.raises(IllegalTransition) as error:
        assert_can_move(casestate.RECEIVED, casestate.SENT)
    assert "cannot move to" in str(error.value)


def test_a_revised_request_can_arrive_at_any_live_moment():
    for status in (
        casestate.MATCHED,
        casestate.AWAITING_CUSTOMER,
        casestate.PRICED,
        casestate.AWAITING_APPROVAL,
        casestate.SENT,
    ):
        assert can_move(status, casestate.REVISED), status


def test_a_won_case_is_finished():
    assert casestate.TRANSITIONS[casestate.WON] == set()


# ---------------------------------------------------------------------------
# Signing in and permissions
# ---------------------------------------------------------------------------
def test_an_unknown_password_is_refused(client):
    response = client.post(
        "/api/auth/sign-in",
        json={"email": "amy.chen@hengtai-industrial.example", "password": "wrong"},
    )
    assert response.status_code == 401


def test_the_api_needs_a_sign_in(client):
    assert client.get("/api/cases").status_code == 401


def test_health_and_status_need_no_sign_in(client):
    assert client.get("/api/health").status_code == 200
    body = client.get("/api/system/status").json()
    assert body["data_loaded"] is True
    assert body["reasoning_engine"]["active_engine"] == "built-in"
    assert "pricing engine alone" in body["reasoning_engine"]["guarantee"]


def test_a_sales_engineer_cannot_activate_a_duty_table(signed_in, session):
    client = signed_in("amy.chen@hengtai-industrial.example")
    draft = session.scalar(select(TariffTable).where(TariffTable.status == "draft"))
    response = client.post(
        f"/api/rates/tariff-tables/{draft.id}/activate",
        json={"confirm_broker_sign_off": True},
    )
    assert response.status_code == 403
    assert "Pricing owner" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------
def test_the_same_email_delivered_twice_makes_one_case(signed_in):
    client = signed_in()
    payload = {
        "sender": "Rosa Mendez <r.mendez@pacificmotion.example>",
        "subject": "Repeat delivery test",
        "body": "Please quote 1000 of ISO 4762 M8x30 12.9 zinc.",
        "external_message_id": "<repeat-delivery-test@pacificmotion.example>",
    }
    first = client.post("/api/cases", json=payload).json()
    second = client.post("/api/cases", json=payload).json()
    assert first["created"] is True
    assert second["created"] is False
    assert first["case"]["reference"] == second["case"]["reference"]


def test_a_request_with_no_attachment_is_read_from_the_email_text(signed_in):
    client = signed_in()
    created = client.post(
        "/api/cases",
        json={
            "sender": "Rosa Mendez <r.mendez@pacificmotion.example>",
            "subject": "Short enquiry",
            "body": (
                "Hi, please quote:\n"
                "1. ISO 4762 M8x30 12.9 zinc plated - 2000 pcs\n"
                "2. ISO 4017 M10x40 8.8 zinc plated - 1500 pcs\n"
                "Thanks"
            ),
            "external_message_id": "<short-enquiry@pacificmotion.example>",
        },
    ).json()
    case_id = created["case"]["id"]
    step = client.post(f"/api/cases/{case_id}/read").json()
    assert step["detail"]["lines_used"] == 2
    assert step["detail"]["source_of_truth"] == "the email text"


def test_prose_in_a_covering_email_does_not_become_a_quote_line(signed_in):
    """The attachment is the bill of materials; the email is the covering note."""
    client = signed_in()
    created = client.post("/api/cases/from-sample", json={"sample_key": "main_request"}).json()
    case_id = created["case"]["id"]
    step = client.post(f"/api/cases/{case_id}/read").json()
    assert step["detail"]["source_of_truth"] == "the attached spreadsheet"
    assert step["detail"]["lines_used"] == 40
    # The covering note mentions DIN numbers; those phrases are recorded, not quoted.
    assert isinstance(step["detail"]["ignored_from_email_text"], list)


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------
@pytest.fixture()
def prepared_case(signed_in):
    client = signed_in()
    created = client.post("/api/cases/from-sample", json={"sample_key": "main_request"}).json()
    case_id = created["case"]["id"]
    client.post(f"/api/cases/{case_id}/run")
    return client, case_id


def test_the_agent_reads_matches_asks_and_prices(prepared_case):
    client, case_id = prepared_case
    case = client.get(f"/api/cases/{case_id}").json()
    counts = case["current_version"]["line_counts"]
    assert counts["total"] == 40
    assert counts.get("needs_clarification", 0) >= 1
    assert Decimal(case["current_version"]["totals"]["grand_total"]) > 0


def test_every_question_goes_out_in_one_email(prepared_case):
    client, case_id = prepared_case
    questions = client.get(f"/api/cases/{case_id}/questions").json()
    assert questions["summary"]["emails_sent"] == 1
    assert questions["summary"]["questions_asked"] >= 1
    assert "One email per round" in questions["summary"]["statement"]


def test_an_email_is_not_sent_until_a_person_approves_it(prepared_case):
    client, case_id = prepared_case
    case = client.get(f"/api/cases/{case_id}").json()
    drafts = [m for m in case["messages"] if m["awaiting_approval"]]
    assert drafts, "the question email should be waiting for approval"
    sent = client.post(
        f"/api/cases/{case_id}/messages/send", json={"message_id": drafts[0]["id"]}
    )
    assert sent.status_code == 200
    assert sent.json()["message"]["sent_at"]


def test_a_line_shows_how_its_price_was_worked_out(prepared_case):
    client, case_id = prepared_case
    version = client.get(f"/api/cases/{case_id}").json()["current_version"]
    priced = [line for line in version["lines"] if line["status"] == "priced"]
    assert priced
    trace = priced[0]["calculation_trace"]
    assert trace["steps"]
    labels = [step["label"] for step in trace["steps"]]
    assert "Unit price" in labels
    assert "Line value" in labels
    assert any(step["inputs"] for step in trace["steps"])


def test_the_quote_cannot_be_sent_while_a_question_is_open(prepared_case):
    client, case_id = prepared_case
    response = client.post(f"/api/cases/{case_id}/send-quote")
    assert response.status_code == 400
    assert "open question" in response.json()["detail"]


def test_changing_the_trade_terms_recomputes_and_explains(prepared_case):
    client, case_id = prepared_case
    # Start from free on board Taichung so the change is a real change.
    client.post(
        f"/api/cases/{case_id}/terms",
        json={
            "incoterm": "FOB",
            "named_place": "Taichung",
            "currency": "TWD",
            "destination_country": "TW",
        },
    )
    response = client.post(
        f"/api/cases/{case_id}/terms",
        json={
            "incoterm": "DDP",
            "named_place": "Ontario, California",
            "currency": "USD",
            "destination_country": "US",
        },
    ).json()
    assert response["before"]["incoterm"] != response["after"]["incoterm"]
    assert Decimal(response["after"]["import_duty"]) > 0
    assert any("import duty" in line for line in response["what_changes"])


def test_a_discount_pushes_lines_under_the_floor_and_asks_a_manager(prepared_case):
    client, case_id = prepared_case
    response = client.post(
        f"/api/cases/{case_id}/discount", json={"discount_percent": "12"}
    ).json()
    assert Decimal(response["total_after"]) < Decimal(response["total_before"])
    if response["lines_below_floor"]:
        assert any(a["required_role"] == "sales_manager" for a in response["approvals"])


def test_the_pricing_integrity_check_passes_on_a_priced_quote(prepared_case):
    client, case_id = prepared_case
    report = client.get(f"/api/cases/{case_id}/integrity").json()
    assert report["ok"] is True
    assert "equals the pricing engine" in report["statement"]


def test_the_quote_document_can_be_previewed(prepared_case):
    client, case_id = prepared_case
    response = client.get(f"/api/cases/{case_id}/quote-preview")
    assert response.status_code == 200
    assert "Quotation" in response.text or "報價單" in response.text


def test_the_line_export_is_produced(prepared_case):
    client, case_id = prepared_case
    response = client.get(f"/api/cases/{case_id}/line-export")
    assert response.status_code == 200
    assert len(response.content) > 0


# ---------------------------------------------------------------------------
# Duty tables
# ---------------------------------------------------------------------------
def test_activating_a_newer_duty_table_flags_open_quotes(prepared_case, session):
    client, case_id = prepared_case
    client.post(
        f"/api/cases/{case_id}/terms",
        json={"incoterm": "DDP", "currency": "USD", "destination_country": "US"},
    )
    draft = session.scalar(select(TariffTable).where(TariffTable.status == "draft"))
    if draft is None:
        pytest.skip("the duty table was already activated by another test")

    response = client.post(
        f"/api/rates/tariff-tables/{draft.id}/activate",
        json={"confirm_broker_sign_off": True, "customs_broker": "Test broker"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["activated"]["status"] == "active"
    assert any(q["reference"] for q in body["quotes_flagged_for_repricing"])

    needing = client.get("/api/rates/quotes-needing-repricing").json()
    assert needing["count"] >= 1


def test_a_duty_table_that_is_not_in_force_yet_cannot_be_activated(signed_in, session):
    client = signed_in()
    import datetime as dt

    future = TariffTable(
        version="test-future",
        title="A table for next year",
        effective_from=dt.date.today() + dt.timedelta(days=30),
        status="draft",
        owned_by="test",
    )
    session.add(future)
    session.commit()
    try:
        response = client.post(
            f"/api/rates/tariff-tables/{future.id}/activate", json={}
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        # The refusal has to name the date it starts and say what activating
        # it now would cost; the exact wording is free to change.
        assert future.effective_from.isoformat() in detail
        assert "no table in force" in detail
    finally:
        # Leave the database as it was found, so later tests see the real data.
        session.delete(future)
        session.commit()


# ---------------------------------------------------------------------------
# The catalogue sandbox
# ---------------------------------------------------------------------------
def test_anyone_can_try_a_line_against_the_matcher(signed_in):
    client = signed_in("amy.chen@hengtai-industrial.example")
    response = client.post(
        "/api/catalogue/match", json={"text": "DIN 912 M8x30 12.9 zinc"}
    ).json()
    assert response["how_it_was_read"]["family"] == "fastener"
    assert response["how_it_was_read"]["attributes"]["thread"] == "M8"
    assert response["status"] in {"matched", "needs_clarification", "non_catalogue"}


def test_a_quote_that_has_been_sent_cannot_be_sent_again(session):
    """Caught only by a unique key before, so it was a 500, not a refusal."""
    import datetime as dt

    from app.models import CaseMessage, QuoteVersion, User
    from app.services import agent

    version = session.scalar(
        select(QuoteVersion).where(QuoteVersion.status == "sent").limit(1)
    )
    if version is None:
        version = session.scalar(select(QuoteVersion).limit(1))
        assert version is not None, "the generated data has no quote versions"
        version.status = "sent"
        version.sent_at = dt.datetime.now(dt.timezone.utc)
        session.flush()

    case = version.case
    user = session.scalar(select(User).where(User.role == "director"))

    def emails() -> int:
        return len(
            list(
                session.scalars(
                    select(CaseMessage).where(
                        CaseMessage.case_id == case.id, CaseMessage.kind == "quote"
                    )
                )
            )
        )

    before = emails()
    with pytest.raises(agent.AgentError) as error:
        agent.send_quote(session, case, user)
    assert "already been sent" in str(error.value)
    assert emails() == before, "a refused send must not leave a second quote email"
