from __future__ import annotations

import math

import pytest

from structbench.stats import mean, percentile, wilson_interval


class TestWilson:
    def test_known_value(self):
        # 8/10 successes -> [0.4902, 0.9433] (standard reference values)
        lo, hi = wilson_interval(8, 10)
        assert lo == pytest.approx(0.4902, abs=1e-4)
        assert hi == pytest.approx(0.9433, abs=1e-4)

    def test_all_success_upper_bound_is_one(self):
        lo, hi = wilson_interval(40, 40)
        assert hi == pytest.approx(1.0)
        assert lo == pytest.approx(0.9124, abs=1e-4)

    def test_zero_success(self):
        lo, hi = wilson_interval(0, 20)
        assert lo == 0.0
        assert hi == pytest.approx(0.1611, abs=1e-4)

    def test_interval_contains_point_estimate_and_narrows_with_n(self):
        lo1, hi1 = wilson_interval(5, 10)
        lo2, hi2 = wilson_interval(50, 100)
        assert lo1 < 0.5 < hi1
        assert (hi2 - lo2) < (hi1 - lo1)

    def test_fractional_successes(self):
        lo, hi = wilson_interval(2.5, 5)
        assert lo < 0.5 < hi

    def test_empty_and_invalid(self):
        assert wilson_interval(0, 0) == (0.0, 1.0)
        with pytest.raises(ValueError, match="successes"):
            wilson_interval(11, 10)


class TestPercentile:
    def test_interpolation(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        assert percentile(xs, 50) == 2.5
        assert percentile(xs, 0) == 1.0
        assert percentile(xs, 100) == 4.0
        assert percentile(xs, 95) == pytest.approx(3.85)

    def test_single_and_empty(self):
        assert percentile([7.0], 95) == 7.0
        assert math.isnan(percentile([], 50))

    def test_bad_q(self):
        with pytest.raises(ValueError, match="q must"):
            percentile([1.0], 101)


def test_mean():
    assert mean([1.0, 2.0, 3.0]) == 2.0
    assert math.isnan(mean([]))
