from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus.server.app import create_app, RateLimitMiddleware


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestVersionEndpoint:
    def test_version_returns_semver(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)


class TestPagination:
    def test_plugins_pagination_default(self, client):
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
        resp = client.get("/plugins?offset=0&limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 1
        assert len(data["items"]) <= 1

    def test_workflows_pagination_default(self, client):
        resp = client.get("/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "has_more" in data


class TestRateLimitMiddleware:
    def test_allows_under_limit(self):
        rl = RateLimitMiddleware(max_requests=5, window_seconds=60)
        # Simulate 4 requests — all should pass
        import asyncio

        async def simulate():
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
        rl = RateLimitMiddleware(max_requests=3, window_seconds=60)
        import asyncio

        async def simulate():
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
    def test_batch_call_empty(self, client):
        resp = client.post("/tools/batch", json=[])
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["succeeded"] == 0
        assert data["failed"] == 0

    def test_batch_call_single(self, client):
        resp = client.post("/tools/batch", json=[
            {"agent_id": "test-agent", "tool_id": "http", "action": "fetch", "params": {"url": "https://example.com"}}
        ])
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1

    def test_batch_call_multiple(self, client):
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
    def test_health_detailed_returns_store_stats(self, client):
        resp = client.get("/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "plugins" in data
        assert "store" in data
        assert "agents" in data["store"]
        assert "calls" in data["store"]


class TestStoreExportImport:
    def test_export_returns_data(self, client):
        resp = client.post("/store/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "plugins" in data
        assert "workflows" in data

    def test_import_replaces_data(self, client):
        # First export
        resp = client.post("/store/export")
        exported = resp.json()

        # Import it back
        resp = client.post("/store/import", json=exported)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] is True


class TestListAgentsEndpoint:
    def test_list_agents_empty(self, client):
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_agents_with_registered(self, client):
        # Register an agent via binding
        client.post("/bindings", json={"agent_id": "agent-x", "tool_id": "http", "level": "read"})
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        agent_ids = [a["agent_id"] for a in data["items"]]
        assert "agent-x" in agent_ids

    def test_list_agents_includes_metadata(self, client):
        client.post("/bindings", json={"agent_id": "agent-meta", "tool_id": "http", "level": "write"})
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        agent = next(a for a in data["items"] if a["agent_id"] == "agent-meta")
        assert "bindings" in agent
        assert "total_calls" in agent
        assert agent["bindings"] >= 1


class TestAgentUsageEndpoint:
    def test_agent_usage_not_found(self, client):
        resp = client.get("/agents/nonexistent/usage")
        assert resp.status_code == 404

    def test_agent_usage_returns_metrics(self, client):
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
    def test_metrics_no_params(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data
        assert "by_tool" in data
        assert "by_agent" in data
        assert "error_rate" in data

    def test_metrics_with_since(self, client):
        resp = client.get("/metrics?since=2026-01-01T00:00:00Z")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data

    def test_metrics_with_since_and_until(self, client):
        resp = client.get("/metrics?since=2026-01-01T00:00:00Z&until=2099-12-31T23:59:59Z")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data

    def test_metrics_invalid_since(self, client):
        resp = client.get("/metrics?since=not-a-date")
        assert resp.status_code == 400

    def test_metrics_invalid_until(self, client):
        resp = client.get("/metrics?until=also-not-a-date")
        assert resp.status_code == 400


class TestValueErrorHandler:
    def test_value_error_returns_400(self, client):
        # Trigger a ValueError via invalid binding level
        resp = client.post("/bindings", json={"agent_id": "a", "tool_id": "b", "level": "superadmin"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "bad_request"
        assert data["code"] == "BAD_REQUEST"


class TestVersionBumped:
    def test_version_is_1_1_0(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.1.0"
