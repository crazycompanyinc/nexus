from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from nexus.core.db import NexusStore
from nexus.core.models import ToolCall
from nexus.metrics._stats import latency_stats


__all__ = ["UsageMetrics"]


class UsageMetrics:
    """Aggregates and summarizes tool usage data from the NexusStore."""

    def __init__(self, store: NexusStore) -> None:
        """Initialize metrics aggregator with a NexusStore.

        Args:
            store: The store containing call records to aggregate.
        """
        self.store = store

    def summary(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a summary of all tool usage within an optional time range.

        Args:
            since: Only include calls at or after this datetime.
            until: Only include calls at or before this datetime.

        Returns:
            Dict with total_calls, by_tool, by_agent, by_status, latency_ms, error_rate.
        """
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
        """Return usage statistics for a specific tool.

        Args:
            tool_id: The tool identifier to query.

        Returns:
            Dict with tool_id, calls count, agents list, and latency stats.

        Raises:
            ValueError: If tool_id is empty or not a string.
        """
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
        """Return usage statistics for a specific agent.

        Args:
            agent_id: The agent identifier to query.

        Returns:
            Dict with agent_id, calls count, actions breakdown, and latency stats.

        Raises:
            ValueError: If agent_id is empty or not a string.
        """
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
        """Filter store calls by optional time range.

        Args:
            since: Only include calls at or after this datetime.
            until: Only include calls at or before this datetime.

        Returns:
            Filtered list of ToolCall objects.
        """
        calls: list[ToolCall] = list(self.store.calls)
        if since is not None:
            calls = [c for c in calls if c.called_at >= since]
        if until is not None:
            calls = [c for c in calls if c.called_at <= until]
        return calls

    def calls_over_time(
        self,
        *,
        bucket: str = "hour",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return call volume time-series data grouped by time bucket.

        Useful for dashboards and trend analysis. Each bucket contains
        the timestamp, total calls, and error count.

        Args:
            bucket: Time bucket size - "minute", "hour", or "day".
            since: Only include calls at or after this datetime.
            until: Only include calls at or before this datetime.

        Returns:
            List of dicts with keys: bucket (ISO timestamp), total, errors.

        Raises:
            ValueError: If bucket is not one of the supported values.

        Example:
            >>> series = metrics.calls_over_time(bucket="hour", since=yesterday)
        """
        valid_buckets = {"minute", "hour", "day"}
        if bucket not in valid_buckets:
            raise ValueError(f"bucket must be one of {sorted(valid_buckets)}, got {bucket!r}")
        calls = self._filter_calls(since=since, until=until)

        buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "errors": 0})
        for call in calls:
            dt = call.called_at
            if bucket == "minute":
                key = dt.replace(second=0, microsecond=0).isoformat()
            elif bucket == "hour":
                key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
            else:  # day
                key = dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            buckets[key]["total"] += 1
            if call.status == "error":
                buckets[key]["errors"] += 1
        return [
            {"bucket": k, "total": v["total"], "errors": v["errors"]}
            for k, v in sorted(buckets.items())
        ]

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text-based exposition format.

        Generates gauges and counters for call counts, error rates,
        latency percentiles, and plugin status. Compatible with
        Prometheus, Grafana Agent, and OpenTelemetry collectors.

        Returns:
            Prometheus-formatted text output (Content-Type: text/plain).
        """
        from nexus.metrics.performance import PerformanceTracker

        lines: list[str] = []
        calls = list(self.store.calls)
        total = len(calls)
        errors = sum(1 for c in calls if c.status == "error")

        # --- nexus_calls_total counter ---
        lines.append("# HELP nexus_calls_total Total number of tool calls.")
        lines.append("# TYPE nexus_calls_total counter")
        lines.append(f'nexus_calls_total {total}')
        by_tool: dict[str, int] = Counter(c.tool_id for c in calls)
        for tool_id, count in by_tool.items():
            safe = tool_id.replace('"', '\\"')
            lines.append(f'nexus_calls_total{{tool_id="{safe}"}} {count}')
        lines.append("")

        # --- nexus_calls_errors_total counter ---
        lines.append("# HELP nexus_calls_errors_total Total number of failed tool calls.")
        lines.append("# TYPE nexus_calls_errors_total counter")
        lines.append(f'nexus_calls_errors_total {errors}')
        err_by_tool: dict[str, int] = Counter(c.tool_id for c in calls if c.status == "error")
        for tool_id, count in err_by_tool.items():
            safe = tool_id.replace('"', '\\"')
            lines.append(f'nexus_calls_errors_total{{tool_id="{safe}"}} {count}')
        lines.append("")

        # --- nexus_call_duration_seconds histogram/summary ---
        durations = [c.duration_ms for c in calls if c.duration_ms > 0]
        if durations:
            from nexus.metrics._stats import latency_stats, percentile
            stats = latency_stats(durations)
            sorted_d = sorted(durations)
            lines.append("# HELP nexus_call_duration_seconds Tool call latency distribution.")
            lines.append("# TYPE nexus_call_duration_seconds summary")
            lines.append(f'nexus_call_duration_seconds{{quantile="0.5"}} {stats["p50"] / 1000:.3f}')
            lines.append(f'nexus_call_duration_seconds{{quantile="0.95"}} {stats["p95"] / 1000:.3f}')
            lines.append(f'nexus_call_duration_seconds{{quantile="0.99"}} {stats["p99"] / 1000:.3f}')
            total_sec = sum(durations) / 1000.0
            lines.append(f"nexus_call_duration_seconds_sum {total_sec:.3f}")
            lines.append(f"nexus_call_duration_seconds_count {len(durations)}")
            lines.append("")

        # --- nexus_agents gauge ---
        lines.append("# HELP nexus_agents Total number of registered agents.")
        lines.append("# TYPE nexus_agents gauge")
        lines.append(f"nexus_agents {len(self.store.agents)}")
        lines.append("")

        # --- nexus_plugins gauge ---
        plugins = list(self.store.plugins.keys()) if hasattr(self.store, 'plugins') else []
        active = sum(1 for pid in plugins)  # simplified; real status from manager
        lines.append("# HELP nexus_plugins Total number of registered plugins.")
        lines.append("# TYPE nexus_plugins gauge")
        lines.append(f"nexus_plugins {len(plugins)}")
        lines.append(f'nexus_plugins{{status="active"}} {active}')
        lines.append("")

        # --- nexus_workflows gauge ---
        lines.append("# HELP nexus_workflows Total number of registered workflows.")
        lines.append("# TYPE nexus_workflows gauge")
        lines.append(f"nexus_workflows {len(self.store.workflows)}")
        lines.append("")

        # --- nexus_bindings gauge ---
        lines.append("# HELP nexus_bindings Total number of agent-tool bindings.")
        lines.append("# TYPE nexus_bindings gauge")
        lines.append(f"nexus_bindings {len(self.store.bindings)}")
        lines.append("")

        return "\n".join(lines)

    def __repr__(self) -> str:
        """Return a summary of usage metrics.

        Returns:
            String with total calls, error count, and agent count.
        """
        total = len(self.store.calls)
        errors = sum(1 for c in self.store.calls if c.status == "error")
        return f"UsageMetrics(total_calls={total}, errors={errors}, agents={len(self.store.agents)})"

    def top_tools(self, n: int = 5) -> list[dict[str, Any]]:
        """Return the most frequently used tools ranked by call count.

        Args:
            n: Number of top tools to return.

        Returns:
            List of dicts with keys: tool_id, calls, avg_duration_ms, error_rate.

        Example:
            >>> top = metrics.top_tools(3)
            >>> top[0]["tool_id"]
            'http'
        """
        from collections import Counter, defaultdict

        tool_calls: dict[str, list[ToolCall]] = defaultdict(list)
        for call in self.store.calls:
            tool_calls[call.tool_id].append(call)

        ranked = sorted(tool_calls.items(), key=lambda x: len(x[1]), reverse=True)
        result: list[dict[str, Any]] = []
        for tool_id, calls in ranked[:n]:
            durations = [c.duration_ms for c in calls if c.duration_ms > 0]
            errors = sum(1 for c in calls if c.status == "error")
            avg_dur = round(sum(durations) / len(durations), 2) if durations else 0.0
            result.append({
                "tool_id": tool_id,
                "calls": len(calls),
                "avg_duration_ms": avg_dur,
                "error_rate": round(errors / len(calls), 4) if calls else 0.0,
            })
        return result

    def slow_calls(self, threshold_ms: float = 1000.0, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return calls that exceeded a duration threshold.

        Useful for performance debugging and identifying bottlenecks.

        Args:
            threshold_ms: Duration threshold in milliseconds.
            limit: Maximum number of results to return.

        Returns:
            List of dicts with keys: call_id, agent_id, tool_id, action,
            duration_ms, status, called_at. Sorted by duration descending.

        Example:
            >>> slow = metrics.slow_calls(threshold_ms=500.0, limit=10)
        """
        slow = [c for c in self.store.calls if c.duration_ms >= threshold_ms]
        slow.sort(key=lambda c: c.duration_ms, reverse=True)
        return [
            {
                "call_id": c.id,
                "agent_id": c.agent_id,
                "tool_id": c.tool_id,
                "action": c.action,
                "duration_ms": c.duration_ms,
                "status": c.status,
                "called_at": c.called_at.isoformat(),
            }
            for c in slow[:limit]
        ]
