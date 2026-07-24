from __future__ import annotations

from datetime import date, timedelta

import pytest

from glasshouse_forecast.seasonal_baseline import InsufficientHistoryError, seasonal_average


def test_uses_same_weekday_average_when_enough_samples():
    target = date(2026, 8, 5)
    same_weekday = [target - timedelta(weeks=w) for w in (1, 2, 3)]
    a_different_weekday = target - timedelta(days=1)  # never lands on target's weekday

    history = [
        (same_weekday[0], 10, 100.0),
        (same_weekday[1], 10, 110.0),
        (same_weekday[2], 10, 120.0),
        (a_different_weekday, 10, 9999.0),  # must NOT be pulled into the average
    ]

    points = seasonal_average(history, target, period_range=range(10, 11))

    assert len(points) == 1
    point = points[0]
    assert point.settlement_period == 10
    assert point.forecast_value == pytest.approx(110.0)
    assert point.sample_size == 3
    assert point.fallback_used is False


def test_falls_back_to_all_weekday_average_when_too_few_same_weekday_samples():
    target = date(2026, 8, 5)
    only_one_same_weekday_sample = target - timedelta(weeks=1)
    other_days = [target - timedelta(days=1), target - timedelta(days=2)]

    history = [
        (only_one_same_weekday_sample, 10, 100.0),
        (other_days[0], 10, 50.0),
        (other_days[1], 10, 60.0),
    ]
    # Only 1 same-weekday sample (below the default minimum of 3), so this
    # should fall back to averaging across all 3 rows regardless of weekday.

    points = seasonal_average(history, target, period_range=range(10, 11))

    assert points[0].fallback_used is True
    assert points[0].forecast_value == pytest.approx(70.0)
    assert points[0].sample_size == 3


def test_period_with_no_history_is_omitted_not_fabricated():
    target = date(2026, 8, 5)
    history = [(target - timedelta(weeks=w), 10, 100.0) for w in (1, 2, 3)]
    # Period 10 has data; period 20 has none at all.

    points = seasonal_average(history, target, period_range=range(10, 21))

    periods_returned = {p.settlement_period for p in points}
    assert 10 in periods_returned
    assert 20 not in periods_returned


def test_raises_when_there_is_no_history_at_all():
    with pytest.raises(InsufficientHistoryError):
        seasonal_average([], date(2026, 8, 5), period_range=range(1, 5))


def test_std_dev_is_zero_for_a_single_sample():
    target = date(2026, 8, 5)
    history = [(target - timedelta(weeks=1), 1, 50.0)]

    points = seasonal_average(history, target, period_range=range(1, 2), min_same_weekday_samples=1)

    assert points[0].std_dev == 0.0


def test_std_dev_reflects_spread_across_samples():
    target = date(2026, 8, 5)
    history = [
        (target - timedelta(weeks=1), 1, 40.0),
        (target - timedelta(weeks=2), 1, 60.0),
    ]

    points = seasonal_average(history, target, period_range=range(1, 2), min_same_weekday_samples=1)

    # mean(40, 60) = 50; population stdev of [40, 60] = 10.
    assert points[0].forecast_value == pytest.approx(50.0)
    assert points[0].std_dev == pytest.approx(10.0)


def test_min_same_weekday_samples_threshold_is_configurable():
    target = date(2026, 8, 5)
    history = [
        (target - timedelta(weeks=1), 1, 100.0),
        (target - timedelta(weeks=2), 1, 200.0),
    ]

    # Default threshold (3) -> not enough same-weekday samples -> would
    # fall back (and here there's nothing to fall back to but itself,
    # since every row IS same-weekday -- fallback_used still flips True
    # because the *threshold* wasn't met, even though the fallback
    # dataset happens to equal the same-weekday dataset).
    default_points = seasonal_average(history, target, period_range=range(1, 2))
    assert default_points[0].fallback_used is True

    # Lower the threshold to 2 -> now it's treated as a confident,
    # same-weekday-only forecast.
    lenient_points = seasonal_average(
        history, target, period_range=range(1, 2), min_same_weekday_samples=2
    )
    assert lenient_points[0].fallback_used is False
