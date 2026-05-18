from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PluginType(str, Enum):
    API = "api"
    CLI = "cli"
    LIBRARY = "library"
    WEBHOOK = "webhook"
    DATABASE = "database"


class PluginStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    DEPRECATED = "deprecated"


class PermissionLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class CallStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    DENIED = "denied"


class WorkflowTrigger(str, Enum):
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
