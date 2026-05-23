from __future__ import annotations

from nexus.core.db import NexusStore
from nexus.core.models import AgentToolBinding, ToolCall, ToolPlugin, Workflow, WorkflowStep


def test_store_registers_agent():
    store = NexusStore()
    store.register_agent("a1")
    assert "a1" in store.agents


def test_store_upserts_plugin():
    store = NexusStore()
    plugin = ToolPlugin("p1", "P1", "desc", "1", "api", ["read"])
    store.upsert_plugin(plugin)
    assert store.plugins["p1"].name == "P1"


def test_store_binds_tool():
    store = NexusStore()
    store.bind_tool(AgentToolBinding("a1", "p1", "read"))
    assert store.get_binding("a1", "p1").permissions == "read"


def test_store_unbinds_tool():
    store = NexusStore()
    store.bind_tool(AgentToolBinding("a1", "p1", "read"))
    store.unbind_tool("a1", "p1")
    assert store.get_binding("a1", "p1") is None


def test_store_records_call():
    store = NexusStore()
    call = store.record_call(ToolCall("a1", "p1", "read", {}))
    assert list(store.calls) == [call]


def test_store_calls_bounded():
    store = NexusStore(max_calls=3)
    for i in range(5):
        store.record_call(ToolCall("a1", "p1", "read", {}))
    assert len(store.calls) == 3


def test_store_audit_bounded():
    store = NexusStore(max_audit_events=2)
    store.audit("evt1")
    store.audit("evt2")
    store.audit("evt3")
    assert len(store.audit_events) == 2
    assert store.audit_events[-1]["type"] == "evt3"


def test_store_saves_workflow():
    store = NexusStore()
    workflow = Workflow("w1", "wf", "desc", [WorkflowStep("p1", "read")])
    store.save_workflow(workflow)
    assert store.workflows["w1"].name == "wf"


def test_store_get_workflow():
    store = NexusStore()
    workflow = Workflow("w1", "wf", "desc", [WorkflowStep("p1", "read")])
    store.save_workflow(workflow)
    assert store.get_workflow("w1") is not None
    assert store.get_workflow("w1").name == "wf"
    assert store.get_workflow("nonexistent") is None


def test_store_delete_workflow():
    store = NexusStore()
    workflow = Workflow("w1", "wf", "desc", [WorkflowStep("p1", "read")])
    store.save_workflow(workflow)
    assert store.delete_workflow("w1") is True
    assert store.get_workflow("w1") is None
    assert store.delete_workflow("w1") is False


def test_store_snapshot_contains_sections():
    store = NexusStore()
    snapshot = store.snapshot()
    assert set(snapshot) == {"agents", "plugins", "bindings", "calls", "workflows", "audit_events", "calls_total", "audit_total"}


def test_tool_plugin_supports_wildcard():
    plugin = ToolPlugin("p1", "P1", "desc", "1", "api", ["*"])
    assert plugin.supports("anything")


def test_agent_tool_binding_repr():
    binding = AgentToolBinding("a1", "p1", "read")
    r = repr(binding)
    assert "a1" in r
    assert "p1" in r
    assert "read" in r


def test_workflow_step_repr():
    step = WorkflowStep("p1", "read", max_retries=3)
    r = repr(step)
    assert "p1" in r
    assert "read" in r
    assert "3" in r


def test_store_clear():
    store = NexusStore()
    store.register_agent("a1")
    store.upsert_plugin(ToolPlugin("p1", "P1", "desc", "1", "api", ["read"]))
    store.bind_tool(AgentToolBinding("a1", "p1", "read"))
    store.record_call(ToolCall("a1", "p1", "read", {}))
    store.save_workflow(Workflow("w1", "wf", "desc", [WorkflowStep("p1", "read")]))
    store.audit("test")
    store.clear()
    assert len(store.agents) == 0
    assert len(store.plugins) == 0
    assert len(store.bindings) == 0
    assert len(store.calls) == 0
    assert len(store.workflows) == 0
    assert len(store.audit_events) == 0


def test_workflow_validate_valid():
    wf = Workflow("w1", "good", "desc", [WorkflowStep("p1", "read")])
    assert wf.validate() == []


def test_workflow_validate_empty_name():
    wf = Workflow("w1", "  ", "desc", [WorkflowStep("p1", "read")])
    errors = wf.validate()
    assert any("name" in e.lower() for e in errors)


def test_workflow_validate_no_steps():
    wf = Workflow("w1", "bad", "desc", [])
    errors = wf.validate()
    assert any("step" in e.lower() for e in errors)


def test_workflow_validate_empty_step_fields():
    wf = Workflow("w1", "bad", "desc", [WorkflowStep("", "")])
    errors = wf.validate()
    assert len(errors) >= 2


def test_workflow_validate_negative_retries():
    wf = Workflow("w1", "bad", "desc", [WorkflowStep("p1", "read", max_retries=-1)])
    errors = wf.validate()
    assert any("retries" in e.lower() for e in errors)


def test_store_export_import():
    store = NexusStore()
    store.register_agent("a1")
    store.upsert_plugin(ToolPlugin("p1", "P1", "desc", "1", "api", ["read"]))
    store.bind_tool(AgentToolBinding("a1", "p1", "read"))
    store.audit("test.event", key="value")

    exported = store.export()
    assert "a1" in exported["agents"]
    assert len(exported["plugins"]) == 1
    assert len(exported["bindings"]) == 1

    new_store = NexusStore()
    new_store.import_(exported)
    assert "a1" in new_store.agents
    assert "p1" in new_store.plugins
    assert new_store.get_binding("a1", "p1") is not None


def test_store_import_replaces_data():
    store = NexusStore()
    store.register_agent("old_agent")
    exported = store.export()

    store.register_agent("new_agent")
    assert len(store.agents) == 2

    store.import_(exported)
    assert store.agents == {"old_agent"}


def test_store_export_empty():
    store = NexusStore()
    exported = store.export()
    assert exported["agents"] == []
    assert exported["plugins"] == []
    assert exported["calls"] == []


def test_agent_tool_binding_to_dict():
    binding = AgentToolBinding("a1", "p1", "write", config={"timeout": 30})
    d = binding.to_dict()
    assert d["agent_id"] == "a1"
    assert d["tool_id"] == "p1"
    assert d["permissions"] == "write"
    assert d["config"] == {"timeout": 30}
    assert "bound_at" in d


def test_workflow_to_dict():
    wf = Workflow(
        id="wf-1",
        name="Test Flow",
        description="A test workflow",
        steps=[WorkflowStep(tool_id="p1", action="read", params={"x": 1})],
        created_by="agent-1",
    )
    d = wf.to_dict()
    assert d["id"] == "wf-1"
    assert d["name"] == "Test Flow"
    assert d["description"] == "A test workflow"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["tool_id"] == "p1"
    assert d["steps"][0]["action"] == "read"
    assert d["steps"][0]["params"] == {"x": 1}
    assert "created_at" in d


def test_store_iter():
    store = NexusStore()
    c1 = store.record_call(ToolCall("a1", "p1", "read", {}))
    c2 = store.record_call(ToolCall("a1", "p1", "write", {}))
    calls = list(store)
    assert len(calls) == 2
    assert calls[0].action == "read"
    assert calls[1].action == "write"


def test_unified_api_repr():
    from nexus.api.unified import UnifiedToolAPI
    api = UnifiedToolAPI(max_retries=5, retry_base_delay=0.5)
    r = repr(api)
    assert "UnifiedToolAPI" in r
    assert "max_retries=5" in r
    assert "retry_base_delay=0.5" in r


def test_store_health_check():
    store = NexusStore()
    store.register_agent("a1")
    store.upsert_plugin(ToolPlugin("p1", "P1", "desc", "1", "api", ["read"]))
    store.bind_tool(AgentToolBinding("a1", "p1", "read"))
    store.record_call(ToolCall("a1", "p1", "read", {}))
    store.save_workflow(Workflow("w1", "wf", "desc", [WorkflowStep("p1", "read")]))
    store.audit("test.event")

    health = store.health_check()
    assert health["status"] == "healthy"
    assert health["agents"] == 1
    assert health["plugins"] == 1
    assert health["bindings"] == 1
    assert health["calls"] == 1
    assert health["calls_capacity"] == 10000
    assert health["workflows"] == 1
    assert health["audit_events"] == 1
    assert health["audit_capacity"] == 5000
    assert "memory_usage_approx_bytes" in health
    assert health["memory_usage_approx_bytes"] >= 0


def test_store_health_check_empty():
    store = NexusStore()
    health = store.health_check()
    assert health["status"] == "healthy"
    assert health["agents"] == 0
    assert health["calls"] == 0
    assert health["memory_usage_approx_bytes"] == 0


def test_store_search_calls():
    store = NexusStore()
    store.record_call(ToolCall("a1", "p1", "read", {}, duration_ms=10.0))
    store.record_call(ToolCall("a1", "p1", "write", {}, duration_ms=50.0))
    store.record_call(ToolCall("a1", "p2", "fetch", {}, duration_ms=200.0))
    store.record_call(ToolCall("a2", "p1", "read", {}, duration_ms=30.0))

    # Filter by agent
    results = store.search_calls(agent_id="a2")
    assert len(results) == 1
    assert results[0].agent_id == "a2"

    # Filter by tool
    results = store.search_calls(tool_id="p2")
    assert len(results) == 1
    assert results[0].tool_id == "p2"

    # Filter by action
    results = store.search_calls(action="write")
    assert len(results) == 1
    assert results[0].action == "write"

    # Filter by duration range
    results = store.search_calls(min_duration_ms=20.0, max_duration_ms=100.0)
    assert len(results) == 2

    # Filter with limit
    results = store.search_calls(agent_id="a1", limit=2)
    assert len(results) == 2

    # Combined filters
    results = store.search_calls(agent_id="a1", tool_id="p1", action="read")
    assert len(results) == 1
    assert results[0].action == "read"


def test_store_search_calls_reverse_chronological():
    store = NexusStore()
    store.record_call(ToolCall("a1", "p1", "first", {}))
    store.record_call(ToolCall("a1", "p1", "second", {}))
    store.record_call(ToolCall("a1", "p1", "third", {}))

    results = store.search_calls(agent_id="a1")
    assert len(results) == 3
    assert results[0].action == "third"
    assert results[2].action == "first"


def test_workflow_step_result_bool():
    from nexus.composition.workflow import StepResult
    ok = StepResult(step_index=0, tool_id="p1", action="read", success=True)
    fail = StepResult(step_index=1, tool_id="p1", action="write", success=False)

    assert bool(ok) is True
    assert bool(fail) is False
    assert ok  # truthy
    assert not fail  # falsy


def test_workflow_step_result_repr():
    from nexus.composition.workflow import StepResult
    ok = StepResult(step_index=0, tool_id="p1", action="read", success=True, duration_ms=42.5)
    fail = StepResult(step_index=1, tool_id="p2", action="write", success=False, duration_ms=10.0)

    assert "#0" in repr(ok)
    assert "p1.read" in repr(ok)
    assert "ok" in repr(ok)
    assert "42.5ms" in repr(ok)

    assert "#1" in repr(fail)
    assert "p2.write" in repr(fail)
    assert "FAIL" in repr(fail)


def test_workflow_builder_repr():
    from nexus.composition.workflow import WorkflowBuilder
    store = NexusStore()
    builder = WorkflowBuilder(store)
    assert "workflows=0" in repr(builder)

    builder.create("test", [{"tool_id": "p1", "action": "read"}], "admin")
    assert "workflows=1" in repr(builder)


def test_workflow_builder_len():
    from nexus.composition.workflow import WorkflowBuilder
    store = NexusStore()
    builder = WorkflowBuilder(store)
    assert len(builder) == 0
    builder.create("test", [{"tool_id": "p1", "action": "read"}], "admin")
    assert len(builder) == 1
