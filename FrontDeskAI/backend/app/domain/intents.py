"""What the visitor came for.

A small, closed list. Closed matters: an intent the product has no tool for
is an intent it should hand to a person, not improvise around. "I'll look
into that for you" from something that cannot look into anything is worse
than "let me get somebody".

Matching is done on the words, by code. Every rule here is a phrase a real
customer used, in English or Chinese, and the reason this is a list rather
than a model is that a buyer can read it, disagree with a line, and have it
changed in a minute.

When an external model is configured it chooses from this same list and
nothing else. It never invents an intent and it never runs a tool: it
returns a name from this file, the code checks the name is in this file,
and the code runs the tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ORDER_STATUS = "order_status"
RETURN_REQUEST = "return_request"
QUOTE_STATUS = "quote_status"
BOOK_VISIT = "book_visit"
OPENING_HOURS = "opening_hours"
HUMAN = "human"
GREETING = "greeting"
UNKNOWN = "unknown"

LABELS: dict[str, str] = {
    ORDER_STATUS: "Where is my order",
    RETURN_REQUEST: "Return or fault",
    QUOTE_STATUS: "Quote",
    BOOK_VISIT: "Technician visit",
    OPENING_HOURS: "Hours and contact",
    HUMAN: "Asked for a person",
    GREETING: "Hello",
    UNKNOWN: "Not understood",
}

#: Whether the desk can finish this on its own, or only start it.
CAN_RESOLVE: dict[str, bool] = {
    ORDER_STATUS: True,
    QUOTE_STATUS: True,
    OPENING_HOURS: True,
    BOOK_VISIT: True,
    GREETING: True,
    #: A return is proposed by the desk and approved by a person. Always.
    RETURN_REQUEST: False,
    HUMAN: False,
    UNKNOWN: False,
}


@dataclass(slots=True)
class Rule:
    intent: str
    patterns: list[str]
    weight: float = 1.0
    compiled: list[re.Pattern] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def score(self, text: str) -> float:
        return sum(self.weight for p in self.compiled if p.search(text))


#: Asking for a person is checked before anything else and always wins.
#: A customer who has said "agent" three times does not want another answer.
RULES: list[Rule] = [
    Rule(
        HUMAN,
        [
            r"\b(human|person|agent|someone|somebody|real)\b.{0,16}\b(please|talk|speak|chat)?",
            r"\b(speak|talk|chat)\b.{0,20}\b(to|with)\b.{0,16}\b(human|person|agent|someone)\b",
            r"\b(representative|operator|manager|supervisor)\b",
            r"\bthis (is )?(not )?help(ing|ful)?\b",
            r"\b(useless|rubbish|nonsense)\b",
            r"(真人|專人|人工|客服人員|轉接)",
        ],
        weight=3.0,
    ),
    Rule(
        ORDER_STATUS,
        [
            r"\bwhere.{0,12}\b(is|are)\b.{0,12}\b(my )?(order|shipment|parcel|goods|delivery)\b",
            r"\border\b.{0,20}\b(status|update|arrive|arriving|shipped|despatch|dispatch)\b",
            r"\b(track|tracking|traced)\b",
            r"\bhas.{0,12}\b(it|my order)\b.{0,12}\bshipped\b",
            r"\b(when|how long).{0,24}\b(arrive|delivered|get here|come)\b",
            r"(訂單|出貨|到貨|物流|寄出|送到|查詢訂單)",
        ],
    ),
    # An order number on its own is weak evidence of why somebody wrote.
    # It turns up in nearly every message, including the ones about a
    # broken part, and at full weight it turns every return into a status
    # enquiry. It is context, not intent.
    Rule(ORDER_STATUS, [r"\bSO[- ]?\d{4,}\b"], weight=0.3),
    Rule(
        RETURN_REQUEST,
        [
            r"\b(return|refund|rma|send.{0,8}back|exchange|replace)\b",
            r"\b(broken|damaged|faulty|defect|cracked|bent|snapped|rusty|rusted)\b",
            r"\b(wrong|incorrect)\b.{0,16}\b(part|item|product|size|thread)\b",
            r"\b(does ?n.t|doesn't|won't|wont)\b.{0,12}\b(fit|work)\b",
            r"\bshort\b.{0,12}\b(ship|delivered|quantity)\b",
            r"(退貨|退款|換貨|瑕疵|損壞|壞掉|破損|不良品|寄錯)",
        ],
    ),
    Rule(
        QUOTE_STATUS,
        [
            r"\b(quote|quotation|rfq|pricing|price list)\b",
            r"\bRQ[- ]?\d{4,}\b",
            r"\bhow much\b.{0,24}\b(would|will|does)\b",
            r"(報價|詢價|價格|報價單)",
        ],
    ),
    Rule(
        BOOK_VISIT,
        [
            r"\b(technician|engineer|service call|site visit|callout|call out)\b",
            r"\b(book|schedule|arrange|send)\b.{0,24}\b(visit|technician|engineer|someone out)\b",
            r"\b(on ?site|on-site)\b",
            r"(技師|工程師|到府|現場|維修|預約)",
        ],
    ),
    # "Come and look" / "come out" is said almost exclusively about a
    # technician visit, including by a customer who also happens to say
    # "someone" in the same breath ("can someone come and look at it?").
    # Weighted above the generic human-request rule so that case still
    # means what it obviously means, rather than being read as a request
    # to escalate.
    Rule(
        BOOK_VISIT,
        [r"\bcome (out|and look|to (our|the) (site|factory|plant))\b"],
        weight=3.5,
    ),
    Rule(
        OPENING_HOURS,
        [
            r"\b(opening|office|business)\b.{0,8}\bhours?\b",
            r"\bwhat time\b.{0,20}\b(open|close|closed)\b",
            r"\b(are you|you)\b.{0,8}\b(open|closed)\b",
            r"\b(phone number|telephone|address|where are you)\b",
            r"(營業時間|幾點|電話|地址)",
        ],
    ),
    Rule(
        GREETING,
        [
            r"^\s*(hi|hello|hey|good (morning|afternoon|evening))\b",
            r"^\s*(你好|您好|哈囉|嗨)",
        ],
        weight=0.5,
    ),
]


@dataclass(slots=True)
class Read:
    intent: str
    confidence: float
    label: str
    can_resolve: bool
    matched: list[str] = field(default_factory=list)
    engine: str = "built-in"

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "can_resolve": self.can_resolve,
            "matched": self.matched,
            "engine": self.engine,
        }


def read(text: str) -> Read:
    """Pick one intent from the list above. Never invents one."""
    message = (text or "").strip()
    if not message:
        return Read(UNKNOWN, 0.0, LABELS[UNKNOWN], False)

    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    for rule in RULES:
        score = rule.score(message)
        if score <= 0:
            continue
        scores[rule.intent] = scores.get(rule.intent, 0.0) + score
        matched.setdefault(rule.intent, []).append(rule.intent)

    if not scores:
        return Read(UNKNOWN, 0.0, LABELS[UNKNOWN], False)

    best = max(scores, key=lambda key: scores[key])
    total = sum(scores.values())
    confidence = scores[best] / total if total else 0.0

    # A greeting alongside anything else is not the reason they wrote.
    if best == GREETING and len(scores) > 1:
        scores.pop(GREETING)
        best = max(scores, key=lambda key: scores[key])
        total = sum(scores.values())
        confidence = scores[best] / total if total else 0.0

    return Read(
        intent=best,
        confidence=confidence,
        label=LABELS[best],
        can_resolve=CAN_RESOLVE.get(best, False),
        matched=matched.get(best, []),
    )


def is_known(intent: str) -> bool:
    """Used to check whatever an external model returned."""
    return intent in LABELS
