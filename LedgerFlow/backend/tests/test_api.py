"""The HTTP surface, including who is allowed to do what."""

from __future__ import annotations

CLERK = "mei.kuo@hengtai-industrial.example"
ACCOUNTANT = "sophie.tan@hengtai-industrial.example"
CONTROLLER = "ravi.menon@hengtai-industrial.example"
ADMINISTRATOR = "admin@hengtai-industrial.example"


class TestSigningIn:
    def test_health_needs_no_sign_in(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["database"] == "ready"

    def test_the_wrong_password_is_refused_without_saying_which_part_was_wrong(self, client):
        response = client.post(
            "/api/auth/sign-in", json={"email": CLERK, "password": "not-the-password"}
        )
        assert response.status_code == 401
        detail = response.json()["detail"].lower()
        assert "do not match" in detail
        assert "password is" not in detail and "no such" not in detail

    def test_an_unknown_address_is_refused_the_same_way(self, client):
        response = client.post(
            "/api/auth/sign-in", json={"email": "nobody@example.com", "password": "demo1234"}
        )
        assert response.status_code == 401
        assert "do not match" in response.json()["detail"].lower()

    def test_a_token_that_has_been_altered_is_refused(self, client, signed_in):
        headers = signed_in(CLERK)
        headers["Authorization"] = headers["Authorization"][:-2] + "xy"
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_nothing_is_readable_without_a_token(self, client):
        for path in ("/api/dashboard", "/api/invoices", "/api/vendors", "/api/ledger"):
            assert client.get(path).status_code == 401, path


class TestWhoMayDoWhat:
    def test_a_clerk_cannot_read_the_audit_trail(self, client, signed_in):
        assert client.get("/api/audit", headers=signed_in(CLERK)).status_code == 403

    def test_a_controller_can(self, client, signed_in):
        assert client.get("/api/audit", headers=signed_in(CONTROLLER)).status_code == 200

    def test_the_refusal_says_which_role_is_needed_and_which_one_you_have(
        self, client, signed_in
    ):
        detail = client.get("/api/audit", headers=signed_in(CLERK)).json()["detail"]
        assert "Controller" in detail
        assert "clerk" in detail.lower()

    def test_only_a_controller_may_record_a_telephone_call(self, client, signed_in):
        response = client.post(
            "/api/vendors/call-backs/1",
            json={"confirmed": True, "note": "Spoke to the owner on the number on file."},
            headers=signed_in(CLERK),
        )
        assert response.status_code == 403

    def test_an_administrator_may_do_what_a_controller_may(self, client, signed_in):
        assert client.get("/api/audit", headers=signed_in(ADMINISTRATOR)).status_code == 200


class TestReading:
    def test_the_dashboard_adds_up(self, client, signed_in):
        body = client.get("/api/dashboard", headers=signed_in(CLERK)).json()
        assert body["invoices"] >= 0
        assert sum(row["count"] for row in body["by_status"]) == body["invoices"]

    def test_money_is_never_sent_as_a_number(self, client, signed_in):
        """A float that has been through JSON is not the ledger's figure."""
        body = client.get("/api/dashboard", headers=signed_in(CLERK)).json()
        assert isinstance(body["held_amount"], str)
        assert isinstance(body["posted_amount"], str)

    def test_the_settings_explain_the_policy_the_screens_show(self, client, signed_in):
        body = client.get("/api/settings", headers=signed_in(CLERK)).json()
        assert body["business_tax_percent"] == 5.0
        assert body["auto_post_ceiling"] > 0
        assert body["two_step_approval"] > body["auto_post_ceiling"]
        assert any(s["code"] == "posted" for s in body["statuses"])

    def test_a_list_that_is_asked_for_a_page_gives_one_page(self, client, signed_in):
        body = client.get("/api/invoices?limit=2", headers=signed_in(CLERK)).json()
        assert len(body["items"]) <= 2
        assert body["limit"] == 2

    def test_asking_for_an_invoice_that_is_not_there_says_so(self, client, signed_in):
        response = client.get("/api/invoices/999999", headers=signed_in(CLERK))
        assert response.status_code == 404
        assert "no invoice" in response.json()["detail"].lower()

    def test_a_silly_page_size_is_refused_rather_than_served(self, client, signed_in):
        assert client.get("/api/invoices?limit=100000", headers=signed_in(CLERK)).status_code == 422


class TestUploading:
    DOCUMENT = (
        "Test Supplier Co., Ltd.\n"
        "Seller tax id: 20005302\n"
        "\n"
        "INVOICE\n"
        "Invoice No: UP-100001\n"
        "Invoice Date: 2026-09-30\n"
        "Buyer tax id: 88124403\n"
        "Currency: TWD\n"
        "\n"
        "Item  Description             Qty   Unit price   Amount\n"
        "1. HT-WSH-M12-200HV-ZNB Flat washer 1000 1.00 1000.00\n"
        "\n"
        "Subtotal: 1000.00\n"
        "Business tax: 50.00\n"
        "Total: 1050.00\n"
    )

    def test_a_document_is_taken_in_read_and_checked(self, client, signed_in):
        response = client.post(
            "/api/invoices/upload",
            files={"file": ("UP-100001.txt", self.DOCUMENT, "text/plain")},
            data={"received_from": "accounts@test-supplier.example"},
            headers=signed_in(CLERK),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["as_read"]["invoice_number"] == "UP-100001"
        assert body["total_amount"] == "1050.00"
        assert body["status"] != "received", "it should have been read and checked"

    def test_an_empty_file_is_refused(self, client, signed_in):
        response = client.post(
            "/api/invoices/upload",
            files={"file": ("empty.txt", b"", "text/plain")},
            headers=signed_in(CLERK),
        )
        assert response.status_code == 400

    def test_a_file_that_cannot_be_matched_is_still_kept(self, client, signed_in):
        """Losing the document because the reading failed is the worst outcome."""
        response = client.post(
            "/api/invoices/upload",
            files={"file": ("nonsense.txt", "there is nothing here", "text/plain")},
            headers=signed_in(CLERK),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert body["document"]["filename"] == "nonsense.txt"
        assert body["exceptions"], "it should say what is wrong rather than vanish"


class TestTheDemonstration:
    def test_the_state_is_readable_before_anybody_signs_in(self, client):
        body = client.get("/api/demo/state").json()
        assert body["loaded"] is True
        assert "reading_engine" in body

    def test_the_batch_says_what_each_document_proves(self, client, signed_in):
        body = client.get("/api/demo/batch", headers=signed_in(CLERK)).json()
        assert body["total"] >= 12
        for item in body["items"]:
            assert item["what_it_tests"]
            assert item["expect"]

    def test_only_an_administrator_may_reload_the_data(self, client, signed_in):
        response = client.post(
            "/api/demo/load", json={"size": "small"}, headers=signed_in(CONTROLLER)
        )
        assert response.status_code == 403


class TestTheEvaluation:
    def test_the_bars_are_published_without_running_anything(self, client, signed_in):
        body = client.get("/api/evaluation/criteria", headers=signed_in(CLERK)).json()
        names = {row["name"] for row in body["criteria"]}
        assert "header fields" in names
        assert "duplicate bills after a crash" in names
        for row in body["criteria"]:
            assert row["question"].endswith("?")

    def test_a_clerk_cannot_start_a_run(self, client, signed_in):
        response = client.post(
            "/api/evaluation/run",
            json={"clean_count": 10, "duplicate_count": 0, "bank_change_count": 0,
                  "retry_count": 0},
            headers=signed_in(CLERK),
        )
        assert response.status_code == 403
