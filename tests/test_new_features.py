"""Tests for new OMEGA Evolution Cycle features."""

import pytest
from datetime import datetime, timezone, timedelta
from nexus.core.db import NexusStore
from nexus.core.models import ToolCall, CallStatus
from nexus.metrics.metrics import UsageMetrics
from nexus.metrics.performance import PerformanceTracker


def _make_call(agent_id: str, tool_id: str, action: str = "read",
    """Helper: make call."""
               status: str = "success", duration_ms: float = 10.0,
               called_at: datetime | None = None,
               params: dict | None = None) -> ToolCall:
    call = ToolCall(
        agent_id=agent_id,
        tool_id=tool_id,
        action=action,
        params=params or {},
        status=status,
        duration_ms=duration_ms,
    )
    if called_at:
        call.called_at = called_at
    return call


class TestAgentCalls:
    """TestAgentCalls."""
    def test_agent_calls_returns_only_matching_agent(self):
    """Test: agent calls returns only matching agent."""
        store = NexusStore()
        store.calls.append(_make_call("a1", "t1"))
        store.calls.append(_make_call("a2", "t1"))
        store.calls.append(_make_call("a1", "t2"))
        result = store.agent_calls("a1")
        assert len(result) == 2
        assert all(c.agent_id == "a1" for c in result)

    def test_agent_calls_most_recent_first(self):
    """Test: agent calls most recent first."""
        store = NexusStore()
        c1 = _make_call("a1", "t1")
        c1.called_at = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        c2 = _make_call("a1", "t2")
        c2.called_at = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
        store.calls.append(c1)
        store.calls.append(c2)
        result = store.agent_calls("a1")
        assert result[0].tool_id == "t2"
        assert result[1].tool_id == "t1"

    def test_agent_calls_filter_by_status(self):
    """Test: agent calls filter by status."""
        store = NexusStore()
        store.calls.append(_make_call("a1", "t1", status="success"))
        store.calls.append(_make_call("a1", "t2", status="error"))
        store.calls.append(_make_call("a1", "t3", status="error"))
        result = store.agent_calls("a1", status="error")
        assert len(result) == 2
        assert all(c.status == "error" for c in result)

    def test_agent_calls_with_limit(self):
    """Test: agent calls with limit."""
        store = NexusStore()
        for i in range(10):
            store.calls.append(_make_call("a1", f"t{i}"))
        result = store.agent_calls("a1", limit=3)
        assert len(result) == 3

    def test_agent_calls_empty_when_no_calls(self):
    """Test: agent calls empty when no calls."""
        store = NexusStore()
        assert store.agent_calls("nonexistent") == []


class TestCallsOverTime:
    """TestCallsOverTime."""
    def test_calls_over_time_hourly_bucket(self):
    """Test: calls over time hourly bucket."""
        store = NexusStore()
        base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        for i in range(5):
            call = _make_call("a1", "t1", called_at=base + timedelta(minutes=i * 10))
            store.calls.append(call)
        for i in range(3):
            call = _make_call("a1", "t2", called_at=base + timedelta(hours=1, minutes=i * 10))
            store.calls.append(call)
        metrics = UsageMetrics(store)
        series = metrics.calls_over_time(bucket="hour")
        assert len(series) == 2
        assert series[0]["total"] == 5
        assert series[1]["total"] == 3

    def test_counts_errors_separately(self):
    """Test: counts errors separately."""
        store = NexusStore()
        base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        store.calls.append(_make_call("a1", "t1", status="success", called_at=base))
        store.calls.append(_make_call("a1", "t2", status="error", called_at=base))
        metrics = UsageMetrics(store)
        series = metrics.calls_over_time(bucket="hour")
        assert len(series) == 1
        assert series[0]["total"] == 2
        assert series[0]["errors"] == 1

    def test_invalid_bucket_raises(self):
    """Test: invalid bucket raises."""
        store = NexusStore()
        metrics = UsageMetrics(store)
        with pytest.raises(ValueError, match="bucket must be one of"):
            metrics.calls_over_time(bucket="weekly")

    def test_empty_store_returns_empty_series(self):
    """Test: empty store returns empty series."""
        store = NexusStore()
        metrics = UsageMetrics(store)
        assert metrics.calls_over_time(bucket="hour") == []


class TestPerformanceByAgent:
    """TestPerformanceByAgent."""
    def test_by_agent_returns_metrics_per_agent(self):
    """Test: by agent returns metrics per agent."""
        store = NexusStore()
        store.agents.add("a1")
        store.agents.add("a2")
        store.calls.append(_make_call("a1", "t1", duration_ms=10.0))
        store.calls.append(_make_call("a1", "t2", duration_ms=20.0))
        store.calls.append(_make_call("a2", "t1", duration_ms=50.0))
        tracker = PerformanceTracker(store)
        result = tracker.by_agent()
        assert "a1" in result
        assert "a2" in result
        assert result["a1"]["calls"] == 2
        assert result["a1"]["avg_ms"] == 15.0
        assert result["a2"]["calls"] == 1
        assert result["a2"]["avg_ms"] == 50.0

    def test_by_agent_empty_for_no_calls(self):
    """Test: by agent empty for no calls."""
        store = NexusStore()
        store.agents.add("a1")
        tracker = PerformanceTracker(store)
        result = tracker.by_agent()
        assert result["a1"]["calls"] == 0
