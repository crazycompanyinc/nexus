from __future__ import annotations

import pytest

from nexus.composition.workflow import Pipeline, WorkflowBuilder, StepResult
from nexus.core.models import WorkflowStep


def test_pipeline_retry_on_failure(hub):
    """Pipeline retries a failing step up to max_retries times before marking failed."""
    store, _, api = hub
    api.grant("agent", "github", "read")
    call_count = 0

    # Create a workflow with a step that will fail
    workflow = WorkflowBuilder(store).create(
        "retry-wf",
        [{"tool_id": "github", "action": "repos.list", "max_retries": 2, "retry_delay_ms": 10}],
        "agent",
    )
    # Patch the step to fail first 2 times then succeed
    original_call = api.call
    def flaky_call(agent_id, tool_id, action, params, fallback_tools=None):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("transient error")
        return original_call(agent_id, tool_id, action, params, fallback_tools)

    api.call = flaky_call
    results = Pipeline(api, store).run(workflow.id, "agent")
    assert results[0].success
    assert call_count == 3  # 2 failures + 1 success


def test_pipeline_retry_exhausted(hub):
    """Pipeline marks step failed when all retries are exhausted."""
    store, _, api = hub
    api.grant("agent", "github", "read")

    workflow = WorkflowBuilder(store).create(
        "retry-exhaust-wf",
        [{"tool_id": "github", "action": "repos.list", "max_retries": 1, "retry_delay_ms": 10}],
        "agent",
    )
    # Always fail
    api.call = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("permanent error"))
    results = Pipeline(api, store).run(workflow.id, "agent")
    assert not results[0].success
    assert "permanent error" in results[0].error


def test_conditional_step_previous_failed(hub):
    """Step with condition='previous_failed' runs only when previous step failed."""
    store, _, api = hub
    api.grant("agent", "github", "read")

    workflow = WorkflowBuilder(store).create(
        "cond-wf",
        [
            {"tool_id": "github", "action": "repos.list"},
            {"tool_id": "github", "action": "repos.list", "condition": "previous_failed"},
        ],
        "agent",
    )
    results = Pipeline(api, store).run(workflow.id, "agent")
    # First step succeeds, second should be skipped
    assert len(results) == 1
    assert results[0].success


def test_conditional_step_previous_succeeded(hub):
    """Step with condition='previous_succeeded' runs only when previous step succeeded."""
    store, _, api = hub
    api.grant("agent", "github", "read")

    workflow = WorkflowBuilder(store).create(
        "cond-succ-wf",
        [
            {"tool_id": "github", "action": "repos.list"},
            {"tool_id": "github", "action": "repos.list", "condition": "previous_succeeded"},
        ],
        "agent",
    )
    results = Pipeline(api, store).run(workflow.id, "agent")
    # Both should run
    assert len(results) == 2
    assert all(r.success for r in results)


def test_workflow_step_default_retry_fields():
    """WorkflowStep has sensible defaults for retry fields."""
    step = WorkflowStep(tool_id="test", action="act")
    assert step.max_retries == 0
    assert step.retry_delay_ms == 100.0


def test_workflow_audit_includes_duration(hub):
    """Workflow.audit 'workflow.ran' event includes duration_ms."""
    store, _, api = hub
    api.grant("agent", "github", "read")

    workflow = WorkflowBuilder(store).create(
        "audit-wf",
        [{"tool_id": "github", "action": "repos.list"}],
        "agent",
    )
    Pipeline(api, store).run(workflow.id, "agent")

    ran_events = [e for e in store.audit_events if e.get("type") == "workflow.ran"]
    assert len(ran_events) >= 1
    assert "duration_ms" in ran_events[-1]
    assert ran_events[-1]["duration_ms"] >= 0


def test_metrics_workflows_endpoint():
    """GET /metrics/workflows returns workflow execution stats."""
    from nexus.server.app import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/metrics/workflows" in paths


def test_metrics_performance_endpoint():
    """GET /metrics/performance returns latency stats."""
    from nexus.server.app import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/metrics/performance" in paths
