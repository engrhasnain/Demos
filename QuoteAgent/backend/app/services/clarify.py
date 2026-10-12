"""Questions to the customer: all of them, once.

The rule that makes this usable is boring and absolute: **one email per round**.
A forty line bill of materials with nine unclear lines produces one message
with nine numbered questions, not nine messages. A customer who answers six of
the nine gets one follow-up with the three that are still open.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Case, CaseMessage, Clarification, QuoteLine, QuoteVersion
from ..text import count

GREETING = {
    "en": "Dear {name},\n\nThank you for your enquiry {reference}.",
    "zh": "{name} 您好：\n\n感謝您的詢價 {reference}。",
}

PREAMBLE = {
    "en": (
        "We have priced most of the lines. Before we can finish the quotation we "
        "need to confirm {points}:"
    ),
    "zh": "多數項目已完成報價，在完成報價單前，尚有 {count} 項需要確認：",
}

CLOSING = {
    "en": (
        "\nEverything else is already priced, so one reply is enough for us to send "
        "the complete quotation.\n\nKind regards,\n{sender}\nHengtai Industrial Supply"
    ),
    "zh": "\n其餘項目皆已完成報價，您回覆後我們即可寄出完整報價單。\n\n謝謝\n{sender}\n恆泰工業供應",
}


@dataclass(slots=True)
class QuestionDraft:
    line_number: int
    kind: str
    question_en: str
    question_zh: str
    options: list[str]
    quote_line_id: int | None = None
    attribute: str = ""


# ---------------------------------------------------------------------------
# Turning an answer into a value
# ---------------------------------------------------------------------------
#: Chinese wording for the finishes Hengtai sells, so a reply written in
#: Chinese settles the line instead of only being filed against it.
_FINISH_WORDS: list[tuple[str, str]] = [
    ("熱浸鍍鋅", "hot_dip_galvanised"),
    ("熱鍍鋅", "hot_dip_galvanised"),
    ("藍白鋅", "zinc_blue"),
    ("彩鋅", "zinc_yellow"),
    ("黃鋅", "zinc_yellow"),
    ("鍍鋅", "zinc_blue"),
    ("黑色氧化", "black_oxide"),
    ("發黑", "black_oxide"),
    ("不鏽鋼", "stainless_plain"),
    ("素材", "plain"),
    ("無處理", "plain"),
]

_SEAL_WORDS: list[tuple[str, str]] = [
    ("雙面密封", "sealed_both"),
    ("兩側密封", "sealed_both"),
    ("密封", "sealed_both"),
    ("雙面防塵", "shielded_both"),
    ("防塵蓋", "shielded_both"),
    ("開放", "open"),
]

_KIND_WORDS: list[tuple[str, str]] = [
    ("內六角圓柱頭", "socket_head_cap_screw"),
    ("內六角", "socket_head_cap_screw"),
    ("六角頭", "hex_head_bolt"),
    ("螺帽", "hex_nut"),
    ("墊圈", "flat_washer"),
]


def interpret_answer(attribute: str, text: str) -> str:
    """Read a free-text answer into the value of one attribute.

    The customer answers in their own words and their own language. "長度請用
    40 mm" and "please use 40mm long" both have to settle the length, or the
    line stays flagged for ever and the agent looks broken.
    """
    if not attribute or not text:
        return ""
    lowered = text.strip().lower()

    if attribute in {"length_mm", "stroke_mm", "bore_mm"}:
        found = re.search(r"(\d{1,4})\s*(?:mm|公釐|毫米)?", lowered)
        return str(int(found.group(1))) if found else ""

    if attribute == "property_class":
        from ..domain.partnumbers import (
            NUT_PROPERTY_CLASSES,
            PROPERTY_CLASSES,
            WASHER_HARDNESS_CLASSES,
        )

        for value in sorted(
            set(PROPERTY_CLASSES + NUT_PROPERTY_CLASSES + WASHER_HARDNESS_CLASSES),
            key=len,
            reverse=True,
        ):
            if value.lower() in lowered:
                return value
        found = re.search(r"\b(0?4|0?5|6|8|10|12)\b", lowered)
        return found.group(1).lstrip("0") if found else ""

    if attribute == "finish":
        from ..domain.partnumbers import FINISH_DISPLAY, FINISH_SYNONYMS

        for code, display in FINISH_DISPLAY.items():
            if display.lower() in lowered:
                return code
        for phrase, code in sorted(FINISH_SYNONYMS.items(), key=lambda kv: -len(kv[0])):
            if phrase in lowered:
                return code
        for phrase, code in _FINISH_WORDS:
            if phrase in text:
                return code
        return ""

    if attribute == "seal":
        for phrase, code in (
            ("sealed both", "sealed_both"),
            ("shielded both", "shielded_both"),
            ("open", "open"),
            ("sealed", "sealed_both"),
            ("shielded", "shielded_both"),
        ):
            if phrase in lowered:
                return code
        for phrase, code in _SEAL_WORDS:
            if phrase in text:
                return code
        return ""

    if attribute == "kind":
        for phrase, code in (
            ("socket head cap screw", "socket_head_cap_screw"),
            ("hexagon head bolt", "hex_head_bolt"),
            ("hex bolt", "hex_head_bolt"),
            ("hexagon nut", "hex_nut"),
            ("flat washer", "flat_washer"),
        ):
            if phrase in lowered:
                return code
        for phrase, code in _KIND_WORDS:
            if phrase in text:
                return code
        return ""

    if attribute == "thread":
        found = re.search(r"\bm\s?(\d{1,2})\b", lowered)
        return f"M{int(found.group(1))}" if found else ""

    if attribute == "clearance":
        found = re.search(r"\b(c2|cn|c3|c4)\b", lowered)
        return found.group(1).upper() if found else ""

    return ""


def _translate(question: str, options: list[str]) -> str:
    """A short Chinese rendering of the standard question shapes.

    Only the question shapes this product produces are translated. Anything
    else is left in English rather than machine-translated badly, and the
    salesperson can edit before approving.
    """
    patterns = [
        (r"^What thread size", "請問需要的螺紋規格為何（例如 M8 或 M10）？"),
        (r"^What length", "請問需要的長度為何（公釐）？"),
        (r"^What strength class", "請問需要的強度等級為何（例如 8.8、10.9、12.9，或不鏽鋼 A2-70、A4-80）？"),
        (r"^What surface finish", "請問需要的表面處理為何（例如素材、鍍鋅、熱浸鍍鋅）？"),
        (r"^Should the bearing", "請問軸承需要開放式、兩側防塵蓋，還是兩側密封？"),
        (r"^What bore size", "請問需要的缸徑為何（公釐）？"),
        (r"^What stroke", "請問需要的行程為何（公釐）？"),
        (r"^Which bearing number", "請問需要的軸承型號為何？"),
        (r"^Two parts fit", "此項目有兩種規格同樣符合，請問需要哪一種？"),
        (r"^No catalogue part", "此項目目前沒有完全符合的現有料號，請確認是否可接受最接近的規格。"),
        (r"^The line gives", "此項目的規格有衝突，請確認應以哪一項為準？"),
    ]
    for pattern, translation in patterns:
        if re.match(pattern, question):
            if options:
                translation += "（" + " / ".join(options[:4]) + "）"
            return translation
    return ""


def open_questions(session: Session, case: Case) -> list[Clarification]:
    return list(
        session.scalars(
            select(Clarification)
            .where(Clarification.case_id == case.id, Clarification.status == "open")
            .order_by(Clarification.line_number, Clarification.id)
        )
    )


def next_round_number(session: Session, case: Case) -> int:
    highest = session.scalar(
        select(func.max(Clarification.round_number)).where(Clarification.case_id == case.id)
    )
    return int(highest or 0) + 1


def record_questions(
    session: Session, case: Case, drafts: list[QuestionDraft], *, round_number: int
) -> list[Clarification]:
    """Store questions without sending anything. Sending needs an approval."""
    created: list[Clarification] = []
    existing = {
        (c.line_number, c.question_kind, c.question_en)
        for c in session.scalars(select(Clarification).where(Clarification.case_id == case.id))
    }
    for draft in drafts:
        key = (draft.line_number, draft.kind, draft.question_en)
        if key in existing:
            continue
        clarification = Clarification(
            case_id=case.id,
            quote_line_id=draft.quote_line_id,
            line_number=draft.line_number,
            round_number=round_number,
            question_kind=draft.kind,
            attribute=draft.attribute,
            question_en=draft.question_en,
            question_zh=draft.question_zh or _translate(draft.question_en, draft.options),
            options=draft.options,
            status="open",
        )
        session.add(clarification)
        created.append(clarification)
        existing.add(key)
    session.flush()
    return created


def compose_email(
    case: Case, questions: list[Clarification], *, sender_name: str
) -> tuple[str, str]:
    """One message, numbered questions, in the customer's own language."""
    language = case.language if case.language in GREETING else "en"
    name = case.contact_name or "Sir or Madam"
    body_parts = [
        GREETING[language].format(name=name, reference=case.reference),
        "",
        PREAMBLE[language].format(
            count=len(questions), points=count(len(questions), 'point')
        ),
        "",
    ]

    for index, question in enumerate(questions, start=1):
        text = question.question_zh if language == "zh" and question.question_zh else question.question_en
        body_parts.append(f"{index}. (Line {question.line_number}) {text}")
        if question.options:
            body_parts.append("   " + " / ".join(str(o) for o in question.options))
        body_parts.append("")

    body_parts.append(CLOSING[language].format(sender=sender_name))
    subject = (
        f"Re: {case.subject} - {count(len(questions), 'question')} before we quote"
        if language == "en"
        else f"Re: {case.subject} - 報價前尚有 {len(questions)} 項需確認"
    )
    return subject, "\n".join(body_parts)


_ANSWER_LINE = re.compile(
    r"^\s*(?:(\d{1,2})\s*[\.\)\:：-]\s*)(.+)$", re.M
)


def apply_answers(
    session: Session, case: Case, reply_text: str, *, round_number: int | None = None
) -> dict[str, Any]:
    """Match a free-text reply back to the numbered questions it answers.

    Questions the customer did not answer stay open, which is what makes the
    follow-up ask only for what is still missing.
    """
    questions = [
        q
        for q in open_questions(session, case)
        if round_number is None or q.round_number == round_number
    ]
    if not questions:
        return {"answered": 0, "still_open": 0, "matched": [], "unmatched_text": reply_text.strip()}

    by_position = {index: question for index, question in enumerate(questions, start=1)}
    by_line: dict[int, list[Clarification]] = {}
    for question in questions:
        by_line.setdefault(question.line_number, []).append(question)

    answered: list[dict[str, Any]] = []
    used: set[int] = set()

    for match in _ANSWER_LINE.finditer(reply_text or ""):
        number = int(match.group(1))
        answer = match.group(2).strip()
        if not answer:
            continue

        # A number in a reply means either "question 3" or "line 18". Both are
        # tried, and one sentence can settle more than one question about the
        # same line: "40 mm long, hexagon head" answers the length and the type.
        candidates: list[Clarification] = []
        positional = by_position.get(number)
        if positional is not None:
            candidates.append(positional)
        candidates.extend(by_line.get(number, []))

        resolved = [
            question
            for question in candidates
            if question.id not in used
            and question.attribute
            and interpret_answer(question.attribute, answer)
        ]
        if not resolved:
            first = next((q for q in candidates if q.id not in used), None)
            resolved = [first] if first is not None else []

        for question in resolved:
            value = interpret_answer(question.attribute, answer)
            question.answer_text = answer
            question.answer_value = {
                "text": answer,
                "matched_on": "question number" if question is positional else "line number",
                "attribute": question.attribute,
                "value": value,
                "understood": bool(value) if question.attribute else None,
            }
            question.status = "answered"
            question.answered_at = dt.datetime.now(dt.timezone.utc)
            used.add(question.id)
            answered.append(
                {
                    "line_number": question.line_number,
                    "question": question.question_en,
                    "answer": answer,
                    "understood_as": value,
                }
            )

    session.flush()
    still_open = [q for q in questions if q.status == "open"]
    return {
        "answered": len(answered),
        "still_open": len(still_open),
        "matched": answered,
        "open_questions": [
            {"line_number": q.line_number, "question": q.question_en} for q in still_open
        ],
    }


def apply_answers_to_lines(session: Session, version: QuoteVersion) -> list[dict[str, Any]]:
    """Fold answered questions back into the request text of their line.

    The line is then re-read and re-matched by the agent, which is how a case
    that waited four days carries on exactly where it stopped.
    """
    changes: list[dict[str, Any]] = []
    answered = list(
        session.scalars(
            select(Clarification).where(
                Clarification.case_id == version.case_id,
                Clarification.status == "answered",
            )
        )
    )
    by_line: dict[int, list[Clarification]] = {}
    for clarification in answered:
        by_line.setdefault(clarification.line_number, []).append(clarification)

    for line in version.lines:
        items = by_line.get(line.line_number)
        if not items:
            continue

        resolved = dict(line.resolved_attributes or {})
        applied: list[dict[str, str]] = []
        not_understood: list[str] = []
        for clarification in items:
            value = (clarification.answer_value or {}).get("value") or interpret_answer(
                clarification.attribute, clarification.answer_text
            )
            if clarification.attribute and value:
                resolved[clarification.attribute] = value
                applied.append({"attribute": clarification.attribute, "value": value})
            elif clarification.answer_text:
                not_understood.append(clarification.answer_text)

        additions = [c.answer_text for c in items if c.answer_text]
        before = line.request_text
        addition = " ".join(a for a in additions if a and a not in line.request_text)
        if addition:
            line.request_text = f"{line.request_text} {addition}".strip()
        line.resolved_attributes = resolved

        if applied or addition:
            changes.append(
                {
                    "line_number": line.line_number,
                    "before": before,
                    "after": line.request_text,
                    "answers": additions,
                    "attributes_settled": applied,
                    "answers_not_understood": not_understood,
                }
            )
    session.flush()
    return changes


def consolidated_round_summary(session: Session, case: Case) -> dict[str, Any]:
    rounds: dict[int, dict[str, Any]] = {}
    for clarification in session.scalars(
        select(Clarification).where(Clarification.case_id == case.id).order_by(Clarification.id)
    ):
        entry = rounds.setdefault(
            clarification.round_number,
            {"round_number": clarification.round_number, "asked": 0, "answered": 0, "questions": []},
        )
        entry["asked"] += 1
        if clarification.status == "answered":
            entry["answered"] += 1
        entry["questions"].append(
            {
                "id": clarification.id,
                "line_number": clarification.line_number,
                "kind": clarification.question_kind,
                "question": clarification.question_en,
                "question_chinese": clarification.question_zh,
                "options": clarification.options,
                "status": clarification.status,
                "answer": clarification.answer_text,
            }
        )
    return {
        "rounds": [rounds[key] for key in sorted(rounds)],
        "emails_sent": len(rounds),
        "questions_asked": sum(entry["asked"] for entry in rounds.values()),
        "statement": (
            f"{count(sum(entry['asked'] for entry in rounds.values()), 'question')} were asked "
            f"in {count(len(rounds), 'email')}. One email per round, never one per line."
        ),
    }


def last_outbound_question_email(session: Session, case: Case) -> CaseMessage | None:
    return session.scalar(
        select(CaseMessage)
        .where(
            CaseMessage.case_id == case.id,
            CaseMessage.direction == "outbound",
            CaseMessage.kind == "clarification",
        )
        .order_by(CaseMessage.id.desc())
        .limit(1)
    )


def line_lookup(session: Session, version: QuoteVersion) -> dict[int, QuoteLine]:
    return {line.line_number: line for line in version.lines}
