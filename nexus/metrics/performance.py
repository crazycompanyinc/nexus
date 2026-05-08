from __future__ import annotations

from statistics import mean
from typing import Any

from nexus.core.db import NexusStore


class PerformanceTracker:
    def __init__(self, store: NexusStore) -> None:
        self.store = store

    def latency(self) -> dict[str, Any]:
        durations = [call.duration_ms for call in self.store.calls]
        if not durations:
            return {"avg_ms": 0, "max_ms": 0, "min_ms": 0}
        return {"avg_ms": mean(durations), "max_ms": max(durations), "min_ms": min(durations)}

    def by_tool(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for tool_id in {call.tool_id for call in self.store.calls}:
            durations = [call.duration_ms for call in self.store.calls if call.tool_id == tool_id]
            result[tool_id] = {"avg_ms": mean(durations), "max_ms": max(durations), "calls": len(durations)}
        return result
