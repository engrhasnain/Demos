"""Measure the product against the bars it was sold on.

Every number here is produced by putting documents with a known right answer
through the same pipeline the screens use. Nothing is asserted, estimated or
remembered from a previous run.

The whole measurement happens inside a savepoint that is rolled back at the
end, so running it does not leave a few hundred test invoices in the demo.
"""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..money import dec
from ..models import EvaluationRun
from ..services import approvals, pipeline, posting
from .cases import Case, build_cases, retry_cases

#: name -> (what it means, the bar, how it is measured)
CRITERIA: list[dict[str, Any]] = [
    {
        "name": "header fields",
        "question": "Of the fields on the front of an invoice, how many are read right?",
        "bar": 98.0,
        "unit": "%",
    },
    {
        "name": "line items",
        "question": "Of the figures on the lines, how many are read right?",
        "bar": 94.0,
        "unit": "%",
    },
    {
        "name": "repeats caught",
        "question": "Of the invoices sent twice, how many were stopped?",
        "bar": 100.0,
        "unit": "%",
    },
    {
        "name": "bank changes blocked",
        "question": "Of the invoices asking for a new account, how many were blocked?",
        "bar": 100.0,
        "unit": "%",
    },
    {
        "name": "posted untouched",
        "question": "Of the invoices with nothing wrong, how many reached the ledger alone?",
        "bar": 60.0,
        "unit": "%",
    },
    {
        "name": "duplicate bills after a crash",
        "question": "After the ledger dropped the connection halfway, how many bills were paid twice?",
        "bar": 0.0,
        "unit": "count",
        "lower_is_better": True,
    },
]


def _equal_number(expected: str, actual: Any) -> bool:
    try:
        return dec(expected) == dec(actual)
    except Exception:
        return False


def _equal_text(expected: str, actual: Any) -> bool:
    return str(expected or "").strip().casefold() == str(actual or "").strip().casefold()


def _run_case(session: Session, case: Case):
    invoice, _created = pipeline.receive(
        session,
        filename=case.filename,
        content=case.content,
        content_type="application/pdf",
        text=case.text,
        barcode_payload=case.barcode_payload,
        received_from=case.received_from,
        kind=case.kind,
    )
    pipeline.run(session, invoice)
    return invoice


# ---------------------------------------------------------------------------
# The individual measurements
# ---------------------------------------------------------------------------
def _score_reading(case: Case, invoice) -> tuple[int, int, int, int, list[str]]:
    """Returns header right, header total, line right, line total, misses."""
    misses: list[str] = []

    checks: list[tuple[str, bool]] = [
        ("invoice_number", _equal_text(case.header_truth["invoice_number"], invoice.invoice_number_read)),
        (
            "invoice_date",
            invoice.invoice_date is not None
            and invoice.invoice_date.isoformat() == case.header_truth["invoice_date"],
        ),
        (
            "purchase_order_number",
            _equal_text(
                case.header_truth["purchase_order_number"], invoice.purchase_order_number_read
            ),
        ),
        (
            "seller_tax_identifier",
            _equal_text(
                case.header_truth["seller_tax_identifier"], invoice.seller_tax_identifier_read
            ),
        ),
        (
            "buyer_tax_identifier",
            _equal_text(
                case.header_truth["buyer_tax_identifier"], invoice.buyer_tax_identifier_read
            ),
        ),
        ("net_amount", _equal_number(case.header_truth["net_amount"], invoice.net_amount)),
        ("tax_amount", _equal_number(case.header_truth["tax_amount"], invoice.tax_amount)),
        ("total_amount", _equal_number(case.header_truth["total_amount"], invoice.total_amount)),
    ]
    header_right = sum(1 for _name, ok in checks if ok)
    for name, ok in checks:
        if not ok:
            misses.append(f"{case.key}: {name}")

    # Lines are paired by part code, because the order they are printed in is
    # the supplier's business, not ours. A part can appear twice on one order,
    # so each read line is claimed once and then taken out of the running.
    unclaimed = [line for line in invoice.lines]
    line_right = 0
    line_total = 0
    for truth in case.line_truth:
        line_total += 3
        line = None
        for candidate in unclaimed:
            if candidate.part_code != truth["part_code"]:
                continue
            if line is None:
                line = candidate
            # Prefer the one whose figures agree, so a repeated part code is
            # paired with its own row rather than with its twin.
            elif _equal_number(truth["quantity"], candidate.quantity):
                line = candidate
                break
        if line is None:
            misses.append(f"{case.key}: line {truth['part_code']} not read")
            continue
        unclaimed.remove(line)
        for field_name, column in (
            ("quantity", line.quantity),
            ("unit_price", line.unit_price),
            ("line_total", line.line_total),
        ):
            if _equal_number(truth[field_name], column):
                line_right += 1
            else:
                misses.append(f"{case.key}: line {truth['part_code']} {field_name}")
    return header_right, len(checks), line_right, line_total, misses


def _measure_retry_safety(session: Session, count: int) -> tuple[int, int]:
    """Crash the ledger halfway through, retry, and count the bills.

    Returns how many were attempted and how many ended up billed twice.
    """
    attempted = 0
    duplicated = 0
    for case in retry_cases(session, count=count):
        invoice, _created = pipeline.receive(
            session,
            filename=case.filename,
            content=case.content,
            content_type="application/pdf",
            text=case.text,
            received_from=case.received_from,
        )
        pipeline.read(session, invoice)
        pipeline.check(session, invoice)
        if approvals.blocking_reasons(session, invoice):
            continue
        for approval in approvals.outstanding(session, invoice):
            approval.status = "approved"
            approval.decided_at = dt.datetime.now(dt.timezone.utc)
        session.flush()

        attempted += 1
        savepoint = session.begin_nested()
        try:
            pipeline.post_to_ledger(session, invoice, fail_after_ledger_write=True)
        except posting.LedgerUnavailable:
            pass
        except Exception:
            savepoint.rollback()
            continue
        savepoint.rollback()

        try:
            pipeline.post_to_ledger(session, invoice)
        except Exception:
            pass
        if len(posting.bills_for(session, invoice)) > 1:
            duplicated += 1
    return attempted, duplicated


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------
def run_evaluation(
    session: Session,
    *,
    clean_count: int = 120,
    duplicate_count: int = 40,
    bank_change_count: int = 20,
    retry_count: int = 50,
    save: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = dt.datetime.now(dt.timezone.utc)

    header_right = header_total = 0
    line_right = line_total = 0
    duplicates_caught = duplicates_planted = 0
    bank_blocked = bank_planted = 0
    untouched = clean_seen = 0
    misses: list[str] = []
    retry_attempted = retry_duplicated = 0

    outer = session.begin_nested()
    try:
        case_count = 0
        cases = build_cases(
            session,
            clean_count=clean_count,
            duplicate_count=duplicate_count,
            bank_change_count=bank_change_count,
        )
        case_count = len(cases)
        for case in cases:
            try:
                invoice = _run_case(session, case)
            except Exception as error:  # a crash is a failure, not an excuse
                misses.append(f"{case.key}: {type(error).__name__}: {error}")
                continue

            if case.header_truth:
                hr, ht, lr, lt, case_misses = _score_reading(case, invoice)
                header_right += hr
                header_total += ht
                line_right += lr
                line_total += lt
                misses.extend(case_misses[:3])

            if case.expect_clean:
                clean_seen += 1
                if invoice.posted_untouched:
                    untouched += 1
            if case.expect_duplicate:
                duplicates_planted += 1
                if any(e.kind == "duplicate" for e in invoice.exceptions):
                    duplicates_caught += 1
                else:
                    misses.append(f"{case.key}: repeat not caught")
            if case.expect_bank_block:
                bank_planted += 1
                if any(
                    e.kind == "bank_detail_change" and e.severity == "block"
                    for e in invoice.exceptions
                ):
                    bank_blocked += 1
                else:
                    misses.append(f"{case.key}: bank change not blocked")

    finally:
        outer.rollback()
        session.expunge_all()

    # The retry test needs orders that have not been billed yet, so it runs
    # on its own, in a savepoint of its own, against the untouched data.
    retry_savepoint = session.begin_nested()
    try:
        retry_attempted, retry_duplicated = _measure_retry_safety(session, retry_count)
    finally:
        retry_savepoint.rollback()
        session.expunge_all()

    def share(part: int, whole: int) -> float:
        return round(100.0 * part / whole, 2) if whole else 0.0

    measured = {
        "header fields": share(header_right, header_total),
        "line items": share(line_right, line_total),
        "repeats caught": share(duplicates_caught, duplicates_planted),
        "bank changes blocked": share(bank_blocked, bank_planted),
        "posted untouched": share(untouched, clean_seen),
        "duplicate bills after a crash": float(retry_duplicated),
    }
    counted = {
        "header fields": f"{header_right} of {header_total} fields",
        "line items": f"{line_right} of {line_total} figures",
        "repeats caught": f"{duplicates_caught} of {duplicates_planted} planted",
        "bank changes blocked": f"{bank_blocked} of {bank_planted} planted",
        "posted untouched": f"{untouched} of {clean_seen} clean invoices",
        "duplicate bills after a crash": f"{retry_duplicated} after {retry_attempted} dropped connections",
    }

    criteria: list[dict[str, Any]] = []
    everything_held = True
    for spec in CRITERIA:
        value = measured[spec["name"]]
        if spec.get("lower_is_better"):
            passed = value <= spec["bar"]
        else:
            passed = value >= spec["bar"]
        everything_held = everything_held and passed
        criteria.append(
            {
                "name": spec["name"],
                "question": spec["question"],
                "bar": spec["bar"],
                "unit": spec["unit"],
                "value": value,
                "measured": counted[spec["name"]],
                "passed": passed,
            }
        )

    seconds = round(time.perf_counter() - started, 2)
    report: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "seconds": seconds,
        "engine": settings.reading_engine,
        "sample_size": case_count,
        "criteria": criteria,
        "passed": everything_held,
        "misses": misses[:40],
        "statement": (
            f"{case_count} documents and {retry_attempted} dropped connections, "
            f"in {seconds} seconds, read by the {settings.reading_engine} engine."
        ),
    }

    if save:
        run = EvaluationRun(
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            engine=settings.reading_engine,
            sample_size=case_count,
            passed=everything_held,
            results=criteria,
            notes=report["statement"],
        )
        session.add(run)
        session.flush()
        report["id"] = run.id

    return report


def last_run(session: Session) -> dict[str, Any] | None:
    from sqlalchemy import select

    run = session.scalar(select(EvaluationRun).order_by(EvaluationRun.id.desc()).limit(1))
    if run is None:
        return None
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "engine": run.engine,
        "sample_size": run.sample_size,
        "passed": run.passed,
        "criteria": run.results,
        "statement": run.notes,
    }
