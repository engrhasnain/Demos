"""Returns, and the law that does not apply here.

Taiwan's Consumer Protection Act gives seven days to change your mind on a
distance sale, no reason needed. It is the best known rule in the country
and it is the wrong rule for this business. Hengtai sells to trade
accounts, and a company buying fasteners to put into its own product is not
a consumer. A front desk that quotes the seven day right to a purchasing
manager has just promised a refund nobody owes, in writing, from a channel
the customer will screenshot.

What a trade account actually has is the contract: a warranty running from
despatch, and a shorter window for reporting transit damage and shortages.
Those are the figures used here, they come from the customer record, and
the reply says which one it is relying on.

The photograph triage suggests. It never decides. Every return in this
product is proposed by the desk and approved by a person, because the
difference between shipping damage and two years of wear is a judgement
with money attached, and because a customer arguing with a photograph
classifier is a customer nobody wants.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Order, OrderLine, ReturnRequest
from .isolation import Scope, owned_by, record

SHIPPING_DAMAGE = "shipping_damage"
WEAR = "wear"
WRONG_PART = "wrong_part"
MANUFACTURING = "manufacturing"
SHORTAGE = "shortage"
UNCLEAR = "unclear"

TRIAGE_WORDS: dict[str, str] = {
    SHIPPING_DAMAGE: "Damaged in transit",
    WEAR: "Worn in service",
    WRONG_PART: "Wrong part supplied",
    MANUFACTURING: "Manufacturing fault",
    SHORTAGE: "Short delivered",
    UNCLEAR: "Not clear from the photograph",
}

#: What each outcome means for who pays, which is the real question. These
#: are contract positions, not the consumer right.
WHO_PAYS: dict[str, str] = {
    SHIPPING_DAMAGE: "us, if reported inside the transit window",
    WEAR: "the customer, unless inside warranty and the part failed early",
    WRONG_PART: "us",
    MANUFACTURING: "us, inside warranty",
    SHORTAGE: "us, if reported inside the transit window",
    UNCLEAR: "to be decided when a person has looked",
}


@dataclass(slots=True)
class Triage:
    """What the photograph appears to show, and how sure that is."""

    kind: str
    label: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    engine: str = "built-in"

    @property
    def confident_enough(self) -> bool:
        return self.confidence >= settings.triage_confidence_floor

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "confident_enough": self.confident_enough,
            "who_usually_pays": WHO_PAYS.get(self.kind, ""),
            "reasons": self.reasons,
            "engine": self.engine,
        }


#: Words in the customer's own description, which are a better signal than
#: anything a built-in engine can get from the pixels. When an external
#: vision model is configured it adds to this rather than replacing it.
_SIGNALS: list[tuple[str, str, float]] = [
    (r"\b(crushed|crush|dented|dent|box|carton|packaging|in transit|arrived damaged)\b",
     SHIPPING_DAMAGE, 0.75),
    (r"(壓壞|外箱|包裝|運送|運輸中|到貨就)", SHIPPING_DAMAGE, 0.75),
    (r"\b(snapped|sheared|cracked|split|fractured|broke).{0,24}\b(after|during|while)\b",
     MANUFACTURING, 0.6),
    (r"\b(porosity|inclusion|burr|thread.{0,8}(stripped|malformed)|out of (round|tolerance))\b",
     MANUFACTURING, 0.8),
    (r"(瑕疵|不良品|毛邊|牙距|公差)", MANUFACTURING, 0.75),
    (r"\b(worn|wear|rust|rusted|corroded|fatigue|after \d+ (months|years))\b", WEAR, 0.7),
    (r"(磨損|生鏽|鏽蝕|使用\s*\d+\s*(個月|年))", WEAR, 0.7),
    (r"\b(wrong|incorrect|not what|different)\b.{0,20}\b(part|item|size|thread|finish|length)\b",
     WRONG_PART, 0.8),
    (r"(寄錯|送錯|規格不對|尺寸不對)", WRONG_PART, 0.8),
    (r"\b(short|missing|only \d+|fewer than|less than ordered)\b", SHORTAGE, 0.7),
    (r"(數量不足|少了|短少)", SHORTAGE, 0.7),
]


def triage(description: str, photo_name: str = "") -> Triage:
    """Suggest what happened. Deliberately unwilling to be certain.

    The built-in engine reads the description. A photograph is recorded and
    its name noted, but nothing here claims to have looked at the pixels:
    pretending to see something in an image is exactly the sort of confident
    wrongness that loses an argument with a customer.
    """
    text = description or ""
    scores: dict[str, float] = {}
    reasons: list[str] = []

    for pattern, kind, weight in _SIGNALS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        scores[kind] = max(scores.get(kind, 0.0), weight)
        reasons.append(f"the words “{match.group(0)}”")

    if not scores:
        return Triage(
            kind=UNCLEAR,
            label=TRIAGE_WORDS[UNCLEAR],
            confidence=0.0,
            reasons=["nothing in the description points one way or the other"],
        )

    best = max(scores, key=lambda key: scores[key])
    confidence = scores[best]
    # Two different stories in one description is a reason to be less sure,
    # not a reason to pick the louder one.
    if len([k for k, v in scores.items() if v >= 0.6]) > 1:
        confidence *= 0.7
        reasons.append("the description points more than one way")
    if photo_name:
        reasons.append(f"a photograph was attached ({photo_name})")

    return Triage(
        kind=best,
        label=TRIAGE_WORDS[best],
        confidence=round(min(0.95, confidence), 2),
        reasons=reasons,
    )


@dataclass(slots=True)
class Cover:
    """Whether the contract covers it, and on which clause."""

    covered: bool
    clause: str
    detail: dict[str, object] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "covered": self.covered,
            "clause": self.clause,
            "detail": self.detail,
            "note": self.note,
        }


def check_cover(
    order: Order,
    kind: str,
    *,
    is_trade_account: bool,
    warranty_months: int,
    today: dt.date,
) -> Cover:
    """Work out what this customer is actually owed."""
    despatched = order.despatched_on or order.placed_on
    delivered = order.delivered_on
    age_days = (today - despatched).days
    months = age_days / 30.44

    consumer_note = (
        "This is a trade account, so the seven day consumer right to cancel "
        "does not apply. The contract warranty does."
        if is_trade_account
        else "A consumer account, so the seven day right to cancel applies."
    )

    if kind in {SHIPPING_DAMAGE, SHORTAGE}:
        window = settings.transit_damage_days
        from_day = delivered or despatched
        days = (today - from_day).days
        inside = days <= window
        return Cover(
            covered=inside,
            clause=f"transit damage reported within {window} days of delivery",
            detail={
                "delivered_on": from_day.isoformat(),
                "days_since": days,
                "window_days": window,
            },
            note=(
                consumer_note
                if inside
                else f"Reported {days} days after delivery, and the window is {window}. "
                "A person can still decide to accept it."
            ),
        )

    if kind in {WRONG_PART}:
        return Cover(
            covered=True,
            clause="wrong part supplied",
            detail={"despatched_on": despatched.isoformat()},
            note="If we sent the wrong thing it comes back whatever the date. "
            + consumer_note,
        )

    inside = months <= warranty_months
    return Cover(
        covered=inside,
        clause=f"{warranty_months} month warranty from despatch",
        detail={
            "despatched_on": despatched.isoformat(),
            "months_since": round(months, 1),
            "warranty_months": warranty_months,
        },
        note=(
            consumer_note
            if inside
            else f"Despatched {round(months, 1)} months ago, and the warranty is "
            f"{warranty_months} months. " + consumer_note
        ),
    )


def propose(
    session: Session,
    scope: Scope,
    *,
    order: Order,
    part_code: str,
    quantity: int,
    reported: str,
    photo_name: str = "",
    is_trade_account: bool = True,
    warranty_months: int | None = None,
    today: dt.date | None = None,
) -> ReturnRequest:
    """Record a return for a person to approve. Never approves one."""
    today = today or dt.date.today()
    found = triage(reported, photo_name)
    cover = check_cover(
        order,
        found.kind,
        is_trade_account=is_trade_account,
        warranty_months=warranty_months or settings.default_warranty_months,
        today=today,
    )

    request = ReturnRequest(
        reference=_next_reference(session),
        customer_id=scope.customer_id,
        order_id=order.id,
        part_code=part_code,
        quantity=max(0, int(quantity or 0)),
        reported=reported,
        triage=found.kind,
        triage_confidence=found.confidence,
        triage_detail=found.to_dict(),
        photo_name=photo_name,
        within_warranty=cover.covered,
        warranty_detail=cover.to_dict(),
        status="proposed",
    )
    session.add(request)
    session.flush()
    record(
        session,
        tool="propose_return",
        scope=scope,
        arguments={"order": order.number, "part_code": part_code},
        rows=1,
    )
    return request


def lines_of(session: Session, scope: Scope, order: Order) -> list[OrderLine]:
    if order.customer_id != scope.customer_id:
        return []
    return list(order.lines)


def _next_reference(session: Session) -> str:
    year = dt.date.today().year
    highest = session.scalar(
        select(ReturnRequest.reference)
        .where(ReturnRequest.reference.like(f"RMA-{year}-%"))
        .order_by(ReturnRequest.reference.desc())
        .limit(1)
    )
    number = int(highest.rsplit("-", 1)[1]) + 1 if highest else 1
    return f"RMA-{year}-{number:04d}"
