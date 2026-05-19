from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from nexus.core.db import NexusStore


class UsageMetrics:
    def __init__(self, store: NexusStore) -> None:
        self.store = store

    def summary(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        calls = self._filter_calls(since=since, until=until)
        by_tool = Counter(call.tool_id for call in calls)
        by_agent = Counter(call.agent_id for call in calls)
        by_status = Counter(call.status for call in calls)
        durations = [call.duration_ms for call in calls if call.duration_ms > 0]
        return {
            "total_calls": len(calls),
            "by_tool": dict(by_tool),
            "by_agent": dict(by_agent),
            "by_status": dict(by_status),
            "latency_ms": self._latency_stats(durations),
        }

    def tool_usage(self, tool_id: str) -> dict[str, Any]:
        calls = [call for call in self.store.calls if call.tool_id == tool_id]
        durations = [call.duration_ms for call in calls if call.duration_ms > 0]
        return {
            "tool_id": tool_id,
            "calls": len(calls),
            "agents": sorted({call.agent_id for call in calls}),
            "latency_ms": self._latency_stats(durations),
        }

    def agent_usage(self, agent_id: str) -> dict[str, Any]:
        calls = [call for call in self.store.calls if call.agent_id == agent_id]
        actions: dict[str, list[str]] = defaultdict(list)
        for call in calls:
            actions[call.tool_id].append(call.action)
        durations = [call.duration_ms for call in calls if call.duration_ms > 0]
        return {
            "agent_id": agent_id,
            "calls": len(calls),
            "actions": dict(actions),
            "latency_ms": self._latency_stats(durations),
        }

    @staticmethod
    def _latency_stats(durations: list[float]) -> dict[str, float]:
        if not durations:
            return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0}
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
            "count": n,
            "avg": round(sum(sorted_d) / n, 3),
            "p50": round(percentile(50), 3),
            "p95": round(percentile(95), 3),
            "p99": round(percentile(99), 3),
            "min": round(sorted_d[0], 3),
            "max": round(sorted_d[-1], 3),
        }
