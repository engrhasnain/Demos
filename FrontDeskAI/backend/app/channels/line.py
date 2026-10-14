"""The LINE channel.

LINE reaches about ninety-four per cent of Taiwan and is where customers
already send photographs of broken parts, so a front desk that is not on it
is a front desk half the customers will not use.

Two things here are real rather than sketched, because they are the two
that go wrong:

**The signature.** LINE signs every webhook with the channel secret. A
webhook endpoint that does not check it is an open endpoint that anybody
can post invented customer messages to, and it will cheerfully reply to a
LINE user id the attacker chose. The check is a constant-time comparison
of a base64 HMAC, and a request that fails it gets 400 and nothing else.

**The reply token.** It is single use and expires in five minutes. Code
that treats it as a general-purpose address silently stops working the
first time anything is slow. It is used once, immediately, and anything
later has to go out as a push.

The transport is left as an outbound function so the demonstration can run
with no account, and so the tests can see exactly what would have been
sent.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import settings


def signature_for(body: bytes, secret: str) -> str:
    """What LINE would have put in the X-Line-Signature header."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def verify(body: bytes, header: str, secret: str | None = None) -> bool:
    """Constant time, because a timing side channel on a signature is a real one."""
    secret = secret if secret is not None else settings.line_channel_secret
    if not secret or not header:
        return False
    return hmac.compare_digest(signature_for(body, secret), header)


@dataclass(slots=True)
class Incoming:
    """One message, lifted out of the webhook envelope."""

    line_user_id: str
    text: str
    reply_token: str
    message_type: str = "text"
    attachment_id: str = ""

    @property
    def is_photo(self) -> bool:
        return self.message_type == "image"


def unpack(payload: dict[str, Any]) -> list[Incoming]:
    """Pull the messages out, ignoring the events we have no use for.

    Follows, unfollows, joins and beacons all arrive here. Replying to them
    is how an account gets reported.
    """
    out: list[Incoming] = []
    for event in payload.get("events") or []:
        if event.get("type") != "message":
            continue
        source = event.get("source") or {}
        message = event.get("message") or {}
        kind = message.get("type", "")
        if kind not in {"text", "image"}:
            continue
        out.append(
            Incoming(
                line_user_id=str(source.get("userId") or ""),
                text=str(message.get("text") or ""),
                reply_token=str(event.get("replyToken") or ""),
                message_type=kind,
                attachment_id=str(message.get("id") or "") if kind == "image" else "",
            )
        )
    return out


#: At most five message objects in one reply, which LINE enforces.
MAX_MESSAGES = 5
#: And a hard limit on each one.
MAX_CHARACTERS = 5000


@dataclass(slots=True)
class Outgoing:
    reply_token: str
    messages: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {"replyToken": self.reply_token, "messages": self.messages[:MAX_MESSAGES]}


def compose(reply_token: str, text: str, actions: list[dict[str, str]]) -> Outgoing:
    """Turn a desk reply into what LINE expects.

    The actions become quick replies, which is how "talk to a person" stays
    one tap away in a channel that has no buttons of its own.
    """
    out = Outgoing(reply_token=reply_token)
    out.messages.append(
        {
            "type": "text",
            "text": text[:MAX_CHARACTERS],
            "quickReply": {
                "items": [
                    {
                        "type": "action",
                        "action": {
                            "type": "message",
                            "label": action["label"][:20],
                            "text": action["label"],
                        },
                    }
                    for action in actions[:13]  # LINE allows thirteen
                ]
            }
            if actions
            else None,
        }
    )
    # LINE rejects a null quickReply rather than ignoring it.
    for message in out.messages:
        if message.get("quickReply") is None:
            message.pop("quickReply", None)
    return out


#: Swapped out in tests and in the demonstration, so nothing leaves the
#: machine unless somebody has configured an account on purpose.
Sender = Callable[[Outgoing], dict[str, Any]]


def no_network(outgoing: Outgoing) -> dict[str, Any]:
    """The default: record what would have been sent, and send nothing."""
    return {"sent": False, "reason": "no LINE account configured", "payload": outgoing.to_payload()}


def over_https(outgoing: Outgoing) -> dict[str, Any]:  # pragma: no cover - needs an account
    """The real one, used when a channel token is set."""
    if not settings.line_channel_access_token.strip():
        return no_network(outgoing)
    import httpx

    response = httpx.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            "Authorization": f"Bearer {settings.line_channel_access_token}",
            "Content-Type": "application/json",
        },
        content=json.dumps(outgoing.to_payload()),
        timeout=10.0,
    )
    return {"sent": response.is_success, "status": response.status_code}


def sender() -> Sender:
    return over_https if settings.line_channel_access_token.strip() else no_network
