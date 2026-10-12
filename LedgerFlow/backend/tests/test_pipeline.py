"""What the product does to a document, end to end.

These run the real batch through the real pipeline. Each test names the one
thing the document exists to prove.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.money import dec, money
from app.services import approvals, guards, pipeline, posting, workflow


def exceptions_of(invoice) -> set[str]:
    return {e.kind for e in invoice.exceptions if e.resolved_at is None}


class TestTheOrdinaryCase:
    def test_an_invoice_that_agrees_reaches_the_ledger_with_nobody_touching_it(self, processed):
        untouched = [i for i in processed.values() if i.posted_untouched]
        assert len(untouched) >= 5, "the batch should not be all hard cases"
        for invoice in untouched:
            assert invoice.status == workflow.POSTED
            assert not invoice.touched_by_a_person
            assert dec(invoice.held_amount) == 0

    def test_nothing_in_the_batch_was_lost(self, processed, batch):
        assert len(processed) == len(batch)
        for invoice in processed.values():
            assert invoice.id is not None
            assert invoice.document is not None


class TestDuplicates:
    def test_the_same_invoice_in_a_different_disguise_is_stopped(self, processed):
        duplicate = processed["duplicate"]
        assert "duplicate" in exceptions_of(duplicate)
        assert duplicate.status == workflow.EXCEPTION

    def test_a_duplicate_is_a_hard_stop_not_a_warning(self, processed):
        duplicate = processed["duplicate"]
        row = next(e for e in duplicate.exceptions if e.kind == "duplicate")
        assert row.severity == "block"

    def test_the_repeat_names_the_invoice_it_repeats(self, processed):
        duplicate = processed["duplicate"]
        row = next(e for e in duplicate.exceptions if e.kind == "duplicate")
        assert row.detail.get("matches"), "a duplicate that cannot say what it matches is useless"


class TestBankDetails:
    def test_a_new_account_blocks_the_payment(self, processed):
        invoice = processed["bank_change"]
        row = next(e for e in invoice.exceptions if e.kind == "bank_detail_change")
        assert row.severity == "block"

    def test_the_supplier_record_is_not_changed_by_the_invoice(self, processed):
        invoice = processed["bank_change"]
        vendor = invoice.vendor
        assert vendor.bank_change_pending
        assert any(a.is_current for a in vendor.bank_accounts)
        assert invoice.bank_account_read not in {
            a.account_number for a in vendor.bank_accounts if a.is_current
        }

    def test_a_call_back_is_raised_against_the_number_already_on_file(self, processed, session):
        invoice = processed["bank_change"]
        from sqlalchemy import select

        from app.models import CallBackTask

        task = session.scalar(
            select(CallBackTask).where(CallBackTask.vendor_id == invoice.vendor_id)
        )
        assert task is not None
        assert task.telephone_on_file == invoice.vendor.telephone
        assert task.status == "open"

    def test_nothing_from_that_supplier_posts_while_the_call_is_outstanding(
        self, processed, session
    ):
        invoice = processed["bank_change"]
        reasons = approvals.blocking_reasons(session, invoice)
        assert any("bank" in reason.lower() for reason in reasons)
        with pytest.raises(pipeline.PipelineError):
            pipeline.post_to_ledger(session, invoice)

    def test_only_a_confirmed_telephone_call_changes_the_account(self, processed, session):
        from sqlalchemy import select

        from app.models import CallBackTask, User

        invoice = processed["bank_change"]
        task = session.scalar(
            select(CallBackTask).where(CallBackTask.vendor_id == invoice.vendor_id)
        )
        controller = session.scalar(select(User).where(User.role == "controller"))
        new_number = invoice.bank_account_read

        guards.complete_call_back(
            session, task, user_id=controller.id, confirmed=True, note="Spoke to the owner."
        )
        current = [a.account_number for a in invoice.vendor.bank_accounts if a.is_current]
        assert current == [new_number]
        assert not invoice.vendor.bank_change_pending


class TestThreeWayMatch:
    def test_only_what_arrived_is_payable(self, processed):
        invoice = processed["partial_delivery"]
        assert dec(invoice.held_amount) > 0
        assert exceptions_of(invoice) & {"partly_received", "not_received"}

    def test_the_held_amount_and_the_payable_amount_add_up_to_the_invoice(self, processed):
        invoice = processed["partial_delivery"]
        lines = sum((dec(line.line_total) for line in invoice.lines), Decimal("0"))
        split = dec(invoice.approved_amount) + dec(invoice.held_amount)
        # The split is of the net, before business tax.
        assert abs(split - lines) <= Decimal("1")

    def test_every_line_can_show_its_working(self, processed):
        invoice = processed["partial_delivery"]
        for line in invoice.lines:
            assert line.calculation_trace, "a figure nobody can explain is a figure nobody trusts"

    def test_a_delivery_charge_inside_the_allowance_is_accepted(self, processed):
        invoice = processed["freight_allowance"]
        extra = [line for line in invoice.lines if line.match_result == "not_ordered"]
        assert extra, "the freight line should be recognised as not on the order"
        assert dec(extra[0].payable_amount) == Decimal("850.00")


class TestIdentity:
    def test_an_invoice_made_out_to_somebody_else_is_refused(self, processed):
        invoice = processed["wrong_buyer"]
        assert "wrong_buyer_tax_id" in exceptions_of(invoice)
        assert dec(invoice.approved_amount) == 0

    def test_a_credit_note_is_not_three_way_matched(self, processed):
        invoice = processed["credit_note"]
        assert invoice.kind == "credit_note"
        assert dec(invoice.total_amount) < 0 or dec(invoice.approved_amount) <= 0


class TestCurrency:
    def test_a_dollar_invoice_is_converted_and_keeps_both_figures(self, processed):
        invoice = processed["foreign_currency"]
        assert invoice.currency == "USD"
        assert invoice.exchange_rate is not None
        assert dec(invoice.amount_in_base) > dec(invoice.total_amount)
        assert dec(invoice.amount_in_base) == (
            dec(invoice.total_amount) * dec(invoice.exchange_rate)
        ).quantize(Decimal("0.01"))


class TestPostingIsRetrySafe:
    def test_the_key_is_the_same_for_the_same_invoice_and_different_otherwise(self, processed):
        keys = {key: posting.idempotency_key(i) for key, i in processed.items()}
        invoice = next(iter(processed.values()))
        assert posting.idempotency_key(invoice) == posting.idempotency_key(invoice)
        assert len(set(keys.values())) == len(keys), "two invoices must not share a key"

    def test_a_crash_after_the_ledger_write_does_not_produce_a_second_bill(
        self, session, ready_to_post
    ):
        invoice = ready_to_post
        assert len(posting.bills_for(session, invoice)) == 0

        savepoint = session.begin_nested()
        with pytest.raises(posting.LedgerUnavailable):
            pipeline.post_to_ledger(session, invoice, fail_after_ledger_write=True)
        savepoint.rollback()

        pipeline.post_to_ledger(session, invoice)
        assert len(posting.bills_for(session, invoice)) == 1

    def test_posting_an_invoice_twice_is_accepted_and_still_leaves_one_bill(
        self, session, ready_to_post
    ):
        """Deliberately not an error.

        A caller that cannot tell whether its first attempt landed has to be
        able to ask again. Refusing the second attempt would push the caller
        into guessing, which is exactly how an invoice gets paid twice.
        """
        invoice = ready_to_post
        first = pipeline.post_to_ledger(session, invoice)
        second = pipeline.post_to_ledger(session, invoice)

        assert len(posting.bills_for(session, invoice)) == 1
        assert first.detail["created_a_bill"] is True
        assert second.detail["created_a_bill"] is False
        assert second.detail["found_an_existing_bill"] is True
        assert first.detail["external_reference"] == second.detail["external_reference"]
        assert second.detail["attempts"] == first.detail["attempts"] + 1


    def test_the_figures_moving_after_posting_cannot_make_a_second_bill(
        self, session, ready_to_post
    ):
        """The loophole in the retry key.

        The key is a hash of the figures, so when a late goods receipt makes
        more of an invoice payable, the key changes with it. Without a guard,
        posting again looks like a brand new posting and writes a second
        bill: the supplier is paid twice, by the module whose whole job is to
        stop exactly that.
        """
        invoice = ready_to_post
        pipeline.post_to_ledger(session, invoice)
        assert len(posting.bills_for(session, invoice)) == 1
        first = posting.bills_for(session, invoice)[0].external_reference

        invoice.approved_amount = money(dec(invoice.approved_amount) + Decimal("1000"))
        session.flush()

        with pytest.raises(pipeline.PipelineError) as error:
            pipeline.post_to_ledger(session, invoice)
        assert "already in the ledger" in str(error.value)

        from sqlalchemy import select as _select

        from app.models import LedgerBill

        rows = list(
            session.scalars(
                _select(LedgerBill).where(
                    LedgerBill.invoice_number == invoice.invoice_number_read
                )
            )
        )
        assert [row.external_reference for row in rows] == [first]


class TestTheStateMachine:
    def test_a_move_that_is_not_on_the_map_is_refused(self):
        with pytest.raises(workflow.IllegalTransition):
            workflow.assert_can_move(workflow.RECEIVED, workflow.POSTED)

    def test_a_finished_invoice_cannot_move(self):
        for finished in workflow.TERMINAL:
            assert workflow.TRANSITIONS[finished] == set()

    def test_the_refusal_says_what_is_allowed_instead(self):
        with pytest.raises(workflow.IllegalTransition) as error:
            workflow.assert_can_move(workflow.RECEIVED, workflow.POSTED)
        assert "Allowed from here" in str(error.value)
