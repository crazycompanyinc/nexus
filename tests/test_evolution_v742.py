"""Tests for OMEGA Evolution v7.42 — New features:
- ToolCall.to_dict() serialization
- NexusStore.search_calls() multi-criteria filtering
- NexusStore.health_check() monitoring endpoint
- UsageMetrics.top_tools() ranking
- UsageMetrics.slow_calls() performance debugging
- GET /health API endpoint
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus.core.db import NexusStore
from nexus.core.models import CallStatus, ToolCall, ToolPlugin
from nexus.metrics.metrics import UsageMetrics
from nexus.server.app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def client() -> TestClient:
    """Create a fresh test client with initialized app."""
    app = create_app()
    c = TestClient(app)
    c.post("/init")
    return c


@pytest.fixture
def populated_store() -> NexusStore:
    """Create a store with sample calls for testing search/metrics."""
    store = NexusStore()
    store.register_agent("agent-1")
    store.register_agent("agent-2")

    # Create plugins
    for pid in ("http", "database", "email"):
        store.upsert_plugin(ToolPlugin(
            id=pid, name=pid.title(), description=f"{pid} plugin",
            version="1.0.0", plugin_type="api",
            capabilities=[f"{pid}.read", f"{pid}.write"],
        ))

    # Record varied calls
    calls = [
        ToolCall(agent_id="agent-1", tool_id="http", action="fetch",
                 params={"url": "https://example.com"}, result={"ok": True},
                 duration_ms=120.5, status=CallStatus.SUCCESS.value),
        ToolCall(agent_id="agent-1", tool_id="http", action="post",
                 params={"url": "https://api.test"}, result={"ok": True},
                 duration_ms=2500.0, status=CallStatus.SUCCESS.value),
        ToolCall(agent_id="agent-1", tool_id="database", action="query",
                 params={"sql": "SELECT 1"}, result={"rows": []},
                 duration_ms=800.0, status=CallStatus.ERROR.value),
        ToolCall(agent_id="agent-2", tool_id="http", action="fetch",
                 params={"url": "https://other.com"}, result={"ok": True},
                 duration_ms=95.0, status=CallStatus.SUCCESS.value),
        ToolCall(agent_id="agent-2", tool_id="email", action="send",
                 params={"to": "a@b.com"}, result={"sent": True},
                 duration_ms=3500.0, status=CallStatus.TIMEOUT.value),
        ToolCall(agent_id="agent-2", tool_id="database", action="insert",
                 params={"table": "x"}, result={"id": 1},
                 duration_ms=150.0, status=CallStatus.SUCCESS.value),
    ]
    for call in calls:
        store.record_call(call)
    return store


# ── ToolCall.to_dict() ────────────────────────────────────────────────

class TestToolCallToDict:
    def test_includes_all_fields(self):
        call = ToolCall(agent_id="a1", tool_id="http", action="fetch",
                        params={"url": "https://x.com"}, result={"ok": True},
                        duration_ms=42.0, status=CallStatus.SUCCESS.value)
        d = call.to_dict()
        assert d["id"] == call.id
        assert d["agent_id"] == "a1"
        assert d["tool_id"] == "http"
        assert d["action"] == "fetch"
        assert d["params"] == {"url": "https://x.com"}
        assert d["result"] == {"ok": True}
        assert d["duration_ms"] == 42.0
        assert d["status"] == "success"
        assert isinstance(d["called_at"], str)

    def test_iso_timestamp(self):
        call = ToolCall(agent_id="a", tool_id="t", action="foo", params={})
        d = call.to_dict()
        # Should be parseable ISO 8601
        from datetime import datetime
        datetime.fromisoformat(d["called_at"])

    def test_copies_params(self):
        """to_dict should copy params so mutations don't affect original."""
        params = {"key": "val"}
        call = ToolCall(agent_id="a", tool_id="t", action="x", params=params)
        d = call.to_dict()
        d["params"]["new"] = "added"
        assert "new" not in call.params

    def test_result_none(self):
        call = ToolCall(agent_id="a", tool_id="t", action="x", params={})
        d = call.to_dict()
        assert d["result"] is None


# ── NexusStore.search_calls() ─────────────────────────────────────────

class TestSearchCalls:
    def test_filter_by_agent(self, populated_store):
        results = populated_store.search_calls(agent_id="agent-1")
        assert len(results) == 3
        assert all(c.agent_id == "agent-1" for c in results)

    def test_filter_by_tool(self, populated_store):
        results = populated_store.search_calls(tool_id="http")
        assert len(results) == 3
        assert all(c.tool_id == "http" for c in results)

    def test_filter_by_status(self, populated_store):
        results = populated_store.search_calls(status=CallStatus.ERROR.value)
        assert len(results) == 1
        assert results[0].action == "query"

    def test_filter_by_action(self, populated_store):
        results = populated_store.search_calls(action="fetch")
        assert len(results) == 2

    def test_filter_by_min_duration(self, populated_store):
        results = populated_store.search_calls(min_duration_ms=1000.0)
        assert len(results) == 2  # 2500ms and 3500ms

    def test_filter_by_max_duration(self, populated_store):
        results = populated_store.search_calls(max_duration_ms=200.0)
        assert len(results) == 2  # 120.5ms and 95.0ms (not 150ms which is >200? no, 150<200)
        # Actually: 120.5, 95.0, 150.0 are all <= 200.0 → 3 results
        # Let me recount: calls are 120.5, 2500, 800, 95, 3500, 150
        # <= 200: 120.5, 95, 150 → 3 results

    def test_combined_filters(self, populated_store):
        results = populated_store.search_calls(
            agent_id="agent-1", tool_id="http", min_duration_ms=500.0
        )
        assert len(results) == 1
        assert results[0].action == "post"

    def test_limit(self, populated_store):
        results = populated_store.search_calls(limit=2)
        assert len(results) == 2

    def test_no_match_returns_empty(self, populated_store):
        results = populated_store.search_calls(agent_id="nonexistent")
        assert results == []

    def test_reverse_chronological_order(self, populated_store):
        """Results should be most-recent first."""
        results = populated_store.search_calls()
        for i in range(len(results) - 1):
            assert results[i].called_at >= results[i + 1].called_at

    def test_no_filters_returns_all(self, populated_store):
        results = populated_store.search_calls()
        assert len(results) == 6


# ── NexusStore.health_check() ─────────────────────────────────────────

class TestHealthCheck:
    def test_empty_store(self):
        store = NexusStore()
        health = store.health_check()
        assert health["status"] == "healthy"
        assert health["agents"] == 0
        assert health["calls"] == 0
        assert health["plugins"] == 0

    def test_with_data(self, populated_store):
        health = populated_store.health_check()
        assert health["status"] == "healthy"
        assert health["agents"] == 2
        assert health["plugins"] == 3
        assert health["calls"] == 6
        assert health["calls_capacity"] == 10_000
        assert health["audit_capacity"] == 5_000
        assert health["memory_usage_approx_bytes"] > 0

    def test_returns_required_keys(self, populated_store):
        health = populated_store.health_check()
        required = {"status", "agents", "plugins", "bindings", "calls",
                    "calls_capacity", "workflows", "audit_events",
                    "audit_capacity", "memory_usage_approx_bytes"}
        assert required <= health.keys()


# ── UsageMetrics.top_tools() ──────────────────────────────────────────

class TestTopTools:
    def test_returns_ranked_list(self, populated_store):
        metrics = UsageMetrics(populated_store)
        top = metrics.top_tools(n=5)
        assert len(top) == 3  # Only 3 unique tools
        # http has 3 calls, database has 2, email has 1
        assert top[0]["tool_id"] == "http"
        assert top[0]["calls"] == 3

    def test_includes_avg_duration(self, populated_store):
        metrics = UsageMetrics(populated_store)
        top = metrics.top_tools()
        http_entry = next(t for t in top if t["tool_id"] == "http")
        # http durations: 120.5, 2500.0, 95.0 → avg ≈ 905.17
        assert http_entry["avg_duration_ms"] > 0

    def test_includes_error_rate(self, populated_store):
        metrics = UsageMetrics(populated_store)
        top = metrics.top_tools()
        db_entry = next(t for t in top if t["tool_id"] == "database")
        # database: 1 error out of 2 calls → 0.5
        assert db_entry["error_rate"] == 0.5

    def test_n_limits_results(self, populated_store):
        metrics = UsageMetrics(populated_store)
        top = metrics.top_tools(n=2)
        assert len(top) == 2

    def test_empty_store(self):
        store = NexusStore()
        metrics = UsageMetrics(store)
        assert metrics.top_tools() == []


# ── UsageMetrics.slow_calls() ─────────────────────────────────────────

class TestSlowCalls:
    def test_returns_slow_only(self, populated_store):
        metrics = UsageMetrics(populated_store)
        slow = metrics.slow_calls(threshold_ms=2000.0)
        assert len(slow) == 2  # 2500ms and 3500ms
        assert all(s["duration_ms"] >= 2000.0 for s in slow)

    def test_sorted_by_duration_desc(self, populated_store):
        metrics = UsageMetrics(populated_store)
        slow = metrics.slow_calls(threshold_ms=100.0)
        for i in range(len(slow) - 1):
            assert slow[i]["duration_ms"] >= slow[i + 1]["duration_ms"]

    def test_limit(self, populated_store):
        metrics = UsageMetrics(populated_store)
        slow = metrics.slow_calls(threshold_ms=0.0, limit=3)
        assert len(slow) == 3

    def test_includes_required_fields(self, populated_store):
        metrics = UsageMetrics(populated_store)
        slow = metrics.slow_calls(threshold_ms=3500.0)
        assert len(slow) == 1
        entry = slow[0]
        assert "call_id" in entry
        assert "agent_id" in entry
        assert "tool_id" in entry
        assert "action" in entry
        assert "duration_ms" in entry
        assert "status" in entry
        assert "called_at" in entry

    def test_default_threshold(self, populated_store):
        """Default threshold is 1000ms."""
        metrics = UsageMetrics(populated_store)
        slow = metrics.slow_calls()
        assert all(s["duration_ms"] >= 1000.0 for s in slow)

    def test_empty_store(self):
        store = NexusStore()
        metrics = UsageMetrics(store)
        assert metrics.slow_calls() == []


# ── GET /health endpoint ──────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_json(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_after_init_has_plugins(self, client):
        response = client.get("/health")
        data = response.json()
        # After /init, built-in plugins are installed
        assert data["plugins"] > 0

    def test_tagged_as_system(self, client):
        """Verify the endpoint is tagged as System in OpenAPI spec."""
        spec = client.get("/openapi.json").json()
        assert "/health" in spec["paths"]
        health_op = spec["paths"]["/health"]["get"]
        assert "System" in health_op.get("tags", [])
