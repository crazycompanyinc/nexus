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
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


@dataclass(slots=True)
class ToolPlugin:
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
        return action in self.capabilities or "*" in self.capabilities

    def __repr__(self) -> str:
        return f"ToolPlugin(id={self.id!r}, name={self.name!r}, type={self.plugin_type!r}, status={self.status!r})"


@dataclass(slots=True)
class AgentToolBinding:
    agent_id: str
    tool_id: str
    permissions: str
    config: dict[str, Any] = field(default_factory=dict)
    bound_at: datetime = field(default_factory=utcnow)

    def __repr__(self) -> str:
        return f"AgentToolBinding(agent={self.agent_id!r}, tool={self.tool_id!r}, perm={self.permissions!r})"


@dataclass(slots=True)
class ToolCall:
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
        return f"ToolCall(id={self.id[:8]}…, agent={self.agent_id!r}, tool={self.tool_id!r}, action={self.action!r}, status={self.status!r}, dur={self.duration_ms:.1f}ms)"


@dataclass(slots=True)
class WorkflowStep:
    tool_id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None
    fallback_tools: list[str] = field(default_factory=list)
    max_retries: int = 0
    retry_delay_ms: float = 100.0

    def __repr__(self) -> str:
        return f"WorkflowStep(tool={self.tool_id!r}, action={self.action!r}, retries={self.max_retries})"


@dataclass(slots=True)
class Workflow:
    id: str
    name: str
    description: str
    steps: list[WorkflowStep]
    trigger: str = WorkflowTrigger.MANUAL.value
    status: str = WorkflowStatus.ACTIVE.value
    created_by: str = "system"
    created_at: datetime = field(default_factory=utcnow)

    def __repr__(self) -> str:
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
