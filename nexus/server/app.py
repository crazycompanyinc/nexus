from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from nexus.api.unified import UnifiedToolAPI
from nexus.composition.workflow import Pipeline, WorkflowBuilder
from nexus.core.db import NexusStore
from nexus.discovery.discovery import ToolDiscovery
from nexus.metrics.metrics import UsageMetrics
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager


class CallRequest(BaseModel):
    agent_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    fallback_tools: list[str] = Field(default_factory=list)


class BindingRequest(BaseModel):
    agent_id: str
    tool_id: str
    level: str


class WorkflowRequest(BaseModel):
    name: str
    steps: list[dict[str, Any]]
    created_by: str
    description: str = ""


def create_app() -> FastAPI:
    store = NexusStore()
    manager = PluginManager(store)
    api = UnifiedToolAPI(store, manager, AccessControl(store))
    workflows = WorkflowBuilder(store)
    pipeline = Pipeline(api, store)
    app = FastAPI(title="Nexus", version="0.1.0")

    @app.post("/init")
    async def init() -> dict[str, Any]:
        return {"plugins": [plugin.id for plugin in manager.install_all_builtins()]}

    @app.get("/plugins")
    async def plugins() -> list[dict[str, Any]]:
        return [asdict(plugin) for plugin in manager.list_plugins()]

    @app.get("/discover")
    async def discover() -> list[dict[str, object]]:
        return ToolDiscovery(manager).available_tools()

    @app.post("/bindings")
    async def bind(request: BindingRequest) -> dict[str, Any]:
        return asdict(api.access.grant(request.agent_id, request.tool_id, request.level))

    @app.post("/tools/{tool_id}/call")
    async def call(tool_id: str, request: CallRequest) -> dict[str, Any]:
        try:
            result = api.call(request.agent_id, tool_id, request.action, request.params, request.fallback_tools)
            return {"result": result}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/workflows")
    async def create_workflow(request: WorkflowRequest) -> dict[str, Any]:
        return asdict(workflows.create(request.name, request.steps, request.created_by, request.description))

    @app.post("/workflows/{workflow_id}/run")
    async def run_workflow(workflow_id: str, agent_id: str) -> dict[str, Any]:
        step_results = pipeline.run(workflow_id, agent_id)
        return {
            "results": [
                {
                    "step": r.step_index,
                    "tool_id": r.tool_id,
                    "action": r.action,
                    "success": r.success,
                    "result": r.result,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
                for r in step_results
            ],
            "succeeded": sum(1 for r in step_results if r.success),
            "failed": sum(1 for r in step_results if not r.success),
        }

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        return UsageMetrics(store).summary()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return manager.health()

    app.state.store = store
    app.state.manager = manager
    app.state.api = api
    return app


app = create_app()
