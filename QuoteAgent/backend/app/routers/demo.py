"""The ten step demonstration script, as endpoints.

Each step does the real thing. There is no scripted output anywhere: step four
really does re-read a Chinese reply, step seven really does activate a different
duty table and flag every open quote, and step ten really does refuse to send
if an approval is outstanding.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    Approval,
    Case,
    Product,
    SupplierRequest,
    TariffLine,
    TariffTable,
    User,
)
from ..money import dec
from ..security import ROLE_LABELS, get_current_user, role_satisfies
from ..seed import samples as sample_module
from ..serializers import approval_out, case_summary_out, quote_version_out
from ..services import agent, approvals, casestate, clarify, documents, pricing
from . import cases as cases_router
from .tariffs import ActivateRequest, activate_table
from ..text import count

router = APIRouter(prefix="/api/demo", tags=["Demonstration script"])

SCRIPT: list[dict[str, Any]] = [
    {
        "number": 1,
        "title": "A forty line request arrives",
        "what_we_do": (
            "Send a request for quotation with a forty line spreadsheet: eight lines "
            "written to a published standard, five competitor part numbers."
        ),
        "what_you_see": (
            "The plan appears. Most lines are matched with a reason for each one. "
            "Four are unclear, two are not catalogue parts and one contradicts itself."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 2,
        "title": "The line that contradicts itself",
        "what_we_do": "Open the line that says stainless in the drawing and zinc in the text.",
        "what_you_see": (
            "The agent does not choose. It adds the question to one consolidated "
            "email, which the salesperson approves before it goes."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 3,
        "title": "A price request to a supplier",
        "what_we_do": "Send a sub request for the two parts Hengtai does not stock.",
        "what_you_see": (
            "Those lines show as waiting for a supplier. The other thirty-eight "
            "carry on and get priced."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 4,
        "title": "The customer replies in Traditional Chinese",
        "what_we_do": "Reply as the customer, answering three of the four questions.",
        "what_you_see": (
            "The same case resumes where it stopped. The one question that was not "
            "answered is asked again, on its own."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 5,
        "title": "The supplier answers",
        "what_we_do": "The supplier quotes a price with a five week lead time.",
        "what_you_see": (
            "Those lines are priced with Hengtai's own margin on top, and the lead "
            "time is shown per line."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 6,
        "title": "The trade terms change",
        "what_we_do": (
            "The customer switches from free on board Taichung to delivered duty "
            "paid Ontario, in United States dollars."
        ),
        "what_you_see": (
            "Freight, insurance, import duty and the currency are all recomputed by "
            "the engine, with the before and after side by side."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 7,
        "title": "A new duty table comes into force",
        "what_we_do": "Load and activate the next version of the duty table.",
        "what_you_see": (
            "Every open quote priced on the old table is flagged by name. This one "
            "is re-priced and the duty change is shown."
        ),
        "needs_role": "pricing_owner",
    },
    {
        "number": 8,
        "title": "The customer asks for twelve per cent off",
        "what_we_do": "Apply the discount the customer asked for.",
        "what_you_see": (
            "Lines fall below the margin floor and go to the sales manager with the "
            "price build-up behind each one."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 9,
        "title": "Revision B of the bill of materials",
        "what_we_do": "The customer sends a revised spreadsheet with changed quantities and new lines.",
        "what_you_see": (
            "Only the changed lines are re-quoted. The new version carries a change "
            "log the customer can read."
        ),
        "needs_role": "sales_engineer",
    },
    {
        "number": 10,
        "title": "Approve and send",
        "what_we_do": (
            "The customer answers the last outstanding question, the approvals are "
            "cleared and the quote is sent."
        ),
        "what_you_see": (
            "The quote document is produced and the timeline shows the whole elapsed "
            "time, every approval and what the reading cost."
        ),
        "needs_role": "sales_manager",
    },
]

DEMO_REFERENCE_KEY = "demonstration"


class StepRequest(BaseModel):
    case_id: int | None = None


def _require(user: User, role: str) -> None:
    if not role_satisfies(user.role, role):
        account = {
            "sales_engineer": "amy.chen@hengtai-industrial.example",
            "sales_manager": "david.hsu@hengtai-industrial.example",
            "director": "grace.wang@hengtai-industrial.example",
            "pricing_owner": "paul.lee@hengtai-industrial.example",
        }.get(role, "admin@hengtai-industrial.example")
        raise HTTPException(
            status_code=403,
            detail=(
                f"This step needs the {ROLE_LABELS.get(role, role)} role. Sign in as "
                f"{account}, or as admin@hengtai-industrial.example to run the whole "
                "script. This is the permission model doing its job, not a fault."
            ),
        )


def _case(session: Session, case_id: int | None) -> Case:
    if case_id is not None:
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="That case does not exist.")
        return case
    case = session.scalar(select(Case).order_by(Case.id.desc()))
    if case is None:
        raise HTTPException(
            status_code=400, detail="Run step one first; there is no case to work on."
        )
    return case


@router.get("/script")
def script(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    latest = session.scalar(select(Case).order_by(Case.id.desc()))
    return {
        "steps": SCRIPT,
        "current_case": case_summary_out(latest) if latest else None,
        "note": (
            "Every step performs the real action against the real engine. Nothing "
            "here is a recording."
        ),
    }


@router.post("/step/{number}")
def run_step(
    number: int,
    payload: StepRequest | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    payload = payload or StepRequest()
    step = next((s for s in SCRIPT if s["number"] == number), None)
    if step is None:
        raise HTTPException(status_code=404, detail="There is no such step.")
    _require(user, step["needs_role"])

    handler = {
        1: _step_one, 2: _step_two, 3: _step_three, 4: _step_four, 5: _step_five,
        6: _step_six, 7: _step_seven, 8: _step_eight, 9: _step_nine, 10: _step_ten,
    }[number]
    result = handler(session, payload.case_id, user)
    result["step"] = step
    return result


# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------
def _step_one(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    sample = next(
        (s for s in cases_router.get_samples(session) if s.key == "main_request"), None
    )
    if sample is None:
        raise HTTPException(status_code=400, detail="Load the demonstration data first.")

    case, _message, created = agent.receive_request(
        session,
        sender=sample.sender,
        subject=sample.subject,
        body=sample.body,
        external_message_id=f"{sample.external_message_id}-{session.scalar(select(Case.id).order_by(Case.id.desc())) or 0}",
        attachments=sample.attachments,
    )
    case.owner_id = user.id
    steps = agent.run_to_first_stop(session, case, sender_name=user.full_name)
    version = agent.require_version(session, case)

    counts: dict[str, int] = {}
    for line in version.lines:
        counts[line.status] = counts.get(line.status, 0) + 1

    return {
        "case_id": case.id,
        "created": created,
        "summary": (
            f"{len(version.lines)} lines read. "
            f"{counts.get('priced', 0) + counts.get('matched', 0)} matched, "
            f"{counts.get('needs_clarification', 0)} need a question, "
            f"{counts.get('awaiting_supplier', 0) + counts.get('non_catalogue', 0)} "
            "are not catalogue parts."
        ),
        "line_counts": counts,
        "expected_from_the_sample": sample.expected,
        "agent_steps": [{"step": s.step, "summary": s.summary} for s in steps],
        "version": quote_version_out(version),
        "case": case_summary_out(case),
    }


def _step_two(session: Session, case_id: int | None, _user: User) -> dict[str, Any]:
    case = _case(session, case_id)
    questions = clarify.open_questions(session, case)
    conflicting = [q for q in questions if q.question_kind == "conflicting_specification"]
    draft = next(
        (
            m
            for m in sorted(case.messages, key=lambda m: m.id, reverse=True)
            if m.kind == "clarification" and m.sent_at is None
        ),
        None,
    )
    version = agent.require_version(session, case)
    line = next(
        (
            l
            for l in version.lines
            if conflicting and l.line_number == conflicting[0].line_number
        ),
        None,
    )
    return {
        "case_id": case.id,
        "summary": (
            f"{count(len(questions), 'question')} are open and all of them are in one email, "
            "not one email each."
        ),
        "conflicting_line": (
            {
                "line_number": line.line_number,
                "request_text": line.request_text,
                "conflicts": (line.attribute_check or {}).get("requested", {}),
                "blocking_reason": line.blocking_reason,
                "agent_did_not_choose": True,
            }
            if line
            else None
        ),
        "questions": [
            {
                "line_number": q.line_number,
                "kind": q.question_kind,
                "question": q.question_en,
                "options": q.options,
            }
            for q in questions
        ],
        "draft_email": (
            {"id": draft.id, "subject": draft.subject, "body": draft.body}
            if draft
            else None
        ),
        "awaiting_approval": draft is not None and draft.sent_at is None,
    }


def _step_three(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)
    requests = list(
        session.scalars(select(SupplierRequest).where(SupplierRequest.case_id == case.id))
    )
    if not requests:
        agent.request_supplier_prices(session, case)
        requests = list(
            session.scalars(select(SupplierRequest).where(SupplierRequest.case_id == case.id))
        )

    draft = next(
        (m for m in case.messages if m.kind == "clarification" and m.sent_at is None), None
    )
    if draft is not None:
        agent.send_message(session, case, draft, user)

    version = agent.require_version(session, case)
    waiting = [l.line_number for l in version.lines if l.status == "awaiting_supplier"]
    carrying_on = [l.line_number for l in version.lines if l.status in {"matched", "priced"}]
    return {
        "case_id": case.id,
        "summary": (
            f"{count(len(waiting), 'line')} are waiting for a supplier. "
            f"{count(len(carrying_on), 'line')} carry on and are priced."
        ),
        "supplier_requests": [
            {
                "reference": r.reference,
                "supplier": r.supplier.name,
                "lines": r.line_numbers,
                "status": r.status,
            }
            for r in requests
        ],
        "waiting_lines": waiting,
        "lines_still_moving": len(carrying_on),
        "question_email_sent": draft is not None,
        "case": case_summary_out(case),
    }


#: How each answer is phrased, in both languages.
_ANSWER_PHRASES: dict[str, tuple[str, str]] = {
    "length_mm": ("Please use {value} mm long.", "長度請用 {value} mm。"),
    "property_class": ("Please use class {value}.", "強度等級請用 {value}。"),
    "finish": ("Please use {value}.", "表面處理請用{value}。"),
    "kind": ("Please use a {value}.", "請用{value}。"),
    "seal": ("Please use {value}.", "請用{value}。"),
    "thread": ("Please use {value}.", "螺紋請用 {value}。"),
    "clearance": ("Please use {value} clearance.", "內隙請用 {value}。"),
}

_CHINESE_VALUES: dict[str, str] = {
    "zinc_blue": "鍍鋅（藍白鋅）",
    "zinc_yellow": "鍍鋅（彩鋅）",
    "hot_dip_galvanised": "熱浸鍍鋅",
    "black_oxide": "發黑",
    "plain": "素材",
    "stainless_plain": "不鏽鋼，不需鍍鋅",
    "socket_head_cap_screw": "內六角圓柱頭螺絲",
    "hex_head_bolt": "六角頭螺栓",
    "hex_nut": "螺帽",
    "flat_washer": "墊圈",
    "sealed_both": "雙面密封",
    "shielded_both": "雙面防塵蓋",
    "open": "開放型",
}

_ENGLISH_VALUES: dict[str, str] = {
    "zinc_blue": "zinc plated, blue passivated",
    "zinc_yellow": "zinc plated, yellow passivated",
    "hot_dip_galvanised": "hot dip galvanised",
    "black_oxide": "black oxide",
    "plain": "plain",
    "stainless_plain": "stainless, untreated",
    "socket_head_cap_screw": "socket head cap screw",
    "hex_head_bolt": "hexagon head bolt",
    "hex_nut": "hexagon nut",
    "flat_washer": "flat washer",
    "sealed_both": "sealed both sides",
    "shielded_both": "shielded both sides",
    "open": "open, no seal",
}


def _answer_for(session: Session, case: Case, question: Any) -> str:
    """Work out an answer the customer could plausibly give.

    The value is read off a real catalogue part that already fits the rest of
    the line, so the answer settles the line onto something Hengtai can
    actually sell rather than onto a specification that does not exist.
    """
    version = agent.require_version(session, case)
    line = next((l for l in version.lines if l.line_number == question.line_number), None)
    value = ""
    if line is not None and question.attribute:
        for alternative in line.alternatives or []:
            candidate = session.scalar(
                select(Product).where(Product.sku == alternative.get("sku", ""))
            )
            if candidate is not None and candidate.attributes.get(question.attribute):
                value = str(candidate.attributes[question.attribute])
                break
    if not value and question.options:
        value = str(question.options[0])
    if not value:
        value = "the nearest equivalent you hold"
    return value


def settle_open_questions(
    session: Session, case: Case, *, language: str, limit: int | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Compose a reply that answers the questions actually asked."""
    questions = clarify.open_questions(session, case)
    if limit is not None:
        questions = questions[:limit]
    if not questions:
        return "", []

    lines: list[str] = []
    closed: list[dict[str, Any]] = []
    for question in questions:
        raw = _answer_for(session, case, question)
        phrases = _ANSWER_PHRASES.get(question.attribute)
        if language == "zh":
            shown = _CHINESE_VALUES.get(raw, raw)
            sentence = (
                phrases[1].format(value=shown) if phrases else f"請用 {shown}。"
            )
        else:
            shown = _ENGLISH_VALUES.get(raw, raw)
            sentence = phrases[0].format(value=shown) if phrases else f"Please use {shown}."
        lines.append(f"{question.line_number}. {sentence}")
        closed.append(
            {
                "line_number": question.line_number,
                "attribute": question.attribute,
                "question": question.question_en,
                "answer": sentence,
            }
        )

    if language == "zh":
        body = (
            "您好：\n\n謝謝您的確認，以下依項次回覆：\n\n"
            + "\n".join(lines)
            + "\n\n其餘項目我再跟工程確認後回覆。\n\n謝謝\nRosa Mendez\nPacific Motion Controls\n"
        )
    else:
        body = (
            "Hi,\n\nAnswers below, by line number.\n\n"
            + "\n".join(lines)
            + "\n\nThanks,\nRosa Mendez\nPacific Motion Controls\n"
        )
    return body, closed


def _step_four(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)

    # The customer answers three of the four questions, in Traditional
    # Chinese, by line number. The reply is written against the questions the
    # agent actually asked, not against a fixed script.
    body, closed = settle_open_questions(session, case, language="zh", limit=3)
    if not body:
        raise HTTPException(
            status_code=400,
            detail="There are no open questions to answer. Run step one first.",
        )

    result = cases_router.customer_reply(
        case.id,
        cases_router.CustomerReply(
            body=body,
            external_message_id=f"{case.reference}-zh-reply",
            reprice=True,
        ),
        session,
        user,
    )
    result["reply_sent_by_the_customer"] = body
    result["questions_answered"] = closed
    return {
        "case_id": case.id,
        "summary": (
            f"{count(result['answers']['answered'], 'question')} answered in Traditional "
            f"Chinese, {result['answers']['still_open']} still open and asked again."
        ),
        **result,
    }


def _step_five(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)
    request = session.scalar(
        select(SupplierRequest).where(
            SupplierRequest.case_id == case.id, SupplierRequest.status == "sent"
        )
    )
    if request is None:
        raise HTTPException(
            status_code=400, detail="There is no open supplier request. Run step three first."
        )
    reply = sample_module.supplier_reply(request.line_numbers or [])
    result = cases_router.supplier_reply(
        case.id,
        request.id,
        cases_router.SupplierReply(
            unit_price=reply["unit_price"],
            currency=reply["currency"],
            lead_time_days=reply["lead_time_days"],
            minimum_order_quantity=reply["minimum_order_quantity"],
            note=reply["note"],
        ),
        session,
        user,
    )
    return {
        "case_id": case.id,
        "summary": (
            f"{request.supplier.name} quoted {reply['unit_price']} {reply['currency']} "
            f"with a {reply['lead_time_days']} day lead time. "
            f"{count(len(result['applied']), 'line')} priced with margin on top."
        ),
        **result,
    }


def _step_six(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)
    result = cases_router.change_terms(
        case.id,
        cases_router.TermsChange(
            incoterm="DDP",
            named_place="Ontario, California",
            currency="USD",
            destination_country="US",
        ),
        session,
        user,
    )
    return {"case_id": case.id, "summary": "Trade terms changed and re-priced.", **result}


def _next_duty_table(session: Session) -> TariffTable:
    """The duty table to bring into force next.

    Normally that is the revision the pricing owner has already loaded and
    left as a draft. If there is none, one is loaded now by taking the table
    in force and raising the Section 232 metals duty, which is what the step
    says it does and what actually happened in April 2026. Doing it this way
    means the step can be run again on the same database.
    """
    today = dt.date.today()
    draft = session.scalar(
        select(TariffTable)
        .where(TariffTable.status == "draft", TariffTable.effective_from <= today)
        .order_by(TariffTable.effective_from.desc())
        .limit(1)
    )
    if draft is not None:
        return draft

    current = session.scalar(
        select(TariffTable)
        .where(TariffTable.status == "active")
        .order_by(TariffTable.effective_from.desc())
        .limit(1)
    )
    if current is None:
        raise HTTPException(
            status_code=400,
            detail="There is no duty table in force to base a revision on.",
        )

    existing = len(list(session.scalars(select(TariffTable))))
    draft = TariffTable(
        version=f"{today.strftime('%Y.%m')}-revision-{existing + 1}",
        title="Revision raising the Section 232 metals duty, awaiting broker sign-off",
        effective_from=today,
        status="draft",
        owned_by="Paul Lee, pricing owner",
        source_note=(
            f"Loaded from {current.version} with the Section 232 metals duty on "
            "derivative steel articles raised by 25 percentage points of the full "
            "customs value."
        ),
    )
    session.add(draft)
    session.flush()

    for row in current.lines:
        rate = dec(row.rate_percent)
        if row.component == "section_232":
            rate = rate + Decimal("25")
        session.add(
            TariffLine(
                tariff_table_id=draft.id,
                harmonised_tariff_code=row.harmonised_tariff_code,
                origin_country=row.origin_country,
                destination_country=row.destination_country,
                component=row.component,
                rate_percent=rate,
                basis=row.basis,
                excluded_by=row.excluded_by,
                combined_cap_percent=row.combined_cap_percent,
                authority=row.authority,
                note=row.note,
            )
        )
    session.flush()
    session.refresh(draft)
    return draft


def _step_seven(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)
    draft = _next_duty_table(session)
    before = agent.require_version(session, case)
    duty_before = str(before.duty_total)

    result = activate_table(
        draft.id,
        ActivateRequest(
            confirm_broker_sign_off=True,
            customs_broker="Chen and Partners Customs Brokers, licence 04218",
        ),
        session,
        user,
    )
    step = agent.price_case(session, case)
    after = agent.require_version(session, case)

    return {
        "case_id": case.id,
        "summary": (
            f"Duty table {draft.version} is now in force. "
            f"{count(len(result['quotes_flagged_for_repricing']), 'open quote')} were flagged. "
            f"Import duty on this quote moved from {duty_before} to {after.duty_total} "
            f"{after.currency}."
        ),
        "duty_before": duty_before,
        "duty_after": str(after.duty_total),
        "currency": after.currency,
        "activated": result["activated"],
        "quotes_flagged": result["quotes_flagged_for_repricing"],
        "repriced": step.detail,
        "duty_breakdown": [
            {
                "line_number": line.line_number,
                "part": line.product.sku if line.product else "",
                "breakdown": line.duty_breakdown,
            }
            for line in after.lines
            if line.duty_breakdown
        ][:5],
    }


def _step_eight(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)
    result = cases_router.request_discount(
        case.id, cases_router.DiscountRequest(discount_percent=12), session, user
    )
    return {
        "case_id": case.id,
        "summary": (
            f"Twelve per cent off takes the total from {result['total_before']} to "
            f"{result['total_after']}. {count(result['lines_below_floor'], 'line')} fall "
            "below the margin floor and need a sales manager."
        ),
        **result,
    }


def _step_nine(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)
    result = cases_router.create_revision(
        case.id, cases_router.RevisionRequest(sample_key="revision_b"), session, user
    )
    # The revision result carries its own "summary" object, so the one line of
    # wording for the screen is kept under its own name.
    change_summary = result.pop("summary")
    return {
        "case_id": case.id,
        "summary": change_summary["statement"],
        "change_summary": change_summary,
        **result,
    }


def _step_ten(session: Session, case_id: int | None, user: User) -> dict[str, Any]:
    case = _case(session, case_id)

    # The customer comes back with the last answer. Written as a real inbound
    # reply so it goes through the same reading, matching and pricing path as
    # every other message, rather than being switched on behind the scenes.
    body, closed_questions = settle_open_questions(session, case, language="en")
    if body:
        cases_router.customer_reply(
            case.id,
            cases_router.CustomerReply(
                body=body,
                external_message_id=f"{case.reference}-final-answers",
                reprice=True,
            ),
            session,
            user,
        )
        case = _case(session, case.id)

    version = agent.require_version(session, case)

    decided: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for approval in approvals.outstanding(session, case):
        allowed, why_not = approvals.can_decide(user, approval)
        if not allowed:
            refused.append({"approval": approval_out(approval), "why_not": why_not})
            continue
        approvals.decide(
            session, approval, user, approved=True,
            comment="Approved during the demonstration walkthrough.",
        )
        decided.append(approval_out(approval))

    if refused:
        return {
            "case_id": case.id,
            "sent": False,
            "summary": (
                "The quote was not sent, because an approval is outstanding that this "
                "account cannot give. That is the control working."
            ),
            "questions_closed": closed_questions,
            "approved_now": decided,
            "still_outstanding": refused,
            "blocking_reasons": approvals.blocking_reasons(session, version),
        }

    if case.status == casestate.AWAITING_APPROVAL:
        case.status = casestate.PRICED
        version.status = "approved"

    blocking = approvals.blocking_reasons(session, version)
    if blocking:
        return {
            "case_id": case.id,
            "sent": False,
            "summary": "The quote cannot be sent yet.",
            "questions_closed": closed_questions,
        "approved_now": decided,
            "blocking_reasons": blocking,
        }

    try:
        step = agent.send_quote(session, case, user)
    except agent.PricingRefused as exc:
        raise HTTPException(status_code=409, detail=exc.report.to_dict()) from exc

    version = agent.require_version(session, case)
    path, document_format = documents.write_quote_document(case, version)
    version.document_path, version.document_format = path, document_format
    export_path, export_format = documents.write_line_export(case, version)
    session.flush()

    return {
        "case_id": case.id,
        "sent": True,
        "summary": (
            f"Quote version {version.version_number} sent for {version.grand_total} "
            f"{version.currency}."
        ),
        "questions_closed": closed_questions,
        "approved_now": decided,
        "document_format": document_format,
        "line_export_format": export_format,
        "pricing_integrity": step.detail["pricing_integrity"],
        "elapsed": agent.elapsed_summary(case),
        "case": case_summary_out(case),
    }
