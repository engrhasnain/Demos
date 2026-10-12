"""The forecasting itself, on series whose right answer is known."""

from __future__ import annotations

import pytest

from app.domain import classify, forecast, metrics


def steady(weeks: int = 104, level: float = 10.0) -> list[float]:
    return [level] * weeks


def every_nth(weeks: int, gap: int, size: float) -> list[float]:
    return [size if (week + 1) % gap == 0 else 0.0 for week in range(weeks)]


class TestClassifying:
    def test_a_part_that_sells_every_week_is_steady(self):
        pattern = classify.classify([10, 11, 9, 10, 12, 9] * 8)
        assert pattern.kind == classify.SMOOTH
        assert pattern.average_demand_interval == 1.0
        assert pattern.suggested_method == "ses"

    def test_long_gaps_and_even_sizes_are_occasional(self):
        pattern = classify.classify(every_nth(104, 4, 40))
        assert pattern.kind == classify.INTERMITTENT
        assert pattern.average_demand_interval == pytest.approx(4.0, abs=0.1)

    def test_long_gaps_and_wild_sizes_are_lumpy(self):
        series = [0, 0, 5, 0, 0, 0, 400, 0, 0, 12, 0, 0] * 8
        pattern = classify.classify(series)
        assert pattern.kind == classify.LUMPY
        assert pattern.coefficient_of_variation_squared >= classify.CV_SQUARED_CUTOFF

    def test_nothing_sold_is_its_own_answer(self):
        pattern = classify.classify([0.0] * 104)
        assert pattern.kind == classify.NO_DEMAND
        assert pattern.suggested_method == "zero"

    def test_the_cutoffs_are_the_published_ones(self):
        """Not invented here. These are the figures the literature compares at."""
        assert classify.ADI_CUTOFF == 1.32
        assert classify.CV_SQUARED_CUTOFF == 0.49

    def test_the_occasional_ones_are_the_ones_reported_separately(self):
        assert classify.is_intermittent(classify.LUMPY)
        assert classify.is_intermittent(classify.INTERMITTENT)
        assert not classify.is_intermittent(classify.SMOOTH)


class TestTheMethods:
    def test_smoothing_lands_near_the_level_it_was_given(self):
        result = forecast.forecast_ses(steady(104, 25))
        assert result.rate == pytest.approx(25.0, rel=0.02)

    def test_croston_divides_the_size_by_the_gap(self):
        # 40 every 4 weeks is 10 a week, and that is what it should say.
        result = forecast.forecast_croston(
            every_nth(104, 4, 40), bias_corrected=False
        )
        assert result.rate == pytest.approx(10.0, rel=0.05)

    def test_the_bias_correction_pulls_croston_down(self):
        series = every_nth(104, 4, 40)
        plain = forecast.forecast_croston(series, bias_corrected=False)
        corrected = forecast.forecast_croston(series, bias_corrected=True)
        assert corrected.rate < plain.rate

    def test_a_part_that_stops_selling_decays_to_nothing(self):
        """The property that makes this the right default.

        Croston only updates in the weeks that sell, so it holds the rate a
        part had on the day it died, for ever. A reorder engine built on it
        keeps buying dead stock. This is the single most expensive habit in
        an inventory system and it is why the default here is not Croston.
        """
        died = steady(52, 8) + [0.0] * 52
        croston = forecast.forecast_croston(died)
        tsb = forecast.forecast_tsb(died)
        assert croston.rate > 4.0, "Croston should still be recommending stock"
        assert tsb.rate < 1.0, "the part has not sold in a year"
        assert tsb.rate < croston.rate / 5

    def test_nothing_sold_forecasts_nothing(self):
        result = forecast.forecast_tsb([0.0] * 104)
        assert result.rate == 0.0
        assert result.method == "zero"

    def test_every_forecast_can_show_its_working(self):
        for series in (steady(), every_nth(104, 5, 60), [0.0] * 104):
            pattern = classify.classify(series)
            result = forecast.run(pattern.suggested_method, series)
            assert result.trace is not None
            assert result.trace.steps, "a figure nobody can explain is a figure nobody trusts"

    def test_a_rate_is_never_negative(self):
        for series in ([0, 0, 0, 1], [5, 0, 0, 0] * 26, [0.0] * 50):
            for method in ("ses", "croston", "sba", "tsb"):
                assert forecast.run(method, series).rate >= 0


class TestScoring:
    def test_percentage_error_is_not_used_because_it_cannot_be(self):
        """Dividing by the actual fails when the actual is zero most weeks."""
        assert not hasattr(metrics, "mape")

    def test_a_flat_series_cannot_be_scored_and_says_so(self):
        result = metrics.score([5.0] * 10, [5.0] * 10, training=[5.0] * 10)
        assert not result.scoreable
        assert result.mase is None

    def test_a_perfect_forecast_scores_zero(self):
        actual = [0, 0, 40, 0, 0, 40, 0, 0]
        result = metrics.score(actual, actual, training=actual)
        assert result.mase == pytest.approx(0.0)

    def test_bias_is_reported_because_accuracy_alone_hides_it(self):
        actual = [10.0] * 12
        high = [12.0] * 12
        result = metrics.score(actual, high, training=[10, 11, 9] * 4)
        assert result.bias == pytest.approx(2.0)

    def test_a_forecast_of_nothing_beats_a_real_one_on_occasional_demand(self):
        """The trap this product refuses to be graded by.

        Absolute error is smallest at the median, and the median of a series
        that is zero four weeks in five is zero. So the most useless
        forecast possible wins on the standard measure. Stating that first
        is more honest than being caught by it later.
        """
        cases = []
        for gap in (4, 5, 6, 8):
            series = every_nth(104, gap, 100)
            training, actual = series[:52], series[52:]
            rate = forecast.forecast_tsb(training).rate
            cases.append((training, actual, [rate] * len(actual)))

        trap = metrics.zero_forecast_beats(cases)
        assert trap.parts_scored == len(cases)
        assert trap.parts_where_zero_wins == trap.parts_scored
        assert trap.zero_mase < trap.model_mase
        assert "stock-outs and money" in trap.to_dict()["verdict"]
