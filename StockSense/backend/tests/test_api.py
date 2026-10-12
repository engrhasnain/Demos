"""The HTTP surface, including who is allowed to do what."""

from __future__ import annotations

BUYER = "wei.chen@hengtai-industrial.example"
SENIOR = "lin.hsu@hengtai-industrial.example"
MANAGER = "tomas.reyes@hengtai-industrial.example"
ADMINISTRATOR = "admin@hengtai-industrial.example"


class TestSigningIn:
    def test_health_needs_no_sign_in(self, client):
        body = client.get("/api/health").json()
        assert body["database"] == "ready"
        assert body["engine"] == "built-in"

    def test_the_wrong_password_does_not_say_which_part_was_wrong(self, client):
        response = client.post(
            "/api/auth/sign-in", json={"email": BUYER, "password": "wrong"}
        )
        assert response.status_code == 401
        assert "do not match" in response.json()["detail"].lower()

    def test_an_unknown_address_is_refused_the_same_way(self, client):
        response = client.post(
            "/api/auth/sign-in", json={"email": "nobody@example.com", "password": "demo1234"}
        )
        assert response.status_code == 401
        assert "do not match" in response.json()["detail"].lower()

    def test_an_altered_token_is_refused(self, client, signed_in):
        headers = signed_in(BUYER)
        headers["Authorization"] = headers["Authorization"][:-2] + "xy"
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_nothing_is_readable_without_a_token(self, client):
        for path in ("/api/dashboard", "/api/parts", "/api/suppliers", "/api/plan"):
            assert client.get(path).status_code == 401, path


class TestWhoMayDoWhat:
    def test_a_buyer_cannot_read_the_audit_trail(self, client, signed_in):
        assert client.get("/api/audit", headers=signed_in(BUYER)).status_code == 403

    def test_a_manager_can(self, client, signed_in):
        assert client.get("/api/audit", headers=signed_in(MANAGER)).status_code == 200

    def test_the_refusal_names_the_role_needed_and_the_one_you_have(self, client, signed_in):
        detail = client.get("/api/audit", headers=signed_in(BUYER)).json()["detail"]
        assert "Purchasing manager" in detail
        assert "buyer" in detail.lower()

    def test_a_buyer_cannot_start_a_replay(self, client, signed_in):
        response = client.post(
            "/api/replay", json={"parts": 50, "weeks": 12}, headers=signed_in(BUYER)
        )
        assert response.status_code == 403

    def test_only_an_administrator_may_reload_the_catalogue(self, client, signed_in):
        response = client.post(
            "/api/demo/load", json={"size": "small"}, headers=signed_in(MANAGER)
        )
        assert response.status_code == 403


class TestReading:
    def test_money_is_never_sent_as_a_number(self, client, signed_in):
        """A float that has been through JSON is not the figure we hold."""
        body = client.get("/api/dashboard", headers=signed_in(BUYER)).json()
        assert isinstance(body["stock_value"], str)
        assert isinstance(body["carrying_cost_low"], str)

    def test_the_carrying_cost_is_a_range_not_a_number(self, client, signed_in):
        """Nobody knows it to the percentage point, so it is never quoted as one."""
        body = client.get("/api/settings", headers=signed_in(BUYER)).json()
        assert body["carrying_cost_percent_low"] < body["carrying_cost_percent_high"]

    def test_the_settings_publish_the_classification_cutoffs(self, client, signed_in):
        body = client.get("/api/settings", headers=signed_in(BUYER)).json()
        assert body["cutoffs"]["average_demand_interval"] == 1.32
        assert body["cutoffs"]["coefficient_of_variation_squared"] == 0.49

    def test_a_part_comes_back_with_its_whole_route(self, client, signed_in):
        headers = signed_in(BUYER)
        first = client.get("/api/parts?limit=1", headers=headers).json()["items"][0]
        body = client.get(f"/api/parts/{first['id']}", headers=headers).json()
        assert body["demand"]["pattern"]["kind"]
        assert body["demand"]["forecast"]["method"]
        assert body["recommendation"]["policy"]["reorder_point"] is not None
        assert body["recommendation"]["trace"]["steps"]
        assert len(body["demand"]["sold"]) > 0

    def test_a_part_that_is_not_there_says_so(self, client, signed_in):
        response = client.get("/api/parts/999999", headers=signed_in(BUYER))
        assert response.status_code == 404
        assert "no part" in response.json()["detail"].lower()

    def test_a_silly_page_size_is_refused(self, client, signed_in):
        assert client.get("/api/parts?limit=99999", headers=signed_in(BUYER)).status_code == 422

    def test_a_supplier_shows_what_it_quotes_and_what_it_does(self, client, signed_in):
        headers = signed_in(BUYER)
        first = client.get("/api/suppliers?limit=1", headers=headers).json()["items"][0]
        body = client.get(f"/api/suppliers/{first['id']}", headers=headers).json()
        assert body["lead_time"]["quoted_days"] > 0
        assert body["lead_time"]["average_days"] > 0
        assert "lead_time_samples" in body


class TestPlanning:
    def test_a_plan_can_be_built_and_read_back(self, client, signed_in):
        headers = signed_in(MANAGER)
        built = client.post("/api/plan", json={"parts": 120}, headers=headers)
        assert built.status_code == 200, built.text
        body = built.json()
        assert body["parts_considered"] == 120
        assert body["by_decision"]
        assert body["by_reason"]

        lines = client.get(f"/api/plan/{body['id']}/lines?limit=5", headers=headers).json()
        assert lines["total"] == 120
        assert len(lines["items"]) == 5

    def test_a_line_shows_its_working_when_asked_for_on_its_own(self, client, signed_in):
        headers = signed_in(MANAGER)
        run = client.post("/api/plan", json={"parts": 60}, headers=headers).json()
        lines = client.get(f"/api/plan/{run['id']}/lines?limit=1", headers=headers).json()
        line_id = lines["items"][0]["id"]
        one = client.get(
            f"/api/plan/{run['id']}/lines/{line_id}", headers=headers
        ).json()
        assert one["trace"]["steps"]

    def test_the_cash_cap_is_respected_over_http(self, client, signed_in):
        headers = signed_in(MANAGER)
        body = client.post(
            "/api/plan", json={"parts": 200, "cash_cap": 30000}, headers=headers
        ).json()
        assert float(body["cash_committed"]) <= 30000.0

    def test_filtering_the_lines_works(self, client, signed_in):
        headers = signed_in(MANAGER)
        run = client.post("/api/plan", json={"parts": 200}, headers=headers).json()
        ordered = client.get(
            f"/api/plan/{run['id']}/lines?decision=order&limit=50", headers=headers
        ).json()
        assert all(item["decision"] == "order" for item in ordered["items"])


class TestEvidence:
    def test_the_bars_are_published_without_running_anything(self, client, signed_in):
        body = client.get("/api/evidence/criteria", headers=signed_in(BUYER)).json()
        names = {row["name"] for row in body["criteria"]}
        assert "stock-out weeks" in names
        assert "inventory value" in names
        for row in body["criteria"]:
            assert row["question"].endswith("?")

    def test_a_replay_reports_both_arms_and_the_trap(self, client, signed_in):
        body = client.post(
            "/api/replay", json={"parts": 120, "weeks": 26}, headers=signed_in(SENIOR)
        )
        assert body.status_code == 200, body.text
        report = body.json()
        assert report["buyers"]["stockout_weeks"] >= 0
        assert report["stocksense"]["stockout_weeks"] >= 0
        assert report["accuracy"]["zero_trap"]["parts_scored"] > 0
        assert len(report["weekly"]) == 26
