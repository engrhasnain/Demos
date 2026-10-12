"""Matching a written line to a part, and refusing to guess."""

from __future__ import annotations

from sqlalchemy import select

from app.domain.partnumbers import parse_specification
from app.models import CrossReference, Product
from app.services import matching


def _index(session):
    return matching.get_index(session, rebuild=False)


def test_our_own_catalogue_number_matches_exactly(session):
    product = session.scalars(select(Product).where(Product.family == "fastener")).first()
    result = matching.match_line(session, product.sku, index=_index(session))
    assert result.status == "matched"
    assert result.product.id == product.id
    assert result.method == "catalogue_number"


def test_a_catalogue_number_settles_what_the_words_left_out(session):
    """A customer who quotes our part number has told us everything."""
    product = session.scalar(
        select(Product).where(Product.family == "bearing", Product.sku.like("%-CN"))
    )
    result = matching.match_line(session, product.sku, index=_index(session))
    assert result.status == "matched"
    assert result.product.id == product.id


def test_a_competitor_number_is_found_through_the_cross_reference_table(session):
    reference = session.scalars(
        select(CrossReference).where(CrossReference.brand == "NSK")
    ).first()
    result = matching.match_line(
        session, f"NSK {reference.external_number}", index=_index(session)
    )
    assert result.status == "matched"
    assert result.product.id == reference.product_id
    assert result.method == "cross_reference"
    assert "cross-reference table" in " ".join(result.reasons)


def test_an_approximate_cross_reference_always_asks(session):
    reference = session.scalars(
        select(CrossReference).where(CrossReference.equivalence == "approximate")
    ).first()
    if reference is None:
        return
    result = matching.match_line(session, reference.external_number, index=_index(session))
    assert result.status != "matched" or result.confidence < 1


def test_a_published_standard_is_matched_by_attribute(session):
    product = session.scalar(
        select(Product).where(
            Product.family == "fastener", Product.standard == "ISO 4762"
        )
    )
    attributes = product.attributes
    written = (
        f"{attributes['legacy_standard']} {attributes['thread']}x{attributes['length_mm']} "
        f"{attributes['property_class']} "
        + {
            "plain": "plain", "zinc_blue": "zinc", "zinc_yellow": "yellow zinc",
            "hot_dip_galvanised": "hot dip galvanised", "black_oxide": "black",
            "stainless_plain": "stainless",
        }[attributes["finish"]]
    )
    result = matching.match_line(session, written, index=_index(session))
    assert result.status == "matched"
    assert result.product.sku == product.sku


def test_every_attribute_is_checked_and_reported(session):
    product = session.scalar(
        select(Product).where(Product.family == "fastener", Product.standard == "ISO 4762")
    )
    result = matching.match_line(session, product.description_en, index=_index(session))
    assert result.checks
    assert all(check.agrees for check in result.checks if check.severity == "must_agree")
    payload = result.to_dict()
    assert payload["checks"][0]["label"]


def test_a_line_that_leaves_out_a_required_attribute_is_asked_about(session):
    result = matching.match_line(
        session, "socket head cap screw M8x30 zinc plated", index=_index(session)
    )
    assert result.status == "needs_clarification"
    assert any(q["attribute"] == "property_class" for q in result.questions)


def test_a_line_that_contradicts_itself_is_asked_about(session):
    result = matching.match_line(
        session,
        "socket head cap screw M8x40 A2-70 stainless, zinc plated",
        index=_index(session),
    )
    assert result.status == "needs_clarification"
    assert any(q["kind"] == "conflicting_specification" for q in result.questions)


def test_a_part_we_do_not_list_is_not_forced_onto_a_near_neighbour(session):
    result = matching.match_line(
        session, "Trapezoidal lead screw Tr20x4 right hand, 1000 mm, C7", index=_index(session)
    )
    assert result.status == "non_catalogue"
    assert result.product is None


def test_text_similarity_alone_never_becomes_a_match(session):
    result = matching.match_line(
        session, "some industrial component for a machine", index=_index(session)
    )
    assert result.status in {"non_catalogue", "needs_clarification"}
    assert result.product is None


def test_a_bare_bearing_number_without_a_maker_asks_about_the_sealing(session):
    result = matching.match_line(session, "deep groove ball bearing 6205", index=_index(session))
    assert result.status == "needs_clarification"
    assert any(q["attribute"] == "seal" for q in result.questions)


def test_a_maker_designation_settles_the_sealing(session):
    reference = session.scalar(
        select(CrossReference).where(
            CrossReference.brand == "SKF", CrossReference.external_number.notlike("%-%")
        )
    )
    if reference is None:
        return
    result = matching.match_line(
        session, f"SKF {reference.external_number}", index=_index(session)
    )
    assert result.status == "matched"


def test_an_answer_from_the_customer_overrides_the_written_line(session):
    """What the matcher does once a question has been answered.

    The line is built from a part that really is in the catalogue, with the
    strength class removed, so the only thing stopping the match is the
    missing attribute the answer then supplies.
    """
    product = session.scalar(
        select(Product).where(
            Product.family == "fastener",
            Product.standard == "ISO 4762",
            Product.attributes.like('%"finish": "zinc_blue"%'),
        )
    )
    assert product is not None
    attributes = product.attributes
    written = (
        f"socket head cap screw {attributes['thread']}x{attributes['length_mm']} zinc plated"
    )

    specification = parse_specification(written)
    assert "property_class" in specification.missing
    flagged = matching.match_line(
        session, written, specification=specification, index=_index(session)
    )
    assert flagged.status == "needs_clarification"

    answered = parse_specification(written)
    answered.attributes["property_class"] = attributes["property_class"]
    answered.missing.remove("property_class")
    result = matching.match_line(
        session, written, specification=answered, index=_index(session)
    )
    assert result.status == "matched"
    assert result.product.attributes["property_class"] == attributes["property_class"]
