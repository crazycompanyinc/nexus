from __future__ import annotations

import math
from typing import Any

from nexus.core.db import NexusStore


class PerformanceTracker:
    def __init__(self, store: NexusStore) -> None:
        self.store = store

    def latency(self) -> dict[str, Any]:
        durations = [call.duration_ms for call in self.store.calls if call.duration_ms > 0]
        if not durations:
            return {"avg_ms": 0, "max_ms": 0, "min_ms": 0, "p50": 0, "p95": 0, "p99": 0, "count": 0}
        sorted_d = sorted(durations)
        n = len(sorted_d)

        def percentile(p: float) -> float:
            if n == 1:
                return sorted_d[0]
            k = (p / 100.0) * (n - 1)
            f = math.floor(k)
            c = min(f + 1, n - 1)
            return sorted_d[f] + (k - f) * (sorted_d[c] - sorted_d[f])

        return {
            "avg_ms": round(sum(sorted_d) / n, 3),
            "max_ms": round(sorted_d[-1], 3),
            "min_ms": round(sorted_d[0], 3),
            "p50": round(percentile(50), 3),
            "p95": round(percentile(95), 3),
            "p99": round(percentile(99), 3),
            "count": n,
        }

    def by_tool(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for tool_id in {call.tool_id for call in self.store.calls}:
            durations = [call.duration_ms for call in self.store.calls if call.tool_id == tool_id and call.duration_ms > 0]
            if durations:
                sorted_d = sorted(durations)
                n = len(sorted_d)
                result[tool_id] = {
                    "avg_ms": round(sum(sorted_d) / n, 3),
                    "max_ms": round(sorted_d[-1], 3),
                    "min_ms": round(sorted_d[0], 3),
                    "p95": round(sorted_d[int(n * 0.95)] if n > 1 else sorted_d[0], 3),
                    "calls": n,
                }
            else:
                result[tool_id] = {"avg_ms": 0, "max_ms": 0, "min_ms": 0, "p95": 0, "calls": 0}
        return result
