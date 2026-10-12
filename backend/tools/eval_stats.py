"""
The few statistics the evaluation report needs, in plain Python (no numpy or scipy), so the numbers are
easy to check by hand and `tests/test_eval_stats.py` pins them against known values.

* `clopper_pearson`: exact binomial interval for "k of n" (accepts, passes, ...).
* `zero_event_upper`: the 95% upper bound when nothing happened in n trials (31% at n=8, 4.9% at n=60).
* `auc`: probability that a genuine score is above an attack score (ties count one half).
* `cluster_bootstrap_auc`: the same with an interval, resampling whole groups (speakers) because the
  takes of one person are not independent of each other.
"""
from __future__ import annotations

import math
import random
from typing import Dict, Hashable, List, Optional, Sequence, Tuple


def _binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    return min(1.0, sum(math.comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k + 1)))


def _solve(decreasing_in_p, target: float) -> float:
    """The p in [0, 1] where a function that falls with p crosses `target` (bisection)."""
    low, high = 0.0, 1.0
    for _ in range(80):
        middle = (low + high) / 2.0
        if decreasing_in_p(middle) > target:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def clopper_pearson(successes: int, trials: int, confidence: float = 0.95, one_sided: bool = False) -> Tuple[float, float]:
    """Exact (lower, upper) interval for a rate of `successes` in `trials`.

    Two-sided by default. With `one_sided=True` only the upper bound is tightened (the lower is 0.0)
    and `confidence` applies to it alone: the right figure for "at most this many attacks get through".
    """
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("need 0 <= successes <= trials and trials > 0")
    alpha = (1.0 - confidence) if one_sided else (1.0 - confidence) / 2.0
    upper = 1.0 if successes == trials else _solve(lambda p: _binomial_cdf(successes, trials, p), alpha)
    if one_sided or successes == 0:
        return 0.0, upper
    # P(X >= successes) = 1 - P(X <= successes - 1) rises with p, so solve on its complement.
    lower = _solve(lambda p: _binomial_cdf(successes - 1, trials, p), 1.0 - alpha)
    return lower, upper


def zero_event_upper(trials: int, confidence: float = 0.95) -> float:
    """One-sided upper bound on a rate after seeing it zero times in `trials` trials."""
    if trials <= 0:
        raise ValueError("trials must be positive")
    return 1.0 - (1.0 - confidence) ** (1.0 / trials)


def auc(genuine: Sequence[float], attack: Sequence[float]) -> Optional[float]:
    """P(genuine score > attack score), ties as one half; None when either side is empty."""
    if not genuine or not attack:
        return None
    wins = 0.0
    for g in genuine:
        for a in attack:
            wins += 1.0 if g > a else 0.5 if g == a else 0.0
    return wins / (len(genuine) * len(attack))


Row = Tuple[Hashable, bool, float]  # (group such as the speaker, is_genuine, score)


def _auc_of(rows: Sequence[Row]) -> Optional[float]:
    return auc([s for _, genuine, s in rows if genuine], [s for _, genuine, s in rows if not genuine])


def cluster_bootstrap_auc(rows: Sequence[Row], resamples: int = 2000, seed: int = 0) -> Dict[str, Optional[float]]:
    """AUC with a percentile interval from resampling whole groups with replacement.

    With fewer than 2 groups the groups are useless as clusters, so each row is its own group and the
    result says so (`clustered` is 0.0). `lower_one_sided` is the 5th percentile: the figure the
    "leave report-only" rule compares with 0.70. Resamples that lose a class are skipped and counted.
    """
    point = _auc_of(rows)
    result: Dict[str, Optional[float]] = {"auc": point, "lower_one_sided": None, "low": None, "high": None, "valid_resamples": 0.0, "clustered": 1.0}
    if point is None:
        return result
    keyed: Dict[Hashable, List[Row]] = {}
    for index, row in enumerate(rows):
        keyed.setdefault(row[0], []).append(row)
    if len(keyed) < 2:
        result["clustered"] = 0.0
        keyed = {index: [row] for index, row in enumerate(rows)}
    groups = list(keyed.values())
    rng = random.Random(seed)
    values: List[float] = []
    for _ in range(resamples):
        sample = [row for group in (rng.choice(groups) for _ in groups) for row in group]
        value = _auc_of(sample)
        if value is not None:
            values.append(value)
    result["valid_resamples"] = float(len(values))
    if values:
        values.sort()
        result["lower_one_sided"] = values[int(0.05 * (len(values) - 1))]
        result["low"] = values[int(0.025 * (len(values) - 1))]
        result["high"] = values[int(0.975 * (len(values) - 1))]
    return result
