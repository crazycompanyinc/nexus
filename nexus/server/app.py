from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from uuid import uuid4 as _uuid4

from nexus.api.unified import UnifiedToolAPI
from nexus.composition.workflow import Pipeline, WorkflowBuilder
from nexus.core.db import NexusStore
from nexus.discovery.discovery import ToolDiscovery
from nexus.metrics.metrics import UsageMetrics
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Simple in-memory sliding window rate limiter.

    Limits each client IP to ``max_requests`` per ``window_seconds``.
    Returns HTTP 429 with ``Retry-After`` header when limit is exceeded.

    Stale IP entries are purged on every check to prevent unbounded
    memory growth in long-running processes.
    """

    def __init__(self, max_requests: int = 120, window_seconds: int = 60) -> None:
        """Initialize the rate limiter.

        Args:
            max_requests: Maximum requests allowed per window per client IP.
            window_seconds: Time window in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    async def check(self, request: Request) -> JSONResponse | None:
        """Check rate limit for the request. Returns None if allowed, JSONResponse if denied."""
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds

        timestamps = self._requests.setdefault(client, [])
        # Purge old entries for this client
        timestamps[:] = [t for t in timestamps if t > window_start]

        # Global cleanup: remove IPs whose entire window has expired
        stale_ips = [ip for ip, ts in self._requests.items() if ip != client and ts and ts[-1] <= window_start]
        for ip in stale_ips:
            del self._requests[ip]

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
    """Standard error response envelope returned by all API error handlers."""

    error: str
    detail: str | None = None
    code: str | None = None


class CallRequest(BaseModel):
    """Request model for executing a tool call via the Nexus API.

    Attributes:
        agent_id: Unique identifier of the calling agent.
        tool_id: Target tool plugin ID (empty string for auto-discovery).
        action: The action to invoke on the target tool.
        params: Key-value parameters forwarded to the tool action.
        fallback_tools: Ordered list of alternate tool IDs if the primary fails.
    """

    agent_id: str
    tool_id: str = ""
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    fallback_tools: list[str] = Field(default_factory=list)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Validate that agent_id is a non-empty string.

        Args:
            v: The agent_id value to validate.

        Returns:
            The stripped agent_id string.

        Raises:
            ValueError: If agent_id is empty or whitespace-only.
        """
        if not v or not v.strip():
            raise ValueError("agent_id must be a non-empty string")
        return v.strip()

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Validate that action is a non-empty string.

        Args:
            v: The action value to validate.

        Returns:
            The stripped action string.

        Raises:
            ValueError: If action is empty or whitespace-only.
        """
        if not v or not v.strip():
            raise ValueError("action must be a non-empty string")
        return v.strip()


class BindingRequest(BaseModel):
    """Request model for creating an agent-to-tool permission binding.

    Attributes:
        agent_id: Unique identifier of the agent.
        tool_id: Target tool plugin ID to bind.
        level: Permission level — one of 'read', 'write', or 'admin'.
    """

    agent_id: str
    tool_id: str
    level: str

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Validate that the permission level is one of the allowed values.

        Args:
            v: The permission level string to validate.

        Returns:
            The validated permission level string.

        Raises:
            ValueError: If level is not one of 'read', 'write', or 'admin'.
        """
        from nexus.core.models import PermissionLevel

        valid = {PermissionLevel.READ.value, PermissionLevel.WRITE.value, PermissionLevel.ADMIN.value}
        if v not in valid:
            raise ValueError(f"Invalid permission level '{v}': must be one of {sorted(valid)}")
        return v


class WorkflowRequest(BaseModel):
    """Request model for creating a new workflow pipeline.

    Attributes:
        name: Human-readable workflow name.
        steps: Ordered list of step definitions (dicts with tool/action/params).
        created_by: Identifier of the user or agent creating the workflow.
        description: Optional workflow description.
    """

    name: str
    steps: list[dict[str, Any]]
    created_by: str
    description: str = ""


class WorkflowPatchRequest(BaseModel):
    """Partial update model for patching an existing workflow."""

    name: str | None = None
    steps: list[dict[str, Any]] | None = None
    created_by: str | None = None
    description: str | None = None


def create_app() -> FastAPI:
    """Create and configure the Nexus FastAPI application.

    Initializes all core components (store, plugin manager, API, workflows,
    pipeline), registers middleware (rate limiting, request ID, CORS), exception
    handlers, and all API route endpoints.

    Returns:
        A fully configured FastAPI application instance ready to serve.
    """
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

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Attach a unique request ID for traceability.

        Uses ``X-Request-ID`` header if provided by the client,
        otherwise generates a short UUID. The ID is injected into
        the response headers so clients can correlate errors.
        """
        request_id = request.headers.get("X-Request-ID") or _uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def timing_middleware(request: Request, call_next):
        """Add X-Response-Time header to every response.

        Measures wall-clock time from request start to response
        completion and attaches it as a milliseconds value in the
        X-Response-Time header.
        """
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
        return response

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
        """Handle PermissionError exceptions, returning a structured 403 JSON response."""
        return JSONResponse(
            status_code=403,
            content=ErrorResponse(error="permission_denied", detail=str(exc), code="FORBIDDEN").model_dump(),
        )

    @app.exception_handler(KeyError)
    async def not_found_handler(request: Request, exc: KeyError) -> JSONResponse:
        """Handle KeyError exceptions, returning a structured 404 JSON response."""
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(error="not_found", detail=str(exc), code="NOT_FOUND").model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        """Handle ValueError exceptions, returning a structured 400 JSON response."""
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="bad_request", detail=str(exc), code="INVALID_INPUT").model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler for unhandled exceptions, returning a structured 500 JSON response."""
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="internal_server_error",
                detail=f"An unexpected error occurred. Request ID: {request_id}",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )

    @app.post("/init")
    async def init() -> dict[str, Any]:
        """Initialize Nexus by installing all built-in plugins.

        Returns:
            A dict with the list of installed plugin IDs.
        """
        return {"plugins": [plugin.id for plugin in manager.install_all_builtins()]}

    @app.get("/health", tags=["System"])
    async def health() -> dict[str, Any]:
        """Return the health status of the Nexus store.

        Returns:
            Health check dict from NexusStore.health_check().
        """
        return store.health_check()

    @app.get("/plugins", tags=["Plugins"])
    async def plugins(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        """List all registered plugins with pagination.

        Args:
            offset: Number of plugins to skip (0-indexed).
            limit: Maximum number of plugins to return (1-200).

        Returns:
            Paginated response with items, total count, and has_more flag.
        """
        all_plugins = manager.list_plugins()
        items = [asdict(p) for p in all_plugins[offset : offset + limit]]
        return {
            "items": items,
            "total": len(all_plugins),
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(all_plugins),
        }

    @app.get("/plugins/{plugin_id}", tags=["Plugins"])
    async def get_plugin(plugin_id: str) -> dict[str, Any]:
        """Get a single plugin by its ID."""
        try:
            plugin = manager.get(plugin_id)
            return asdict(plugin.metadata.to_model())
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")

    @app.delete("/plugins/{plugin_id}", tags=["Plugins"])
    async def delete_plugin(plugin_id: str) -> dict[str, Any]:
        """Unregister a plugin by its ID."""
        if manager.unregister(plugin_id):
            return {"unregistered": True, "plugin_id": plugin_id}
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")

    @app.get("/discover", tags=["Discovery"])
    async def discover() -> list[dict[str, object]]:
        """Discover all available tools from registered plugins.

        Returns:
            A list of tool descriptors with their capabilities.
        """
        return ToolDiscovery(manager).available_tools()

    @app.post("/bindings", tags=["Bindings"])
    async def bind(request: BindingRequest) -> dict[str, Any]:
        """Create a binding between an agent and a tool with a permission level.

        Args:
            request: Binding request containing agent_id, tool_id, and level.

        Returns:
            A dict representation of the created AgentToolBinding.
        """
        return asdict(api.access.grant(request.agent_id, request.tool_id, request.level))

    @app.post("/tools/{tool_id}/call", tags=["Tools"])
    async def call(tool_id: str, request: CallRequest) -> dict[str, Any]:
        """Execute a single tool call on behalf of an agent.

        Args:
            tool_id: The tool to invoke.
            request: Call parameters including agent_id, action, and params.

        Returns:
            A dict with the tool execution result.

        Raises:
            HTTPException: 403 if permission denied, 400 on execution error.
        """
        try:
            result = api.call(request.agent_id, tool_id, request.action, request.params, request.fallback_tools)
            return {"result": result}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/tools/batch", tags=["Tools"])
    async def batch_call(requests: list[CallRequest]) -> dict[str, Any]:
        """Execute multiple tool calls concurrently with bounded parallelism.

        Uses the async API internally to run calls concurrently rather than
        sequentially, improving throughput for multi-tool batches.

        Args:
            requests: List of call requests, each with agent_id, tool_id, action, params.

        Returns:
            Dict with results list, succeeded count, and failed count.
        """
        from nexus.api.async_unified import AsyncUnifiedToolAPI as _AsyncAPI

        async_api = _AsyncAPI(store, manager, AccessControl(store))
        calls = [
            {"tool_id": req.tool_id, "action": req.action, "params": req.params, "fallback_tools": req.fallback_tools}
            for req in requests
        ]
        agent_ids = list({req.agent_id for req in requests})
        primary_agent = agent_ids[0] if len(agent_ids) == 1 else "system"

        raw_results = await async_api.batch_call(primary_agent, calls, fail_fast=False, max_concurrency=10)
        results = []
        for req, res in zip(requests, raw_results):
            if res["success"]:
                results.append({
                    "tool_id": req.tool_id,
                    "action": req.action,
                    "result": res["result"],
                    "success": True,
                    "duration_ms": res.get("duration_ms", 0),
                })
            else:
                results.append({
                    "tool_id": req.tool_id,
                    "action": req.action,
                    "error": res.get("error", "unknown"),
                    "success": False,
                    "duration_ms": res.get("duration_ms", 0),
                })
        succeeded = sum(1 for r in results if r["success"])
        return {"results": results, "succeeded": succeeded, "failed": len(results) - succeeded}

    @app.post("/workflows", tags=["Workflows"])
    async def create_workflow(request: WorkflowRequest) -> dict[str, Any]:
        """Create a new multi-step workflow.

        Args:
            request: Workflow definition with name, steps, and creator.

        Returns:
            A dict representation of the created Workflow.
        """
        return asdict(workflows.create(request.name, request.steps, request.created_by, request.description))

    @app.post("/workflows/{workflow_id}/run", tags=["Workflows"])
    async def run_workflow(workflow_id: str, agent_id: str, fail_fast: bool = False) -> dict[str, Any]:
        """Execute a workflow by its ID on behalf of an agent.

        Args:
            workflow_id: The workflow to execute.
            agent_id: The agent running the workflow.
            fail_fast: If True, stop on first step failure.

        Returns:
            A dict with per-step results, succeeded count, and failed count.
        """
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

    @app.delete("/workflows/{workflow_id}", tags=["Workflows"])
    async def delete_workflow(workflow_id: str) -> dict[str, Any]:
        """Delete a workflow by its ID.

        Args:
            workflow_id: The workflow to delete.

        Returns:
            A dict confirming deletion.

        Raises:
            HTTPException: 404 if the workflow does not exist.
        """
        if not store.delete_workflow(workflow_id):
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        return {"deleted": True, "workflow_id": workflow_id}

    @app.get("/workflows", tags=["Workflows"])
    async def list_workflows(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        """List all workflows with pagination support.

        Args:
            offset: Number of items to skip.
            limit: Maximum number of items to return.

        Returns:
            A paginated response with workflow items.
        """
        all_wf = workflows.list()
        items = [asdict(wf) for wf in all_wf[offset : offset + limit]]
        return {
            "items": items,
            "total": len(all_wf),
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(all_wf),
        }

    @app.get("/workflows/{workflow_id}", tags=["Workflows"])
    async def get_workflow(workflow_id: str) -> dict[str, Any]:
        """Get a single workflow by its ID.

        Args:
            workflow_id: The workflow to retrieve.

        Returns:
            A dict representation of the workflow.

        Raises:
            HTTPException: 404 if the workflow does not exist.
        """
        wf = workflows.get(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        return asdict(wf)

    @app.put("/workflows/{workflow_id}", tags=["Workflows"])
    async def update_workflow(workflow_id: str, request: WorkflowRequest) -> dict[str, Any]:
        """Fully update a workflow (PUT semantics — all fields required).

        Args:
            workflow_id: The workflow to update.
            request: New workflow definition.

        Returns:
            A dict representation of the updated workflow.

        Raises:
            HTTPException: 404 if the workflow does not exist.
        """
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

    @app.get("/agents/{agent_id}/permissions", tags=["Agents"])
    async def agent_permissions(agent_id: str) -> list[dict[str, Any]]:
        """List all tool permission bindings for a specific agent.

        Args:
            agent_id: The agent to query.

        Returns:
            A list of binding dicts with tool_id and permission level.
        """
        return [asdict(b) for b in api.access.list_agent_permissions(agent_id)]

    @app.get("/audit", tags=["Audit"])
    async def audit_trail(limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve the most recent audit events.

        Args:
            limit: Maximum number of events to return.

        Returns:
            A list of audit event dicts, most recent first.
        """
        return store.audit_events[-limit:]

    @app.delete("/bindings/{agent_id}/{tool_id}", tags=["Bindings"])
    async def unbind(agent_id: str, tool_id: str) -> dict[str, Any]:
        """Revoke a tool binding from an agent.

        Args:
            agent_id: The agent to revoke access from.
            tool_id: The tool to unbind.

        Returns:
            A dict confirming the revocation.
        """
        api.access.revoke(agent_id, tool_id)
        return {"revoked": True, "agent_id": agent_id, "tool_id": tool_id}

    @app.get("/agents", tags=["Agents"])
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

    @app.get("/agents/{agent_id}/usage", tags=["Agents"])
    async def agent_usage(agent_id: str) -> dict[str, Any]:
        """Get detailed usage metrics for a specific agent."""
        if agent_id not in store.agents:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        return UsageMetrics(store).agent_usage(agent_id)

    @app.get("/metrics", tags=["Metrics"])
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

    @app.get("/metrics/performance", tags=["Metrics"])
    async def performance() -> dict[str, Any]:
        """Get latency performance percentiles across all tool calls.

        Returns:
            A dict with p50, p95, p99 latency values and call count.
        """
        from nexus.metrics.performance import PerformanceTracker
        return PerformanceTracker(store).latency()

    @app.get("/metrics/workflows", tags=["Metrics"])
    async def workflow_metrics() -> dict[str, Any]:
        """Get aggregate workflow execution metrics.

        Returns:
            A dict with total workflows, runs, failures, and average duration.
        """
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

    @app.get("/metrics/agents", tags=["Metrics"])
    async def agent_performance() -> dict[str, Any]:
        """Get latency performance metrics broken down by agent."""
        from nexus.metrics.performance import PerformanceTracker
        return PerformanceTracker(store).by_agent()

    @app.get("/metrics/tools", tags=["Metrics"])
    async def tool_performance() -> dict[str, Any]:
        """Get latency performance metrics broken down by tool."""
        from nexus.metrics.performance import PerformanceTracker
        return PerformanceTracker(store).by_tool()

    @app.get("/agents/{agent_id}/calls", tags=["Agents"])
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

    @app.get("/workflows/{workflow_id}/runs", tags=["Workflows"])
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

    @app.patch("/workflows/{workflow_id}", tags=["Workflows"])
    async def patch_workflow(workflow_id: str, request: WorkflowPatchRequest) -> dict[str, Any]:
        """Partially update a workflow (PATCH semantics — all fields optional)."""
        try:
            updated = workflows.patch(
                workflow_id,
                name=request.name,
                description=request.description,
                created_by=request.created_by,
                steps=request.steps,
            )
            return updated.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/health/plugins", tags=["System"])
    async def health_plugins() -> dict[str, Any]:
        """Get basic health status of all registered plugins.

        Returns:
            A dict with plugin health information and overall status.
        """
        plugin_health = manager.health()
        all_healthy = all(
            v.get("status") == "healthy" if isinstance(v, dict) else True
            for v in plugin_health.values()
        )
        return {
            "status": "healthy" if all_healthy else "degraded",
            "plugins": plugin_health,
        }

    @app.get("/ready", tags=["System"])
    async def readiness() -> dict[str, Any]:
        """Readiness probe for orchestrators (K8s, Docker Compose).

        Returns:
            A dict with ``ready`` boolean and component status checks.
        """
        checks: dict[str, bool] = {
            "store": store is not None,
            "plugins": manager is not None,
            "api": api is not None,
        }
        ready = all(checks.values())
        return {
            "ready": ready,
            "checks": checks,
        }

    @app.get("/health/detailed", tags=["System"])
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

    @app.post("/store/export", tags=["System"])
    async def export_store() -> dict[str, Any]:
        """Export the full store state for backup.

        Returns:
            A dict containing all store data (agents, plugins, bindings, etc.).
        """
        return store.export()

    @app.post("/store/import", tags=["System"])
    async def import_store(request: dict[str, Any]) -> dict[str, Any]:
        """Import store state from a previous export. Replaces all data.

        Args:
            request: The store state to import.

        Returns:
            A dict confirming import with counts of imported entities.
        """
        store.import_(request)
        return {"imported": True, "agents": len(store.agents), "plugins": len(store.plugins)}

    @app.get("/version", tags=["System"])
    async def version() -> dict[str, str]:
        """Return the Nexus API version."""
        from nexus import __version__
        return {"version": __version__}

    app.state.store = store
    app.state.manager = manager
    app.state.api = api

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """Graceful shutdown: persist store snapshot and log final stats.

        Called when the FastAPI application is shutting down. Logs a
        summary of calls, agents, and plugins for observability.
        """
        stats = store.stats()
        logger.info(
            "Nexus shutting down — agents=%d plugins=%d calls=%d workflows=%d",
            len(store.agents),
            len(store.plugins),
            stats.get("calls", 0),
            stats.get("workflows", 0),
        )

    return app


app = create_app()
