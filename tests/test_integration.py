from __future__ import annotations

from click.testing import CliRunner
from fastapi.testclient import TestClient

from nexus.cli import cli
from nexus.discovery.discovery import ToolDiscovery
from nexus.metrics.metrics import UsageMetrics
from nexus.metrics.performance import PerformanceTracker
from nexus.server.app import create_app


def test_discovery_lists_tools(hub):
    _, manager, _ = hub
    tools = ToolDiscovery(manager).available_tools()
    assert any(tool["id"] == "github" for tool in tools)


def test_discovery_by_capability(hub):
    _, manager, _ = hub
    assert "slack" in ToolDiscovery(manager).by_capability("messages.send")


def test_usage_metrics_after_call(hub):
    store, _, api = hub
    api.grant("agent", "github", "read")
    api.call("agent", "github", "repos.list", {})
    assert UsageMetrics(store).summary()["by_tool"]["github"] == 1


def test_performance_tracker_after_call(hub):
    store, _, api = hub
    api.grant("agent", "github", "read")
    api.call("agent", "github", "repos.list", {})
    assert PerformanceTracker(store).latency()["max_ms"] >= 0


def test_fastapi_init_and_plugins():
    client = TestClient(create_app())
    assert len(client.post("/init").json()["plugins"]) == 10
    assert len(client.get("/plugins").json()) == 10


def test_fastapi_call_enforces_permission():
    client = TestClient(create_app())
    client.post("/init")
    response = client.post("/tools/github/call", json={"agent_id": "agent", "action": "repos.list"})
    assert response.status_code == 403


def test_fastapi_binding_and_call():
    client = TestClient(create_app())
    client.post("/init")
    client.post("/bindings", json={"agent_id": "agent", "tool_id": "github", "level": "read"})
    response = client.post("/tools/github/call", json={"agent_id": "agent", "action": "repos.list"})
    assert response.json()["result"][0]["name"] == "nexus"


def test_cli_demo_runs():
    result = CliRunner().invoke(cli, ["demo"])
    assert result.exit_code == 0
    assert "Deploy notification" in result.output


def test_cli_init_lists_plugins():
    result = CliRunner().invoke(cli, ["init"])
    assert result.exit_code == 0
    assert "github" in result.output
