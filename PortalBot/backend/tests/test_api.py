"""The HTTP surface and who may use it."""

from __future__ import annotations

CLERK = "kai.chen@hengtai-industrial.example"
LEAD = "tomas.reyes@hengtai-industrial.example"
DEVELOPER = "ana.silva@hengtai-industrial.example"
ADMINISTRATOR = "admin@hengtai-industrial.example"


class TestAccess:
    def test_health_is_open(self, client):
        assert client.get("/api/health").json()["database"] == "ready"

    def test_everything_else_needs_signing_in(self, client):
        for path in ("/api/dashboard", "/api/shipments", "/api/runs", "/api/flags"):
            assert client.get(path).status_code == 401, path

    def test_a_clerk_cannot_acknowledge_a_script_flag(self, client, signed_in):
        """Only a developer decides a changed form is understood."""
        assert (
            client.post(
                "/api/flags/1", json={"note": "fine"}, headers=signed_in(CLERK)
            ).status_code
            == 403
        )

    def test_a_clerk_cannot_release_a_new_portal_version(self, client, signed_in):
        assert (
            client.post(
                "/api/portal/release", json={"version": "v2"}, headers=signed_in(CLERK)
            ).status_code
            == 403
        )

    def test_a_clerk_cannot_run_the_evidence(self, client, signed_in):
        assert (
            client.post(
                "/api/evidence/run", json={"shipments": 20}, headers=signed_in(CLERK)
            ).status_code
            == 403
        )

    def test_only_an_administrator_may_reload(self, client, signed_in):
        assert (
            client.post(
                "/api/demo/load", json={"shipments": 20}, headers=signed_in(LEAD)
            ).status_code
            == 403
        )


class TestRunning:
    def test_a_run_reports_what_it_did(self, client, signed_in):
        body = client.post("/api/run", json={"limit": 30}, headers=signed_in(CLERK))
        assert body.status_code == 200, body.text
        run = body.json()
        assert run["run"]["considered"] <= 30
        assert run["completed"] >= 0

    def test_a_second_run_picks_up_only_what_is_left(self, client, signed_in):
        headers = signed_in(CLERK)
        client.post("/api/run", json={}, headers=headers)
        again = client.post("/api/run", json={}, headers=headers).json()
        # Everything finished is gone from the query entirely.
        assert again["run"]["considered"] <= again["run"]["considered"]
        assert again["completed"] >= 0

    def test_a_shipment_carries_its_whole_trace(self, client, signed_in):
        headers = signed_in(CLERK)
        client.post("/api/run", json={"limit": 10}, headers=headers)
        listed = client.get("/api/shipments?limit=1", headers=headers).json()
        reference = listed["items"][0]["reference"]
        detail = client.get(f"/api/shipments/{reference}", headers=headers).json()
        assert detail["idempotency_key"]
        assert isinstance(detail["steps"], list)
        for step in detail["steps"]:
            assert step["system"] in {"bot", "carrier", "legacy"}
            assert step["outcome"]

    def test_a_shipment_that_is_not_there_says_so(self, client, signed_in):
        response = client.get("/api/shipments/NOPE", headers=signed_in(CLERK))
        assert response.status_code == 404


class TestTheFormMoving:
    def test_releasing_a_new_portal_halts_the_next_run(self, client, signed_in):
        developer = signed_in(DEVELOPER)
        clerk = signed_in(CLERK)
        try:
            client.post("/api/portal/release", json={"version": "v2"}, headers=developer)
            run = client.post("/api/run", json={"limit": 10}, headers=clerk).json()
            assert run["halted"]
            assert run["drift"]["missing"]
            flags = client.get("/api/flags", headers=clerk).json()
            assert flags["total"] > 0
        finally:
            client.post("/api/portal/release", json={"version": "v1"}, headers=developer)

    def test_a_developer_can_acknowledge_it(self, client, signed_in):
        developer = signed_in(DEVELOPER)
        clerk = signed_in(CLERK)
        try:
            client.post("/api/portal/release", json={"version": "v2"}, headers=developer)
            client.post("/api/run", json={"limit": 5}, headers=clerk)
            flags = client.get("/api/flags", headers=clerk).json()["items"]
            assert flags
            answered = client.post(
                f"/api/flags/{flags[0]['id']}",
                json={"note": "Carrier renamed two fields in their March release."},
                headers=developer,
            )
            assert answered.status_code == 200
            assert answered.json()["status"] == "acknowledged"
        finally:
            client.post("/api/portal/release", json={"version": "v1"}, headers=developer)


class TestEvidence:
    def test_the_bars_are_published(self, client, signed_in):
        body = client.get("/api/evidence/criteria", headers=signed_in(CLERK)).json()
        names = {row["name"] for row in body["criteria"]}
        assert "duplicates" in names
        assert "the portal changing is noticed" in names
        for row in body["criteria"]:
            assert row["question"].endswith("?")

    def test_the_lead_can_run_it_and_the_absolutes_hold(self, client, signed_in):
        report = client.post(
            "/api/evidence/run", json={"shipments": 60}, headers=signed_in(LEAD)
        )
        assert report.status_code == 200, report.text
        body = report.json()
        assert len(body["criteria"]) == 4
        duplicates = next(c for c in body["criteria"] if c["name"] == "duplicates")
        drift = next(
            c for c in body["criteria"] if c["name"] == "the portal changing is noticed"
        )
        assert duplicates["value"] == 0
        assert drift["passed"]
