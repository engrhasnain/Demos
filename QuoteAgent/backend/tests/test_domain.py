"""The industry rules: part numbers, units, tax identifiers and trade terms."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.domain.incoterms import compare, get_incoterm
from app.domain.partnumbers import (
    merge_specifications,
    normalise_number,
    parse_specification,
)
from app.domain.taxid import (
    check_tax_identifier,
    check_unified_business_number,
    generate_unified_business_number,
)
from app.domain.units import UnitError, plan_quantity, to_pieces


# ---------------------------------------------------------------------------
# Reading part descriptions
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,thread,length,property_class,finish",
    [
        ("DIN 912 M8x30 12.9 zinc", "M8", "30", "12.9", "zinc_blue"),
        ("ISO 4762 M18x90 8.8 plain", "M18", "90", "8.8", "plain"),
        ("ISO 4762 M8-1.25 x 30 cl.12.9 A2K", "M8", "30", "12.9", "zinc_blue"),
        ("M12x1.5x60 socket head cap screw 12.9 plain", "M12", "60", "12.9", "plain"),
        ("DIN 933 M20x140 10.9 hot dip galvanised", "M20", "140", "10.9", "hot_dip_galvanised"),
    ],
)
def test_reads_a_fastener(text, thread, length, property_class, finish):
    spec = parse_specification(text)
    assert spec.family == "fastener"
    assert spec.attributes["thread"] == thread
    assert spec.attributes["length_mm"] == length
    assert spec.attributes["property_class"] == property_class
    assert spec.attributes["finish"] == finish
    assert spec.missing == []


def test_a_length_after_the_thread_is_not_confused_with_the_pitch():
    spec = parse_specification("ISO 4762 M18x90 8.8 plain")
    assert spec.attributes["length_mm"] == "90"
    assert spec.attributes["pitch_mm"] == "2.5"       # coarse pitch for M18
    assert "pitch_mm" in spec.assumed


def test_a_fine_pitch_is_read_and_marked_as_stated():
    spec = parse_specification("ISO 4762 M12x1.5x60 12.9 plain")
    assert spec.attributes["pitch_mm"] == "1.5"
    assert spec.attributes["pitch_kind"] == "fine"
    assert "pitch_mm" not in spec.assumed


def test_zinc_plated_blue_passivated_is_one_finish_not_two():
    spec = parse_specification("ISO 4762 M8x30 8.8 zinc plated, blue passivated")
    assert spec.attributes["finish"] == "zinc_blue"
    assert spec.conflicts == []


def test_stainless_with_a_plating_is_a_conflict():
    spec = parse_specification("Socket head cap screw M8x40 A2-70 stainless, zinc plated")
    assert [c["attribute"] for c in spec.conflicts] == ["finish"]
    assert "not plated" in spec.conflicts[0]["explanation"]


def test_a_nut_is_not_graded_like_a_bolt():
    spec = parse_specification("Hexagon nut ISO 4032 M12 class 10, zinc plated")
    assert spec.attributes["kind"] == "hex_nut"
    assert spec.attributes["property_class"] == "10"
    assert "length_mm" not in spec.missing

    wrong = parse_specification("Hexagon nut ISO 4032 M12 class 8.8 zinc")
    assert [c["attribute"] for c in wrong.conflicts] == ["property_class"]


def test_a_washer_is_specified_by_hardness():
    spec = parse_specification("Flat washer ISO 7089 M12 200 HV zinc plated")
    assert spec.attributes["kind"] == "flat_washer"
    assert spec.attributes["property_class"] == "200HV"


def test_a_bare_bolt_is_read_as_a_fastener_with_the_type_missing():
    spec = parse_specification("M10 bolt, class 8.8, zinc")
    assert spec.family == "fastener"
    assert "kind" in spec.missing
    assert "length_mm" in spec.missing


def test_a_standard_we_do_not_stock_is_not_guessed_at():
    spec = parse_specification("Shoulder bolt ISO 7379 12x50 M10 class 12.9 plain")
    assert spec.family == "unknown"
    assert "does not stock" in " ".join(spec.notes)


# ---------------------------------------------------------------------------
# Bearings
# ---------------------------------------------------------------------------
def test_bearing_dimensions_come_from_the_published_standard():
    spec = parse_specification("6204-2RS C3")
    assert spec.attributes["designation"] == "6204"
    # ISO 15:2017 fixes 6204 at 20 x 47 x 14 mm for every maker.
    assert spec.attributes["bore_mm"] == "20"
    assert spec.attributes["outside_diameter_mm"] == "47"
    assert spec.attributes["width_mm"] == "14"
    assert spec.attributes["seal"] == "sealed_both"
    assert spec.attributes["clearance"] == "C3"


@pytest.mark.parametrize(
    "text", ["SKF 6204-2RS1", "FAG 6204.2RSR", "NSK 6204DDU", "NTN 6204LLU", "Timken 6204-2RS"]
)
def test_every_maker_seal_suffix_reads_as_sealed_both_sides(text):
    spec = parse_specification(text)
    assert spec.attributes["designation"] == "6204"
    assert spec.attributes["seal"] == "sealed_both"


def test_a_bearing_with_no_sealing_stated_is_not_assumed_to_be_open():
    spec = parse_specification("Deep groove ball bearing 6205")
    assert "seal" in spec.missing


def test_clearance_is_marked_as_assumed_when_it_is_not_stated():
    spec = parse_specification("6204-2RS")
    assert spec.attributes["clearance"] == "CN"
    assert "clearance" in spec.assumed


# ---------------------------------------------------------------------------
# Merging two readings of the same line
# ---------------------------------------------------------------------------
def test_merging_records_a_disagreement_between_the_email_and_the_attachment():
    email = parse_specification("ISO 4762 M8x30 12.9 zinc")
    attachment = parse_specification("ISO 4762 M8x35 12.9 zinc")
    merged = merge_specifications(email, attachment)
    assert any(c["attribute"] == "length_mm" for c in merged.conflicts)


def test_normalising_a_part_number_ignores_how_it_is_punctuated():
    assert normalise_number("skf 6204-2RS1") == normalise_number("SKF6204 2rs1")


# ---------------------------------------------------------------------------
# Units, packs and minimum order quantities
# ---------------------------------------------------------------------------
def test_pieces_are_rounded_up_to_a_whole_box():
    plan = plan_quantity(
        requested_quantity=1_234, requested_unit="pcs", pack_size=100, product_label="HT-TEST"
    )
    assert plan.pieces_billed == Decimal("1300")
    assert plan.boxes == Decimal("13")
    assert plan.was_rounded
    assert "boxes of 100" in plan.rounding_note


def test_boxes_are_converted_into_pieces():
    plan = plan_quantity(
        requested_quantity=14, requested_unit="boxes", pack_size=500, product_label="HT-TEST"
    )
    assert plan.pieces_billed == Decimal("7000")


def test_the_supplier_minimum_is_applied_before_the_pack_size():
    plan = plan_quantity(
        requested_quantity=250,
        requested_unit="pcs",
        pack_size=100,
        minimum_order_quantity=2_000,
        is_stocked=False,
        product_label="HT-TEST",
    )
    assert plan.pieces_billed == Decimal("2000")
    assert "will not make fewer than 2000" in plan.rounding_note


def test_a_stocked_part_ignores_the_supplier_minimum():
    plan = plan_quantity(
        requested_quantity=250,
        requested_unit="pcs",
        pack_size=100,
        minimum_order_quantity=2_000,
        is_stocked=True,
        product_label="HT-TEST",
    )
    assert plan.pieces_billed == Decimal("300")


def test_a_quantity_by_weight_is_refused_rather_than_guessed():
    with pytest.raises(UnitError):
        to_pieces(25, "kg", 100)


def test_thousands_are_understood():
    assert to_pieces(10, "k", 100) == Decimal("10000")


# ---------------------------------------------------------------------------
# Tax identifiers
# ---------------------------------------------------------------------------
def test_taiwan_number_uses_the_rule_in_force_after_april_2023():
    # Generated against the current rule, so it has to pass under it.
    number = generate_unified_business_number(4_712_033, on_date=dt.date(2026, 10, 5))
    assert check_unified_business_number(number, on_date=dt.date(2026, 10, 5)).valid


def test_the_relaxed_rule_accepts_numbers_the_old_rule_rejected():
    relaxed = None
    for seed in range(200):
        candidate = generate_unified_business_number(seed, on_date=dt.date(2026, 10, 5))
        new_rule = check_unified_business_number(candidate, on_date=dt.date(2026, 10, 5))
        old_rule = check_unified_business_number(candidate, on_date=dt.date(2022, 1, 1))
        if new_rule.valid and not old_rule.valid:
            relaxed = candidate
            break
    assert relaxed is not None, (
        "the divide-by-five rule has to accept numbers the divide-by-ten rule refused"
    )


def test_a_number_of_the_wrong_length_is_refused():
    assert not check_unified_business_number("1234567").valid


def test_a_united_states_employer_number_is_checked_for_shape():
    assert check_tax_identifier("94-3871205", "US").valid
    assert not check_tax_identifier("9438712", "US").valid


# ---------------------------------------------------------------------------
# Incoterms 2020
# ---------------------------------------------------------------------------
def test_delivered_duty_paid_carries_the_import_duty():
    rule = get_incoterm("DDP")
    assert rule.seller_pays_import_duty
    assert rule.seller_pays_main_carriage
    assert "import duty and import taxes" in rule.cost_components()


def test_free_on_board_leaves_freight_and_duty_with_the_buyer():
    rule = get_incoterm("FOB")
    assert not rule.seller_pays_main_carriage
    assert not rule.seller_pays_import_duty


def test_changing_the_rule_explains_what_moves():
    changes = compare("FOB", "DDP")
    joined = " ".join(changes)
    assert "main freight" in joined
    assert "import duty" in joined


def test_an_unknown_rule_is_refused():
    with pytest.raises(ValueError):
        get_incoterm("XYZ")
