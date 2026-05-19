from __future__ import annotations

from collections import deque
from dataclasses import asdict, is_dataclass
from typing import Any

from nexus.core.models import AgentToolBinding, ToolCall, ToolPlugin, Workflow


_DEFAULT_MAX_CALLS = 10_000
_DEFAULT_MAX_AUDIT = 5_000


class NexusStore:
    """Small in-memory store used by all local Nexus surfaces."""

    def __init__(
        self,
        max_calls: int = _DEFAULT_MAX_CALLS,
        max_audit_events: int = _DEFAULT_MAX_AUDIT,
    ) -> None:
        self.agents: set[str] = set()
        self.plugins: dict[str, ToolPlugin] = {}
        self.bindings: dict[tuple[str, str], AgentToolBinding] = {}
        self.calls: deque[ToolCall] = deque(maxlen=max_calls)
        self.workflows: dict[str, Workflow] = {}
        self.audit_events: deque[dict[str, Any]] = deque(maxlen=max_audit_events)
        self._max_calls = max_calls
        self._max_audit = max_audit_events

    def register_agent(self, agent_id: str) -> None:
        self.agents.add(agent_id)

    def upsert_plugin(self, plugin: ToolPlugin) -> None:
        self.plugins[plugin.id] = plugin

    def bind_tool(self, binding: AgentToolBinding) -> None:
        self.register_agent(binding.agent_id)
        self.bindings[(binding.agent_id, binding.tool_id)] = binding

    def unbind_tool(self, agent_id: str, tool_id: str) -> None:
        self.bindings.pop((agent_id, tool_id), None)

    def get_binding(self, agent_id: str, tool_id: str) -> AgentToolBinding | None:
        return self.bindings.get((agent_id, tool_id))

    def record_call(self, call: ToolCall) -> ToolCall:
        self.calls.append(call)
        return call

    def save_workflow(self, workflow: Workflow) -> Workflow:
        self.workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        return self.workflows.get(workflow_id)

    def delete_workflow(self, workflow_id: str) -> bool:
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            return True
        return False

    def list_workflows(self) -> list[Workflow]:
        return list(self.workflows.values())

    def audit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {"type": event_type, **payload}
        self.audit_events.append(event)
        return event

    def __len__(self) -> int:
        return len(self.calls)

    def __bool__(self) -> bool:
        return True

    def recent_calls(self, n: int = 10) -> list[ToolCall]:
        return self.calls[-n:]

    def snapshot(self) -> dict[str, Any]:
        return {
            "agents": sorted(self.agents),
            "plugins": [self._to_dict(plugin) for plugin in self.plugins.values()],
            "bindings": [self._to_dict(binding) for binding in self.bindings.values()],
            "calls": [self._to_dict(call) for call in self.calls],
            "workflows": [self._to_dict(workflow) for workflow in self.workflows.values()],
            "audit_events": list(self.audit_events),
        }

    @staticmethod
    def _to_dict(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        return value
