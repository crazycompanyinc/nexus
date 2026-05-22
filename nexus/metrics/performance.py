from __future__ import annotations

from typing import Any

from nexus.core.db import NexusStore
from nexus.metrics._stats import latency_stats, percentile


class PerformanceTracker:
    """Tracks latency and performance metrics for tool calls.

    Provides overall, per-tool, and per-agent performance breakdowns.
    """

    def __init__(self, store: NexusStore) -> None:
        """Initialize the performance tracker with a NexusStore.

        Args:
            store: The store containing call records with duration data.
        """
        self.store = store

    def latency(self) -> dict[str, Any]:
        """Return overall latency statistics across all tool calls.

        Returns:
            Dict with avg_ms, max_ms, min_ms, p50, p95, p99, count.
        """
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
        """Return latency performance metrics broken down by tool.

        Computes avg/max/min/p95 latency and call count per tool
        using a single pass over the store calls.

        Returns:
            Dict mapping tool_id to performance dict with keys:
            avg_ms, max_ms, min_ms, p95, calls.
        """
        tool_durations: dict[str, list[float]] = {}
        for call in self.store.calls:
            if call.duration_ms > 0:
                tool_durations.setdefault(call.tool_id, []).append(call.duration_ms)
        result: dict[str, dict[str, Any]] = {}
        for tool_id, durations in tool_durations.items():
            sorted_d = sorted(durations)
            n = len(sorted_d)
            result[tool_id] = {
                "avg_ms": round(sum(sorted_d) / n, 3),
                "max_ms": round(sorted_d[-1], 3),
                "min_ms": round(sorted_d[0], 3),
                "p95": round(percentile(sorted_d, 95), 3),
                "calls": n,
            }
        return result

    def by_agent(self) -> dict[str, dict[str, Any]]:
        """Return latency performance metrics broken down by agent.

        Computes avg/max/min/p95 latency and call count per agent.

        Returns:
            Dict mapping agent_id to performance dict with keys:
            avg_ms, max_ms, min_ms, p95, calls.
        """
        result: dict[str, dict[str, Any]] = {}
        for agent_id in self.store.agents:
            durations = [call.duration_ms for call in self.store.calls if call.agent_id == agent_id and call.duration_ms > 0]
            if durations:
                sorted_d = sorted(durations)
                n = len(sorted_d)
                result[agent_id] = {
                    "avg_ms": round(sum(sorted_d) / n, 3),
                    "max_ms": round(sorted_d[-1], 3),
                    "min_ms": round(sorted_d[0], 3),
                    "p95": round(percentile(sorted_d, 95), 3),
                    "calls": n,
                }
            else:
                result[agent_id] = {"avg_ms": 0, "max_ms": 0, "min_ms": 0, "p95": 0, "calls": 0}
        return result

    def __repr__(self) -> str:
        lat = self.latency()
        return (
            f"PerformanceTracker(calls={lat['count']}, "
            f"avg={lat['avg_ms']:.1f}ms, p95={lat['p95']:.1f}ms, p99={lat['p99']:.1f}ms)"
        )
