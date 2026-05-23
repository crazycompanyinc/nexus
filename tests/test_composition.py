"""Tests for the Nexus composition layer (ToolChain and WorkflowRunner).

Covers sequential tool chaining, error propagation, retry logic,
and workflow step execution with fallback tools.
"""
from __future__ import annotations

import pytest

from nexus.composition.chain import ToolChain
from nexus.composition.workflow import Pipeline, WorkflowBuilder


def test_tool_chain_runs_steps(hub):
    _, _, api = hub
    api.grant("agent", "github", "read")
    chain = ToolChain(api, "agent").add("github", "repos.list")
    assert chain.run()[0][0]["name"] == "nexus"


def test_workflow_builder_creates_workflow(hub):
    store, _, _ = hub
    workflow = WorkflowBuilder(store).create("wf", [{"tool_id": "github", "action": "repos.list"}], "agent")
    assert workflow.id in store.workflows


def test_pipeline_runs_workflow(hub):
    store, _, api = hub
    api.grant("agent", "github", "read")
    workflow = WorkflowBuilder(store).create("wf", [{"tool_id": "github", "action": "repos.list"}], "agent")
    results = Pipeline(api, store).run(workflow.id, "agent")
    assert results[0].success
    assert results[0].result[0]["name"] == "nexus"


def test_pipeline_resolves_previous(hub):
    store, _, api = hub
    api.grant("agent", "github", "write")
    api.grant("agent", "slack", "write")
    workflow = WorkflowBuilder(store).create(
        "wf",
        [
            {"tool_id": "github", "action": "prs.create", "params": {"title": "T"}},
            {"tool_id": "slack", "action": "messages.send", "params": {"$previous": True, "text": "done"}},
        ],
        "agent",
    )
    results = Pipeline(api, store).run(workflow.id, "agent")
    assert results[0].success
    assert results[1].success
    assert results[1].result["sent"]


def test_api_fallback_uses_alternative_plugin(hub):
    _, _, api = hub
    api.grant("agent", "http", "read")
    api.grant("agent", "github", "read")
    result = api.call("agent", "missing", "repos.list", {}, ["github"])
    assert result[0]["name"] == "nexus"


def test_api_raises_when_all_fallbacks_fail(hub):
    _, _, api = hub
    api.grant("agent", "github", "read")
    with pytest.raises(RuntimeError):
        api.call("agent", "github", "unknown.action", {})


def test_workflow_builder_get_and_list(hub):
    store, _, _ = hub
    builder = WorkflowBuilder(store)
    wf = builder.create("wf", [{"tool_id": "github", "action": "repos.list"}], "agent")
    assert builder.get(wf.id) is not None
    assert builder.get(wf.id).name == "wf"
    assert builder.get("nonexistent") is None
    assert len(builder.list()) == 1


def test_workflow_builder_update(hub):
    store, _, _ = hub
    builder = WorkflowBuilder(store)
    wf = builder.create("wf", [{"tool_id": "github", "action": "repos.list"}], "agent")
    updated = builder.update(wf.id, name="wf-v2", status="paused")
    assert updated.name == "wf-v2"
    assert updated.status == "paused"


def test_pipeline_fail_fast(hub):
    store, _, api = hub
    api.grant("agent", "github", "read")
    workflow = WorkflowBuilder(store).create(
        "wf",
        [
            {"tool_id": "github", "action": "repos.list"},
            {"tool_id": "github", "action": "unknown.action"},
            {"tool_id": "github", "action": "repos.list"},
        ],
        "agent",
    )
    results = Pipeline(api, store).run(workflow.id, "agent", fail_fast=True)
    assert len(results) == 2
    assert results[0].success
    assert not results[1].success


def test_nexus_store_len_and_recent(hub):
    store, _, api = hub
    api.grant("agent", "github", "read")
    assert len(store) == 0
    api.call("agent", "github", "repos.list")
    api.call("agent", "github", "repos.list")
    assert len(store) == 2
    assert len(store.recent_calls(1)) == 1
    assert len(store.recent_calls(5)) == 2


def test_tool_chain_fallback_tools_passed(hub):
    _, _, api = hub
    api.grant("agent", "http", "read")
    api.grant("agent", "github", "read")
    chain = ToolChain(api, "agent").add("missing", "repos.list", fallback_tools=["github"])
    result = chain.run()
    assert result[0][0]["name"] == "nexus"


def test_dataclass_repr():
    from nexus.core.models import ToolPlugin, ToolCall, Workflow, WorkflowStep
    plugin = ToolPlugin(id="p1", name="Test", description="d", version="1.0", plugin_type="api", capabilities=["read"])
    assert "p1" in repr(plugin)
    assert "Test" in repr(plugin)
    call = ToolCall(agent_id="a1", tool_id="p1", action="read", params={})
    assert "a1" in repr(call)
    assert "read" in repr(call)
    wf = Workflow(id="wf1", name="W", description="", steps=[])
    assert "W" in repr(wf)
    assert "steps=0" in repr(wf)
