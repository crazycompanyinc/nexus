from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

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


class CallRequest(BaseModel):
    agent_id: str
    tool_id: str = ""
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    fallback_tools: list[str] = Field(default_factory=list)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("agent_id must be a non-empty string")
        return v.strip()

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("action must be a non-empty string")
        return v.strip()


class BindingRequest(BaseModel):
    agent_id: str
    tool_id: str
    level: str

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        from nexus.core.models import PermissionLevel

        valid = {PermissionLevel.READ.value, PermissionLevel.WRITE.value, PermissionLevel.ADMIN.value}
        if v not in valid:
            raise ValueError(f"Invalid permission level '{v}': must be one of {sorted(valid)}")
        return v


class WorkflowRequest(BaseModel):
    name: str
    steps: list[dict[str, Any]]
    created_by: str
    description: str = ""


class WorkflowPatchRequest(BaseModel):
    name: str | None = None
    steps: list[dict[str, Any]] | None = None
    created_by: str | None = None
    description: str | None = None


def create_app() -> FastAPI:
    store = NexusStore()
    manager = PluginManager(store)
    api = UnifiedToolAPI(store, manager, AccessControl(store))
    workflows = WorkflowBuilder(store)
    pipeline = Pipeline(api, store)
    app = FastAPI(title="Nexus", version="1.1.0")
    rate_limiter = RateLimitMiddleware(max_requests=120, window_seconds=60)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Apply rate limiting to all incoming requests."""
        response = await rate_limiter.check(request)
        if response is not None:
            return response
        return await call_next(request)

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

    @app.exception_handler(ValueError)
    async def bad_request_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="bad_request", detail=str(exc), code="BAD_REQUEST").model_dump(),
        )

    @app.post("/init")
    async def init() -> dict[str, Any]:
        return {"plugins": [plugin.id for plugin in manager.install_all_builtins()]}

    @app.get("/plugins")
    async def plugins(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        all_plugins = manager.list_plugins()
        items = [asdict(p) for p in all_plugins[offset : offset + limit]]
        return {
            "items": items,
            "total": len(all_plugins),
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(all_plugins),
        }

    @app.get("/plugins/{plugin_id}")
    async def get_plugin(plugin_id: str) -> dict[str, Any]:
        """Get a single plugin by its ID."""
        try:
            plugin = manager.get(plugin_id)
            return asdict(plugin.metadata.to_model())
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")

    @app.delete("/plugins/{plugin_id}")
    async def delete_plugin(plugin_id: str) -> dict[str, Any]:
        """Unregister a plugin by its ID."""
        if manager.unregister(plugin_id):
            return {"unregistered": True, "plugin_id": plugin_id}
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")

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

    @app.post("/tools/batch")
    async def batch_call(requests: list[CallRequest]) -> dict[str, Any]:
        """Execute multiple tool calls in sequence."""
        results = []
        for req in requests:
            try:
                result = api.call(req.agent_id, req.tool_id, req.action, req.params, req.fallback_tools)
                results.append({"tool_id": req.tool_id, "action": req.action, "result": result, "success": True})
            except Exception as exc:
                results.append({"tool_id": req.tool_id, "action": req.action, "error": str(exc), "success": False})
        succeeded = sum(1 for r in results if r["success"])
        return {"results": results, "succeeded": succeeded, "failed": len(results) - succeeded}

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
    async def list_workflows(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        all_wf = workflows.list()
        items = [asdict(wf) for wf in all_wf[offset : offset + limit]]
        return {
            "items": items,
            "total": len(all_wf),
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(all_wf),
        }

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

    @app.get("/agents")
    async def list_agents() -> dict[str, Any]:
        """List all registered agents with their binding counts."""
        agents = sorted(store.agents)
        items = []
        for agent_id in agents:
            bindings = api.access.list_agent_permissions(agent_id)
            total_calls = store.agent_call_count(agent_id)
            last_call = store.last_call_for_agent(agent_id)
            items.append({
                "agent_id": agent_id,
                "bindings": len(bindings),
                "total_calls": total_calls,
                "last_called_at": last_call.called_at.isoformat() if last_call else None,
            })
        return {"items": items, "total": len(agents)}

    @app.get("/agents/{agent_id}/usage")
    async def agent_usage(agent_id: str) -> dict[str, Any]:
        """Get detailed usage metrics for a specific agent."""
        if agent_id not in store.agents:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        return UsageMetrics(store).agent_usage(agent_id)

    @app.get("/metrics")
    async def metrics(
        since: str | None = Query(None, description="ISO 8601 start datetime (e.g. 2026-01-01T00:00:00Z)"),
        until: str | None = Query(None, description="ISO 8601 end datetime"),
    ) -> dict[str, Any]:
        """Get usage metrics, optionally filtered by time range."""
        from datetime import datetime, timezone
        parsed_since = None
        parsed_until = None
        if since:
            try:
                parsed_since = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid 'since' datetime: {since}")
        if until:
            try:
                parsed_until = datetime.fromisoformat(until.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid 'until' datetime: {until}")
        return UsageMetrics(store).summary(since=parsed_since, until=parsed_until)

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

    @app.get("/metrics/agents")
    async def agent_performance() -> dict[str, Any]:
        """Get latency performance metrics broken down by agent."""
        from nexus.metrics.performance import PerformanceTracker
        return PerformanceTracker(store).by_agent()

    @app.get("/metrics/tools")
    async def tool_performance() -> dict[str, Any]:
        """Get latency performance metrics broken down by tool."""
        from nexus.metrics.performance import PerformanceTracker
        return PerformanceTracker(store).by_tool()

    @app.get("/agents/{agent_id}/calls")
    async def agent_calls(
        agent_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        status: str | None = Query(None, description="Filter by call status: success, error, timeout, denied"),
    ) -> dict[str, Any]:
        """Get paginated tool calls for a specific agent, optionally filtered by status."""
        if agent_id not in store.agents:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        calls = store.agent_calls(agent_id, status=status, limit=None)
        total = len(calls)
        paginated = calls[offset : offset + limit]
        return {
            "items": [
                {
                    "id": c.id,
                    "tool_id": c.tool_id,
                    "action": c.action,
                    "status": c.status,
                    "duration_ms": c.duration_ms,
                    "called_at": c.called_at.isoformat(),
                    "result": c.result,
                }
                for c in paginated
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
        }

    @app.get("/workflows/{workflow_id}/runs")
    async def workflow_runs(
        workflow_id: str,
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        """Get run history for a specific workflow from audit events."""
        if workflow_id not in store.workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        runs = [
            e for e in store.audit_events
            if e.get("type") == "workflow.ran" and e.get("workflow_id") == workflow_id
        ]
        return {
            "items": runs[-limit:],
            "total": len(runs),
        }

    @app.patch("/workflows/{workflow_id}")
    async def patch_workflow(workflow_id: str, request: WorkflowPatchRequest) -> dict[str, Any]:
        """Partially update a workflow (PATCH semantics — all fields optional)."""
        try:
            from nexus.core.models import WorkflowStep
            wf = store.workflows.get(workflow_id)
            if wf is None:
                raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
            if request.name is not None and request.name:
                wf.name = request.name
            if request.description is not None and request.description:
                wf.description = request.description
            if request.created_by is not None and request.created_by:
                wf.created_by = request.created_by
            if request.steps:
                wf.steps = [
                    WorkflowStep(
                        tool_id=s["tool_id"],
                        action=s["action"],
                        params=s.get("params", {}),
                        condition=s.get("condition"),
                        fallback_tools=s.get("fallback_tools", []),
                        max_retries=s.get("max_retries", 0),
                        retry_delay_ms=s.get("retry_delay_ms", 100.0),
                    )
                    for s in request.steps
                ]
            errors = wf.validate()
            if errors:
                raise HTTPException(status_code=400, detail=f"Validation failed: {'; '.join(errors)}")
            store.audit("workflow.patched", workflow_id=workflow_id)
            return wf.to_dict()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return manager.health()

    @app.get("/health/detailed")
    async def health_detailed() -> dict[str, Any]:
        """Detailed health check including plugin capabilities and store stats."""
        plugins = manager.list_plugins()
        return {
            "status": "healthy",
            "plugins": {
                "total": len(plugins),
                "active": sum(1 for p in plugins if p.status == "active"),
                "inactive": sum(1 for p in plugins if p.status != "active"),
                "details": manager.health(),
            },
            "store": {
                "agents": len(store.agents),
                "plugins": len(store.plugins),
                "bindings": len(store.bindings),
                "calls": len(store.calls),
                "workflows": len(store.workflows),
                "audit_events": len(store.audit_events),
            },
        }

    @app.post("/store/export")
    async def export_store() -> dict[str, Any]:
        """Export the full store state for backup."""
        return store.export()

    @app.post("/store/import")
    async def import_store(request: dict[str, Any]) -> dict[str, Any]:
        """Import store state from a previous export. Replaces all data."""
        store.import_(request)
        return {"imported": True, "agents": len(store.agents), "plugins": len(store.plugins)}

    @app.get("/version")
    async def version() -> dict[str, str]:
        """Return the Nexus API version."""
        from nexus import __version__
        return {"version": __version__}

    app.state.store = store
    app.state.manager = manager
    app.state.api = api
    return app


app = create_app()
