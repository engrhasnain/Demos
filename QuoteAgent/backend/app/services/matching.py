"""Matching a written request line to a part Hengtai can actually sell.

Four routes are tried in order, and whichever one answers, the answer is then
**verified attribute by attribute against the catalogue record**. A proposal
that cannot be verified does not become a match; it becomes a question.

1. Hengtai's own catalogue number, written any way a human writes it.
2. The cross-reference table: competitor numbers and published standards.
3. Attribute matching: read the specification, filter the catalogue on it.
4. Text similarity over the catalogue, as a last resort and never on its own.

A line is flagged rather than guessed when a required attribute is missing,
when two attributes contradict each other, or when two different parts fit
equally well.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.partnumbers import (
    ParsedSpecification,
    describe_attribute,
    normalise_number,
    normalise_text,
    parse_specification,
)
from ..models import CrossReference, Product

# Attributes that must agree for a candidate to be accepted, per family.
VERIFIED_ATTRIBUTES: dict[str, list[str]] = {
    "fastener": ["kind", "thread", "length_mm", "property_class", "finish", "pitch_mm"],
    "bearing": ["designation", "seal", "clearance"],
    "pneumatic": ["kind", "bore_mm", "stroke_mm", "port", "action"],
}

#: Attributes whose disagreement only lowers confidence instead of rejecting,
#: even when the customer did state them.
SOFT_ATTRIBUTES = {"pitch_mm", "port"}

#: A match found only by text similarity is never good enough on its own. It
#: has to clear this score and agree on at least one stated attribute.
TEXT_SIMILARITY_FLOOR = Decimal("0.55")

#: How close the runner-up has to be before the line is called ambiguous.
AMBIGUITY_MARGIN = Decimal("0.06")


@dataclass(slots=True)
class AttributeCheck:
    attribute: str
    requested: str
    catalogue: str
    agrees: bool
    severity: str  # must_agree | advisory

    def to_dict(self) -> dict[str, Any]:
        return {
            "attribute": self.attribute,
            "label": describe_attribute(self.attribute, self.requested).split(":")[0],
            "requested": self.requested,
            "catalogue": self.catalogue,
            "agrees": self.agrees,
            "severity": self.severity,
        }


@dataclass(slots=True)
class Candidate:
    product: Product
    method: str
    score: Decimal
    reasons: list[str] = field(default_factory=list)
    checks: list[AttributeCheck] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return all(c.agrees for c in self.checks if c.severity == "must_agree")

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product.id,
            "sku": self.product.sku,
            "description": self.product.description_en,
            "method": self.method,
            "score": str(self.score),
            "reasons": self.reasons,
            "checks": [c.to_dict() for c in self.checks],
            "verified": self.verified,
        }


@dataclass(slots=True)
class MatchResult:
    status: str                  # matched | needs_clarification | non_catalogue
    product: Product | None
    method: str
    confidence: Decimal
    reasons: list[str]
    checks: list[AttributeCheck]
    alternatives: list[dict[str, Any]]
    specification: ParsedSpecification
    questions: list[dict[str, Any]] = field(default_factory=list)
    blocking_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "product_id": self.product.id if self.product else None,
            "sku": self.product.sku if self.product else "",
            "method": self.method,
            "confidence": str(self.confidence),
            "reasons": self.reasons,
            "checks": [c.to_dict() for c in self.checks],
            "alternatives": self.alternatives,
            "specification": self.specification.to_dict(),
            "questions": self.questions,
            "blocking_reason": self.blocking_reason,
        }


# ---------------------------------------------------------------------------
# Catalogue index
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _trigrams(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.lower()).strip()
    if len(cleaned) < 3:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + 3] for i in range(len(cleaned) - 2)]


class CatalogueIndex:
    """A small search index held in memory.

    Deliberately not a vector database. Eighteen thousand parts fit in memory,
    the scoring is explainable on screen, and the demonstration has one fewer
    service that can be down.
    """

    def __init__(self) -> None:
        self.products: dict[int, Product] = {}
        self.by_sku: dict[str, int] = {}
        self.by_cross_reference: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
        self.by_attribute_key: dict[str, list[int]] = defaultdict(list)
        self.postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        self.document_count = 0
        self.loaded = False

    # -- building ---------------------------------------------------------
    def build(self, session: Session) -> "CatalogueIndex":
        products = list(session.scalars(select(Product).where(Product.is_active.is_(True))))
        self.products = {p.id: p for p in products}
        self.by_sku = {normalise_number(p.sku): p.id for p in products}
        self.document_count = len(products) or 1

        document_frequency: dict[str, int] = defaultdict(int)
        grams_per_product: dict[int, dict[str, int]] = {}
        for product in products:
            counts: dict[str, int] = defaultdict(int)
            for gram in _trigrams(product.search_text or product.description_en):
                counts[gram] += 1
            grams_per_product[product.id] = counts
            for gram in counts:
                document_frequency[gram] += 1

            key = self.attribute_key(product.family, product.attributes)
            if key:
                self.by_attribute_key[key].append(product.id)

        for product_id, counts in grams_per_product.items():
            norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
            for gram, count in counts.items():
                weight = (count / norm) * math.log(
                    self.document_count / (1 + document_frequency[gram]) + 1.0
                )
                self.postings[gram].append((product_id, weight))

        for reference in session.scalars(select(CrossReference)):
            self.by_cross_reference[reference.normalised_number].append(
                (reference.product_id, reference.brand, reference.equivalence)
            )

        self.loaded = True
        return self

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def attribute_key(family: str, attributes: dict[str, Any]) -> str:
        """A compact key for the attributes that identify a part exactly."""
        if family == "fastener":
            parts = [
                attributes.get("kind", ""),
                attributes.get("thread", ""),
                str(attributes.get("length_mm", "")),
                attributes.get("property_class", ""),
                attributes.get("finish", ""),
            ]
        elif family == "bearing":
            parts = [
                attributes.get("designation", ""),
                attributes.get("seal", ""),
                attributes.get("clearance", "CN"),
            ]
        elif family == "pneumatic":
            parts = [
                attributes.get("kind", ""),
                str(attributes.get("bore_mm", "")),
                str(attributes.get("stroke_mm", "")),
            ]
        else:
            return ""
        if not all(parts[:2]):
            return ""
        return family + "|" + "|".join(str(p) for p in parts)

    def search_text(self, text: str, limit: int = 8) -> list[tuple[int, float]]:
        counts: dict[str, int] = defaultdict(int)
        for gram in _trigrams(text):
            counts[gram] += 1
        if not counts:
            return []
        norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
        scores: dict[int, float] = defaultdict(float)
        for gram, count in counts.items():
            for product_id, weight in self.postings.get(gram, ()):  # type: ignore[arg-type]
                scores[product_id] += (count / norm) * weight
        best = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
        top = best[0][1] if best else 1.0
        return [(pid, (value / top) if top else 0.0) for pid, value in best]


_INDEX: CatalogueIndex | None = None


def get_index(session: Session, *, rebuild: bool = False) -> CatalogueIndex:
    global _INDEX
    if _INDEX is None or rebuild or not _INDEX.loaded:
        _INDEX = CatalogueIndex().build(session)
    return _INDEX


def reset_index() -> None:
    """Called after the demo data is loaded or the catalogue changes."""
    global _INDEX
    _INDEX = None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify(specification: ParsedSpecification, product: Product) -> list[AttributeCheck]:
    """Compare what the line asked for with what the catalogue record actually is.

    An attribute the customer wrote down has to agree. An attribute the agent
    filled in itself, such as normal clearance on a bearing that did not state
    one, is advisory: disagreeing with an assumption lowers confidence rather
    than rejecting a part the customer may well have meant.
    """
    checks: list[AttributeCheck] = []
    family = specification.family or product.family
    assumed = set(specification.assumed)
    for attribute in VERIFIED_ATTRIBUTES.get(family, []):
        requested = specification.attributes.get(attribute)
        if requested in (None, ""):
            continue
        catalogue = product.attributes.get(attribute, "")
        agrees = str(requested).strip().lower() == str(catalogue).strip().lower()
        soft = attribute in assumed or attribute in SOFT_ATTRIBUTES
        checks.append(
            AttributeCheck(
                attribute=attribute,
                requested=str(requested),
                catalogue=str(catalogue),
                agrees=agrees,
                severity="advisory" if soft else "must_agree",
            )
        )
    return checks


def _candidate(
    product: Product,
    specification: ParsedSpecification,
    method: str,
    base_score: Decimal,
    reasons: Iterable[str],
) -> Candidate:
    checks = verify(specification, product)
    score = base_score
    for check in checks:
        if not check.agrees:
            score -= Decimal("0.35") if check.severity == "must_agree" else Decimal("0.05")
    return Candidate(
        product=product,
        method=method,
        score=max(score, Decimal("0")),
        reasons=list(reasons),
        checks=checks,
    )


_TOKEN_IN_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-\./]{1,}")


def _lookup_keys(text: str) -> list[tuple[str, str]]:
    """Every sensible way of reading a part number out of a line.

    A customer writes ``SKF 6000-2RS1 C3``. The clearance is a separate word,
    but the cross-reference table holds it as part of one number, so adjacent
    words are also tried joined together.
    """
    tokens = _TOKEN_IN_TEXT.findall(text or "")
    keys: list[tuple[str, str]] = []
    for position, token in enumerate(tokens):
        single = normalise_number(token)
        if len(single) >= 4:
            keys.append((token, single))
        if position + 1 < len(tokens):
            joined_text = f"{token} {tokens[position + 1]}"
            joined = normalise_number(joined_text)
            if len(joined) >= 4:
                keys.append((joined_text, joined))
        for span in (2, 3):
            if position + span < len(tokens):
                joined_text = " ".join(tokens[position : position + span + 1])
                joined = normalise_number(joined_text)
                if len(joined) >= 4:
                    keys.append((joined_text, joined))
    return keys


# ---------------------------------------------------------------------------
# The matcher
# ---------------------------------------------------------------------------
def match_line(
    session: Session,
    request_text: str,
    *,
    specification: ParsedSpecification | None = None,
    index: CatalogueIndex | None = None,
) -> MatchResult:
    result = _match_line(session, request_text, specification=specification, index=index)
    if result.product is not None:
        # The index is cached across requests, so the parts it holds belong to
        # the session that built it, which is closed by the time a later
        # request asks. Their columns still read, but following a relationship
        # (the supplier, the stock) needs a live session and failed with
        # DetachedInstanceError. The part handed back is the caller's own copy.
        result.product = session.get(Product, result.product.id) or result.product
    return result


def _match_line(
    session: Session,
    request_text: str,
    *,
    specification: ParsedSpecification | None = None,
    index: CatalogueIndex | None = None,
) -> MatchResult:
    index = index or get_index(session)
    specification = specification or parse_specification(request_text)
    normalised = normalise_number(request_text)
    candidates: list[Candidate] = []

    # --- 1. Hengtai's own catalogue number -------------------------------
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\./]{5,}", request_text or ""):
        product_id = index.by_sku.get(normalise_number(token))
        if product_id:
            product = index.products[product_id]
            candidates.append(
                _candidate(
                    product, specification, "catalogue_number", Decimal("1.00"),
                    [f"{token} is Hengtai's own catalogue number for this part."],
                )
            )
            break

    # --- 2. Cross-reference table ----------------------------------------
    if not candidates:
        seen_numbers: set[str] = set()
        for token, key in _lookup_keys(request_text):
            if key in seen_numbers:
                continue
            seen_numbers.add(key)
            for product_id, brand, equivalence in index.by_cross_reference.get(key, []):
                product = index.products.get(product_id)
                if product is None:
                    continue
                base = {
                    "exact": Decimal("0.99"),
                    "interchange": Decimal("0.94"),
                    "approximate": Decimal("0.70"),
                }.get(equivalence, Decimal("0.80"))
                reason = (
                    f"{token} is listed in the cross-reference table as the {brand} "
                    f"number for this part ({equivalence.replace('_', ' ')})."
                )
                if equivalence == "approximate":
                    reason += " An approximate reference always needs a human check."
                candidates.append(
                    _candidate(product, specification, "cross_reference", base, [reason])
                )

    # --- 3. Attribute matching -------------------------------------------
    if specification.family in VERIFIED_ATTRIBUTES:
        key = CatalogueIndex.attribute_key(specification.family, specification.attributes)
        for product_id in index.by_attribute_key.get(key, [])[:5]:
            product = index.products[product_id]
            if any(c.product.id == product.id for c in candidates):
                continue
            candidates.append(
                _candidate(
                    product, specification, "attribute_match", Decimal("0.93"),
                    [
                        "Every attribute written on the line matches this catalogue "
                        "record: " + ", ".join(
                            describe_attribute(a, v)
                            for a, v in specification.attributes.items()
                            if a in VERIFIED_ATTRIBUTES[specification.family]
                        ),
                    ],
                )
            )

    # --- 4. Text similarity ----------------------------------------------
    if not candidates or max(c.score for c in candidates) < Decimal("0.85"):
        for product_id, similarity in index.search_text(request_text, limit=6):
            product = index.products.get(product_id)
            if product is None or any(c.product.id == product.id for c in candidates):
                continue
            candidates.append(
                _candidate(
                    product,
                    specification,
                    "text_similarity",
                    (Decimal(str(round(similarity, 4))) * Decimal("0.80")).quantize(
                        Decimal("0.0001")
                    ),
                    [
                        f"The wording is {round(similarity * 100)}% similar to this "
                        "catalogue description. Text similarity alone is never enough "
                        "to price a line."
                    ],
                )
            )

    candidates.sort(key=lambda c: (-c.score, c.product.sku))
    questions: list[dict[str, Any]] = []

    # --- The customer did not say enough ---------------------------------
    for attribute in specification.missing:
        questions.append(
            {
                "kind": "missing_attribute",
                "attribute": attribute,
                "question": _missing_question(attribute, specification),
                "options": _options_for(attribute, specification, candidates),
            }
        )
    for conflict in specification.conflicts:
        questions.append(
            {
                "kind": "conflicting_specification",
                "attribute": conflict.get("attribute", ""),
                "question": (
                    f"The line gives {conflict.get('values', '')} for "
                    f"{conflict.get('attribute', 'this part').replace('_', ' ')}. "
                    + conflict.get("explanation", "")
                    + " Which one should we quote?"
                ),
                "options": [v.strip() for v in str(conflict.get("values", "")).split(" and ")],
            }
        )

    if not candidates:
        return MatchResult(
            status="non_catalogue",
            product=None,
            method="none",
            confidence=Decimal("0"),
            reasons=["No part in the catalogue matches this line."],
            checks=[],
            alternatives=[],
            specification=specification,
            questions=questions,
            blocking_reason="Not a catalogue part. A price has to be asked of a supplier.",
        )

    best = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None

    # A line that quotes one of our own catalogue numbers, or a cross-reference
    # recorded as an exact equivalent, is already settled. The catalogue record
    # supplies whatever the written line left out, so asking the customer for
    # the finish of a part they identified by number would be absurd.
    # An approximate cross-reference never settles anything; that is what the
    # word approximate is recorded for.
    settled_by_number = best.method == "catalogue_number" or (
        best.method == "cross_reference" and "approximate" not in " ".join(best.reasons)
    )

    # One exception, and it is the most expensive mistake in bearings. "SKF
    # 6307" is a complete designation and means the open bearing. A bare
    # "6307" with no maker and no suffix is usually somebody who has not
    # written the suffix down, so the sealing is confirmed rather than assumed.
    if (
        settled_by_number
        and best.method == "cross_reference"
        and specification.family == "bearing"
        and "seal" in specification.missing
        and not specification.brand
    ):
        settled_by_number = False

    if settled_by_number and best.verified and not specification.conflicts:
        return MatchResult(
            status="matched",
            product=best.product,
            method=best.method,
            confidence=best.score,
            reasons=best.reasons
            + (
                [
                    "The line gives a part number, so the catalogue record supplies "
                    "what the written description left out: "
                    + ", ".join(
                        describe_attribute(a, best.product.attributes.get(a, ""))
                        for a in specification.missing
                        if best.product.attributes.get(a)
                    )
                ]
                if specification.missing
                else []
            ),
            checks=best.checks,
            alternatives=[c.to_dict() for c in candidates[1:4]],
            specification=specification,
        )

    if questions:
        return MatchResult(
            status="needs_clarification",
            product=best.product if best.verified else None,
            method=best.method,
            confidence=best.score,
            reasons=best.reasons,
            checks=best.checks,
            alternatives=[c.to_dict() for c in candidates[:4]],
            specification=specification,
            questions=questions,
            blocking_reason="The line does not say enough to price it with confidence.",
        )

    # Text similarity on its own is a guess. A part Hengtai does not list will
    # always look a bit like one it does, so a similarity-only hit with nothing
    # verified behind it is treated as "not a catalogue part", not as a match.
    if best.method == "text_similarity":
        verified_attributes = [
            check for check in best.checks if check.severity == "must_agree" and check.agrees
        ]
        if not verified_attributes or best.score < TEXT_SIMILARITY_FLOOR:
            return MatchResult(
                status="non_catalogue",
                product=None,
                method="text_similarity",
                confidence=best.score,
                reasons=[
                    "The closest catalogue part was found only by how similar the "
                    "wording is, and no attribute on the line could be checked "
                    "against it. That is not enough to price a line."
                ],
                checks=best.checks,
                alternatives=[c.to_dict() for c in candidates[:4]],
                specification=specification,
                questions=questions,
                blocking_reason=(
                    "Not a catalogue part. A price has to be asked of a supplier. "
                    f"The nearest listed part is {best.product.sku}."
                ),
            )

    failed = [c for c in best.checks if c.severity == "must_agree" and not c.agrees]
    if failed:
        detail = "; ".join(
            f"the line asks for {describe_attribute(c.attribute, c.requested)} but this part is "
            f"{describe_attribute(c.attribute, c.catalogue).split(': ', 1)[-1]}"
            for c in failed
        )
        return MatchResult(
            status="needs_clarification",
            product=None,
            method=best.method,
            confidence=best.score,
            reasons=best.reasons + [f"The proposed part was rejected because {detail}."],
            checks=best.checks,
            alternatives=[c.to_dict() for c in candidates[:4]],
            specification=specification,
            questions=[
                {
                    "kind": "ambiguous_match",
                    "attribute": failed[0].attribute,
                    "question": (
                        "No catalogue part matches every attribute on this line. The "
                        f"closest is {best.product.sku}, {best.product.description_en}. "
                        "Please confirm whether that is acceptable."
                    ),
                    "options": [
                        f"Yes, quote {best.product.sku}",
                        "No, we need the exact specification",
                    ],
                }
            ],
            blocking_reason=f"No exact catalogue match: {detail}.",
        )

    if (
        runner_up is not None
        and runner_up.verified
        and (best.score - runner_up.score) <= AMBIGUITY_MARGIN
        and _meaningfully_different(best.product, runner_up.product)
    ):
        difference = _difference_label(best.product, runner_up.product)
        return MatchResult(
            status="needs_clarification",
            product=None,
            method=best.method,
            confidence=best.score,
            reasons=best.reasons,
            checks=best.checks,
            alternatives=[c.to_dict() for c in candidates[:4]],
            specification=specification,
            questions=[
                {
                    "kind": "ambiguous_match",
                    "attribute": difference,
                    "question": (
                        f"Two parts fit this line equally well and they differ in "
                        f"{difference.replace('_', ' ')}: {best.product.sku} "
                        f"({best.product.description_en}) and {runner_up.product.sku} "
                        f"({runner_up.product.description_en}). Which one do you need?"
                    ),
                    "options": [best.product.sku, runner_up.product.sku],
                }
            ],
            blocking_reason="Two catalogue parts fit this line equally well.",
        )

    return MatchResult(
        status="matched",
        product=best.product,
        method=best.method,
        confidence=best.score,
        reasons=best.reasons,
        checks=best.checks,
        alternatives=[c.to_dict() for c in candidates[1:4]],
        specification=specification,
    )


# ---------------------------------------------------------------------------
# Question wording
# ---------------------------------------------------------------------------
def _missing_question(attribute: str, specification: ParsedSpecification) -> str:
    subject = {
        "thread": "What thread size is needed, for example M8 or M10?",
        "length_mm": "What length is needed, in millimetres?",
        "property_class": (
            "What strength class is needed, for example 8.8, 10.9 or 12.9, or "
            "stainless A2-70 or A4-80?"
        ),
        "finish": (
            "What surface finish is needed, for example plain, zinc plated or "
            "hot dip galvanised?"
        ),
        "seal": (
            "Should the bearing be open, shielded both sides or sealed both sides?"
        ),
        "bore_mm": "What bore size is needed, in millimetres?",
        "stroke_mm": "What stroke is needed, in millimetres?",
        "designation": "Which bearing number is needed?",
        "kind": "What type of part is this line for?",
    }.get(attribute, f"Please confirm the {attribute.replace('_', ' ')} for this line.")
    written = ", ".join(
        describe_attribute(a, v)
        for a, v in specification.attributes.items()
        if a not in {"seal_suffix_seen", "pitch_kind"}
    )
    return subject + (f" The line gives {written}." if written else "")


def _options_for(
    attribute: str, specification: ParsedSpecification, candidates: list[Candidate]
) -> list[str]:
    from ..domain.partnumbers import (
        FINISH_DISPLAY,
        NUT_PROPERTY_CLASSES,
        PROPERTY_CLASSES,
        WASHER_HARDNESS_CLASSES,
    )

    if attribute == "property_class":
        kind = specification.attributes.get("kind", "")
        if kind == "hex_nut":
            return NUT_PROPERTY_CLASSES
        if kind in {"flat_washer", "spring_washer"}:
            return WASHER_HARDNESS_CLASSES
        return PROPERTY_CLASSES
    if attribute == "kind":
        return [
            "socket head cap screw",
            "hexagon head bolt",
            "hexagon nut",
            "flat washer",
        ]
    if attribute == "finish":
        return [FINISH_DISPLAY[c] for c in ("plain", "zinc_blue", "zinc_yellow", "hot_dip_galvanised")]
    if attribute == "seal":
        return ["open, no seal", "shielded both sides", "sealed both sides"]
    seen: list[str] = []
    for candidate in candidates[:4]:
        value = str(candidate.product.attributes.get(attribute, ""))
        if value and value not in seen:
            seen.append(value)
    return seen


def _meaningfully_different(left: Product, right: Product) -> bool:
    return bool(_difference_label(left, right))


def _difference_label(left: Product, right: Product) -> str:
    if left.family != right.family:
        return "part type"
    for attribute in VERIFIED_ATTRIBUTES.get(left.family, []):
        if str(left.attributes.get(attribute, "")) != str(right.attributes.get(attribute, "")):
            return attribute
    return ""
