"""Run the whole demonstration from the command line.

    python backend/scripts/walkthrough.py
    python backend/scripts/walkthrough.py --evaluate

It loads the data, puts the twelve document batch through the real pipeline,
prints what a person would see for each one, then proves the retry is safe and
prints the dashboard numbers. It exits non-zero if anything is wrong, so it
works as a smoke test as well as a rehearsal.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import create_all, session_scope  # noqa: E402
from app.money import dec, money  # noqa: E402
from app.seed import generator, invoices as sample_invoices  # noqa: E402
from app.models import Invoice, User  # noqa: E402
from app.services import approvals, pipeline, posting, workflow  # noqa: E402


def heading(text: str) -> None:
    print("\n" + text)
    print("-" * len(text))


def _empty_the_tray(session) -> int:
    """Remove the invoices and their documents, keeping the company itself."""
    from sqlalchemy import delete, func, select

    from app.models import (
        Approval,
        CallBackTask,
        Document,
        Exception_,
        Invoice,
        InvoiceEvent,
        InvoiceLine,
        LedgerBill,
        Posting,
        Vendor,
    )

    count = session.scalar(select(func.count(Invoice.id))) or 0
    if not count:
        return 0
    for model in (
        InvoiceEvent, InvoiceLine, Exception_, Approval, Posting, LedgerBill,
        CallBackTask, Invoice, Document,
    ):
        session.execute(delete(model))
    # A supplier left flagged would block the new batch for reasons that
    # belong to the batch before it.
    for vendor in session.scalars(select(Vendor).where(Vendor.bank_change_pending.is_(True))):
        vendor.bank_change_pending = False
    session.flush()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the LedgerFlow demonstration.")
    parser.add_argument("--small", action="store_true", help="fewer suppliers and orders")
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="keep the suppliers and orders already loaded, and start the batch again",
    )
    parser.add_argument("--evaluate", action="store_true", help="also run the acceptance criteria")
    arguments = parser.parse_args()

    create_all()
    failures = 0

    if not arguments.skip_load:
        heading("Loading the demonstration data")
        started = time.perf_counter()
        with session_scope() as session:
            counts = generator.build_demo_data(
                session,
                vendor_target=40 if arguments.small else 140,
                order_target=60 if arguments.small else 220,
            )
        print(f"Loaded in {time.perf_counter() - started:.1f} seconds:")
        for key, value in counts.items():
            print(f"  {key.replace('_', ' '):<24} {value:>8,}")

    # ------------------------------------------------------------------
    heading("The batch")
    with session_scope() as session:
        # Running the batch on top of a batch that has already run would make
        # every document a duplicate of itself. That is the guard working, but
        # it is not what this script is here to show, so the tray is emptied
        # first. The suppliers, orders and deliveries are left alone.
        cleared = _empty_the_tray(session)
        if cleared:
            print(f"Cleared {cleared} invoices from an earlier run.")

        batch = sample_invoices.build_batch(session)
        print(f"{len(batch)} documents prepared")

        results = []
        for document in batch:
            invoice, _created = pipeline.receive(
                session,
                filename=document.filename,
                content=document.content,
                content_type=document.content_type,
                text=document.text,
                barcode_payload=document.barcode_payload,
                received_from=document.received_from,
                kind=document.kind,
            )
            try:
                if document.key == "clean":
                    # Held one step short of the ledger, so the crash and
                    # retry below have something real to post.
                    pipeline.read(session, invoice)
                    pipeline.check(session, invoice)
                else:
                    pipeline.run(session, invoice)
            except Exception as error:  # pragma: no cover - surfaced below
                print(f"  {document.key}: FAILED {type(error).__name__}: {error}")
                failures += 1
                continue
            results.append((document, invoice))

        print()
        print(f"  {'what it tests':<34} {'status':<22} {'payable':>12}  {'held':>10}")
        print("  " + "-" * 82)
        untouched = 0
        for document, invoice in results:
            if invoice.posted_untouched:
                untouched += 1
            # Worst first, the same order the screen uses, so the line here
            # says what a clerk would actually be shown.
            rank = {"block": 0, "hold": 1, "note": 2}
            exceptions = sorted(
                (e for e in invoice.exceptions if e.resolved_at is None),
                key=lambda e: rank.get(e.severity, 3),
            )
            status = workflow.LABELS.get(invoice.status, invoice.status)
            if exceptions:
                status += f" ({exceptions[0].kind})"
            print(
                f"  {document.key:<34} {status:<22} "
                f"{money(invoice.approved_amount):>12}  {money(invoice.held_amount):>10}"
            )

        print()
        print(f"  posted with nobody touching them: {untouched} of {len(results)}")

        # --------------------------------------------------------------
        heading("Checks that have to hold")

        by_key = {d.key: i for d, i in results}

        def check(name: str, condition: bool, detail: str = "") -> None:
            nonlocal failures
            print(f"  {'pass' if condition else 'FAIL'}  {name}" + (f" - {detail}" if detail else ""))
            if not condition:
                failures += 1

        duplicate = by_key.get("duplicate")
        check(
            "the repeat is blocked as a duplicate",
            duplicate is not None
            and any(e.kind == "duplicate" for e in duplicate.exceptions),
            duplicate.status if duplicate else "missing",
        )

        bank = by_key.get("bank_change")
        check(
            "the new bank account is a hard stop",
            bank is not None
            and any(
                e.kind == "bank_detail_change" and e.severity == "block"
                for e in bank.exceptions
            ),
        )
        if bank is not None and bank.vendor is not None:
            check(
                "the supplier record was not changed",
                any(a.is_current for a in bank.vendor.bank_accounts)
                and bank.vendor.bank_change_pending,
            )

        wrong = by_key.get("wrong_buyer")
        check(
            "the wrong business number is refused",
            wrong is not None
            and any(e.kind == "wrong_buyer_tax_id" for e in wrong.exceptions),
        )

        partial = by_key.get("partial_delivery")
        check(
            "only what arrived is payable",
            partial is not None and dec(partial.held_amount) > 0,
            f"{money(partial.held_amount)} held" if partial else "",
        )

        freight = by_key.get("freight_allowance")
        if freight is not None:
            allowed = [
                line
                for line in freight.lines
                if line.match_result == "not_ordered" and dec(line.payable_amount) > 0
            ]
            check(
                "the delivery charge inside the allowance is accepted",
                bool(allowed),
                f"{money(allowed[0].payable_amount)} accepted" if allowed else "none accepted",
            )

        electronic = by_key.get("uniform_electronic")
        check(
            "the barcode was used",
            electronic is not None and electronic.field_confidence.get("invoice_number") == 1.0,
        )

        statement = by_key.get("forwarder_statement")
        check(
            "the four page statement was read in full",
            statement is not None and len(statement.lines) >= 16,
            f"{len(statement.lines)} lines" if statement else "",
        )

        dollars = by_key.get("foreign_currency")
        check(
            "the dollar invoice was converted",
            dollars is not None and dec(dollars.amount_in_base) > dec(dollars.total_amount),
        )

        # --------------------------------------------------------------
        heading("Posting the same invoice twice")
        clean = by_key.get("clean")
        if clean is None:
            print("  no clean invoice to test with")
            failures += 1
        else:
            # Clear anything in the way, so this tests the retry and nothing
            # else. Each signature comes from somebody who holds that role,
            # and the second one from a different person, as the rules demand.
            from sqlalchemy import select as _select

            def _signer(role: str, used: set[int]):
                for candidate in session.scalars(_select(User).where(User.role == role)):
                    if candidate.id not in used:
                        return candidate
                return session.scalar(_select(User).where(User.role == "administrator"))

            used_signers: set[int] = set()
            for approval in list(approvals.outstanding(session, clean)):
                signer = _signer(approval.required_role, used_signers)
                used_signers.add(signer.id)
                approvals.decide(
                    session, approval, signer, approved=True, comment="Walkthrough."
                )
            # Everything up to here is settled first. The rollback below has
            # to undo the half finished posting and nothing else.
            session.commit()
            clean_id = clean.id
            before = len(posting.bills_for(session, clean))
            try:
                pipeline.post_to_ledger(session, clean, fail_after_ledger_write=True)
            except posting.LedgerUnavailable as error:
                print(f"  the connection dropped: {error}")
            except pipeline.PipelineError as error:
                print(f"  it could not be posted at all: {error}")
                failures += 1
                session.rollback()
                clean = None
            session.rollback()
            clean = session.get(Invoice, clean_id) if clean is not None else None
            if clean is None:
                return 1
            try:
                pipeline.post_to_ledger(session, clean)
            except Exception as error:
                print(f"  the retry failed: {error}")
                failures += 1
            after = len(posting.bills_for(session, clean))
            print(f"  bills in the ledger before {before}, after the crash and retry {after}")
            check("exactly one bill after a crash and a retry", after == 1, f"{after} found")

    # ------------------------------------------------------------------
    if arguments.evaluate:
        heading("Acceptance criteria")
        from app.evaluation.runner import run_evaluation

        with session_scope() as session:
            report = run_evaluation(session)
        for criterion in report["criteria"]:
            mark = {True: "pass", False: "FAIL", None: "not measured"}[criterion["passed"]]
            print(f"  {criterion['name']:<30} {mark:<13} {criterion['measured']}")
        print(f"  {report['statement']}")
        if not report["passed"]:
            failures += 1

    heading("Result")
    if failures:
        print(f"  {failures} check(s) did not pass.")
        return 1
    print("  Every document was handled and every check held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
