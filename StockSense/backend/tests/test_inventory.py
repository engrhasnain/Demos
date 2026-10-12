"""Lead times, cover, shutdowns and the cash cap."""

from __future__ import annotations

import datetime as dt

import pytest

from app.clock import today
from app.domain import calendar as shutdowns, leadtime, safetystock, uncertainty
from app.numbers import round_to_pack, z_for_service_level

#: Taken from the clock, not typed in. A pinned date here passes until the
#: day it does not: the generated data is laid out relative to the real
#: today, and the same mistake in QuoteAgent's pricing tests failed six of
#: them overnight.
TODAY = today()


class TestLeadTime:
    def test_the_quote_is_kept_and_the_record_is_used(self):
        profile = leadtime.profile(28, [34, 36, 31, 39, 33, 35])
        assert profile.quoted_days == 28
        assert profile.average_days > 28
        assert profile.slippage_days > 5

    def test_too_few_deliveries_is_treated_pessimistically(self):
        """Not knowing is a reason for more cover, not for the quoted figure."""
        profile = leadtime.profile(28, [30])
        assert profile.average_days == 28
        assert profile.deviation_days >= 7
        assert profile.ninetieth_percentile_days > 28

    def test_a_supplier_that_keeps_to_its_word_is_called_reliable(self):
        assert leadtime.profile(28, [28, 29, 27, 28, 28, 29]).is_reliable
        assert not leadtime.profile(28, [28, 45, 22, 51, 30, 19]).is_reliable


class TestCover:
    def _profile(self, **kwargs):
        return leadtime.profile(kwargs.pop("quoted", 28), kwargs.pop("samples", [28] * 8))

    def test_the_supplier_timing_term_is_not_dropped(self):
        """The term a home-built spreadsheet always leaves out.

        Two suppliers with the same average lead time and different
        reliability must not produce the same safety stock.
        """
        steady_supplier = leadtime.profile(28, [28] * 10)
        erratic_supplier = leadtime.profile(28, [14, 42, 20, 36, 28, 44, 16, 30])
        common = dict(
            weekly_rate=50.0,
            weekly_deviation=10.0,
            review_period_days=7,
            service_level=0.95,
        )
        tight = safetystock.build(lead_time=steady_supplier, **common)
        loose = safetystock.build(lead_time=erratic_supplier, **common)
        assert loose.safety_stock > tight.safety_stock * 1.5

    def test_cover_includes_the_wait_for_the_next_ordering_round(self):
        policy = safetystock.build(
            weekly_rate=70.0,
            weekly_deviation=10.0,
            lead_time=leadtime.profile(28, [28] * 8),
            review_period_days=7,
            service_level=0.95,
        )
        assert policy.cover_days == pytest.approx(35.0)

    def test_a_higher_service_level_costs_more_stock(self):
        common = dict(
            weekly_rate=50.0,
            weekly_deviation=20.0,
            lead_time=leadtime.profile(28, [28, 31, 26, 33] * 2),
            review_period_days=7,
        )
        assert (
            safetystock.build(service_level=0.98, **common).safety_stock
            > safetystock.build(service_level=0.90, **common).safety_stock
        )

    def test_the_reorder_point_is_below_the_order_up_to_level(self):
        policy = safetystock.build(
            weekly_rate=30.0,
            weekly_deviation=8.0,
            lead_time=leadtime.profile(21, [21] * 6),
            review_period_days=7,
            service_level=0.95,
        )
        assert policy.reorder_point < policy.order_up_to

    def test_the_history_is_used_instead_of_the_bell_curve_when_there_is_one(self):
        """Why this matters: on lumpy demand the normal formula is absurd.

        A part selling 400 once every ten weeks has a huge standard
        deviation, so z times sigma demands a buffer far larger than any
        ten week run has ever needed. Taking the distribution from the
        history instead is both more correct and much cheaper.
        """
        lumpy = [0.0] * 9 + [400.0]
        series = lumpy * 10
        supplier = leadtime.profile(28, [28] * 8)
        common = dict(
            weekly_rate=40.0,
            weekly_deviation=120.0,
            lead_time=supplier,
            review_period_days=7,
            service_level=0.95,
        )
        textbook = safetystock.build(**common)
        measured = safetystock.build(**common, history=series)

        assert textbook.method == "normal"
        assert measured.method == "history"
        assert measured.safety_stock < textbook.safety_stock
        assert measured.distribution is not None
        assert measured.distribution.windows > 0

    def test_too_little_history_falls_back_rather_than_guessing(self):
        policy = safetystock.build(
            weekly_rate=10.0,
            weekly_deviation=4.0,
            lead_time=leadtime.profile(28, [28] * 6),
            review_period_days=7,
            service_level=0.95,
            history=[5.0] * 10,
        )
        assert policy.method == "normal"


class TestTheEmpiricalDistribution:
    def test_the_windows_are_actual_runs_of_weeks(self):
        series = [1.0] * 52
        result = uncertainty.from_history(
            series,
            lead_time=leadtime.profile(28, [28] * 8),
            review_period_days=7,
            service_level=0.95,
        )
        assert result is not None
        # Five weeks of cover at one a week is five.
        assert result.average == pytest.approx(5.0, abs=0.5)

    def test_it_declines_rather_than_inventing_a_distribution(self):
        assert (
            uncertainty.from_history(
                [1.0] * 10,
                lead_time=leadtime.profile(28, [28] * 8),
                review_period_days=7,
                service_level=0.95,
            )
            is None
        )


class TestShutdowns:
    def test_the_new_year_dates_are_the_published_ones(self):
        assert shutdowns.LUNAR_NEW_YEAR[2027] == dt.date(2027, 2, 6)
        assert shutdowns.LUNAR_NEW_YEAR[2028] == dt.date(2028, 1, 26)

    def test_the_mainland_shuts_for_far_longer_than_taiwan(self):
        china = shutdowns.next_shutdown("CN", TODAY)
        taiwan = shutdowns.next_shutdown("TW", TODAY)
        assert china.disrupted_days > taiwan.disrupted_days * 2
        assert china.order_by < taiwan.order_by

    def test_somewhere_that_does_not_keep_it_is_unaffected(self):
        assert not shutdowns.next_shutdown("US", TODAY).affects
        assert shutdowns.weeks_of_cover_needed(shutdowns.next_shutdown("US", TODAY)) == 0

    def test_an_order_placed_after_the_cutoff_waits_for_the_factory(self):
        china = shutdowns.next_shutdown("CN", TODAY)
        before = china.order_by - dt.timedelta(days=1)
        after = china.order_by + dt.timedelta(days=7)
        assert china.extra_lead_time_days(before) == 0
        assert china.extra_lead_time_days(after) > 30

    def test_the_next_shutdown_is_never_one_that_has_already_finished(self):
        for day in (dt.date(2027, 1, 1), dt.date(2027, 3, 1), dt.date(2027, 6, 1)):
            shutdown = shutdowns.next_shutdown("CN", day)
            assert shutdown.back_to_normal_on >= day


class TestOrderQuantities:
    def test_orders_are_whole_packs(self):
        assert round_to_pack(1, 500, 0) == 500
        assert round_to_pack(501, 500, 0) == 1000
        assert round_to_pack(1000, 500, 0) == 1000

    def test_the_minimum_is_respected(self):
        assert round_to_pack(100, 50, 400) == 400

    def test_rounding_is_up_never_down(self):
        """Rounding an order down to save a little is how cover is lost."""
        for wanted in range(1, 500):
            assert round_to_pack(wanted, 100, 0) >= wanted

    def test_nothing_wanted_is_nothing_ordered(self):
        assert round_to_pack(0, 500, 100) == 0


class TestServiceLevels:
    def test_the_deviates_are_the_ones_in_the_table(self):
        assert z_for_service_level(0.95) == pytest.approx(1.645, abs=0.01)
        assert z_for_service_level(0.90) == pytest.approx(1.282, abs=0.01)
        assert z_for_service_level(0.99) == pytest.approx(2.326, abs=0.01)

    def test_asking_for_more_service_asks_for_more_stock(self):
        levels = [0.80, 0.90, 0.95, 0.98, 0.99]
        values = [z_for_service_level(level) for level in levels]
        assert values == sorted(values)
