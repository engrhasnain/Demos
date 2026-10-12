"""Everything that happens to a request for quotation."""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.incoterms import UnknownIncoterm, compare as compare_incoterms, get_incoterm
from ..money import dec
from ..models import (
    Approval,
    Case,
    CaseMessage,
    Clarification,
    QuoteVersion,
    SupplierRequest,
    User,
)
from ..security import get_current_user, require_role
from ..seed import samples as sample_module
from ..serializers import (
    approval_out,
    case_summary_out,
    clarification_out,
    event_out,
    message_out,
    quote_version_out,
    supplier_request_out,
)
from ..services import agent, approvals, casestate, clarify, documents, pricing, revisions, supplier
from ..services.audit import record_change, record_event
from ..services.intake import ExtractedRow, read_attachment
from ..text import count

router = APIRouter(prefix="/api/cases", tags=["Requests for quotation"])

_SAMPLE_CACHE: dict[str, list[sample_module.SampleRequest]] = {}


def get_samples(session: Session) -> list[sample_module.SampleRequest]:
    if "all" not in _SAMPLE_CACHE:
        _SAMPLE_CACHE["all"] = sample_module.build_samples(session)
    return _SAMPLE_CACHE["all"]


def clear_sample_cache() -> None:
    _SAMPLE_CACHE.clear()


def _case_or_404(session: Session, case_id: int) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="That request for quotation does not exist.")
    return case


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, casestate.IllegalTransition):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, agent.PricingRefused):
        return HTTPException(status_code=409, detail=exc.report.to_dict())
    if isinstance(exc, (agent.AgentError, pricing.PricingError, UnknownIncoterm, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Samples and intake
# ---------------------------------------------------------------------------
@router.get("/samples", tags=["Requests for quotation"])
def list_samples(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return [
        {
            "key": sample.key,
            "title": sample.title,
            "description": sample.description,
            "sender": sample.sender,
            "subject": sample.subject,
            "attachments": [name for name, _, _ in sample.attachments],
            "expected": sample.expected,
        }
        for sample in get_samples(session)
    ]


class SampleIntake(BaseModel):
    sample_key: str = "main_request"


@router.post("/from-sample")
def create_from_sample(
    payload: SampleIntake,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    sample = next((s for s in get_samples(session) if s.key == payload.sample_key), None)
    if sample is None:
        raise HTTPException(status_code=404, detail="No sample request with that name.")

    case, _message, created = agent.receive_request(
        session,
        sender=sample.sender,
        subject=sample.subject,
        body=sample.body,
        external_message_id=sample.external_message_id,
        attachments=sample.attachments,
    )
    if created:
        case.owner_id = user.id
        record_change(
            session, user=user, action="create", entity="case", entity_id=case.id,
            after={"reference": case.reference, "from_sample": sample.key},
        )
    session.flush()
    return {"created": created, "case": case_summary_out(case)}


class EmailAttachment(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    content_base64: str


class EmailIntake(BaseModel):
    sender: str
    subject: str
    body: str
    external_message_id: str
    attachments: list[EmailAttachment] = Field(default_factory=list)


@router.post("")
def create_case(
    payload: EmailIntake,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    attachments = [
        (a.filename, base64.b64decode(a.content_base64), a.content_type)
        for a in payload.attachments
    ]
    case, _message, created = agent.receive_request(
        session,
        sender=payload.sender,
        subject=payload.subject,
        body=payload.body,
        external_message_id=payload.external_message_id,
        attachments=attachments,
    )
    if created:
        case.owner_id = user.id
    session.flush()
    return {"created": created, "case": case_summary_out(case)}


# ---------------------------------------------------------------------------
# Listing and reading
# ---------------------------------------------------------------------------
@router.get("")
def list_cases(
    status: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    query = select(Case).order_by(Case.id.desc()).limit(min(limit, 200))
    if status:
        query = query.where(Case.status == status)
    cases = list(session.scalars(query))
    counts: dict[str, int] = {}
    for case in session.scalars(select(Case)):
        counts[case.status] = counts.get(case.status, 0) + 1
    return {
        "cases": [case_summary_out(case) for case in cases],
        "counts_by_status": counts,
        "statuses": casestate.all_statuses(),
    }


@router.get("/{case_id}")
def get_case(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    versions = sorted(case.quote_versions, key=lambda v: v.version_number)
    current = versions[-1] if versions else None
    pending = approvals.outstanding(session, case)
    return {
        "case": case_summary_out(case),
        "status": dataclasses.asdict(casestate.describe(case.status)),
        "current_version": quote_version_out(current) if current else None,
        "versions": [quote_version_out(v, include_lines=False) for v in versions],
        "messages": [message_out(m) for m in case.messages],
        "questions": clarify.consolidated_round_summary(session, case),
        "approvals": [
            approval_out(a)
            for a in session.scalars(
                select(Approval).where(Approval.case_id == case.id).order_by(Approval.id)
            )
        ],
        "outstanding_approvals": len(pending),
        "supplier_requests": [
            supplier_request_out(r)
            for r in session.scalars(
                select(SupplierRequest).where(SupplierRequest.case_id == case.id)
            )
        ],
        "blocking_reasons": approvals.blocking_reasons(session, current) if current else [],
        "elapsed": agent.elapsed_summary(case),
    }


@router.get("/{case_id}/timeline")
def timeline(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    events = sorted(case.events, key=lambda e: e.id)
    return {
        "reference": case.reference,
        "events": [event_out(e) for e in events],
        "elapsed": agent.elapsed_summary(case),
    }


# ---------------------------------------------------------------------------
# Running the agent
# ---------------------------------------------------------------------------
@router.post("/{case_id}/run")
def run_agent(
    case_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    try:
        steps = agent.run_to_first_stop(session, case, sender_name=user.full_name)
    except Exception as exc:
        raise _handle(exc) from exc
    return {
        "steps": [
            {"step": s.step, "summary": s.summary, "detail": s.detail, "duration_ms": s.duration_ms}
            for s in steps
        ],
        "case": case_summary_out(case),
    }


@router.post("/{case_id}/read")
def read_request(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    try:
        step = agent.read_request(session, case)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"step": step.step, "summary": step.summary, "detail": step.detail}


@router.post("/{case_id}/match")
def match_lines(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    try:
        step = agent.match_lines(session, case)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"step": step.step, "summary": step.summary, "detail": step.detail}


@router.post("/{case_id}/price")
def price_case(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    try:
        step = agent.price_case(session, case)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"step": step.step, "summary": step.summary, "detail": step.detail}


# ---------------------------------------------------------------------------
# Questions to the customer
# ---------------------------------------------------------------------------
@router.get("/{case_id}/questions")
def questions(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    return {
        "summary": clarify.consolidated_round_summary(session, case),
        "open": [clarification_out(q) for q in clarify.open_questions(session, case)],
    }


@router.post("/{case_id}/questions/draft")
def draft_questions(
    case_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    message = agent.draft_question_email(session, case, sender_name=user.full_name)
    if message is None:
        return {"drafted": False, "reason": "There are no open questions."}
    return {"drafted": True, "message": message_out(message)}


class SendMessageRequest(BaseModel):
    message_id: int


@router.post("/{case_id}/messages/send")
def send_message(
    case_id: int,
    payload: SendMessageRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    message = session.get(CaseMessage, payload.message_id)
    if message is None or message.case_id != case.id:
        raise HTTPException(status_code=404, detail="That email is not on this case.")
    try:
        agent.send_message(session, case, message, user)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"sent": True, "message": message_out(message)}


class CustomerReply(BaseModel):
    body: str
    external_message_id: str | None = None
    reprice: bool = True


@router.post("/{case_id}/customer-reply")
def customer_reply(
    case_id: int,
    payload: CustomerReply,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    identifier = payload.external_message_id or (
        f"{case.reference}-reply-{len(case.messages) + 1}"
    )
    if session.scalar(
        select(CaseMessage).where(CaseMessage.external_message_id == identifier)
    ):
        raise HTTPException(status_code=409, detail="That reply has already been recorded.")

    message = CaseMessage(
        case_id=case.id,
        direction="inbound",
        external_message_id=identifier,
        sender=case.contact_email,
        recipients=["sales@hengtai-industrial.example"],
        subject=f"Re: {case.subject}",
        body=payload.body,
        language="zh" if sum(1 for c in payload.body if "一" <= c <= "鿿") >= 4 else "en",
        kind="customer",
    )
    session.add(message)
    session.flush()

    outcome = clarify.apply_answers(session, case, payload.body)
    version = agent.require_version(session, case)
    changes = clarify.apply_answers_to_lines(session, version)

    record_event(
        session,
        case_id=case.id,
        kind="customer_replied",
        summary=(
            f"{count(outcome['answered'], 'question')} answered, {outcome['still_open']} still open. "
            f"{count(len(changes), 'line')} updated and re-read."
        ),
        actor_type="customer",
        actor_name=case.contact_email,
        detail={"outcome": outcome, "line_changes": changes},
    )

    if changes:
        casestate.assert_can_move(case.status, casestate.MATCHED)
        case.status = casestate.MATCHED
        agent.match_lines(session, case)

    follow_up = None
    if outcome["still_open"]:
        follow_up = agent.draft_question_email(session, case, sender_name=user.full_name)

    priced = None
    if payload.reprice:
        version = agent.require_version(session, case)
        if any(line.status in {"matched", "priced"} for line in version.lines):
            try:
                priced = agent.price_case(session, case)
            except Exception as exc:
                raise _handle(exc) from exc

    return {
        "answers": outcome,
        "line_changes": changes,
        "follow_up_email": message_out(follow_up) if follow_up else None,
        "priced": priced.detail if priced else None,
        "case": case_summary_out(case),
    }


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
@router.post("/{case_id}/supplier-requests")
def create_supplier_request(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    try:
        step = agent.request_supplier_prices(session, case)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"step": step.step, "summary": step.summary, "detail": step.detail}


class SupplierReply(BaseModel):
    unit_price: Decimal
    currency: str = "TWD"
    lead_time_days: int = 35
    minimum_order_quantity: int = 1
    note: str = ""


@router.post("/{case_id}/supplier-requests/{request_id}/reply")
def supplier_reply(
    case_id: int,
    request_id: int,
    payload: SupplierReply,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    request = session.get(SupplierRequest, request_id)
    if request is None or request.case_id != case.id:
        raise HTTPException(status_code=404, detail="That supplier request is not on this case.")

    response = supplier.SupplierResponse(
        unit_price=dec(payload.unit_price),
        currency=payload.currency,
        lead_time_days=payload.lead_time_days,
        minimum_order_quantity=payload.minimum_order_quantity,
        note=payload.note,
    )
    supplier.record_response(session, request, response)
    version = agent.require_version(session, case)

    rate = None
    if payload.currency != "TWD":
        from ..services.rates import find_exchange_rate

        row = find_exchange_rate(session, payload.currency, "TWD")
        rate = dec(row.rate) if row else None

    applied = supplier.apply_response(
        session, version, request, response, exchange_rate_to_base=rate
    )
    record_event(
        session,
        case_id=case.id,
        kind="supplier_replied",
        summary=(
            f"{request.supplier.name} quoted {payload.unit_price} {payload.currency} with a "
            f"{payload.lead_time_days} day lead time. {count(len(applied), 'line')} priced."
        ),
        actor_type="supplier",
        actor_name=request.supplier.name,
        detail={"reference": request.reference, "applied": applied, "note": payload.note},
    )

    if case.status == casestate.AWAITING_SUPPLIER:
        case.status = casestate.MATCHED
    try:
        step = agent.price_case(session, case)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"applied": applied, "priced": step.detail, "case": case_summary_out(case)}


# ---------------------------------------------------------------------------
# Commercial changes
# ---------------------------------------------------------------------------
class TermsChange(BaseModel):
    incoterm: str | None = None
    named_place: str | None = None
    currency: str | None = None
    destination_country: str | None = None


@router.post("/{case_id}/terms")
def change_terms(
    case_id: int,
    payload: TermsChange,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    version = agent.require_version(session, case)
    before = {
        "incoterm": version.incoterm,
        "named_place": version.named_place,
        "currency": version.currency,
        "destination_country": version.destination_country,
        "grand_total": str(version.grand_total),
        "freight": str(version.freight_total),
        "import_duty": str(version.duty_total),
    }

    if payload.incoterm:
        get_incoterm(payload.incoterm)
        case.incoterm = payload.incoterm.upper()
    if payload.named_place:
        case.named_place = payload.named_place[:60]
    if payload.currency:
        case.quote_currency = payload.currency.upper()
    if payload.destination_country:
        case.destination_country = payload.destination_country.upper()

    try:
        step = agent.price_case(session, case)
    except Exception as exc:
        raise _handle(exc) from exc

    version = agent.require_version(session, case)
    after = {
        "incoterm": version.incoterm,
        "named_place": version.named_place,
        "currency": version.currency,
        "destination_country": version.destination_country,
        "grand_total": str(version.grand_total),
        "freight": str(version.freight_total),
        "import_duty": str(version.duty_total),
    }
    explanation = (
        compare_incoterms(before["incoterm"], after["incoterm"])
        if before["incoterm"] != after["incoterm"]
        else []
    )
    record_event(
        session,
        case_id=case.id,
        kind="terms_changed",
        summary=(
            f"Trade terms changed from {before['incoterm']} {before['named_place']} to "
            f"{after['incoterm']} {after['named_place']}."
        ),
        detail={"before": before, "after": after, "what_changes": explanation},
    )
    return {
        "before": before,
        "after": after,
        "what_changes": explanation,
        "priced": step.detail,
    }


class DiscountRequest(BaseModel):
    discount_percent: Decimal = Field(ge=0, le=90)


@router.post("/{case_id}/discount")
def request_discount(
    case_id: int,
    payload: DiscountRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    version = agent.require_version(session, case)
    before_total = str(version.grand_total)
    version.requested_discount_percent = dec(payload.discount_percent)
    try:
        step = agent.price_case(session, case)
    except Exception as exc:
        raise _handle(exc) from exc

    version = agent.require_version(session, case)
    below = [line for line in version.lines if line.below_margin_floor]
    record_event(
        session,
        case_id=case.id,
        kind="discount_requested",
        summary=(
            f"The customer asked for {payload.discount_percent}% off. "
            f"{count(len(below), 'line')} fall below the margin floor and need a sales manager."
        ),
        actor_type="customer",
        actor_name=case.contact_email,
        detail={
            "discount_percent": str(payload.discount_percent),
            "total_before": before_total,
            "total_after": str(version.grand_total),
            "lines_below_floor": [
                {
                    "line_number": line.line_number,
                    "part": line.product.sku if line.product else "",
                    "margin_percent": str(line.margin_percent),
                    "price_build_up": line.calculation_trace,
                }
                for line in below
            ],
        },
    )
    return {
        "total_before": before_total,
        "total_after": str(version.grand_total),
        "lines_below_floor": len(below),
        "priced": step.detail,
        "approvals": [approval_out(a) for a in approvals.outstanding(session, case)],
    }


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------
class RevisionRequest(BaseModel):
    sample_key: str | None = None
    filename: str | None = None
    content_base64: str | None = None
    note: str = ""


@router.post("/{case_id}/revision")
def create_revision(
    case_id: int,
    payload: RevisionRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    previous = agent.require_version(session, case)

    if payload.sample_key:
        sample = next((s for s in get_samples(session) if s.key == payload.sample_key), None)
        if sample is None or not sample.attachments:
            raise HTTPException(status_code=404, detail="No sample revision with that name.")
        filename, data, _content_type = sample.attachments[0]
    elif payload.filename and payload.content_base64:
        filename, data = payload.filename, base64.b64decode(payload.content_base64)
    else:
        raise HTTPException(
            status_code=400,
            detail="Send either a sample name or a file to use as the revised request.",
        )

    reading = read_attachment(data, filename)
    if not reading.rows:
        raise HTTPException(
            status_code=400,
            detail="No line items could be read from that file: " + "; ".join(reading.problems),
        )

    plan = revisions.compare(previous.lines, reading.rows)
    casestate.assert_can_move(case.status, casestate.REVISED)
    case.status = casestate.REVISED

    version = revisions.build_next_version(session, previous, reading.rows, plan)
    record_event(
        session,
        case_id=case.id,
        kind="revision_received",
        summary=(
            f"Revision received. {count(len(plan.requires_requote), 'line')} changed, "
            f"{len(plan.unchanged)} carried over unchanged, {len(plan.removed)} withdrawn."
        ),
        actor_type="customer",
        actor_name=case.contact_email,
        detail={"summary": plan.summary(), "changes": [c.to_dict() for c in plan.changes]},
    )

    agent.match_lines(session, case)
    try:
        step = agent.price_case(session, case)
    except Exception as exc:
        raise _handle(exc) from exc

    version = agent.require_version(session, case)
    return {
        "summary": plan.summary(),
        "changes": [c.to_dict() for c in plan.changes],
        "comparison": revisions.compare_versions(previous, version),
        "priced": step.detail,
        "version": quote_version_out(version, include_lines=False),
    }


@router.get("/{case_id}/versions/{earlier}/compare/{later}")
def compare_versions(
    case_id: int,
    earlier: int,
    later: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    by_number = {v.version_number: v for v in case.quote_versions}
    if earlier not in by_number or later not in by_number:
        raise HTTPException(status_code=404, detail="One of those quote versions does not exist.")
    return revisions.compare_versions(by_number[earlier], by_number[later])


@router.get("/{case_id}/versions/{number}")
def get_version(
    case_id: int,
    number: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    version = next((v for v in case.quote_versions if v.version_number == number), None)
    if version is None:
        raise HTTPException(status_code=404, detail="That quote version does not exist.")
    return quote_version_out(version)


# ---------------------------------------------------------------------------
# Approvals and sending
# ---------------------------------------------------------------------------
class ApprovalDecision(BaseModel):
    approved: bool
    comment: str = ""


@router.post("/{case_id}/approvals/{approval_id}/decide")
def decide_approval(
    case_id: int,
    approval_id: int,
    payload: ApprovalDecision,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    approval = session.get(Approval, approval_id)
    if approval is None or approval.case_id != case.id:
        raise HTTPException(status_code=404, detail="That approval is not on this case.")
    try:
        approvals.decide(session, approval, user, approved=payload.approved, comment=payload.comment)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    record_event(
        session,
        case_id=case.id,
        kind="approval_decided",
        summary=(
            f"{approval.title}: {'approved' if payload.approved else 'rejected'} by "
            f"{user.full_name}."
        ),
        actor_type="person",
        actor_name=user.full_name,
        detail={"rule": approval.rule_code, "comment": payload.comment},
    )
    record_change(
        session, user=user, action="decide", entity="approval", entity_id=approval.id,
        after={"status": approval.status, "comment": payload.comment},
    )

    version = agent.require_version(session, case)
    if not approvals.outstanding(session, case) and case.status == casestate.AWAITING_APPROVAL:
        case.status = casestate.PRICED
        version.status = "approved"
    return {
        "approval": approval_out(approval),
        "blocking_reasons": approvals.blocking_reasons(session, version),
        "case": case_summary_out(case),
    }


@router.get("/{case_id}/integrity")
def integrity(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    version = agent.require_version(session, case)
    return pricing.verify_pricing_integrity(session, version).to_dict()


@router.post("/{case_id}/send-quote")
def send_quote(
    case_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("sales_engineer")),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    try:
        step = agent.send_quote(session, case, user)
    except Exception as exc:
        raise _handle(exc) from exc

    version = agent.require_version(session, case)
    path, document_format = documents.write_quote_document(case, version)
    version.document_path = path
    version.document_format = document_format
    session.flush()
    return {
        "sent": True,
        "detail": step.detail,
        "document_format": document_format,
        "case": case_summary_out(case),
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
@router.get("/{case_id}/quote-document")
def quote_document(
    case_id: int,
    version_number: int | None = None,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> Response:
    case = _case_or_404(session, case_id)
    version = (
        next((v for v in case.quote_versions if v.version_number == version_number), None)
        if version_number
        else agent.require_version(session, case)
    )
    if version is None:
        raise HTTPException(status_code=404, detail="That quote version does not exist.")
    path, document_format = documents.write_quote_document(case, version)
    version.document_path, version.document_format = path, document_format
    session.flush()
    media = "application/pdf" if document_format == "pdf" else "text/html; charset=utf-8"
    return FileResponse(
        path,
        media_type=media,
        filename=f"{case.reference}-v{version.version_number}.{document_format}",
    )


@router.get("/{case_id}/quote-preview", response_class=Response)
def quote_preview(
    case_id: int,
    version_number: int | None = None,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> Response:
    case = _case_or_404(session, case_id)
    version = (
        next((v for v in case.quote_versions if v.version_number == version_number), None)
        if version_number
        else agent.require_version(session, case)
    )
    if version is None:
        raise HTTPException(status_code=404, detail="That quote version does not exist.")
    return Response(content=documents.render_html(case, version), media_type="text/html")


@router.get("/{case_id}/line-export")
def line_export(
    case_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> Response:
    case = _case_or_404(session, case_id)
    version = agent.require_version(session, case)
    path, export_format = documents.write_line_export(case, version)
    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if export_format == "xlsx"
        else "text/csv"
    )
    return FileResponse(
        path, media_type=media, filename=f"{case.reference}-lines.{export_format}"
    )


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------
class OutcomeRequest(BaseModel):
    outcome: str = Field(pattern="^(won|lost)$")
    reason: str = ""


@router.post("/{case_id}/outcome")
def set_outcome(
    case_id: int,
    payload: OutcomeRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    case = _case_or_404(session, case_id)
    try:
        casestate.assert_can_move(case.status, payload.outcome)
    except casestate.IllegalTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    case.status = payload.outcome
    case.outcome = payload.outcome
    case.outcome_reason = payload.reason[:255]
    case.closed_at = dt.datetime.now(dt.timezone.utc)
    record_event(
        session,
        case_id=case.id,
        kind="case_closed",
        summary=f"Marked as {payload.outcome} by {user.full_name}. {payload.reason}".strip(),
        actor_type="person",
        actor_name=user.full_name,
        detail={"outcome": payload.outcome, "reason": payload.reason},
    )
    return {"case": case_summary_out(case)}
