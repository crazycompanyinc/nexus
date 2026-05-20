from __future__ import annotations

import math
from typing import Any


def percentile(sorted_data: list[float], p: float) -> float:
    """Compute percentile on sorted data using linear interpolation."""
    n = len(sorted_data)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_data[0]
    k = (p / 100.0) * (n - 1)
    f = math.floor(k)
    c = min(f + 1, n - 1)
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def latency_stats(durations: list[float]) -> dict[str, float]:
    """Compute latency statistics (count, avg, p50, p95, p99, min, max)."""
    if not durations:
        return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0}
    sorted_d = sorted(durations)
    n = len(sorted_d)
    return {
        "count": n,
        "avg": round(sum(sorted_d) / n, 3),
        "p50": round(percentile(sorted_d, 50), 3),
        "p95": round(percentile(sorted_d, 95), 3),
        "p99": round(percentile(sorted_d, 99), 3),
        "min": round(sorted_d[0], 3),
        "max": round(sorted_d[-1], 3),
    }
