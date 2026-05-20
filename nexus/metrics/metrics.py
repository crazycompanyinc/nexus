from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from nexus.core.db import NexusStore
from nexus.metrics._stats import latency_stats


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
        total = len(calls)
        errors = sum(1 for c in calls if c.status == "error")
        return {
            "total_calls": total,
            "by_tool": dict(by_tool),
            "by_agent": dict(by_agent),
            "by_status": dict(by_status),
            "latency_ms": latency_stats(durations),
            "error_rate": round(errors / total, 4) if total > 0 else 0.0,
        }

    def tool_usage(self, tool_id: str) -> dict[str, Any]:
        calls = [call for call in self.store.calls if call.tool_id == tool_id]
        durations = [call.duration_ms for call in calls if call.duration_ms > 0]
        return {
            "tool_id": tool_id,
            "calls": len(calls),
            "agents": sorted({call.agent_id for call in calls}),
            "latency_ms": latency_stats(durations),
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
            "latency_ms": latency_stats(durations),
        }

    def _filter_calls(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list:
        calls = list(self.store.calls)
        if since is not None:
            calls = [c for c in calls if c.called_at >= since]
        if until is not None:
            calls = [c for c in calls if c.called_at <= until]
        return calls
