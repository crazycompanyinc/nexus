"""Tests for Prometheus metrics endpoint and UsageMetrics.to_prometheus()."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from nexus.server.app import create_app
from nexus.core.models import CallStatus, ToolCall


client = TestClient(create_app())


class TestPrometheusEndpoint:
    """Tests for GET /metrics/prometheus."""

    def test_prometheus_returns_plain_text(self) -> None:
        resp = client.get("/metrics/prometheus")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_prometheus_has_help_and_type_lines(self) -> None:
        resp = client.get("/metrics/prometheus")
        text = resp.text
        assert "# HELP nexus_calls_total" in text
        assert "# TYPE nexus_calls_total counter" in text
        assert "# HELP nexus_agents" in text
        assert "# TYPE nexus_agents gauge" in text

    def test_prometheus_has_call_counter_zero_default(self) -> None:
        resp = client.get("/metrics/prometheus")
        assert "nexus_calls_total 0" in resp.text

    def test_prometheus_metrics_after_calls(self) -> None:
        # Make some tool calls
        client.post("/tools/http/call", json={
            "agent_id": "test-agent",
            "tool_id": "http",
            "action": "fetch",
            "params": {"url": "https://example.com"},
        })
        resp = client.get("/metrics/prometheus")
        text = resp.text
        assert "nexus_calls_total 1" in text
        assert 'nexus_calls_total{tool_id="http"} 1' in text

    def test_prometheus_gauges_present(self) -> None:
        resp = client.get("/metrics/prometheus")
        text = resp.text
        assert "nexus_agents" in text
        assert "nexus_workflows" in text
        assert "nexus_bindings" in text


class TestCircuitBreakerEndpoint:
    """Tests for GET /metrics/circuit-breakers."""

    def test_circuit_breakers_returns_dict(self) -> None:
        resp = client.get("/metrics/circuit-breakers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_circuit_breakers_have_state_or_no_cb(self) -> None:
        resp = client.get("/metrics/circuit-breakers")
        data = resp.json()
        for plugin_id, status in data.items():
            assert "state" in status


class TestAuditPagination:
    """Tests for GET /audit with offset pagination."""

    def test_audit_pagination_returns_paginated(self) -> None:
        resp = client.get("/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert "has_more" in data

    def test_audit_pagination_default_offset(self) -> None:
        resp = client.get("/audit", params={"limit": 10})
        data = resp.json()
        assert data["offset"] == 0
        assert data["limit"] == 10

    def test_audit_pagination_offset_param(self) -> None:
        resp = client.get("/audit", params={"offset": 5, "limit": 10})
        data = resp.json()
        assert data["offset"] == 5
        assert data["limit"] == 10


class TestVersionBump:
    """Tests for version 1.3.0."""

    def test_version_is_1_3_0(self) -> None:
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.3.0"
