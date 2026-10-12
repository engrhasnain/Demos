"""Turning database rows into what the screens show.

Plain words only. The interface says "Request for Quote", not an abbreviation,
and every money figure is accompanied by the trace that produced it so it can
be opened and read.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from .domain.incoterms import get_incoterm
from .domain.partnumbers import describe_attribute
from .money import dec
from .models import (
    Approval,
    Case,
    CaseAttachment,
    CaseEvent,
    CaseMessage,
    Clarification,
    Product,
    QuoteLine,
    QuoteVersion,
    SupplierRequest,
    TariffTable,
    User,
)
from .security import ROLE_LABELS
from .services import casestate

PRICE_SOURCE_LABELS = {
    "contract": "Contract price",
    "volume_break": "Volume price",
    "list": "List price",
    "supplier_quote": "Supplier quotation",
    "": "Not priced",
}

MATCH_METHOD_LABELS = {
    "catalogue_number": "Our own catalogue number",
    "cross_reference": "Cross-reference table",
    "attribute_match": "Attribute match",
    "text_similarity": "Text similarity",
    "manual": "Chosen by a person",
    "none": "No match",
}

LINE_STATUS_LABELS = {
    "matched": "Part identified",
    "priced": "Priced",
    "needs_clarification": "Question outstanding",
    "awaiting_supplier": "Waiting for a supplier price",
    "non_catalogue": "Not a catalogue part",
    "withdrawn": "Withdrawn",
}


def user_out(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "language": user.language,
    }


def product_out(product: Product | None) -> dict[str, Any] | None:
    if product is None:
        return None
    attributes = product.attributes or {}
    return {
        "id": product.id,
        "sku": product.sku,
        "family": product.family,
        "description": product.description_en,
        "description_chinese": product.description_zh,
        "standard": product.standard,
        "attributes": attributes,
        "attributes_in_words": [
            describe_attribute(key, value)
            for key, value in attributes.items()
            if key not in {"metal_content_percent", "legacy_standard"}
        ],
        "selling_unit": product.selling_unit,
        "pack_size": product.pack_size,
        "weight_grams": str(product.weight_grams),
        "commodity_code": product.harmonised_tariff_code,
        "country_of_origin": product.country_of_origin,
        "list_price": str(product.list_price),
        "standard_cost": str(product.standard_cost),
        "is_stocked": product.is_stocked,
        "replenishment_lead_time_days": product.replenishment_lead_time_days,
        "supplier": (
            {
                "id": product.supplier.id,
                "name": product.supplier.name,
                "country": product.supplier.country,
                "lead_time_days": product.supplier.lead_time_days,
                "minimum_order_quantity": product.supplier.minimum_order_quantity,
            }
            if product.supplier
            else None
        ),
    }


def quote_line_out(line: QuoteLine) -> dict[str, Any]:
    return {
        "id": line.id,
        "line_number": line.line_number,
        "request_text": line.request_text,
        "original_request_text": line.original_request_text or line.request_text,
        "was_clarified": bool(
            line.original_request_text and line.original_request_text != line.request_text
        ),
        "customer_reference": line.customer_reference,
        "source_reference": line.source_reference,
        "requested_quantity": str(line.requested_quantity),
        "requested_unit": line.requested_unit,
        "requested_attributes": line.requested_attributes,
        "settled_by_the_customer": line.resolved_attributes,
        "status": line.status,
        "status_label": LINE_STATUS_LABELS.get(line.status, line.status),
        "blocking_reason": line.blocking_reason,
        "product": product_out(line.product),
        "match": {
            "method": line.match_method,
            "method_label": MATCH_METHOD_LABELS.get(line.match_method, line.match_method),
            "confidence": str(line.match_confidence),
            "confidence_percent": str((dec(line.match_confidence) * 100).quantize(Decimal("0.1"))),
            "reasons": line.match_reasons,
            "attribute_check": line.attribute_check,
            "alternatives": line.alternatives,
            "proposed_by": line.proposed_by,
            "verified_by": "the server, attribute by attribute",
        },
        "pricing": {
            "quantity_billed": str(line.quantity_billed),
            "unit_of_sale": line.unit_of_sale,
            "rounding_note": line.rounding_note,
            "unit_price": str(line.unit_price),
            "price_source": line.price_source,
            "price_source_label": PRICE_SOURCE_LABELS.get(line.price_source, line.price_source),
            "price_source_reference": line.price_source_reference,
            "discount_percent": str(line.discount_percent),
            "line_total": str(line.extended_price),
            "unit_cost": str(line.unit_cost),
            "margin_percent": str(line.margin_percent),
            "below_margin_floor": line.below_margin_floor,
            "freight_share": str(line.freight_share),
            "insurance_share": str(line.insurance_share),
            "import_duty": str(line.duty_amount),
            "duty_breakdown": line.duty_breakdown,
            "landed_total": str(line.landed_total),
        },
        "supply": {
            "lead_time_days": line.lead_time_days,
            "options": line.fulfilment_options,
            "chosen": line.chosen_fulfilment,
        },
        "calculation_trace": line.calculation_trace,
    }


def quote_version_out(version: QuoteVersion, *, include_lines: bool = True) -> dict[str, Any]:
    incoterm = get_incoterm(version.incoterm)
    payload: dict[str, Any] = {
        "id": version.id,
        "version_number": version.version_number,
        "status": version.status,
        "currency": version.currency,
        "incoterm": version.incoterm,
        "incoterm_name": incoterm.name,
        "incoterm_explained": incoterm.plain_summary(),
        "named_place": version.named_place,
        "destination_country": version.destination_country,
        "valid_until": version.valid_until.isoformat() if version.valid_until else None,
        "totals": {
            "goods": str(version.goods_total),
            "freight": str(version.freight_total),
            "insurance": str(version.insurance_total),
            "import_duty": str(version.duty_total),
            "grand_total": str(version.grand_total),
            "total_cost": str(version.total_cost),
            "margin_percent": str(version.margin_percent),
        },
        "requested_discount_percent": str(version.requested_discount_percent),
        "needs_repricing": version.needs_repricing,
        "repricing_reason": version.repricing_reason,
        "change_log": version.change_log,
        "totals_trace": version.totals_trace,
        "pricing_checksum": version.pricing_checksum,
        "sent_at": version.sent_at.isoformat() if version.sent_at else None,
        "document_format": version.document_format,
        "exchange_rate": (
            {
                "id": version.exchange_rate.id,
                "pair": f"{version.exchange_rate.base_currency} to {version.exchange_rate.quote_currency}",
                "rate": str(version.exchange_rate.rate),
                "as_of_date": version.exchange_rate.as_of_date.isoformat(),
                "source": version.exchange_rate.source,
                "locked_at": (
                    version.exchange_rate_locked_at.isoformat()
                    if version.exchange_rate_locked_at
                    else None
                ),
            }
            if version.exchange_rate
            else None
        ),
        "tariff_table": (
            {
                "id": version.tariff_table.id,
                "version": version.tariff_table.version,
                "title": version.tariff_table.title,
                "signed_off": version.tariff_table.is_signed_off,
                "customs_broker": version.tariff_table.customs_broker,
            }
            if version.tariff_table
            else None
        ),
    }
    if include_lines:
        payload["lines"] = [
            quote_line_out(line) for line in sorted(version.lines, key=lambda l: l.line_number)
        ]
        payload["line_counts"] = _line_counts(version)
    return payload


def _line_counts(version: QuoteVersion) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in version.lines:
        counts[line.status] = counts.get(line.status, 0) + 1
    counts["total"] = len(version.lines)
    return counts


def event_out(event: CaseEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat(),
        "actor_type": event.actor_type,
        "actor_name": event.actor_name,
        "kind": event.kind,
        "summary": event.summary,
        "detail": event.detail,
        "duration_ms": event.duration_ms,
        "engine": event.engine,
        "model": event.model,
        "input_tokens": event.input_tokens,
        "output_tokens": event.output_tokens,
        "cost_usd": str(event.cost_usd),
    }


def message_out(message: CaseMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "direction": message.direction,
        "kind": message.kind,
        "sender": message.sender,
        "recipients": message.recipients,
        "subject": message.subject,
        "body": message.body,
        "language": message.language,
        "occurred_at": message.occurred_at.isoformat(),
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "awaiting_approval": message.direction == "outbound" and message.sent_at is None,
        "attachments": [attachment_out(a) for a in message.attachments],
    }


def attachment_out(attachment: CaseAttachment) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "read_with": {
            "spreadsheet_reader": "read by code, row by row",
            "pdf_text_reader": "text layer read from the document",
            "plain_text": "read as plain text",
            "unavailable": "could not be read",
        }.get(attachment.parsed_with, attachment.parsed_with),
        "note": attachment.parse_note,
        "row_count": len(attachment.extracted_rows or []),
    }


def clarification_out(clarification: Clarification) -> dict[str, Any]:
    return {
        "id": clarification.id,
        "line_number": clarification.line_number,
        "round_number": clarification.round_number,
        "kind": clarification.question_kind,
        "attribute": clarification.attribute,
        "question": clarification.question_en,
        "question_chinese": clarification.question_zh,
        "options": clarification.options,
        "status": clarification.status,
        "answer": clarification.answer_text,
        "answer_understood_as": clarification.answer_value,
        "answered_at": clarification.answered_at.isoformat() if clarification.answered_at else None,
    }


def approval_out(approval: Approval) -> dict[str, Any]:
    return {
        "id": approval.id,
        "rule_code": approval.rule_code,
        "title": approval.title,
        "reason": approval.reason,
        "required_role": approval.required_role,
        "required_role_label": ROLE_LABELS.get(approval.required_role, approval.required_role),
        "status": approval.status,
        "detail": approval.detail,
        "requested_at": approval.requested_at.isoformat(),
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
        "decided_by": approval.decided_by.full_name if approval.decided_by else "",
        "comment": approval.decision_comment,
    }


def supplier_request_out(request: SupplierRequest) -> dict[str, Any]:
    return {
        "id": request.id,
        "reference": request.reference,
        "supplier": {
            "id": request.supplier.id,
            "name": request.supplier.name,
            "country": request.supplier.country,
            "email": request.supplier.email,
        },
        "line_numbers": request.line_numbers,
        "status": request.status,
        "sent_at": request.sent_at.isoformat(),
        "responded_at": request.responded_at.isoformat() if request.responded_at else None,
        "response": request.response,
    }


def case_summary_out(case: Case) -> dict[str, Any]:
    latest = sorted(case.quote_versions, key=lambda v: v.version_number)
    version = latest[-1] if latest else None
    return {
        "id": case.id,
        "reference": case.reference,
        "subject": case.subject,
        "customer": (
            {"id": case.customer.id, "name": case.customer.name, "country": case.customer.country}
            if case.customer
            else None
        ),
        "contact_email": case.contact_email,
        "contact_name": case.contact_name,
        "language": case.language,
        "status": case.status,
        "status_label": casestate.STATUS_LABELS.get(case.status, case.status),
        "status_description": casestate.STATUS_DESCRIPTIONS.get(case.status, ""),
        "is_waiting": case.status in casestate.WAITING,
        "incoterm": case.incoterm,
        "named_place": case.named_place,
        "currency": case.quote_currency,
        "owner": case.owner.full_name if case.owner else "",
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "version_count": len(latest),
        "current_version": version.version_number if version else 0,
        "line_count": len(version.lines) if version else 0,
        "grand_total": str(version.grand_total) if version else "0",
    }


def tariff_table_out(table: TariffTable, *, include_lines: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": table.id,
        "version": table.version,
        "title": table.title,
        "effective_from": table.effective_from.isoformat(),
        "effective_to": table.effective_to.isoformat() if table.effective_to else None,
        "status": table.status,
        "owned_by": table.owned_by,
        "customs_broker": table.customs_broker,
        "signed_off": table.is_signed_off,
        "signed_off_at": (
            table.broker_signed_off_at.isoformat() if table.broker_signed_off_at else None
        ),
        "source_note": table.source_note,
        "line_count": len(table.lines),
    }
    if include_lines:
        payload["lines"] = [
            {
                "id": line.id,
                "commodity_code": line.harmonised_tariff_code,
                "origin_country": line.origin_country,
                "destination_country": line.destination_country,
                "component": line.component,
                "rate_percent": str(line.rate_percent),
                "charged_on": (
                    "the full customs value"
                    if line.basis == "customs_value"
                    else "the metal content value"
                ),
                "combined_cap_percent": (
                    str(line.combined_cap_percent) if line.combined_cap_percent is not None else None
                ),
                "not_stacked_with": line.excluded_by,
                "authority": line.authority,
                "note": line.note,
            }
            for line in sorted(
                table.lines,
                key=lambda l: (l.destination_country, l.origin_country, l.harmonised_tariff_code, l.component),
            )
        ]
    return payload
