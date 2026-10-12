"""The acceptance criteria, run against a labelled test set.

The bars this product is judged on, turned into measurements:

| Measure            | Pass bar                                                    |
|--------------------|-------------------------------------------------------------|
| Line matching      | 92 per cent or more correct at the first attempt             |
| Ambiguity handling | 95 per cent or more of genuinely unclear lines flagged, and  |
|                    | no more than 3 per cent of clear lines wrongly flagged       |
| Pricing integrity  | every price on a quote equals the pricing engine's output    |
| Revisions          | every change between two versions detected                   |
| Speed              | a draft ready within 15 minutes at the ninetieth percentile  |
| Edits              | a median of two lines or fewer changed by the salesperson    |

Results are reported as measured, including the ones that fall short, and the
"edits" bar is reported as not measurable here, because it needs a salesperson
editing real drafts rather than a test set.
"""

from __future__ import annotations

import datetime as dt
import random
import statistics
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..domain.partnumbers import FINISH_DISPLAY
from ..models import CrossReference, EvaluationRun, Product, QuoteVersion
from ..services import matching, pricing
from ..services.intake import ExtractedRow
from ..services.revisions import compare
from ..text import count

EVALUATION_SEED = 77_201


@dataclass(slots=True)
class LabelledLine:
    text: str
    expected_sku: str
    should_be_flagged: bool
    reason: str
    style: str


@dataclass(slots=True)
class CriterionResult:
    key: str
    name: str
    pass_bar: str
    measured: str
    passed: bool | None
    sample: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "pass_bar": self.pass_bar,
            "measured": self.measured,
            "passed": self.passed,
            "sample": self.sample,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Building the labelled set
# ---------------------------------------------------------------------------
def _render_clear(product: Product, style: str, cross: dict[int, list[CrossReference]]) -> str | None:
    attributes = product.attributes or {}
    if style == "catalogue_number":
        return product.sku
    if style == "description":
        return product.description_en
    if style == "published_standard" and product.family == "fastener":
        legacy = attributes.get("legacy_standard") or product.standard
        thread = attributes.get("thread", "")
        length = attributes.get("length_mm", "")
        size = f"{thread}x{length}" if length else thread
        finish = {
            "plain": "plain", "zinc_blue": "zinc", "zinc_yellow": "yellow zinc",
            "hot_dip_galvanised": "hot dip galvanised", "black_oxide": "black",
            "stainless_plain": "stainless",
        }.get(attributes.get("finish", ""), "")
        return f"{legacy} {size} {attributes.get('property_class', '')} {finish}".strip()
    if style == "competitor_number":
        references = cross.get(product.id) or []
        usable = [r for r in references if r.equivalence != "approximate"]
        if usable:
            reference = usable[0]
            # "Published standard" is how the table labels a DIN or ISO number;
            # a customer just writes the number.
            if reference.brand == "Published standard":
                return reference.external_number
            return f"{reference.brand} {reference.external_number}"
    return None


def _render_ambiguous(product: Product) -> tuple[str, str] | None:
    """Remove one required attribute so the line genuinely cannot be priced."""
    attributes = product.attributes or {}
    if product.family == "fastener":
        thread = attributes.get("thread", "")
        length = attributes.get("length_mm", "")
        property_class = attributes.get("property_class", "")
        finish = FINISH_DISPLAY.get(attributes.get("finish", ""), "")
        kind_words = {
            "socket_head_cap_screw": "socket head cap screw",
            "hex_head_bolt": "hexagon head bolt",
            "button_head_screw": "button head screw",
            "countersunk_socket_screw": "countersunk socket screw",
            "hex_nut": "hexagon nut",
            "flat_washer": "flat washer",
        }.get(attributes.get("kind", ""), "screw")
        if length:
            drop = random.Random(product.id).choice(["length", "class", "finish"])
        else:
            drop = random.Random(product.id).choice(["class", "finish"])
        if drop == "length":
            return f"{kind_words} {thread} class {property_class} {finish}", "no length given"
        if drop == "class":
            size = f"{thread}x{length}" if length else thread
            return f"{kind_words} {size} {finish}", "no strength class given"
        size = f"{thread}x{length}" if length else thread
        return f"{kind_words} {size} class {property_class}", "no surface finish given"
    if product.family == "bearing":
        return (
            f"deep groove ball bearing {attributes.get('designation', '')}, quantity needed",
            "no sealing given",
        )
    if product.family == "pneumatic" and attributes.get("kind") == "iso_15552_cylinder":
        return (
            f"pneumatic cylinder to ISO 15552 bore {attributes.get('bore_mm', '')} mm",
            "no stroke given",
        )
    return None


def _render_conflicting(product: Product) -> tuple[str, str] | None:
    attributes = product.attributes or {}
    if product.family != "fastener":
        return None
    thread = attributes.get("thread", "")
    length = attributes.get("length_mm", "")
    size = f"{thread}x{length}" if length else thread
    return (
        f"socket head cap screw {size} A2-70 stainless, zinc plated per drawing",
        "stainless steel is not plated",
    )


def build_test_set(
    session: Session, *, request_count: int, lines_per_request: int
) -> list[list[LabelledLine]]:
    generator = random.Random(EVALUATION_SEED)
    products = list(
        session.scalars(
            select(Product).where(Product.is_active.is_(True)).order_by(Product.id)
        )
    )
    if not products:
        return []

    references: dict[int, list[CrossReference]] = {}
    for reference in session.scalars(select(CrossReference)):
        references.setdefault(reference.product_id, []).append(reference)

    styles = ["catalogue_number", "description", "published_standard", "competitor_number"]
    requests: list[list[LabelledLine]] = []

    for _ in range(request_count):
        lines: list[LabelledLine] = []
        while len(lines) < lines_per_request:
            product = generator.choice(products)
            roll = generator.random()

            if roll < 0.14:
                rendered = _render_ambiguous(product)
                if rendered is None:
                    continue
                text, reason = rendered
                lines.append(LabelledLine(text, "", True, reason, "ambiguous"))
            elif roll < 0.18:
                rendered = _render_conflicting(product)
                if rendered is None:
                    continue
                text, reason = rendered
                lines.append(LabelledLine(text, "", True, reason, "conflicting"))
            else:
                style = generator.choice(styles)
                text = _render_clear(product, style, references)
                if not text:
                    continue
                lines.append(LabelledLine(text, product.sku, False, "", style))
        requests.append(lines)

    return requests


# ---------------------------------------------------------------------------
# Measuring
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[str, int, int], None]


def run_evaluation(
    session: Session,
    *,
    request_count: int = 60,
    lines_per_request: int = 25,
    revision_pairs: int = 30,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    report = progress or (lambda *_: None)
    started = dt.datetime.now(dt.timezone.utc)
    index = matching.get_index(session, rebuild=True)

    report("Building the labelled test set", 0, 1)
    requests = build_test_set(
        session, request_count=request_count, lines_per_request=lines_per_request
    )
    total_lines = sum(len(r) for r in requests)
    report("Building the labelled test set", 1, 1)

    clear_total = clear_correct = clear_wrongly_flagged = 0
    ambiguous_total = ambiguous_flagged = 0
    mistakes: list[dict[str, Any]] = []
    request_durations: list[float] = []

    done = 0
    for lines in requests:
        request_started = time.perf_counter()
        for line in lines:
            result = matching.match_line(session, line.text, index=index)
            flagged = result.status != "matched"

            if line.should_be_flagged:
                ambiguous_total += 1
                if flagged:
                    ambiguous_flagged += 1
                elif len(mistakes) < 40:
                    mistakes.append(
                        {
                            "kind": "unclear line was not flagged",
                            "text": line.text,
                            "why_unclear": line.reason,
                            "matched_to": result.product.sku if result.product else "",
                        }
                    )
            else:
                clear_total += 1
                if flagged:
                    clear_wrongly_flagged += 1
                    if len(mistakes) < 40:
                        mistakes.append(
                            {
                                "kind": "clear line was wrongly flagged",
                                "text": line.text,
                                "expected": line.expected_sku,
                                "reason": result.blocking_reason,
                                "style": line.style,
                            }
                        )
                elif result.product is not None and result.product.sku == line.expected_sku:
                    clear_correct += 1
                elif len(mistakes) < 40:
                    mistakes.append(
                        {
                            "kind": "matched to the wrong part",
                            "text": line.text,
                            "expected": line.expected_sku,
                            "got": result.product.sku if result.product else "",
                            "style": line.style,
                        }
                    )
            done += 1
            if done % 250 == 0:
                report("Matching the test set", done, total_lines)

        request_durations.append(time.perf_counter() - request_started)

    report("Matching the test set", total_lines, total_lines)

    # --- matching ---------------------------------------------------------
    matching_rate = (clear_correct / clear_total * 100) if clear_total else 0.0
    criteria: list[CriterionResult] = [
        CriterionResult(
            key="line_matching",
            name="Line matching",
            pass_bar="92 per cent or more correct at the first attempt",
            measured=f"{matching_rate:.1f} per cent",
            passed=matching_rate >= 92.0,
            sample=f"{clear_total} clear lines across {len(requests)} requests",
            detail={
                "correct": clear_correct,
                "total": clear_total,
                "wrongly_flagged": clear_wrongly_flagged,
                "examples": [m for m in mistakes if m["kind"] == "matched to the wrong part"][:10],
            },
        )
    ]

    # --- ambiguity --------------------------------------------------------
    recall = (ambiguous_flagged / ambiguous_total * 100) if ambiguous_total else 0.0
    false_rate = (clear_wrongly_flagged / clear_total * 100) if clear_total else 0.0
    criteria.append(
        CriterionResult(
            key="ambiguity_handling",
            name="Ambiguity handling",
            pass_bar=(
                "95 per cent or more of genuinely unclear lines flagged, and no more "
                "than 3 per cent of clear lines wrongly flagged"
            ),
            measured=(
                f"{recall:.1f} per cent of unclear lines flagged; "
                f"{false_rate:.1f} per cent of clear lines wrongly flagged"
            ),
            passed=recall >= 95.0 and false_rate <= 3.0,
            sample=f"{ambiguous_total} unclear lines and {clear_total} clear lines",
            detail={
                "unclear_flagged": ambiguous_flagged,
                "unclear_total": ambiguous_total,
                "clear_wrongly_flagged": clear_wrongly_flagged,
                "clear_total": clear_total,
                "examples": [m for m in mistakes if m["kind"] != "matched to the wrong part"][:10],
            },
        )
    )

    # --- pricing integrity -------------------------------------------------
    report("Checking pricing integrity", 0, 1)
    checked = 0
    failures: list[dict[str, Any]] = []
    for version in session.scalars(
        select(QuoteVersion).where(QuoteVersion.pricing_checksum != "")
    ):
        checked += 1
        recomputed = pricing.pricing_checksum(version)
        if recomputed != version.pricing_checksum:
            failures.append(
                {
                    "quote_version_id": version.id,
                    "stored": version.pricing_checksum[:16],
                    "recomputed": recomputed[:16],
                }
            )
    report("Checking pricing integrity", 1, 1)
    criteria.append(
        CriterionResult(
            key="pricing_integrity",
            name="Pricing integrity",
            pass_bar="every price on a quote equals the pricing engine's own output",
            measured=(
                f"{checked - len(failures)} of {checked} priced quotes match the engine"
                if checked
                else "no priced quotes yet, so there is nothing to check"
            ),
            passed=(len(failures) == 0) if checked else None,
            sample=f"{count(checked, 'priced quote version')}",
            detail={
                "checked": checked,
                "failures": failures,
                "how": (
                    "The server stores a fingerprint of every figure the engine "
                    "produced. Re-running the engine has to reproduce it exactly, or "
                    "the quote cannot be approved or sent."
                ),
            },
        )
    )

    # --- revisions ---------------------------------------------------------
    report("Comparing revised requests", 0, revision_pairs)
    detected = expected = 0
    for pair_index in range(revision_pairs):
        before, after, changes_expected = _revision_pair(session, pair_index)
        plan = compare(before, after)
        expected += changes_expected
        detected += len(plan.requires_requote) + len(plan.removed)
        report("Comparing revised requests", pair_index + 1, revision_pairs)

    revision_rate = (detected / expected * 100) if expected else 0.0
    criteria.append(
        CriterionResult(
            key="revisions",
            name="Revisions",
            pass_bar="every change between two versions detected",
            measured=f"{revision_rate:.1f} per cent of changes detected",
            passed=detected == expected,
            sample=f"{revision_pairs} pairs of requests",
            detail={"changes_expected": expected, "changes_detected": detected},
        )
    )

    # --- speed -------------------------------------------------------------
    per_forty_lines = [
        duration / lines_per_request * 40 for duration in request_durations
    ] or [0.0]
    ninetieth = (
        statistics.quantiles(per_forty_lines, n=10)[-1]
        if len(per_forty_lines) >= 10
        else max(per_forty_lines)
    )
    criteria.append(
        CriterionResult(
            key="speed",
            name="Speed",
            pass_bar="a draft ready within 15 minutes at the ninetieth percentile, for 40 lines",
            measured=f"{ninetieth:.2f} seconds at the ninetieth percentile",
            passed=ninetieth <= 15 * 60,
            sample=f"{len(request_durations)} requests, scaled to 40 lines each",
            detail={
                "median_seconds": round(statistics.median(per_forty_lines), 3),
                "slowest_seconds": round(max(per_forty_lines), 3),
                "engine": settings.reasoning_engine,
                "note": (
                    "This is the agent's own working time with the built-in engine. "
                    "It excludes time waiting for a customer or a supplier, and it "
                    "excludes network time when an external model is active."
                    if settings.reasoning_engine == "built-in"
                    else "This is the agent's own working time, including the time "
                    "spent calling the external model. It excludes time waiting for "
                    "a customer or a supplier."
                ),
            },
        )
    )

    # --- edits -------------------------------------------------------------
    criteria.append(
        CriterionResult(
            key="edits",
            name="Edits by the salesperson",
            pass_bar="a median of two lines or fewer changed between the draft and the sent quote",
            measured="not measured",
            passed=None,
            sample="none",
            detail={
                "why": (
                    "This bar can only be measured once salespeople are editing real "
                    "drafts. The product records the draft and the sent version of "
                    "every quote, so the figure becomes measurable from the first week "
                    "of a pilot. It is reported as not measured rather than estimated."
                )
            },
        )
    )

    finished = dt.datetime.now(dt.timezone.utc)
    measured = [c for c in criteria if c.passed is not None]
    overall = all(c.passed for c in measured) if measured else False

    run = EvaluationRun(
        started_at=started,
        finished_at=finished,
        engine=settings.reasoning_engine,
        sample_size=total_lines,
        passed=overall,
        results=[c.to_dict() for c in criteria],
        notes=(
            f"{len(requests)} requests, {total_lines} lines, "
            f"{revision_pairs} revision pairs."
        ),
    )
    session.add(run)
    session.flush()

    return {
        "id": run.id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "seconds": round((finished - started).total_seconds(), 2),
        "engine": settings.reasoning_engine,
        "sample_size": total_lines,
        "requests": len(requests),
        "passed": overall,
        "criteria": [c.to_dict() for c in criteria],
        "mistakes": mistakes,
        "statement": (
            "All measured acceptance criteria are met."
            if overall
            else "At least one acceptance criterion is not met. The figures above are "
            "as measured, not adjusted."
        ),
    }


def _revision_pair(
    session: Session, index: int
) -> tuple[list[Any], list[ExtractedRow], int]:
    """Make a before and after pair with a known number of changes."""
    generator = random.Random(EVALUATION_SEED + index)
    products = list(
        session.scalars(select(Product).where(Product.is_active.is_(True)).limit(2_000))
    )
    chosen = generator.sample(products, 12)

    class _PreviousLine:
        """A stand-in for a stored quote line, with the fields the comparison reads."""

        __slots__ = (
            "id", "line_number", "request_text", "original_request_text",
            "customer_reference", "requested_quantity", "requested_unit",
        )

        def __init__(self, identifier: int, number: int, product: Product, quantity: int) -> None:
            self.id = identifier
            self.line_number = number
            self.request_text = product.description_en
            self.original_request_text = product.description_en
            self.customer_reference = product.sku
            self.requested_quantity = Decimal(quantity)
            self.requested_unit = "piece"

    quantities = [generator.choice([100, 250, 500, 1000, 2500]) for _ in chosen]
    before = [
        _PreviousLine(i + 1, i + 1, product, quantity)
        for i, (product, quantity) in enumerate(zip(chosen, quantities))
    ]

    after: list[ExtractedRow] = []
    changes = 0
    quantity_changes = generator.sample(range(len(chosen)), 3)
    removed_index = generator.randrange(len(chosen))

    position = 0
    for i, (product, quantity) in enumerate(zip(chosen, quantities)):
        if i == removed_index:
            changes += 1
            continue
        position += 1
        new_quantity = quantity
        if i in quantity_changes:
            new_quantity = quantity * 2
            changes += 1
        after.append(
            ExtractedRow(
                line_number=position,
                description=product.description_en,
                customer_reference=product.sku,
                quantity=Decimal(new_quantity),
                unit="piece",
                requested_date="",
                note="",
                source_reference="evaluation",
            )
        )

    extra = generator.choice(products)
    position += 1
    after.append(
        ExtractedRow(
            line_number=position,
            description=extra.description_en + " (added in revision)",
            customer_reference="",
            quantity=Decimal(750),
            unit="piece",
            requested_date="",
            note="",
            source_reference="evaluation",
        )
    )
    changes += 1

    return before, after, changes
