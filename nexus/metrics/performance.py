from __future__ import annotations

from typing import Any

from nexus.core.db import NexusStore
from nexus.metrics._stats import latency_stats, percentile


class PerformanceTracker:
    def __init__(self, store: NexusStore) -> None:
        self.store = store

    def latency(self) -> dict[str, Any]:
        durations = [call.duration_ms for call in self.store.calls if call.duration_ms > 0]
        stats = latency_stats(durations)
        # Rename keys for backward-compatible API
        return {
            "avg_ms": stats["avg"],
            "max_ms": stats["max"],
            "min_ms": stats["min"],
            "p50": stats["p50"],
            "p95": stats["p95"],
            "p99": stats["p99"],
            "count": stats["count"],
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
                    "p95": round(percentile(sorted_d, 95), 3),
                    "calls": n,
                }
            else:
                result[tool_id] = {"avg_ms": 0, "max_ms": 0, "min_ms": 0, "p95": 0, "calls": 0}
        return result

    def __repr__(self) -> str:
        lat = self.latency()
        return (
            f"PerformanceTracker(calls={lat['count']}, "
            f"avg={lat['avg_ms']:.1f}ms, p95={lat['p95']:.1f}ms, p99={lat['p99']:.1f}ms)"
        )
