"""Tests for OMEGA Evolution v7.43 — New features:
- X-Response-Time header on all responses (timing_middleware)
- Concurrent batch_call endpoint (async backend)
- Graceful shutdown via lifespan context manager
- GET /version endpoint
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus.server.app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def client() -> TestClient:
    """Create a fresh test client with initialized app and agent permissions."""
    app = create_app()
    c = TestClient(app)
    c.post("/init")
    # Grant agent-1 admin permission on the http plugin (no auth required)
    c.post("/bindings", json={
        "agent_id": "agent-1",
        "tool_id": "http",
        "level": "admin",
    })
    return c


# ── X-Response-Time Header ────────────────────────────────────────────

class TestResponseTimeHeader:
    """Every response should include X-Response-Time header."""

    def test_health_has_timing(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert "X-Response-Time" in response.headers
        assert response.headers["X-Response-Time"].endswith("ms")

    def test_plugins_has_timing(self, client):
        response = client.get("/plugins")
        assert "X-Response-Time" in response.headers

    def test_version_has_timing(self, client):
        response = client.get("/version")
        assert "X-Response-Time" in response.headers

    def test_timing_is_non_negative(self, client):
        response = client.get("/health")
        header_val = response.headers["X-Response-Time"]
        ms = float(header_val.rstrip("ms"))
        assert ms >= 0

    def test_timing_on_list_agents(self, client):
        response = client.get("/agents")
        assert "X-Response-Time" in response.headers


# ── Concurrent Batch Call ─────────────────────────────────────────────

class TestBatchCall:
    """POST /tools/batch should return results for all calls."""

    def test_empty_batch(self, client):
        response = client.post("/tools/batch", json=[])
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["succeeded"] == 0
        assert data["failed"] == 0

    def test_single_call_batch(self, client):
        payload = [{"agent_id": "agent-1", "tool_id": "http", "action": "info", "params": {}}]
        response = client.post("/tools/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1

    def test_batch_returns_duration(self, client):
        payload = [{"agent_id": "agent-1", "tool_id": "http", "action": "info", "params": {}}]
        response = client.post("/tools/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        for result in data["results"]:
            assert "duration_ms" in result

    def test_batch_multiple_calls(self, client):
        payload = [
            {"agent_id": "agent-1", "tool_id": "http", "action": "info", "params": {}},
            {"agent_id": "agent-1", "tool_id": "http", "action": "status", "params": {}},
        ]
        response = client.post("/tools/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2

    def test_batch_succeeded_count(self, client):
        payload = [{"agent_id": "agent-1", "tool_id": "http", "action": "info", "params": {}}]
        response = client.post("/tools/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["succeeded"] + data["failed"] == len(data["results"])


# ── Graceful Shutdown (Lifespan) ──────────────────────────────────────

class TestLifespan:
    """Verify lifespan context manager is properly configured."""

    def test_app_has_state(self):
        """create_app should set store, manager, and api on app.state."""
        app = create_app()
        assert hasattr(app.state, "store")
        assert hasattr(app.state, "manager")
        assert hasattr(app.state, "api")

    def test_store_stats_available(self):
        """Store.stats() should return dict with expected keys."""
        from nexus.core.db import NexusStore
        store = NexusStore()
        stats = store.stats()
        assert isinstance(stats, dict)
        assert "calls" in stats
        assert "agents" in stats
        assert "plugins" in stats


# ── Version Endpoint ──────────────────────────────────────────────────

class TestVersion:
    """GET /version should return the Nexus version."""

    def test_returns_200(self, client):
        response = client.get("/version")
        assert response.status_code == 200

    def test_returns_version_string(self, client):
        response = client.get("/version")
        data = response.json()
        assert "version" in data
        parts = data["version"].split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts)

    def test_version_matches_package(self, client):
        from nexus import __version__
        response = client.get("/version")
        data = response.json()
        assert data["version"] == __version__


# ── Request ID + Timing Together ──────────────────────────────────────

class TestHeadersTogether:
    """Both X-Request-ID and X-Response-Time should be present."""

    def test_health_has_both(self, client):
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert "X-Response-Time" in response.headers

    def test_custom_request_id_preserved(self, client):
        custom_id = "test-req-abc123"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id
        assert "X-Response-Time" in response.headers

    def test_plugins_has_both(self, client):
        response = client.get("/plugins")
        assert "X-Request-ID" in response.headers
        assert "X-Response-Time" in response.headers
