from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utcnow() -> datetime:
    """Return the current datetime in UTC timezone.

    Returns:
        A timezone-aware datetime representing the current moment in UTC.
    """
    return datetime.now(timezone.utc)


class PluginType(str, Enum):
    """Enumeration of supported plugin integration types."""

    API = "api"
    CLI = "cli"
    LIBRARY = "library"
    WEBHOOK = "webhook"
    DATABASE = "database"


class PluginStatus(str, Enum):
    """Enumeration of possible plugin lifecycle states."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    DEPRECATED = "deprecated"


class PermissionLevel(str, Enum):
    """Enumeration of agent permission levels for tool access."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class CallStatus(str, Enum):
    """Enumeration of possible tool call outcomes."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    DENIED = "denied"


class WorkflowTrigger(str, Enum):
    """Enumeration of workflow trigger types."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"


class WorkflowStatus(str, Enum):
    """Enumeration of possible workflow execution states."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


@dataclass(slots=True)
class ToolPlugin:
    """Represents a registered tool plugin with its metadata and capabilities.

    Attributes:
        id: Unique plugin identifier.
        name: Human-readable plugin name.
        description: Brief description of the plugin's purpose.
        version: Semantic version string.
        plugin_type: Integration type (api, cli, library, etc.).
        capabilities: List of action strings the plugin supports.
        endpoint: Optional URL endpoint for the plugin.
        auth_required: Whether authentication is needed.
        auth_type: Optional authentication type identifier.
        config_schema: JSON-serializable configuration schema.
        health_check_endpoint: Optional health check URL.
        status: Current plugin lifecycle status.
        registered_at: Timestamp of plugin registration.
    """

    id: str
    name: str
    description: str
    version: str
    plugin_type: str
    capabilities: list[str]
    endpoint: str | None = None
    auth_required: bool = False
    auth_type: str | None = None
    config_schema: dict[str, Any] = field(default_factory=dict)
    health_check_endpoint: str | None = None
    status: str = PluginStatus.ACTIVE.value
    registered_at: datetime = field(default_factory=utcnow)

    def supports(self, action: str) -> bool:
        """Check if this plugin supports a given action.

        Args:
            action: The action string to check (e.g. 'file.read').

        Returns:
            True if the action is in capabilities or wildcard '*' is present.
        """
        return action in self.capabilities or "*" in self.capabilities

    def __repr__(self) -> str:
        """Return a concise developer-friendly representation.

        Returns:
            String with id, name, type, and status fields.
        """
        return f"ToolPlugin(id={self.id!r}, name={self.name!r}, type={self.plugin_type!r}, status={self.status!r})"

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict with ISO 8601 timestamps.

        Returns:
            A dict representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "plugin_type": self.plugin_type,
            "capabilities": list(self.capabilities),
            "endpoint": self.endpoint,
            "auth_required": self.auth_required,
            "auth_type": self.auth_type,
            "config_schema": dict(self.config_schema),
            "health_check_endpoint": self.health_check_endpoint,
            "status": self.status,
            "registered_at": self.registered_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolPlugin":
        """Reconstruct a ToolPlugin from a dict.

        Accepts the same keys produced by ``to_dict()``. Extra keys
        are silently ignored, making the method forward-compatible.

        Args:
            data: Dict with tool plugin fields.

        Returns:
            A new ToolPlugin instance.

        Example:
            >>> data = {"id": "x", "name": "X", "description": "d",
            ...         "version": "1.0.0", "plugin_type": "api",
            ...         "capabilities": ["read"]}
            >>> plugin = ToolPlugin.from_dict(data)
            >>> plugin.id
            'x'
        """
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            version=data["version"],
            plugin_type=data["plugin_type"],
            capabilities=list(data.get("capabilities", [])),
            endpoint=data.get("endpoint"),
            auth_required=data.get("auth_required", False),
            auth_type=data.get("auth_type"),
            config_schema=dict(data.get("config_schema", {})),
            health_check_endpoint=data.get("health_check_endpoint"),
            status=data.get("status", PluginStatus.ACTIVE.value),
        )


@dataclass(slots=True)
class AgentToolBinding:
    """Represents a binding between an agent and a tool with specific permissions.

    Attributes:
        agent_id: Unique identifier for the agent.
        tool_id: Unique identifier for the tool.
        permissions: Permission level granted (read, write, admin).
        config: Optional configuration overrides for this binding.
        bound_at: Timestamp when the binding was created.
    """

    agent_id: str
    tool_id: str
    permissions: str
    config: dict[str, Any] = field(default_factory=dict)
    bound_at: datetime = field(default_factory=utcnow)

    def __repr__(self) -> str:
        """Return a concise developer-friendly representation.

        Returns:
            String with agent_id, tool_id, and permissions fields.
        """
        return f"AgentToolBinding(agent={self.agent_id!r}, tool={self.tool_id!r}, perm={self.permissions!r})"

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict with ISO 8601 timestamps.

        Returns:
            A dict representation suitable for JSON serialization.
        """
        return {
            "agent_id": self.agent_id,
            "tool_id": self.tool_id,
            "permissions": self.permissions,
            "config": dict(self.config),
            "bound_at": self.bound_at.isoformat(),
        }


@dataclass(slots=True)
class ToolCall:
    """Represents a single tool invocation by an agent.

    Attributes:
        agent_id: Unique identifier for the calling agent.
        tool_id: Unique identifier for the invoked tool.
        action: Action name executed on the tool.
        params: Parameters passed to the action.
        result: Output from the tool execution.
        duration_ms: Execution time in milliseconds.
        status: Call outcome status (success, error, timeout, denied).
        id: Unique call identifier (auto-generated UUID).
        called_at: Timestamp of the call.
    """

    agent_id: str
    tool_id: str
    action: str
    params: dict[str, Any]
    result: Any = None
    duration_ms: float = 0.0
    status: str = CallStatus.SUCCESS.value
    id: str = field(default_factory=lambda: str(uuid4()))
    called_at: datetime = field(default_factory=utcnow)

    def __repr__(self) -> str:
        """Return a concise developer-friendly representation.

        Returns:
            String with id prefix, agent, tool, action, status, and duration.
        """
        return f"ToolCall(id={self.id[:8]}…, agent={self.agent_id!r}, tool={self.tool_id!r}, action={self.action!r}, status={self.status!r}, dur={self.duration_ms:.1f}ms)"

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict with ISO 8601 timestamps.

        Returns:
            A dict representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "tool_id": self.tool_id,
            "action": self.action,
            "params": dict(self.params),
            "result": self.result,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "called_at": self.called_at.isoformat(),
        }


@dataclass(slots=True)
class WorkflowStep:
    """Represents a single step within a workflow.

    Attributes:
        tool_id: Tool identifier to invoke.
        action: Action name to execute.
        params: Parameters passed to the action.
        condition: Optional condition for step execution.
        fallback_tools: Ordered list of backup tool IDs.
        max_retries: Maximum retry attempts on failure.
        retry_delay_ms: Base delay between retries in milliseconds.
    """

    tool_id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None
    fallback_tools: list[str] = field(default_factory=list)
    max_retries: int = 0
    retry_delay_ms: float = 100.0

    def __repr__(self) -> str:
        """Return a concise developer-friendly representation.

        Returns:
            String with tool_id, action, and max_retries fields.
        """
        return f"WorkflowStep(tool={self.tool_id!r}, action={self.action!r}, retries={self.max_retries})"

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict.

        Returns:
            A dict representation suitable for JSON serialization.
        """
        return {
            "tool_id": self.tool_id,
            "action": self.action,
            "params": dict(self.params),
            "condition": self.condition,
            "fallback_tools": list(self.fallback_tools),
            "max_retries": self.max_retries,
            "retry_delay_ms": self.retry_delay_ms,
        }


@dataclass(slots=True)
class Workflow:
    """Represents a multi-step workflow definition.

    Attributes:
        id: Unique workflow identifier (auto-generated UUID).
        name: Human-readable workflow name.
        description: Brief description of the workflow's purpose.
        steps: Ordered list of workflow steps.
        trigger: Trigger type (manual, scheduled, event).
        status: Current workflow lifecycle status.
        created_by: Identifier of the agent that created the workflow.
        created_at: Timestamp of workflow creation.
    """

    id: str
    name: str
    description: str
    steps: list[WorkflowStep]
    trigger: str = WorkflowTrigger.MANUAL.value
    status: str = WorkflowStatus.ACTIVE.value
    created_by: str = "system"
    created_at: datetime = field(default_factory=utcnow)

    def __repr__(self) -> str:
        """Return a concise developer-friendly representation.

        Returns:
            String with id prefix, name, step count, trigger, and status.
        """
        return f"Workflow(id={self.id[:8]}…, name={self.name!r}, steps={len(self.steps)}, trigger={self.trigger!r}, status={self.status!r})"

    def validate(self) -> list[str]:
        """Validate workflow integrity. Returns list of error messages (empty = valid)."""
        errors: list[str] = []
        if not self.name.strip():
            errors.append("Workflow name cannot be empty")
        if not self.steps:
            errors.append("Workflow must have at least one step")
        for i, step in enumerate(self.steps):
            if not step.tool_id.strip():
                errors.append(f"Step {i}: tool_id cannot be empty")
            if not step.action.strip():
                errors.append(f"Step {i}: action cannot be empty")
            if step.max_retries < 0:
                errors.append(f"Step {i}: max_retries cannot be negative")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict with ISO 8601 timestamps.

        Returns:
            A dict representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "trigger": self.trigger,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }
