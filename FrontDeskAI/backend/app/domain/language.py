"""Which language to answer in, and what must survive translation.

Taiwan customers write in Chinese, in English, and in both in the same
sentence. Replying in the wrong one is rude; replying in the right one and
mangling a part number is worse, because `HT-SHC-M8X030-12.9-ZNB` and
`HT-SHC-M8X030-12.9-ZNC` are different parts and a customer reading the
second one orders the wrong thing.

So part numbers, order numbers, tracking numbers and quantities are lifted
out before anything is composed and put back afterwards, byte for byte.
Nothing between here and the screen is allowed to touch them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ENGLISH = "en"
CHINESE = "zh"

#: Anything shaped like an identifier. Deliberately greedy about hyphens
#: and dots, because that is what part numbers are made of.
IDENTIFIER = re.compile(
    r"\b("
    r"HT-[A-Z0-9][A-Z0-9.\-]{3,}"          # a part number
    r"|SO-?\d{4,}"                          # an order
    r"|RQ-?\d{4,}"                          # a quotation
    r"|RMA-?\d{3,}"                         # a return
    r"|VIS-?\d{3,}"                         # a visit
    r"|[A-Z]{2,4}\d{8,}"                    # a tracking number
    r")\b"
)

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def detect(text: str) -> str:
    """Chinese if there is any Chinese in it.

    Not a proportion: a customer writing "請問 SO-10422 到哪了" is writing
    Chinese with an order number in it, and the reply should be Chinese.
    """
    return CHINESE if _CJK.search(text or "") else ENGLISH


@dataclass(slots=True)
class Protected:
    """Text with its identifiers taken out, and the means to put them back."""

    masked: str
    identifiers: list[str] = field(default_factory=list)

    def restore(self, text: str) -> str:
        out = text
        for index, value in enumerate(self.identifiers):
            out = out.replace(f"‹{index}›", value)
        return out


def protect(text: str) -> Protected:
    """Lift every identifier out of a message before anything rewrites it."""
    identifiers: list[str] = []

    def take(match: re.Match) -> str:
        identifiers.append(match.group(0))
        return f"‹{len(identifiers) - 1}›"

    return Protected(masked=IDENTIFIER.sub(take, text or ""), identifiers=identifiers)


def identifiers_in(text: str) -> list[str]:
    return [match.group(0) for match in IDENTIFIER.finditer(text or "")]


def survived(original: str, reply: str) -> list[str]:
    """Which identifiers from the original are missing from the reply.

    Used as a check, not as a repair. A reply that dropped a part number is
    a reply that should not be sent.
    """
    wanted = identifiers_in(original)
    return [value for value in wanted if value not in reply]


# ---------------------------------------------------------------------------
# The words
# ---------------------------------------------------------------------------
#: Every sentence the desk can say, in both languages. A closed list, for
#: the same reason the intents are a closed list: somebody has to be able
#: to read everything this thing is capable of saying.
PHRASES: dict[str, dict[str, str]] = {
    "greeting": {
        ENGLISH: "Hello. I can look up an order, a quotation, a return or a technician visit.",
        CHINESE: "您好。我可以查詢訂單、報價、退貨或預約技師。",
    },
    "ask_to_verify": {
        ENGLISH: "To look that up I need your order number and the email address it was placed with.",
        CHINESE: "為了查詢，請提供您的訂單號碼與下單時使用的電子郵件。",
    },
    "verified": {
        ENGLISH: "Thank you.",
        CHINESE: "謝謝您。",
    },
    "handing_over": {
        ENGLISH: "I am passing this to a person now.",
        CHINESE: "我現在轉給專人處理。",
    },
    "not_understood": {
        ENGLISH: "I am not sure I can help with that one, so I am passing it to a person.",
        CHINESE: "這個問題我可能無法處理，我轉給專人。",
    },
    "person_available": {
        ENGLISH: "A person is one tap away at any point.",
        CHINESE: "您隨時可以轉接專人。",
    },
    "return_proposed": {
        ENGLISH: "I have put a return request in for you. A person approves every one of these.",
        CHINESE: "已為您建立退貨申請，所有退貨都需要專人核准。",
    },
    "visit_booked": {
        ENGLISH: "That is booked.",
        CHINESE: "已為您預約。",
    },
    "slot_taken": {
        ENGLISH: "Somebody took that slot a moment before you. Here is the next one.",
        CHINESE: "該時段剛被預約，以下是下一個可用時段。",
    },
}


def say(key: str, language: str) -> str:
    return PHRASES.get(key, {}).get(language) or PHRASES.get(key, {}).get(ENGLISH, "")
