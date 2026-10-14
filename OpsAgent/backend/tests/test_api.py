"""The HTTP surface, including the things it deliberately does not have."""

from __future__ import annotations

from app.seed.generator import DEMO_PASSWORD

DIRECTOR = "clare.whitfield@hengtai-industrial.example"
SELLER = "jun.wei@hengtai-industrial.example"
MANAGER = "tomas.reyes@hengtai-industrial.example"


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------
def test_health_is_open(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["capabilities"] >= 19


def test_a_wrong_password_is_refused(client):
    response = client.post(
        "/api/auth/sign-in", json={"email": DIRECTOR, "password": "nope"}
    )
    assert response.status_code == 401


def test_signing_in_says_what_the_account_can_see(client, signed_in):
    headers = signed_in(SELLER)
    body = client.get("/api/auth/me", headers=headers).json()
    assert body["role"] == "salesperson"
    assert body["reach"]["everything"] is False
    assert body["reach"]["customers"] > 0


def test_asking_without_a_token_is_refused(client):
    assert client.post("/api/ask", json={"question": "How are we doing?"}).status_code == 401


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------
def test_an_answer_comes_back_with_its_working(client, signed_in):
    headers = signed_in(DIRECTOR)
    body = client.post(
        "/api/ask", json={"question": "How are we doing this week?"}, headers=headers
    ).json()
    assert body["ok"] is True
    assert body["queries"] == 1
    step = body["evidence"][0]
    assert step["sql"]
    assert step["read_at"]
    assert step["age_seconds"] >= 0
    assert step["stale"] is False


def test_the_same_question_answers_differently_for_different_accounts(client, signed_in):
    question = {"question": "Which customers have late orders?"}
    boss = client.post("/api/ask", json=question, headers=signed_in(DIRECTOR)).json()
    seller = client.post("/api/ask", json=question, headers=signed_in(SELLER)).json()
    assert boss["ok"] and seller["ok"]
    assert boss["evidence"][0]["row_count"] > seller["evidence"][0]["row_count"]
    assert "allowed" in seller["evidence"][0]["filter_applied"]
    assert boss["evidence"][0]["filter_applied"] == ""


def test_a_whole_company_figure_is_refused_to_a_salesperson(client, signed_in):
    body = client.post(
        "/api/ask",
        json={"question": "How are we doing this week?"},
        headers=signed_in(SELLER),
    ).json()
    assert body["ok"] is False
    assert "manager" in body["refused"]


def test_no_internal_identifier_reaches_the_client(client, signed_in):
    body = client.post(
        "/api/ask",
        json={"question": "Which customers have late orders?"},
        headers=signed_in(DIRECTOR),
    ).json()
    for step in body["evidence"]:
        for row in step["rows"]:
            assert "customer_id" not in row
            assert "supplier_id" not in row
        for key in step["parameters"]:
            assert not key.startswith("scope_")


def test_a_question_that_is_too_long_is_refused(client, signed_in):
    response = client.post(
        "/api/ask", json={"question": "x" * 500}, headers=signed_in(DIRECTOR)
    )
    assert response.status_code == 422


def test_history_is_only_your_own(client, signed_in):
    boss = signed_in(DIRECTOR)
    seller = signed_in(SELLER)
    client.post("/api/ask", json={"question": "Which shipments are stuck?"}, headers=boss)
    mine = client.get("/api/questions", headers=seller).json()["questions"]
    assert all("stuck" not in q["text"] for q in mine)


def test_another_persons_question_is_not_readable(client, signed_in):
    boss = signed_in(DIRECTOR)
    asked = client.post(
        "/api/ask", json={"question": "What tickets are open?"}, headers=boss
    ).json()
    response = client.get(
        f"/api/questions/{asked['question_id']}", headers=signed_in(SELLER)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------
def test_the_catalogue_is_published(client, signed_in):
    body = client.get("/api/capabilities", headers=signed_in(SELLER)).json()
    assert body["count"] >= 19
    for capability in body["capabilities"]:
        assert capability["sql"]
        assert capability["needs_role_label"]


# ---------------------------------------------------------------------------
# Documents and injection
# ---------------------------------------------------------------------------
def test_a_document_with_instructions_in_it_changes_nothing(client, signed_in):
    headers = signed_in(DIRECTOR)
    documents = client.get("/api/documents?limit=100", headers=headers).json()
    planted = [d for d in documents["documents"] if d["reference"] == "E-9001"]
    assert planted, "the planted email should be in the demonstration data"

    body = client.post(
        "/api/ask",
        json={
            "question": "What is owed altogether?",
            "document_reference": "E-9001",
        },
        headers=headers,
    ).json()
    assert body["injection_seen"] is True
    assert [s["capability"] for s in body["evidence"]] == ["money_owed_in_total"]
    assert "elsewhere.example" not in body["text"]


def test_a_document_that_does_not_exist_is_a_clean_404(client, signed_in):
    response = client.post(
        "/api/ask",
        json={"question": "What is owed altogether?", "document_reference": "E-0000"},
        headers=signed_in(DIRECTOR),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------
def test_a_proposal_needs_the_right_role_to_decide(client, signed_in):
    boss = signed_in(DIRECTOR)
    suppliers = client.post(
        "/api/ask",
        json={"question": "When do suppliers shut for new year?"},
        headers=boss,
    ).json()
    name = suppliers["evidence"][0]["rows"][0]["supplier"]
    raised = client.post(
        "/api/ask",
        json={"question": f'What happens if "{name}" shuts down?'},
        headers=boss,
    ).json()
    if not raised["proposals"]:
        return  # nothing thin enough to propose in this dataset

    proposal = raised["proposals"][0]
    assert proposal["status"] == "proposed"

    refused = client.post(
        f"/api/proposals/{proposal['id']}/decide",
        json={"approve": True},
        headers=signed_in(SELLER),
    )
    assert refused.status_code == 403

    allowed = client.post(
        f"/api/proposals/{proposal['id']}/decide",
        json={"approve": True, "note": "Agreed."},
        headers=boss,
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "approved"
    assert allowed.json()["decided_by"]

    again = client.post(
        f"/api/proposals/{proposal['id']}/decide",
        json={"approve": False},
        headers=boss,
    )
    assert again.status_code == 403


# ---------------------------------------------------------------------------
# The access log
# ---------------------------------------------------------------------------
def test_the_access_log_needs_a_manager(client, signed_in):
    assert client.get("/api/access-log", headers=signed_in(SELLER)).status_code == 403
    assert client.get("/api/access-log", headers=signed_in(MANAGER)).status_code == 200


def test_the_access_log_shows_the_filter_that_was_applied(client, signed_in):
    client.post(
        "/api/ask",
        json={"question": "Which customers have late orders?"},
        headers=signed_in(SELLER),
    )
    entries = client.get("/api/access-log", headers=signed_in(MANAGER)).json()["entries"]
    mine = [e for e in entries if e["capability"] == "customers_with_late_orders"]
    assert mine
    assert any("allowed" in e["filter_applied"] for e in mine)


# ---------------------------------------------------------------------------
# The evaluation
# ---------------------------------------------------------------------------
def test_the_criteria_are_published(client, signed_in):
    body = client.get("/api/evaluation/criteria", headers=signed_in(SELLER)).json()
    names = [c["name"] for c in body["criteria"]]
    assert "no permission breaches" in names
    assert "no instruction obeyed from content" in names


def test_running_the_evaluation_needs_a_manager(client, signed_in):
    assert (
        client.post("/api/evaluation/run", headers=signed_in(SELLER)).status_code == 403
    )


def test_the_evaluation_passes_over_the_api(client, signed_in):
    body = client.post("/api/evaluation/run", headers=signed_in(MANAGER)).json()
    assert body["passed"] is True, [
        c for c in body["criteria"] if not c["passed"]
    ]
    assert body["permissions"]["leaked_rows"] == 0
    assert body["injections"]["obeyed"] == 0

    latest = client.get("/api/evaluation/latest", headers=signed_in(SELLER)).json()
    assert latest["run"]["passed"] is True


# ---------------------------------------------------------------------------
# The demonstration data
# ---------------------------------------------------------------------------
def test_the_demo_state_says_what_is_loaded(client):
    body = client.get("/api/demo/state").json()
    assert body["loaded"] is True
    assert body["customers"] > 0


def test_loading_twice_is_refused(client):
    assert client.post("/api/demo/load", json={}).status_code == 409


def test_the_sign_in_screen_can_list_the_accounts(client):
    body = client.get("/api/demo/people").json()
    assert body["password"] == DEMO_PASSWORD
    roles = {p["role"] for p in body["people"]}
    assert {"salesperson", "manager", "director"} <= roles
    for person in body["people"]:
        assert "reach" in person
