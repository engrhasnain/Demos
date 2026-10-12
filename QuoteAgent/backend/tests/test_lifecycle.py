"""Questions, suppliers, revisions and the ten step script, end to end."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Case, Clarification, QuoteVersion
from app.seed.samples import build_bill_of_materials, workbook_bytes
from app.services.clarify import interpret_answer
from app.services.intake import read_attachment, rows_from_grid, split_thread
from app.services.revisions import compare


# ---------------------------------------------------------------------------
# Reading what arrives
# ---------------------------------------------------------------------------
def test_a_spreadsheet_with_a_letterhead_is_still_read(session):
    rows = build_bill_of_materials(session)
    data = workbook_bytes(rows, title="Request for quotation")
    reading = read_attachment(data, "bom.xlsx")
    assert len(reading.rows) == len(rows)
    assert reading.parsed_with == "spreadsheet_reader"
    # The headings sit on row six, under the letterhead.
    assert "row 6" in reading.note


def test_a_row_with_no_quantity_is_reported_not_dropped():
    grid = [
        ["ACME ENGINEERING"],
        [],
        ["Item", "Part No.", "Description", "Qty", "UOM"],
        [1, "", "ISO 4762 M8x30 12.9 zinc", 1000, "pcs"],
        [2, "", "ISO 4762 M10x40 12.9 zinc", None, "pcs"],
    ]
    reading = rows_from_grid(grid, sheet_name="test")
    assert len(reading.rows) == 2
    assert any("no quantity" in problem for problem in reading.problems)


def test_chinese_column_headings_are_understood():
    grid = [
        ["項次", "料號", "品名", "數量", "單位"],
        [1, "", "內六角螺絲 ISO 4762 M8x30 12.9 鍍鋅", 5000, "pcs"],
    ]
    reading = rows_from_grid(grid, sheet_name="test")
    assert len(reading.rows) == 1
    assert reading.rows[0].quantity == Decimal("5000")


def test_a_quoted_reply_is_separated_from_the_newest_message():
    newest, history = split_thread(
        "Thanks, please proceed.\n\nOn 1 October Rosa wrote:\n> original enquiry"
    )
    assert newest == "Thanks, please proceed."
    assert "original enquiry" in history


def test_an_unreadable_file_type_is_reported_clearly():
    reading = read_attachment(b"whatever", "drawing.dwg")
    assert reading.parsed_with == "unavailable"
    assert reading.problems


# ---------------------------------------------------------------------------
# Answers in any language
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "attribute,answer,expected",
    [
        ("length_mm", "長度請用 40 mm。", "40"),
        ("length_mm", "please use 40mm long", "40"),
        ("property_class", "強度等級請用 12.9。", "12.9"),
        ("property_class", "class 10.9 please", "10.9"),
        ("finish", "表面處理請用鍍鋅（藍白鋅）。", "zinc_blue"),
        ("finish", "熱浸鍍鋅", "hot_dip_galvanised"),
        ("finish", "please use hot dip galvanised", "hot_dip_galvanised"),
        ("seal", "請用雙面密封。", "sealed_both"),
        ("seal", "sealed both sides", "sealed_both"),
        ("kind", "請用六角頭螺栓。", "hex_head_bolt"),
        ("thread", "螺紋請用 M10。", "M10"),
    ],
)
def test_an_answer_is_read_into_a_value(attribute, answer, expected):
    assert interpret_answer(attribute, answer) == expected


def test_an_answer_that_means_nothing_is_not_invented():
    assert interpret_answer("finish", "we will confirm later") == ""


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------
class _Line:
    """The fields the comparison reads off a stored quote line."""

    def __init__(self, identifier, number, text, reference, quantity):
        self.id = identifier
        self.line_number = number
        self.request_text = text
        self.original_request_text = text
        self.customer_reference = reference
        self.requested_quantity = Decimal(quantity)
        self.requested_unit = "piece"


class _Row:
    def __init__(self, number, description, reference, quantity):
        self.line_number = number
        self.description = description
        self.customer_reference = reference
        self.quantity = Decimal(quantity)
        self.unit = "piece"
        self.requested_date = ""
        self.note = ""
        self.source_reference = "test"


def test_only_changed_lines_are_marked_for_re_quoting():
    before = [
        _Line(1, 1, "ISO 4762 M8x30 12.9 zinc", "A-1", 1000),
        _Line(2, 2, "ISO 4762 M10x40 12.9 zinc", "A-2", 500),
        _Line(3, 3, "ISO 4032 M12 class 10 zinc", "A-3", 250),
    ]
    after = [
        _Row(1, "ISO 4762 M8x30 12.9 zinc", "A-1", 1000),       # unchanged
        _Row(2, "ISO 4762 M10x40 12.9 zinc", "A-2", 1500),      # quantity changed
        _Row(3, "ISO 4032 M12 class 10 zinc", "A-3", 250),      # unchanged
        _Row(4, "ISO 7089 M12 200 HV zinc", "", 4000),          # added
    ]
    plan = compare(before, after)
    assert len(plan.unchanged) == 2
    assert len(plan.quantity_changed) == 1
    assert len(plan.added) == 1
    assert len(plan.removed) == 0
    assert len(plan.requires_requote) == 2


def test_a_withdrawn_line_is_noticed():
    before = [
        _Line(1, 1, "ISO 4762 M8x30 12.9 zinc", "A-1", 1000),
        _Line(2, 2, "ISO 4762 M10x40 12.9 zinc", "A-2", 500),
    ]
    after = [_Row(1, "ISO 4762 M8x30 12.9 zinc", "A-1", 1000)]
    plan = compare(before, after)
    assert len(plan.removed) == 1
    assert plan.removed[0].line_number == 2


def test_the_same_description_on_two_lines_does_not_collapse_into_one():
    before = [
        _Line(1, 1, "ISO 4762 M8x30 12.9 zinc", "", 1000),
        _Line(2, 2, "ISO 4762 M8x30 12.9 zinc", "", 2000),
    ]
    after = [
        _Row(1, "ISO 4762 M8x30 12.9 zinc", "", 1000),
        _Row(2, "ISO 4762 M8x30 12.9 zinc", "", 2000),
    ]
    plan = compare(before, after)
    assert len(plan.unchanged) == 2
    assert not plan.removed
    assert not plan.added


def test_a_rewritten_specification_is_treated_as_a_change():
    before = [_Line(1, 1, "ISO 4762 M8x30 12.9 zinc", "A-1", 1000)]
    after = [_Row(1, "ISO 4762 M8x35 12.9 zinc", "A-1", 1000)]
    plan = compare(before, after)
    assert len(plan.specification_changed) == 1


# ---------------------------------------------------------------------------
# The demonstration script, all ten steps
# ---------------------------------------------------------------------------
def test_the_whole_demonstration_script_runs(signed_in, session):
    client = signed_in()
    case_id = None
    summaries = []

    for number in range(1, 11):
        response = client.post(f"/api/demo/step/{number}", json={"case_id": case_id})
        assert response.status_code == 200, f"step {number}: {response.text}"
        body = response.json()
        case_id = body.get("case_id", case_id)
        summaries.append(body.get("summary", ""))

    assert "33 matched" in summaries[0] or "matched" in summaries[0]
    assert "one email" in summaries[1]
    assert "waiting for a supplier" in summaries[2]
    assert "Traditional" in summaries[3]
    assert "lead time" in summaries[4]
    assert "Import duty on this quote moved" in summaries[6]
    assert "margin floor" in summaries[7]
    assert "re-quoted" in summaries[8]
    assert "sent" in summaries[9].lower()

    case = client.get(f"/api/cases/{case_id}").json()
    assert case["case"]["status"] == "sent"
    integrity = client.get(f"/api/cases/{case_id}/integrity").json()
    assert integrity["ok"] is True


def test_a_step_that_needs_a_higher_role_says_which_account_to_use(signed_in):
    client = signed_in("amy.chen@hengtai-industrial.example")
    response = client.post("/api/demo/step/7", json={})
    assert response.status_code == 403
    assert "paul.lee@hengtai-industrial.example" in response.json()["detail"]
