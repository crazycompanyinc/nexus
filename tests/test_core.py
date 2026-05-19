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
