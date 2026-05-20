from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from nexus.core.db import NexusStore
from nexus.core.models import ToolCall
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
        if not isinstance(tool_id, str) or not tool_id.strip():
            raise ValueError(f"tool_id must be a non-empty string, got {tool_id!r}")
        calls = [call for call in self.store.calls if call.tool_id == tool_id]
        durations = [call.duration_ms for call in calls if call.duration_ms > 0]
        return {
            "tool_id": tool_id,
            "calls": len(calls),
            "agents": sorted({call.agent_id for call in calls}),
            "latency_ms": latency_stats(durations),
        }

    def agent_usage(self, agent_id: str) -> dict[str, Any]:
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError(f"agent_id must be a non-empty string, got {agent_id!r}")
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

    def error_summary(self, *, since: datetime | None = None, until: datetime | None = None) -> dict[str, Any]:
        """Return a summary of errors grouped by tool and error message.

        Args:
            since: Only include calls at or after this datetime.
            until: Only include calls at or before this datetime.

        Returns:
            Dict with total_errors, by_tool, and top_errors keys.
        """
        calls = self._filter_calls(since=since, until=until)
        error_calls = [c for c in calls if c.status == "error"]
        by_tool: dict[str, int] = Counter(call.tool_id for call in error_calls)
        error_messages: Counter[str] = Counter()
        for call in error_calls:
            msg = (call.result or {}).get("error", "unknown") if isinstance(call.result, dict) else "unknown"
            # Truncate long error messages for grouping
            key = msg[:120] if len(msg) > 120 else msg
            error_messages[key] += 1
        return {
            "total_errors": len(error_calls),
            "by_tool": dict(by_tool),
            "top_errors": dict(error_messages.most_common(10)),
        }

    def _filter_calls(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ToolCall]:
        calls: list[ToolCall] = list(self.store.calls)
        if since is not None:
            calls = [c for c in calls if c.called_at >= since]
        if until is not None:
            calls = [c for c in calls if c.called_at <= until]
        return calls

    def __repr__(self) -> str:
        total = len(self.store.calls)
        errors = sum(1 for c in self.store.calls if c.status == "error")
        return f"UsageMetrics(total_calls={total}, errors={errors}, agents={len(self.store.agents)})"
