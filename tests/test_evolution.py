from __future__ import annotations

import pytest

from nexus.composition.workflow import Pipeline, WorkflowBuilder, StepResult
from nexus.core.circuit_breaker import CircuitBreaker
from nexus.core.db import NexusStore, ToolCall
from nexus.core.models import ToolPlugin, WorkflowStep


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


# ── OMEGA Evolution Cycle — New Tests ──

def test_stepresult_bool_true():
    """StepResult with success=True is truthy."""
    from nexus.composition.workflow import StepResult
    r = StepResult(step_index=0, tool_id="t", action="a", success=True)
    assert bool(r) is True
    assert r  # truthy check


def test_stepresult_bool_false():
    """StepResult with success=False is falsy."""
    from nexus.composition.workflow import StepResult
    r = StepResult(step_index=0, tool_id="t", action="a", success=False, error="fail")
    assert bool(r) is False
    assert not r  # falsy check


def test_stepresult_repr():
    """StepResult repr includes status and duration."""
    from nexus.composition.workflow import StepResult
    r = StepResult(step_index=1, tool_id="t", action="a", success=True, duration_ms=42.5)
    rep = repr(r)
    assert "#1" in rep
    assert "ok" in rep
    assert "42.5" in rep


def test_store_list_workflows():
    """NexusStore.list_workflows returns all saved workflows."""
    from nexus.core.db import NexusStore
    from nexus.core.models import Workflow
    store = NexusStore()
    assert store.list_workflows() == []
    wf = Workflow("w1", "wf", "desc", [])
    store.save_workflow(wf)
    wfs = store.list_workflows()
    assert len(wfs) == 1
    assert wfs[0].name == "wf"


def test_workflow_builder_delete(hub):
    """WorkflowBuilder.delete removes a workflow."""
    store, _, _ = hub
    builder = WorkflowBuilder(store)
    wf = builder.create("wf", [{"tool_id": "github", "action": "repos.list"}], "agent")
    assert builder.delete(wf.id) is True
    assert builder.get(wf.id) is None
    assert builder.delete("nonexistent") is False


def test_tool_chain_run_conditional_fail_fast(hub):
    """ToolChain.run_conditional with fail_fast=True raises on first failure."""
    import pytest
    from nexus.composition.chain import ToolChain
    _, _, api = hub
    api.grant("agent", "github", "read")
    chain = ToolChain(api, "agent").add("github", "unknown.action")
    with pytest.raises(Exception):
        chain.run_conditional(fail_fast=True)


def test_tool_chain_run_conditional_no_fail_fast(hub):
    """ToolChain.run_conditional with fail_fast=False collects errors."""
    from nexus.composition.chain import ToolChain
    _, _, api = hub
    api.grant("agent", "github", "read")
    chain = ToolChain(api, "agent").add("github", "unknown.action")
    results = chain.run_conditional(fail_fast=False)
    assert len(results) == 1
    assert "error" in results[0]


def test_api_list_workflows_endpoint():
    """GET /workflows lists all workflows."""
    from nexus.server.app import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/workflows" in paths


def test_api_get_workflow_endpoint():
    """GET /workflows/{id} returns a single workflow."""
    from nexus.server.app import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    # The route pattern includes {workflow_id}
    assert any("workflow_id" in r.path for r in app.routes)


def test_api_update_workflow_endpoint():
    """PUT /workflows/{id} updates a workflow."""
    from nexus.server.app import create_app
    app = create_app()
    methods = {r.path: r.methods for r in app.routes}
    # Check PUT method exists on workflow routes
    wf_routes = [r for r in app.routes if "workflow_id" in r.path]
    assert any(r.methods and "PUT" in r.methods for r in wf_routes)


def test_api_agent_permissions_endpoint():
    """GET /agents/{agent_id}/permissions lists agent permissions."""
    from nexus.server.app import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    assert any("permissions" in p for p in paths)


def test_api_audit_trail_endpoint():
    """GET /audit returns audit trail."""
    from nexus.server.app import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/audit" in paths


# ── OMEGA Evolution Cycle 2026-05-20 — New Tests ──

def test_stepresult_slots():
    """StepResult uses __slots__ (no __dict__)."""
    from nexus.composition.workflow import StepResult
    r = StepResult(step_index=0, tool_id="t", action="a", success=True)
    assert not hasattr(r, "__dict__")


def test_toolchain_repr():
    """ToolChain repr shows agent and step count."""
    from nexus.composition.chain import ToolChain
    from nexus.core.db import NexusStore
    from nexus.api.unified import UnifiedToolAPI
    store = NexusStore()
    api = UnifiedToolAPI(store)
    chain = ToolChain(api, "agent").add("t1", "a1").add("t2", "a2")
    rep = repr(chain)
    assert "agent" in rep
    assert "steps=2" in rep


def test_workflow_builder_delete_audits(hub):
    """WorkflowBuilder.delete emits workflow.deleted audit event."""
    store, _, _ = hub
    from nexus.composition.workflow import WorkflowBuilder
    builder = WorkflowBuilder(store)
    wf = builder.create("wf", [{"tool_id": "github", "action": "repos.list"}], "agent")
    builder.delete(wf.id)
    deleted_events = [e for e in store.audit_events if e.get("type") == "workflow.deleted"]
    assert len(deleted_events) >= 1
    assert deleted_events[-1]["workflow_id"] == wf.id


def test_workflow_builder_delete_nonexistent(hub):
    """WorkflowBuilder.delete returns False for nonexistent workflow."""
    store, _, _ = hub
    from nexus.composition.workflow import WorkflowBuilder
    builder = WorkflowBuilder(store)
    assert builder.delete("nonexistent") is False


def test_pipeline_resolve_params_all(hub):
    """Pipeline._resolve_params resolves $all to all previous results."""
    store, _, api = hub
    from nexus.composition.workflow import Pipeline
    pipeline = Pipeline(api, store)
    results = [{"id": 1}, {"id": 2}]
    resolved = pipeline._resolve_params({"$all": True, "other": "val"}, results)
    assert "all" in resolved
    assert len(resolved["all"]) == 2
    assert "$all" not in resolved
    assert resolved["other"] == "val"


def test_capability_registry_repr(hub):
    """CapabilityRegistry repr shows tool and capability counts."""
    store, manager, _ = hub
    from nexus.discovery.discovery import CapabilityRegistry
    reg = CapabilityRegistry(manager)
    rep = repr(reg)
    assert "CapabilityRegistry" in rep
    assert "tools=" in rep


def test_tool_discovery_repr(hub):
    """ToolDiscovery repr shows tool count."""
    store, manager, _ = hub
    from nexus.discovery.discovery import ToolDiscovery
    td = ToolDiscovery(manager)
    rep = repr(td)
    assert "ToolDiscovery" in rep
    assert "tools=" in rep


def test_performance_tracker_percentiles():
    """PerformanceTracker.latency returns p50/p95/p99."""
    from nexus.core.db import NexusStore, ToolCall
    from nexus.metrics.performance import PerformanceTracker
    from nexus.core.models import CallStatus
    store = NexusStore()
    # Inject calls with known durations
    for ms in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]:
        call = ToolCall(agent_id="a", tool_id="t", action="x", params={}, duration_ms=ms, status=CallStatus.SUCCESS.value)
        store.record_call(call)
    tracker = PerformanceTracker(store)
    lat = tracker.latency()
    assert lat["count"] == 10
    assert lat["min_ms"] == 10.0
    assert lat["max_ms"] == 100.0
    assert 50.0 <= lat["p50"] <= 60.0
    assert 90.0 <= lat["p95"] <= 100.0
    assert 95.0 <= lat["p99"] <= 100.0


# ── OMEGA Evolution Cycle 2026-05-20 (v7.41) — New Tests ──

def test_nexus_store_repr():
    """NexusStore repr shows counts for all collections."""
    from nexus.core.db import NexusStore
    store = NexusStore()
    store.register_agent("a1")
    rep = repr(store)
    assert "NexusStore" in rep
    assert "agents=1" in rep
    assert "calls=0/10000" in rep


def test_nexus_store_repr_with_data():
    """NexusStore repr reflects actual data counts."""
    from nexus.core.db import NexusStore, ToolCall
    from nexus.core.models import CallStatus
    store = NexusStore(max_calls=100, max_audit_events=50)
    store.register_agent("a1")
    store.register_agent("a2")
    store.record_call(ToolCall("a1", "t1", "x", {}, duration_ms=5.0, status=CallStatus.SUCCESS.value))
    store.audit("test.event")
    rep = repr(store)
    assert "agents=2" in rep
    assert "calls=1/100" in rep
    assert "audit=1/50" in rep


def test_usage_metrics_error_rate_zero():
    """UsageMetrics.summary returns error_rate=0.0 when no errors."""
    from nexus.core.db import NexusStore, ToolCall
    from nexus.core.models import CallStatus
    from nexus.metrics.metrics import UsageMetrics
    store = NexusStore()
    store.record_call(ToolCall("a1", "t1", "x", {}, status=CallStatus.SUCCESS.value))
    store.record_call(ToolCall("a1", "t1", "x", {}, status=CallStatus.SUCCESS.value))
    metrics = UsageMetrics(store)
    summary = metrics.summary()
    assert summary["error_rate"] == 0.0
    assert summary["total_calls"] == 2


def test_usage_metrics_error_rate_mixed():
    """UsageMetrics.summary returns correct error_rate for mixed results."""
    from nexus.core.db import NexusStore, ToolCall
    from nexus.core.models import CallStatus
    from nexus.metrics.metrics import UsageMetrics
    store = NexusStore()
    store.record_call(ToolCall("a1", "t1", "x", {}, status=CallStatus.SUCCESS.value))
    store.record_call(ToolCall("a1", "t1", "x", {}, status=CallStatus.ERROR.value))
    store.record_call(ToolCall("a1", "t1", "x", {}, status=CallStatus.ERROR.value))
    store.record_call(ToolCall("a1", "t1", "x", {}, status=CallStatus.SUCCESS.value))
    metrics = UsageMetrics(store)
    summary = metrics.summary()
    assert summary["error_rate"] == 0.5


def test_usage_metrics_error_rate_empty():
    """UsageMetrics.summary returns error_rate=0.0 for empty store."""
    from nexus.core.db import NexusStore
    from nexus.metrics.metrics import UsageMetrics
    store = NexusStore()
    metrics = UsageMetrics(store)
    summary = metrics.summary()
    assert summary["error_rate"] == 0.0
    assert summary["total_calls"] == 0


def test_plugin_manager_list_by_status(hub):
    """PluginManager.list_plugins_by_status filters correctly."""
    store, manager, _ = hub
    active = manager.list_plugins_by_status("active")
    assert len(active) > 0
    assert all(p.status == "active" for p in active)


def test_plugin_manager_list_by_status_error(hub):
    """PluginManager.list_plugins_by_status returns empty for error status."""
    store, manager, _ = hub
    errors = manager.list_plugins_by_status("error")
    assert errors == []


def test_plugin_manager_repr(hub):
    """PluginManager repr shows plugin counts."""
    store, manager, _ = hub
    rep = repr(manager)
    assert "PluginManager" in rep
    assert "plugins=" in rep
    assert "active=" in rep


def test_metrics_error_rate_all_errors():
    """UsageMetrics.summary returns error_rate=1.0 when all calls errored."""
    from nexus.core.db import NexusStore, ToolCall
    from nexus.core.models import CallStatus
    from nexus.metrics.metrics import UsageMetrics
    store = NexusStore()
    for _ in range(5):
        store.record_call(ToolCall("a1", "t1", "x", {}, status=CallStatus.ERROR.value))
    metrics = UsageMetrics(store)
    summary = metrics.summary()
    assert summary["error_rate"] == 1.0


# ── OMEGA Evolution Cycle 2026-05-20 (v1.1.1) — New Tests ──

class TestNexusStoreValidation:
    """Test input validation in NexusStore methods."""

    def test_register_agent_empty_string(self):
        """register_agent raises ValueError for empty string."""
        store = NexusStore()
        with pytest.raises(ValueError, match="non-empty string"):
            store.register_agent("")

    def test_register_agent_whitespace_only(self):
        """register_agent raises ValueError for whitespace-only string."""
        store = NexusStore()
        with pytest.raises(ValueError, match="non-empty string"):
            store.register_agent("   ")

    def test_register_agent_strips_whitespace(self):
        """register_agent strips leading/trailing whitespace."""
        store = NexusStore()
        store.register_agent("  agent-1  ")
        assert "agent-1" in store.agents
        assert "  agent-1  " not in store.agents

    def test_upsert_plugin_wrong_type(self):
        """upsert_plugin raises TypeError for non-ToolPlugin."""
        store = NexusStore()
        with pytest.raises(TypeError, match="Expected ToolPlugin"):
            store.upsert_plugin("not a plugin")

    def test_upsert_plugin_none(self):
        """upsert_plugin raises TypeError for None."""
        store = NexusStore()
        with pytest.raises(TypeError, match="Expected ToolPlugin"):
            store.upsert_plugin(None)


class TestNexusStoreContains:
    """Test __contains__ for agent membership testing."""

    def test_contains_registered_agent(self):
        store = NexusStore()
        store.register_agent("a1")
        assert "a1" in store

    def test_not_contains_unregistered_agent(self):
        store = NexusStore()
        assert "nonexistent" not in store

    def test_contains_after_clear(self):
        store = NexusStore()
        store.register_agent("a1")
        assert "a1" in store
        store.clear()
        assert "a1" not in store


class TestNexusStoreAgentCallCount:
    """Test agent_call_count and last_call_for_agent methods."""

    def test_agent_call_count_zero(self):
        store = NexusStore()
        store.register_agent("a1")
        assert store.agent_call_count("a1") == 0

    def test_agent_call_count_multiple(self):
        store = NexusStore()
        for _ in range(5):
            store.record_call(ToolCall("a1", "t1", "read", {}))
        for _ in range(3):
            store.record_call(ToolCall("a2", "t1", "read", {}))
        assert store.agent_call_count("a1") == 5
        assert store.agent_call_count("a2") == 3

    def test_agent_call_count_unknown_agent(self):
        store = NexusStore()
        assert store.agent_call_count("unknown") == 0

    def test_last_call_for_agent_none(self):
        store = NexusStore()
        store.register_agent("a1")
        assert store.last_call_for_agent("a1") is None

    def test_last_call_for_agent_returns_most_recent(self):
        store = NexusStore()
        store.record_call(ToolCall("a1", "t1", "read", {}))
        store.record_call(ToolCall("a1", "t2", "write", {}))
        store.record_call(ToolCall("a2", "t1", "read", {}))
        last = store.last_call_for_agent("a1")
        assert last is not None
        assert last.tool_id == "t2"
        assert last.action == "write"


class TestCircuitBreakerValidation:
    """Test CircuitBreaker parameter validation."""

    def test_zero_failure_threshold_raises(self):
        with pytest.raises(ValueError, match="failure_threshold must be >= 1"):
            CircuitBreaker(failure_threshold=0)

    def test_negative_failure_threshold_raises(self):
        with pytest.raises(ValueError, match="failure_threshold must be >= 1"):
            CircuitBreaker(failure_threshold=-1)

    def test_negative_recovery_timeout_raises(self):
        with pytest.raises(ValueError, match="recovery_timeout must be >= 0"):
            CircuitBreaker(recovery_timeout=-1.0)

    def test_valid_defaults(self):
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 30.0

    def test_valid_custom_params(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.0)
        assert cb.failure_threshold == 1
        assert cb.recovery_timeout == 0.0


class TestToolPluginToDict:
    """Test ToolPlugin.to_dict serialization."""

    def test_to_dict_contains_all_fields(self):
        plugin = ToolPlugin("p1", "P1", "desc", "1.0", "api", ["read", "write"])
        d = plugin.to_dict()
        assert d["id"] == "p1"
        assert d["name"] == "P1"
        assert d["description"] == "desc"
        assert d["version"] == "1.0"
        assert d["plugin_type"] == "api"
        assert d["capabilities"] == ["read", "write"]
        assert d["status"] == "active"
        assert "registered_at" in d

    def test_to_dict_iso_timestamp(self):
        plugin = ToolPlugin("p1", "P1", "desc", "1.0", "api", ["read"])
        d = plugin.to_dict()
        # ISO 8601 format check: should contain 'T' and end with '+00:00' or 'Z'
        ts = d["registered_at"]
        assert "T" in ts
        assert "+" in ts or ts.endswith("Z")

    def test_to_dict_copies_mutable_fields(self):
        plugin = ToolPlugin("p1", "P1", "desc", "1.0", "api", ["read"])
        d = plugin.to_dict()
        d["capabilities"].append("admin")
        assert "admin" not in plugin.capabilities
