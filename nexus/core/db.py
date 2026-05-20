from __future__ import annotations

from collections import deque
from dataclasses import asdict, is_dataclass
from typing import Any

from nexus.core.models import AgentToolBinding, ToolCall, ToolPlugin, Workflow


_DEFAULT_MAX_CALLS = 10_000
_DEFAULT_MAX_AUDIT = 5_000


class NexusStore:
    """Small in-memory store used by all local Nexus surfaces.

    Stores agents, plugins, bindings, tool calls, workflows, and audit events.
    Uses bounded deques for calls and audit events to prevent unbounded memory growth.

    Example:
        >>> store = NexusStore(max_calls=1000, max_audit_events=500)
        >>> store.register_agent("agent-1")
        >>> len(store)
        0
    """

    def __init__(
        self,
        max_calls: int = _DEFAULT_MAX_CALLS,
        max_audit_events: int = _DEFAULT_MAX_AUDIT,
    ) -> None:
        """Initialize the store with bounded capacity.

        Args:
            max_calls: Maximum number of tool calls to retain (default 10000).
            max_audit_events: Maximum audit events to retain (default 5000).
        """
        self.agents: set[str] = set()
        self.plugins: dict[str, ToolPlugin] = {}
        self.bindings: dict[tuple[str, str], AgentToolBinding] = {}
        self.calls: deque[ToolCall] = deque(maxlen=max_calls)
        self.workflows: dict[str, Workflow] = {}
        self.audit_events: deque[dict[str, Any]] = deque(maxlen=max_audit_events)
        self._max_calls = max_calls
        self._max_audit = max_audit_events

    def register_agent(self, agent_id: str) -> None:
        """Register an agent in the store.

        Args:
            agent_id: Unique identifier for the agent.
        """
        self.agents.add(agent_id)

    def upsert_plugin(self, plugin: ToolPlugin) -> None:
        """Insert or update a tool plugin in the store.

        Args:
            plugin: The ToolPlugin instance to store.
        """
        self.plugins[plugin.id] = plugin

    def bind_tool(self, binding: AgentToolBinding) -> None:
        """Create an agent-tool binding, auto-registering the agent if needed.

        Args:
            binding: The AgentToolBinding to store.
        """
        self.register_agent(binding.agent_id)
        self.bindings[(binding.agent_id, binding.tool_id)] = binding

    def unbind_tool(self, agent_id: str, tool_id: str) -> None:
        """Remove an agent-tool binding.

        Args:
            agent_id: The agent identifier.
            tool_id: The tool identifier.
        """
        self.bindings.pop((agent_id, tool_id), None)

    def get_binding(self, agent_id: str, tool_id: str) -> AgentToolBinding | None:
        """Retrieve an agent-tool binding.

        Args:
            agent_id: The agent identifier.
            tool_id: The tool identifier.

        Returns:
            The AgentToolBinding if found, None otherwise.
        """
        return self.bindings.get((agent_id, tool_id))

    def record_call(self, call: ToolCall) -> ToolCall:
        """Record a tool call in the store.

        Args:
            call: The ToolCall instance to record.

        Returns:
            The recorded ToolCall instance.
        """
        self.calls.append(call)
        return call

    def save_workflow(self, workflow: Workflow) -> Workflow:
        """Persist a workflow in the store.

        Args:
            workflow: The Workflow instance to save.

        Returns:
            The saved Workflow instance.
        """
        self.workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Retrieve a workflow by its ID.

        Args:
            workflow_id: The unique workflow identifier.

        Returns:
            The Workflow if found, None otherwise.
        """
        return self.workflows.get(workflow_id)

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow by its ID.

        Args:
            workflow_id: The unique workflow identifier.

        Returns:
            True if the workflow was deleted, False if not found.
        """
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            return True
        return False

    def list_workflows(self) -> list[Workflow]:
        """List all stored workflows.

        Returns:
            A list of all Workflow instances.
        """
        return list(self.workflows.values())

    def audit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        """Record an audit event.

        Args:
            event_type: The type of audit event.
            **payload: Additional event data.

        Returns:
            The recorded audit event dict.
        """
        event = {"type": event_type, **payload}
        self.audit_events.append(event)
        return event

    def __len__(self) -> int:
        return len(self.calls)

    def __bool__(self) -> bool:
        return True

    def clear(self) -> None:
        """Clear all stored data. Useful for testing."""
        self.agents.clear()
        self.plugins.clear()
        self.bindings.clear()
        self.calls.clear()
        self.workflows.clear()
        self.audit_events.clear()

    def recent_calls(self, n: int = 10) -> list[ToolCall]:
        """Return the most recent tool calls.

        Args:
            n: Maximum number of calls to return.

        Returns:
            A list of up to n recent ToolCall instances.
        """
        return list(self.calls)[-n:]

    def snapshot(self, *, call_limit: int = 100, audit_limit: int = 100) -> dict[str, Any]:
        """Create a full snapshot of the store state.

        Args:
            call_limit: Maximum number of calls to include.
            audit_limit: Maximum number of audit events to include.

        Returns:
            A dict containing agents, plugins, bindings, calls, workflows, and audit events.
        """
        all_calls = list(self.calls)
        all_audit = list(self.audit_events)
        return {
            "agents": sorted(self.agents),
            "plugins": [self._to_dict(plugin) for plugin in self.plugins.values()],
            "bindings": [self._to_dict(binding) for binding in self.bindings.values()],
            "calls": [self._to_dict(call) for call in all_calls[-call_limit:]],
            "calls_total": len(all_calls),
            "workflows": [self._to_dict(workflow) for workflow in self.workflows.values()],
            "audit_events": all_audit[-audit_limit:],
            "audit_total": len(all_audit),
        }

    @staticmethod
    def _to_dict(value: Any) -> Any:
        """Convert a dataclass instance to a dict, or return as-is.

        Args:
            value: The value to convert.

        Returns:
            A dict if the value is a dataclass, otherwise the original value.
        """
        if is_dataclass(value):
            return asdict(value)
        return value
