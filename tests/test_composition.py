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
    assert results[0][0]["name"] == "nexus"


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
    assert results[1]["sent"]


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
