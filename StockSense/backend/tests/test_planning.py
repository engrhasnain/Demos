"""The whole route, from a part's history to a week's orders."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Part, PlanLine
from app.numbers import dec
from app.services import cashcap, demand as demand_service, history, plan, reorder, replay

TODAY = dt.date(2026, 10, 5)


class TestPreparingHistory:
    def test_an_empty_shelf_is_unknown_demand_not_zero_demand(self):
        """The loop this breaks.

        A zero recorded because there was nothing to sell teaches the
        forecast that demand is falling, so it orders less, so the shelf is
        empty more often. Parts that keep running out keep running out.
        """
        sold = [10.0] * 20 + [0.0] + [10.0] * 20
        empty = [False] * 20 + [True] + [False] * 20
        prepared = history.prepare(sold, empty)
        assert prepared.demand[20] == pytest.approx(10.0)
        assert prepared.recovered_units == pytest.approx(10.0)
        assert prepared.censored_weeks == [20]

    def test_a_genuine_quiet_week_is_left_alone(self):
        sold = [10.0] * 20 + [0.0] + [10.0] * 20
        prepared = history.prepare(sold, [False] * 41)
        assert prepared.demand[20] == 0.0
        assert not prepared.censored_weeks

    def test_a_project_order_is_kept_out_of_the_baseline(self):
        sold = [10.0] * 40
        sold[20] = 4000.0
        prepared = history.prepare(sold)
        assert 20 in prepared.project_weeks
        assert prepared.demand[20] < 100
        assert prepared.project_units > 3000

    def test_a_replaced_part_carries_its_predecessors_history(self):
        successor = [0.0] * 90 + [12.0] * 14
        predecessor = [11.0] * 104
        joined = history.carry_forward(successor, predecessor)
        assert len(joined) == 104
        assert joined[10] == 11.0, "the old part's weeks fill the gap"
        assert joined[100] == 12.0, "the new part's own weeks win"


class TestDemandForOnePart:
    def test_every_part_gets_a_forecast_and_a_pattern(self, session):
        for part in session.scalars(select(Part).limit(40)):
            view = demand_service.for_part(session, part)
            assert view.pattern.kind
            assert view.forecast.method
            assert view.weekly_rate >= 0

    def test_a_part_with_two_years_of_nothing_is_not_treated_as_new(self, session):
        """Otherwise dead stock borrows the family's demand and gets reordered.

        A part that has not existed long and a part nobody wants look alike
        if you only count the weeks that sold. They are told apart by when
        the sales start, not by how many there are.
        """
        dead = None
        for part in session.scalars(select(Part).limit(600)):
            view = demand_service.for_part(session, part)
            if sum(view.prepared.demand) == 0:
                dead = view
                break
        if dead is None:
            pytest.skip("no part with an empty history in this sample")
        assert dead.weekly_rate == 0.0
        assert not dead.forecast.borrowed

    def test_a_genuinely_new_part_borrows_and_says_so(self, session):
        borrowed = None
        for part in session.scalars(select(Part).limit(600)):
            view = demand_service.for_part(session, part)
            if view.forecast.borrowed:
                borrowed = view
                break
        if borrowed is None:
            pytest.skip("no new part in this sample")
        assert borrowed.analogue_of
        assert borrowed.forecast.notes
        # A borrowed forecast has to carry a wider range than its own would.
        assert borrowed.forecast.deviation >= borrowed.forecast.rate


class TestTheWeeklyPlan:
    def test_every_part_gets_a_decision(self, session):
        summary = plan.run_plan(session, limit=150)
        lines = list(session.scalars(
            select(PlanLine).where(PlanLine.run_id == summary.run.id)
        ))
        assert len(lines) == summary.run.parts_considered == 150
        assert all(line.decision for line in lines)

    def test_the_cash_cap_is_never_exceeded(self, session):
        summary = plan.run_plan(session, limit=200, cash_cap=50_000)
        assert dec(summary.run.cash_committed) <= dec(50_000)
        assert summary.allocation.committed <= summary.allocation.cap

    def test_a_tighter_cap_buys_less_and_defers_more(self, session):
        generous = plan.run_plan(session, limit=150, cash_cap=50_000_000)
        session.flush()
        tight = plan.run_plan(session, limit=150, cash_cap=20_000)
        assert tight.run.lines_recommended <= generous.run.lines_recommended
        assert tight.run.lines_deferred >= generous.run.lines_deferred

    def test_every_recommendation_can_account_for_itself(self, session):
        """The fourth acceptance bar, as a test rather than a promise."""
        summary = plan.run_plan(session, limit=120)
        for line in session.scalars(
            select(PlanLine).where(PlanLine.run_id == summary.run.id)
        ):
            assert line.demand_method, f"{line.part.code} has no demand model"
            assert dec(line.lead_time_days) > 0, f"{line.part.code} has no lead time"
            assert line.trace and line.trace.get("steps"), f"{line.part.code} shows no working"
            if line.decision in {"order", "prebuild"}:
                assert dec(line.value) > 0, f"{line.part.code} orders without a cost"

    def test_dead_stock_is_found_rather_than_reordered(self, session):
        summary = plan.run_plan(session, limit=400)
        reasons = {
            line.reason
            for line in session.scalars(
                select(PlanLine).where(PlanLine.run_id == summary.run.id)
            )
        }
        assert "dead_stock" in reasons or "no_demand" in reasons

    def test_a_replaced_part_is_not_bought(self, session):
        summary = plan.run_plan(session, limit=400)
        for line in session.scalars(
            select(PlanLine).where(PlanLine.run_id == summary.run.id)
        ):
            if line.part.replaced_by_part_id:
                assert line.quantity == 0, f"{line.part.code} has a successor"


class TestTheCashCap:
    def _fake(self, value: float, urgency: float, minimum: float = 0.0):
        class Supplier:
            id = 1
            name = "Test supplier"
            minimum_order_value = dec(minimum)

        class FakePart:
            supplier_id = 1
            supplier = Supplier()
            code = "TEST"

        return reorder.Recommendation(
            part=FakePart(),
            view=None,
            decision=reorder.ORDER,
            reason="below_reorder_point",
            quantity=1,
            raw_quantity=1.0,
            value=dec(value),
            policy=None,
            position=0.0,
            days_of_cover=0.0,
            urgency=urgency,
            shutdown=None,
        )

    def test_everything_fits_when_there_is_room(self):
        allocation = cashcap.allocate(
            [self._fake(100, 1.0), self._fake(200, 1.0)], 1000
        )
        assert len(allocation.accepted) == 2
        assert not allocation.deferred

    def test_the_cheap_urgent_part_is_bought_before_the_expensive_calm_one(self):
        """Sorting by value buys the wrong things and runs out of money."""
        urgent_and_cheap = self._fake(100, 5.0)
        calm_and_dear = self._fake(900, 1.0)
        allocation = cashcap.allocate([calm_and_dear, urgent_and_cheap], 500)
        assert urgent_and_cheap in allocation.accepted
        assert calm_and_dear in allocation.deferred

    def test_a_supplier_under_its_minimum_is_dropped_whole(self):
        """Part of a minimum order is a rejected order, not a cheaper one."""
        allocation = cashcap.allocate([self._fake(100, 1.0, minimum=5000)], 1000)
        assert not allocation.accepted
        assert allocation.deferred[0].reason == "below_minimum"
        assert allocation.below_minimum


class TestTheReplay:
    def test_the_forecast_at_a_week_cannot_see_past_it(self):
        """The property that makes a backtest worth anything.

        The replay forecasts from ``demand[:week]`` and nowhere else. A
        spike after that point must not change the answer, or the model is
        being shown the future and every figure that follows is worthless.
        """
        from app.domain import classify, forecast as models

        training = [10.0] * 52
        quiet_future = training + [0.0] * 52
        wild_future = training + [0.0] * 52
        wild_future[80] = 50_000.0

        week = 52
        before = models.run(
            classify.classify(quiet_future[:week]).suggested_method,
            quiet_future[:week],
        )
        after = models.run(
            classify.classify(wild_future[:week]).suggested_method,
            wild_future[:week],
        )
        assert before.rate == after.rate
        assert quiet_future[:week] == wild_future[:week]

    def test_the_replay_gives_the_same_answer_twice(self, session):
        """No hidden state and no randomness, so a buyer can check it."""
        first = replay.run_replay(session, weeks=26, limit=40)
        second = replay.run_replay(session, weeks=26, limit=40)
        assert first["stocksense"] == second["stocksense"]
        assert first["buyers"] == second["buyers"]

    def test_both_arms_face_the_same_demand_and_the_same_opening_stock(self, session):
        report = replay.run_replay(session, weeks=26, limit=40)
        assert report["parts"] > 0
        assert report["weeks"] == 26
        # Neither arm can be judged against a different year.
        assert len(report["weekly"]) == 26

    def test_it_reports_the_occasional_parts_separately(self, session):
        report = replay.run_replay(session, weeks=26, limit=120)
        assert report["by_pattern"]
        assert any(row["intermittent"] for row in report["by_pattern"])

    def test_it_says_when_a_flat_zero_would_have_scored_better(self, session):
        report = replay.run_replay(session, weeks=26, limit=120)
        trap = report["accuracy"]["zero_trap"]
        assert trap["parts_scored"] > 0
        assert "stock-outs and money" in trap["verdict"]
