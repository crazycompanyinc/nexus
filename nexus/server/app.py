from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus.api.unified import UnifiedToolAPI
from nexus.composition.workflow import Pipeline, WorkflowBuilder
from nexus.core.db import NexusStore
from nexus.discovery.discovery import ToolDiscovery
from nexus.metrics.metrics import UsageMetrics
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager


class RateLimitMiddleware:
    """Simple in-memory sliding window rate limiter.

    Limits each client IP to `max_requests` per `window_seconds`.
    Returns HTTP 429 with Retry-After header when limit is exceeded.
    """

    def __init__(self, max_requests: int = 120, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    async def check(self, request: Request) -> JSONResponse | None:
        """Check rate limit for the request. Returns None if allowed, JSONResponse if denied."""
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds

        timestamps = self._requests.setdefault(client, [])
        # Purge old entries
        timestamps[:] = [t for t in timestamps if t > window_start]

        if len(timestamps) >= self.max_requests:
            retry_after = int(timestamps[0] + self.window_seconds - now) + 1
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)
        return None


class PaginatedResponse(BaseModel):
    """Standard paginated response envelope."""
    items: list[Any]
    total: int
    offset: int
    limit: int
    has_more: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=ErrorResponse(error="permission_denied", detail=str(exc), code="FORBIDDEN").model_dump(),
        )

    @app.exception_handler(KeyError)
    async def not_found_handler(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(error="not_found", detail=str(exc), code="NOT_FOUND").model_dump(),
        )

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
    async def run_workflow(workflow_id: str, agent_id: str, fail_fast: bool = False) -> dict[str, Any]:
        step_results = pipeline.run(workflow_id, agent_id, fail_fast=fail_fast)
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

    @app.delete("/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str) -> dict[str, Any]:
        if not store.delete_workflow(workflow_id):
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        return {"deleted": True, "workflow_id": workflow_id}

    @app.get("/workflows")
    async def list_workflows() -> list[dict[str, Any]]:
        return [asdict(wf) for wf in workflows.list()]

    @app.get("/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict[str, Any]:
        wf = workflows.get(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        return asdict(wf)

    @app.put("/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, request: WorkflowRequest) -> dict[str, Any]:
        try:
            updated = workflows.update(
                workflow_id,
                name=request.name,
                description=request.description,
                steps=request.steps,
            )
            return asdict(updated)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    @app.get("/agents/{agent_id}/permissions")
    async def agent_permissions(agent_id: str) -> list[dict[str, Any]]:
        return [asdict(b) for b in api.access.list_agent_permissions(agent_id)]

    @app.get("/audit")
    async def audit_trail(limit: int = 50) -> list[dict[str, Any]]:
        return store.audit_events[-limit:]

    @app.delete("/bindings/{agent_id}/{tool_id}")
    async def unbind(agent_id: str, tool_id: str) -> dict[str, Any]:
        api.access.revoke(agent_id, tool_id)
        return {"revoked": True, "agent_id": agent_id, "tool_id": tool_id}

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        return UsageMetrics(store).summary()

    @app.get("/metrics/performance")
    async def performance() -> dict[str, Any]:
        from nexus.metrics.performance import PerformanceTracker
        return PerformanceTracker(store).latency()

    @app.get("/metrics/workflows")
    async def workflow_metrics() -> dict[str, Any]:
        total = len(store.workflows)
        total_runs = sum(1 for e in store.audit_events if e.get("type") == "workflow.ran")
        total_failures = sum(1 for e in store.audit_events if e.get("type") == "workflow.step_failed")
        durations = [e.get("duration_ms", 0) for e in store.audit_events if e.get("type") == "workflow.ran" and e.get("duration_ms")]
        avg_duration = round(sum(durations) / len(durations), 2) if durations else 0
        return {
            "total_workflows": total,
            "total_runs": total_runs,
            "total_step_failures": total_failures,
            "avg_run_duration_ms": avg_duration,
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return manager.health()

    app.state.store = store
    app.state.manager = manager
    app.state.api = api
    return app


app = create_app()
