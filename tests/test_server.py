"""Integration tests for the Nexus FastAPI HTTP server.

Tests all REST endpoints: plugins, bindings, calls, workflows, store,
and error handling for 404/422 responses.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus.server.app import create_app, RateLimitMiddleware


@pytest.fixture
def client():
    """client."""
    app = create_app()
    return TestClient(app)


class TestVersionEndpoint:
    """TestVersionEndpoint."""
    def test_version_returns_semver(self, client):
        """Test: version returns semver."""
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)


class TestPagination:
    """TestPagination."""
    def test_plugins_pagination_default(self, client):
        """Test: plugins pagination default."""
        resp = client.get("/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert "has_more" in data
        assert data["offset"] == 0

    def test_plugins_pagination_offset(self, client):
        """Test: plugins pagination offset."""
        resp = client.get("/plugins?offset=0&limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 1
        assert len(data["items"]) <= 1

    def test_workflows_pagination_default(self, client):
        """Test: workflows pagination default."""
        resp = client.get("/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "has_more" in data


class TestRateLimitMiddleware:
    """TestRateLimitMiddleware."""
    def test_allows_under_limit(self):
        """Test: allows under limit."""
        rl = RateLimitMiddleware(max_requests=5, window_seconds=60)
        # Simulate 4 requests — all should pass
        import asyncio

        async def simulate():
            """simulate."""
            from starlette.requests import Request
            from starlette.datastructures import Address

            results = []
            for _ in range(4):
                scope = {
                    "type": "http",
                    "client": Address("127.0.0.1", 12345),
                    "method": "GET",
                    "path": "/test",
                    "query_string": b"",
                    "headers": [],
                }
                req = Request(scope)
                result = await rl.check(req)
                results.append(result)
            return results

        results = asyncio.run(simulate())
        assert all(r is None for r in results), "All requests under limit should pass"

    def test_blocks_over_limit(self):
        """Test: blocks over limit."""
        rl = RateLimitMiddleware(max_requests=3, window_seconds=60)
        import asyncio

        async def simulate():
            """simulate."""
            from starlette.requests import Request
            from starlette.datastructures import Address

            results = []
            for _ in range(5):
                scope = {
                    "type": "http",
                    "client": Address("127.0.0.1", 12345),
                    "method": "GET",
                    "path": "/test",
                    "query_string": b"",
                    "headers": [],
                }
                req = Request(scope)
                result = await rl.check(req)
                results.append(result)
            return results

        results = asyncio.run(simulate())
        # First 3 should pass, last 2 should be blocked
        assert results[0] is None
        assert results[1] is None
        assert results[2] is None
        assert results[3] is not None  # blocked
        assert results[4] is not None  # blocked
        assert results[3].status_code == 429


class TestBatchCallEndpoint:
    """TestBatchCallEndpoint."""
    def test_batch_call_empty(self, client):
        """Test: batch call empty."""
        resp = client.post("/tools/batch", json=[])
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["succeeded"] == 0
        assert data["failed"] == 0

    def test_batch_call_single(self, client):
        """Test: batch call single."""
        resp = client.post("/tools/batch", json=[
            {"agent_id": "test-agent", "tool_id": "http", "action": "fetch", "params": {"url": "https://example.com"}}
        ])
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1

    def test_batch_call_multiple(self, client):
        """Test: batch call multiple."""
        resp = client.post("/tools/batch", json=[
            {"agent_id": "test-agent", "tool_id": "http", "action": "fetch", "params": {}},
            {"agent_id": "test-agent", "tool_id": "filesystem", "action": "file.read", "params": {"path": "/tmp/test"}},
        ])
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert "succeeded" in data
        assert "failed" in data


class TestHealthDetailed:
    """TestHealthDetailed."""
    def test_health_detailed_returns_store_stats(self, client):
        """Test: health detailed returns store stats."""
        resp = client.get("/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "plugins" in data
        assert "store" in data
        assert "agents" in data["store"]
        assert "calls" in data["store"]


class TestStoreExportImport:
    """TestStoreExportImport."""
    def test_export_returns_data(self, client):
        """Test: export returns data."""
        resp = client.post("/store/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "plugins" in data
        assert "workflows" in data

    def test_import_replaces_data(self, client):
        """Test: import replaces data."""
        # First export
        resp = client.post("/store/export")
        exported = resp.json()

        # Import it back
        resp = client.post("/store/import", json=exported)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] is True


class TestListAgentsEndpoint:
    """TestListAgentsEndpoint."""
    def test_list_agents_empty(self, client):
        """Test: list agents empty."""
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_agents_with_registered(self, client):
        """Test: list agents with registered."""
        # Register an agent via binding
        client.post("/bindings", json={"agent_id": "agent-x", "tool_id": "http", "level": "read"})
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        agent_ids = [a["agent_id"] for a in data["items"]]
        assert "agent-x" in agent_ids

    def test_list_agents_includes_metadata(self, client):
        """Test: list agents includes metadata."""
        client.post("/bindings", json={"agent_id": "agent-meta", "tool_id": "http", "level": "write"})
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        agent = next(a for a in data["items"] if a["agent_id"] == "agent-meta")
        assert "bindings" in agent
        assert "total_calls" in agent
        assert agent["bindings"] >= 1


class TestAgentUsageEndpoint:
    """TestAgentUsageEndpoint."""
    def test_agent_usage_not_found(self, client):
        """Test: agent usage not found."""
        resp = client.get("/agents/nonexistent/usage")
        assert resp.status_code == 404

    def test_agent_usage_returns_metrics(self, client):
        """Test: agent usage returns metrics."""
        # Register agent and make a call
        client.post("/bindings", json={"agent_id": "agent-usage", "tool_id": "http", "level": "write"})
        client.post("/tools/http/call", json={
            "agent_id": "agent-usage", "tool_id": "http",
            "action": "fetch", "params": {"url": "https://example.com"}
        })
        resp = client.get("/agents/agent-usage/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "agent-usage"
        assert data["calls"] >= 1
        assert "actions" in data
        assert "latency_ms" in data


class TestMetricsTimeRange:
    """TestMetricsTimeRange."""
    def test_metrics_no_params(self, client):
        """Test: metrics no params."""
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data
        assert "by_tool" in data
        assert "by_agent" in data
        assert "error_rate" in data

    def test_metrics_with_since(self, client):
        """Test: metrics with since."""
        resp = client.get("/metrics?since=2026-01-01T00:00:00Z")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data

    def test_metrics_with_since_and_until(self, client):
        """Test: metrics with since and until."""
        resp = client.get("/metrics?since=2026-01-01T00:00:00Z&until=2099-12-31T23:59:59Z")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data

    def test_metrics_invalid_since(self, client):
        """Test: metrics invalid since."""
        resp = client.get("/metrics?since=not-a-date")
        assert resp.status_code == 400

    def test_metrics_invalid_until(self, client):
        """Test: metrics invalid until."""
        resp = client.get("/metrics?until=also-not-a-date")
        assert resp.status_code == 400


class TestValueErrorHandler:
    """TestValueErrorHandler."""
    def test_value_error_returns_400(self, client):
        """Test: value error returns 400."""
        # Trigger a ValueError via workflow creation with empty name
        resp = client.post("/workflows", json={"name": "", "steps": [], "created_by": "test"})
        assert resp.status_code == 400
        data = resp.json()
        assert "detail" in data


class TestVersionBumped:
    """TestVersionBumped."""
    def test_version_is_current(self, client):
        """Test: version matches current release."""
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.6.1"


class TestTopologyEndpoint:
    """Tests for the /topology system graph endpoint."""

    def test_topology_returns_nodes_and_edges(self, client):
        """Topology must return 'nodes' and 'edges' keys."""
        resp = client.get("/topology")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_topology_includes_plugin_nodes(self, client):
        """After init, topology should have plugin nodes."""
        client.post("/init")
        resp = client.get("/topology")
        data = resp.json()
        plugin_nodes = [n for n in data["nodes"] if n["type"] == "plugin"]
        assert len(plugin_nodes) > 0

    def test_topology_nodes_have_required_fields(self, client):
        """Every node must have 'id' and 'type' fields."""
        resp = client.get("/topology")
        data = resp.json()
        for node in data["nodes"]:
            assert "id" in node
            assert "type" in node
            assert node["type"] in ("plugin", "agent", "workflow")

    def test_topology_edges_have_source_target(self, client):
        """Every edge must have 'source' and 'target' fields."""
        resp = client.get("/topology")
        data = resp.json()
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
