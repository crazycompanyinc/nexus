from __future__ import annotations

from click.testing import CliRunner

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
    summary = UsageMetrics(store).summary()
    assert summary["by_tool"]["github"] == 1
    assert "latency_ms" in summary
    assert summary["latency_ms"]["count"] >= 1


def test_latency_percentiles():
    from nexus.metrics.metrics import UsageMetrics
    stats = UsageMetrics._latency_stats([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert stats["count"] == 10
    assert stats["min"] == 10
    assert stats["max"] == 100
    assert stats["avg"] == 55.0
    assert stats["p50"] > 0
    assert stats["p95"] >= stats["p50"]


def test_latency_percentiles_empty():
    from nexus.metrics.metrics import UsageMetrics
    stats = UsageMetrics._latency_stats([])
    assert stats["count"] == 0
    assert stats["avg"] == 0.0


def test_performance_tracker_after_call(hub):
    store, _, api = hub
    api.grant("agent", "github", "read")
    api.call("agent", "github", "repos.list", {})
    assert PerformanceTracker(store).latency()["max_ms"] >= 0


def test_fastapi_app_exposes_routes():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert {"/init", "/plugins", "/tools/{tool_id}/call", "/metrics", "/health"} <= paths


def test_fastapi_state_can_initialize_plugins():
    app = create_app()
    assert len(app.state.manager.install_all_builtins()) == 10


def test_fastapi_runtime_enforces_permissions():
    app = create_app()
    app.state.manager.install_all_builtins()
    app.state.api.grant("agent", "github", "read")
    assert app.state.api.call("agent", "github", "repos.list", {})[0]["name"] == "nexus"


def test_cli_demo_runs():
    result = CliRunner().invoke(cli, ["demo"])
    assert result.exit_code == 0
    assert "Deploy notification" in result.output


def test_cli_init_lists_plugins():
    result = CliRunner().invoke(cli, ["init"])
    assert result.exit_code == 0
    assert "github" in result.output
