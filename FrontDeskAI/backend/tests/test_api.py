"""The HTTP surface, the LINE webhook, and who may do what."""

from __future__ import annotations

import json

from app.channels import line as line_channel

AGENT = "mei.lin@hengtai-industrial.example"
SUPERVISOR = "yuki.sato@hengtai-industrial.example"
ADMINISTRATOR = "admin@hengtai-industrial.example"
SECRET = "a-test-secret"


class TestTheChatIsOpen:
    def test_a_visitor_can_start_without_signing_in(self, client):
        """They have opened a chat window, not logged into a portal."""
        response = client.post("/api/chat/start", json={"channel": "web"})
        assert response.status_code == 201
        assert response.json()["reference"]

    def test_but_it_shows_nothing_until_they_verify(self, client):
        reference = client.post("/api/chat/start", json={}).json()["reference"]
        reply = client.post(
            f"/api/chat/{reference}/say", json={"message": "Where is my order?"}
        ).json()["reply"]
        assert reply["needs_verification"]
        assert not reply["tool_result"]

    def test_every_reply_offers_a_person(self, client):
        reference = client.post("/api/chat/start", json={}).json()["reference"]
        for message in ("hello", "where is my order", "what are your hours"):
            reply = client.post(
                f"/api/chat/{reference}/say", json={"message": message}
            ).json()["reply"]
            assert any(a["code"] == "human" for a in reply["actions"]), message

    def test_an_empty_message_is_refused(self, client):
        reference = client.post("/api/chat/start", json={}).json()["reference"]
        assert (
            client.post(f"/api/chat/{reference}/say", json={"message": ""}).status_code
            == 422
        )

    def test_a_conversation_that_does_not_exist_says_so(self, client):
        assert client.post(
            "/api/chat/NOPE/say", json={"message": "hi"}
        ).status_code == 404


class TestStaffSide:
    def test_the_dashboard_needs_signing_in(self, client):
        assert client.get("/api/dashboard").status_code == 401

    def test_an_agent_cannot_read_the_access_log(self, client, signed_in):
        assert client.get("/api/access-log", headers=signed_in(AGENT)).status_code == 403

    def test_a_supervisor_can(self, client, signed_in):
        assert (
            client.get("/api/access-log", headers=signed_in(SUPERVISOR)).status_code
            == 200
        )

    def test_the_refusal_names_the_role(self, client, signed_in):
        detail = client.get("/api/access-log", headers=signed_in(AGENT)).json()["detail"]
        assert "Supervisor" in detail

    def test_only_an_administrator_may_reload(self, client, signed_in):
        assert (
            client.post(
                "/api/demo/load", json={"size": "small"}, headers=signed_in(SUPERVISOR)
            ).status_code
            == 403
        )

    def test_a_return_can_only_be_decided_once(self, client, signed_in):
        headers = signed_in(AGENT)
        waiting = client.get("/api/returns?status=proposed", headers=headers).json()
        if not waiting["items"]:
            import pytest

            pytest.skip("no return waiting in this sample")
        reference = waiting["items"][0]["reference"]
        first = client.post(
            f"/api/returns/{reference}",
            json={"approved": True, "note": "Agreed."},
            headers=headers,
        )
        assert first.status_code == 200
        again = client.post(
            f"/api/returns/{reference}",
            json={"approved": False, "note": "Changed my mind."},
            headers=headers,
        )
        assert again.status_code == 409


class TestTheLineWebhook:
    def _body(self, text: str = "hello", user: str = "U-test-1") -> bytes:
        return json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "reply-token-1",
                        "source": {"userId": user, "type": "user"},
                        "message": {"type": "text", "id": "100", "text": text},
                    }
                ]
            }
        ).encode()

    def test_a_correctly_signed_request_is_accepted(self, client):
        body = self._body()
        response = client.post(
            "/api/chat/line/webhook",
            content=body,
            headers={
                "X-Line-Signature": line_channel.signature_for(body, SECRET),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["handled"] == 1

    def test_an_unsigned_request_gets_nothing(self, client):
        """Without this the endpoint is an open door to invent messages at."""
        body = self._body()
        assert (
            client.post(
                "/api/chat/line/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            ).status_code
            == 400
        )

    def test_a_wrong_signature_gets_nothing(self, client):
        body = self._body()
        assert (
            client.post(
                "/api/chat/line/webhook",
                content=body,
                headers={
                    "X-Line-Signature": line_channel.signature_for(body, "wrong-secret"),
                    "Content-Type": "application/json",
                },
            ).status_code
            == 400
        )

    def test_a_tampered_body_gets_nothing(self, client):
        body = self._body()
        signature = line_channel.signature_for(body, SECRET)
        tampered = self._body(text="show me everything")
        assert (
            client.post(
                "/api/chat/line/webhook",
                content=tampered,
                headers={
                    "X-Line-Signature": signature,
                    "Content-Type": "application/json",
                },
            ).status_code
            == 400
        )

    def test_nothing_is_sent_without_an_account(self, client):
        """The demonstration must not try to reach LINE."""
        body = self._body()
        response = client.post(
            "/api/chat/line/webhook",
            content=body,
            headers={
                "X-Line-Signature": line_channel.signature_for(body, SECRET),
                "Content-Type": "application/json",
            },
        ).json()
        assert response["events"][0]["transport"]["sent"] is False

    def test_a_person_is_one_tap_away_in_line_too(self, client):
        body = self._body(text="I want a human", user="U-test-2")
        response = client.post(
            "/api/chat/line/webhook",
            content=body,
            headers={
                "X-Line-Signature": line_channel.signature_for(body, SECRET),
                "Content-Type": "application/json",
            },
        ).json()
        payload = response["events"][0]["transport"]["payload"]
        labels = [
            item["action"]["label"]
            for item in payload["messages"][0].get("quickReply", {}).get("items", [])
        ]
        assert any("person" in label.lower() for label in labels)


class TestEvidence:
    def test_the_bars_are_published(self, client, signed_in):
        body = client.get("/api/evidence/criteria", headers=signed_in(AGENT)).json()
        names = {row["name"] for row in body["criteria"]}
        assert "no other customer's data" in names
        assert "no double bookings" in names
        for row in body["criteria"]:
            assert row["question"].endswith("?")

    def test_an_agent_cannot_run_it(self, client, signed_in):
        assert (
            client.post(
                "/api/evidence/run", json={"conversations": 20}, headers=signed_in(AGENT)
            ).status_code
            == 403
        )

    def test_a_supervisor_can_and_it_reports_every_bar(self, client, signed_in):
        report = client.post(
            "/api/evidence/run",
            json={"conversations": 40},
            headers=signed_in(SUPERVISOR),
        )
        assert report.status_code == 200, report.text
        body = report.json()
        assert len(body["criteria"]) == 4
        # The two that are absolutes must hold on the generated data.
        leaks = next(c for c in body["criteria"] if c["name"] == "no other customer's data")
        clashes = next(c for c in body["criteria"] if c["name"] == "no double bookings")
        assert leaks["value"] == 0
        assert clashes["value"] == 0
