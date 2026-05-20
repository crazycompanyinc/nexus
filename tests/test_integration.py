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
    from nexus.metrics._stats import latency_stats
    stats = latency_stats([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert stats["count"] == 10
    assert stats["min"] == 10
    assert stats["max"] == 100
    assert stats["avg"] == 55.0
    assert stats["p50"] > 0
    assert stats["p95"] >= stats["p50"]


def test_latency_percentiles_empty():
    from nexus.metrics._stats import latency_stats
    stats = latency_stats([])
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


def test_fastapi_delete_workflow():
    from starlette.testclient import TestClient
    app = create_app()
    app.state.manager.install_all_builtins()
    client = TestClient(app)
    # Create a workflow
    resp = client.post("/workflows", json={
        "name": "test-wf",
        "steps": [{"tool_id": "github", "action": "repos.list"}],
        "created_by": "agent",
    })
    wf_id = resp.json()["id"]
    # Delete it
    resp = client.delete(f"/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    # Deleting again should 404
    resp = client.delete(f"/workflows/{wf_id}")
    assert resp.status_code == 404


def test_fastapi_unbind():
    from starlette.testclient import TestClient
    app = create_app()
    app.state.manager.install_all_builtins()
    client = TestClient(app)
    # Bind then unbind
    client.post("/bindings", json={"agent_id": "a1", "tool_id": "github", "level": "read"})
    resp = client.delete("/bindings/a1/github")
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True


def test_fastapi_workflow_run_fail_fast():
    from starlette.testclient import TestClient
    app = create_app()
    app.state.manager.install_all_builtins()
    client = TestClient(app)
    app.state.api.grant("agent", "github", "read")
    resp = client.post("/workflows", json={
        "name": "ff-wf",
        "steps": [
            {"tool_id": "github", "action": "repos.list"},
            {"tool_id": "github", "action": "nonexistent.action"},
            {"tool_id": "github", "action": "repos.list"},
        ],
        "created_by": "agent",
    })
    wf_id = resp.json()["id"]
    resp = client.post(f"/workflows/{wf_id}/run?agent_id=agent&fail_fast=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"] == 1
    assert len(data["results"]) == 2  # stopped after 2nd step failed


def test_step_result_repr():
    from nexus.composition.workflow import StepResult
    ok = StepResult(step_index=0, tool_id="p1", action="read", success=True, duration_ms=1.5)
    assert "ok" in repr(ok)
    assert "p1" in repr(ok)
    fail = StepResult(step_index=1, tool_id="p2", action="write", success=False, duration_ms=3.2, error="boom")
    assert "FAIL" in repr(fail)
    assert "boom" not in repr(fail)  # repr doesn't include error detail
