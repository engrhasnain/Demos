"""Revisions: the customer sends version two of the bill of materials.

What must not happen is a blanket re-quote. Re-reading all forty lines throws
away answers already given, prices already approved and questions already
closed, and it produces a second quote the customer cannot compare with the
first.

So the two versions are compared line by line. Only lines whose meaning
changed are re-read, re-matched and re-priced. Everything else is carried over
exactly as it was, and the new version carries a change log the customer can
read.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..domain.partnumbers import normalise_number, normalise_text
from ..money import dec
from ..models import QuoteLine, QuoteVersion
from .intake import ExtractedRow
from ..text import count


@dataclass(slots=True)
class LineChange:
    kind: str                  # added | removed | quantity_changed | specification_changed | unchanged
    line_number: int
    description: str
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "line_number": self.line_number,
            "description": self.description,
            "before": self.before,
            "after": self.after,
            "note": self.note,
        }


@dataclass(slots=True)
class RevisionPlan:
    changes: list[LineChange]

    @property
    def added(self) -> list[LineChange]:
        return [c for c in self.changes if c.kind == "added"]

    @property
    def removed(self) -> list[LineChange]:
        return [c for c in self.changes if c.kind == "removed"]

    @property
    def quantity_changed(self) -> list[LineChange]:
        return [c for c in self.changes if c.kind == "quantity_changed"]

    @property
    def specification_changed(self) -> list[LineChange]:
        return [c for c in self.changes if c.kind == "specification_changed"]

    @property
    def unchanged(self) -> list[LineChange]:
        return [c for c in self.changes if c.kind == "unchanged"]

    @property
    def requires_requote(self) -> list[LineChange]:
        return [c for c in self.changes if c.kind in {"added", "quantity_changed", "specification_changed"}]

    def summary(self) -> dict[str, Any]:
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "quantity_changed": len(self.quantity_changed),
            "specification_changed": len(self.specification_changed),
            "unchanged": len(self.unchanged),
            "requires_requote": len(self.requires_requote),
            "statement": (
                f"{count(len(self.requires_requote), 'line')} changed and will be re-quoted. "
                f"{count(len(self.unchanged), 'line')} are carried over unchanged."
            ),
        }


def _key_for(reference: str, description: str) -> tuple[str, str]:
    return normalise_number(reference), normalise_text(description)


def _looks_like_same_part(left: str, right: str) -> bool:
    """A cheap word overlap test, used only to confirm a positional pairing."""
    left_words = set(normalise_text(left).split())
    right_words = set(normalise_text(right).split())
    if not left_words or not right_words:
        return False
    shared = len(left_words & right_words)
    return shared / max(len(left_words), len(right_words)) >= 0.6


def _row_payload(row: ExtractedRow) -> dict[str, Any]:
    return {
        "description": row.description,
        "customer_reference": row.customer_reference,
        "quantity": str(row.quantity),
        "unit": row.unit,
        "requested_date": row.requested_date,
    }


def _original_text(line: QuoteLine) -> str:
    return line.original_request_text or line.request_text


def _line_payload(line: QuoteLine) -> dict[str, Any]:
    return {
        "description": _original_text(line),
        "customer_reference": line.customer_reference,
        "quantity": str(line.requested_quantity),
        "unit": line.requested_unit,
        "requested_date": "",
    }


def compare(previous: Iterable[QuoteLine], incoming: Iterable[ExtractedRow]) -> RevisionPlan:
    """Pair up the old lines and the new rows, then say what moved.

    Pairing goes by the customer's own part reference first, because that is
    what survives a re-export from their system; then by the exact wording;
    then by position, which is the weakest signal and is only used when the
    line counts still line up.
    """
    previous_lines = list(previous)
    incoming_rows = list(incoming)

    # A bill of materials repeats itself: the same description can appear on
    # two lines, and half the lines carry no part reference at all. So each
    # key holds every line that matches it and they are consumed one at a
    # time, instead of the first one standing in for all of them.
    by_reference: dict[str, list[QuoteLine]] = {}
    by_description: dict[str, list[QuoteLine]] = {}
    for line in previous_lines:
        reference, description = _key_for(line.customer_reference, _original_text(line))
        if reference:
            by_reference.setdefault(reference, []).append(line)
        if description:
            by_description.setdefault(description, []).append(line)

    matched_previous: set[int] = set()
    changes: list[LineChange] = []

    def take(bucket: dict[str, list[QuoteLine]], key: str) -> QuoteLine | None:
        for candidate in bucket.get(key, []):
            if candidate.id not in matched_previous:
                return candidate
        return None

    for row in incoming_rows:
        reference, description = _key_for(row.customer_reference, row.description)
        line = take(by_reference, reference) if reference else None
        if line is None:
            line = take(by_description, description)
        if line is None:
            candidate = next(
                (
                    p
                    for p in previous_lines
                    if p.line_number == row.line_number and p.id not in matched_previous
                ),
                None,
            )
            # Position is the weakest signal, so it is only trusted when the
            # wording is at least recognisably the same part.
            if candidate is not None and _looks_like_same_part(
                _original_text(candidate), row.description
            ):
                line = candidate

        if line is None or line.id in matched_previous:
            changes.append(
                LineChange(
                    kind="added",
                    line_number=row.line_number,
                    description=row.description,
                    after=_row_payload(row),
                    note="This line is new in the revised request.",
                )
            )
            continue

        matched_previous.add(line.id)
        before, after = _line_payload(line), _row_payload(row)
        quantity_moved = dec(line.requested_quantity) != dec(row.quantity) or (
            line.requested_unit != row.unit
        )
        specification_moved = normalise_text(_original_text(line)) != normalise_text(row.description)

        if specification_moved:
            changes.append(
                LineChange(
                    kind="specification_changed",
                    line_number=row.line_number,
                    description=row.description,
                    before=before,
                    after=after,
                    note="The written specification changed, so the line is matched and priced again.",
                )
            )
        elif quantity_moved:
            changes.append(
                LineChange(
                    kind="quantity_changed",
                    line_number=row.line_number,
                    description=row.description,
                    before=before,
                    after=after,
                    note=(
                        f"Quantity moved from {line.requested_quantity} "
                        f"{line.requested_unit} to {row.quantity} {row.unit}. "
                        "The price may move with the volume break."
                    ),
                )
            )
        else:
            changes.append(
                LineChange(
                    kind="unchanged",
                    line_number=row.line_number,
                    description=row.description,
                    before=before,
                    after=after,
                    note="Carried over from the previous quote without re-pricing.",
                )
            )

    for line in previous_lines:
        if line.id in matched_previous:
            continue
        changes.append(
            LineChange(
                kind="removed",
                line_number=line.line_number,
                description=_original_text(line),
                before=_line_payload(line),
                note="This line is not in the revised request and has been withdrawn.",
            )
        )

    changes.sort(key=lambda c: (c.line_number, c.kind))
    return RevisionPlan(changes=changes)


def build_next_version(
    session: Session,
    previous: QuoteVersion,
    incoming: list[ExtractedRow],
    plan: RevisionPlan,
) -> QuoteVersion:
    """Create version N+1, carrying unchanged lines over untouched."""
    version = QuoteVersion(
        case=previous.case,
        version_number=previous.version_number + 1,
        status="draft",
        currency=previous.currency,
        incoterm=previous.incoterm,
        named_place=previous.named_place,
        destination_country=previous.destination_country,
        exchange_rate_id=previous.exchange_rate_id,
        exchange_rate_locked_at=previous.exchange_rate_locked_at,
        requested_discount_percent=previous.requested_discount_percent,
        change_log=[c.to_dict() for c in plan.changes],
    )
    session.add(version)
    session.flush()

    previous_by_number = {line.line_number: line for line in previous.lines}
    incoming_by_number = {row.line_number: row for row in incoming}

    for change in plan.changes:
        if change.kind == "removed":
            continue
        row = incoming_by_number.get(change.line_number)
        old = previous_by_number.get(change.line_number)

        if change.kind == "unchanged" and old is not None:
            carried = _clone_line(old, version.id)
            carried.status = old.status
            version.lines.append(carried)
            continue

        line = QuoteLine(
            line_number=change.line_number,
            request_text=row.description if row else change.description,
            original_request_text=row.description if row else change.description,
            customer_reference=row.customer_reference if row else "",
            requested_quantity=dec(row.quantity) if row else Decimal("0"),
            requested_unit=row.unit if row else "piece",
            source_reference=row.source_reference if row else "",
            status="matched",
        )
        version.lines.append(line)
        if change.kind == "quantity_changed" and old is not None:
            # The part did not change, so keep the match and only re-price.
            line.product_id = old.product_id
            line.match_method = old.match_method
            line.match_confidence = old.match_confidence
            line.match_reasons = list(old.match_reasons or [])
            line.attribute_check = dict(old.attribute_check or {})
            line.resolved_attributes = copy.deepcopy(old.resolved_attributes or {})
            line.proposed_by = old.proposed_by

    previous.status = "superseded"
    session.flush()
    session.refresh(version)
    return version


def _clone_line(line: QuoteLine, quote_version_id: int) -> QuoteLine:
    return QuoteLine(
        quote_version_id=quote_version_id,
        line_number=line.line_number,
        request_text=line.request_text,
        original_request_text=_original_text(line),
        customer_reference=line.customer_reference,
        requested_quantity=line.requested_quantity,
        requested_unit=line.requested_unit,
        requested_attributes=copy.deepcopy(line.requested_attributes or {}),
        resolved_attributes=copy.deepcopy(line.resolved_attributes or {}),
        source_reference=line.source_reference,
        product_id=line.product_id,
        match_method=line.match_method,
        match_confidence=line.match_confidence,
        match_reasons=copy.deepcopy(line.match_reasons or []),
        attribute_check=copy.deepcopy(line.attribute_check or {}),
        alternatives=copy.deepcopy(line.alternatives or []),
        proposed_by=line.proposed_by,
        status=line.status,
        blocking_reason=line.blocking_reason,
        quantity_billed=line.quantity_billed,
        unit_of_sale=line.unit_of_sale,
        rounding_note=line.rounding_note,
        unit_price=line.unit_price,
        price_source=line.price_source,
        price_source_reference=line.price_source_reference,
        discount_percent=line.discount_percent,
        extended_price=line.extended_price,
        unit_cost=line.unit_cost,
        margin_percent=line.margin_percent,
        below_margin_floor=line.below_margin_floor,
        freight_share=line.freight_share,
        insurance_share=line.insurance_share,
        duty_amount=line.duty_amount,
        duty_breakdown=copy.deepcopy(line.duty_breakdown or []),
        landed_total=line.landed_total,
        lead_time_days=line.lead_time_days,
        fulfilment_options=copy.deepcopy(line.fulfilment_options or []),
        chosen_fulfilment=line.chosen_fulfilment,
        calculation_trace=copy.deepcopy(line.calculation_trace or {}),
    )


def compare_versions(previous: QuoteVersion, current: QuoteVersion) -> dict[str, Any]:
    """A before and after view of two priced versions, for the screen."""
    previous_lines = {line.line_number: line for line in previous.lines}
    rows: list[dict[str, Any]] = []
    for line in current.lines:
        old = previous_lines.get(line.line_number)
        rows.append(
            {
                "line_number": line.line_number,
                "description": _original_text(line),
                "quantity_before": str(old.quantity_billed) if old else "",
                "quantity_after": str(line.quantity_billed),
                "unit_price_before": str(old.unit_price) if old else "",
                "unit_price_after": str(line.unit_price),
                "line_total_before": str(old.extended_price) if old else "",
                "line_total_after": str(line.extended_price),
                "changed": (
                    old is None
                    or old.quantity_billed != line.quantity_billed
                    or old.unit_price != line.unit_price
                ),
            }
        )
    return {
        "previous_version": previous.version_number,
        "current_version": current.version_number,
        "currency": current.currency,
        "total_before": str(previous.grand_total),
        "total_after": str(current.grand_total),
        "difference": str(dec(current.grand_total) - dec(previous.grand_total)),
        "lines": rows,
        "changed_lines": sum(1 for row in rows if row["changed"]),
    }
