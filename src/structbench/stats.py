"""Small statistics helpers (no numpy dependency)."""

from __future__ import annotations

import math
from collections.abc import Sequence


def wilson_interval(
    successes: float, n: float, z: float = 1.959963984540054
) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion.

    ``successes`` may be fractional (used for the task-level "effective n"
    interval, where each task contributes its mean success over repetitions).
    """
    if n <= 0:
        return (0.0, 1.0)
    if not 0 <= successes <= n:
        raise ValueError("successes must lie in [0, n]")
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, ``q`` in [0, 100]."""
    if not values:
        return float("nan")
    if not 0 <= q <= 100:
        raise ValueError("q must be in [0, 100]")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")
