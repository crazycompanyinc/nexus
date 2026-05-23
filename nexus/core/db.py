from __future__ import annotations

from collections import deque
from dataclasses import asdict, is_dataclass
from typing import Any, Iterator

from nexus.core.models import AgentToolBinding, ToolCall, ToolPlugin, Workflow, WorkflowStep


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

        Raises:
            ValueError: If agent_id is empty or not a string.
        """
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError(f"agent_id must be a non-empty string, got {agent_id!r}")
        self.agents.add(agent_id.strip())

    def upsert_plugin(self, plugin: ToolPlugin) -> None:
        """Insert or update a tool plugin in the store.

        Args:
            plugin: The ToolPlugin instance to store.

        Raises:
            TypeError: If plugin is not a ToolPlugin instance.
            ValueError: If plugin.id is empty.
        """
        if not isinstance(plugin, ToolPlugin):
            raise TypeError(f"Expected ToolPlugin instance, got {type(plugin).__name__}")
        if not plugin.id or not plugin.id.strip():
            raise ValueError("Plugin id cannot be empty")
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
        """Return the number of recorded tool calls.

        Returns:
            Integer count of calls in the store.
        """
        return len(self.calls)

    def stats(self) -> dict[str, int]:
        """Return summary statistics of the store contents.

        Returns:
            Dict with counts for agents, plugins, bindings, calls,
            workflows, and audit_events.

        Example:
            >>> store = NexusStore()
            >>> store.register_agent("a1")
            >>> s = store.stats()
            >>> s["agents"]
            1
        """
        return {
            "agents": len(self.agents),
            "plugins": len(self.plugins),
            "bindings": len(self.bindings),
            "calls": len(self.calls),
            "workflows": len(self.workflows),
            "audit_events": len(self.audit_events),
        }

    def __bool__(self) -> bool:
        """Return True — a NexusStore is always truthy.

        Returns:
            Always True, even when the store is empty.
        """
        return True

    def __contains__(self, agent_id: str) -> bool:
        """Check if an agent is registered in the store.

        Args:
            agent_id: The agent identifier to check.

        Returns:
            True if the agent is registered, False otherwise.

        Example:
            >>> store = NexusStore()
            >>> store.register_agent("a1")
            >>> "a1" in store
            True
            >>> "nonexistent" in store
            False
        """
        return agent_id in self.agents

    def __iter__(self) -> Iterator[ToolCall]:
        """Iterate over recorded tool calls in chronological order.

        Returns:
            An iterator over ToolCall instances.

        Example:
            >>> for call in store:
            ...     print(call.action)
        """
        return iter(self.calls)

    def agent_call_count(self, agent_id: str) -> int:
        """Return the number of tool calls made by a specific agent.

        Uses an efficient generator-based count instead of building
        an intermediate list.

        Args:
            agent_id: The agent identifier.

        Returns:
            The number of calls recorded for the agent.
        """
        return sum(1 for c in self.calls if c.agent_id == agent_id)

    def last_call_for_agent(self, agent_id: str) -> ToolCall | None:
        """Return the most recent tool call for a specific agent.

        Searches calls in reverse order for efficiency.

        Args:
            agent_id: The agent identifier.

        Returns:
            The most recent ToolCall for the agent, or None if no calls exist.
        """
        for call in reversed(self.calls):
            if call.agent_id == agent_id:
                return call
        return None

    def agent_calls(self, agent_id: str, *, status: str | None = None, limit: int | None = None) -> list[ToolCall]:
        """Return tool calls for a specific agent, optionally filtered by status.

        Iterates in reverse chronological order (most recent first).

        Args:
            agent_id: The agent identifier to filter by.
            status: Optional CallStatus value to filter by (e.g. 'success', 'error').
            limit: Maximum number of calls to return. None returns all.

        Returns:
            List of ToolCall instances for the agent, most recent first.

        Example:
            >>> calls = store.agent_calls("agent-1", status="error", limit=5)
        """
        results: list[ToolCall] = []
        for call in reversed(self.calls):
            if call.agent_id != agent_id:
                continue
            if status is not None and call.status != status:
                continue
            results.append(call)
            if limit is not None and len(results) >= limit:
                break
        return results

    def __repr__(self) -> str:
        """Return a summary of the store's current contents.

        Returns:
            String with counts of agents, plugins, bindings, calls, workflows, and audit events.
        """
        return (
            f"NexusStore(agents={len(self.agents)}, plugins={len(self.plugins)}, "
            f"bindings={len(self.bindings)}, calls={len(self.calls)}/{self._max_calls}, "
            f"workflows={len(self.workflows)}, audit={len(self.audit_events)}/{self._max_audit})"
        )

    def clear(self) -> None:
        """Clear all stored data. Useful for testing."""
        self.agents.clear()
        self.plugins.clear()
        self.bindings.clear()
        self.calls.clear()
        self.workflows.clear()
        self.audit_events.clear()

    def export(self) -> dict[str, Any]:
        """Export the full store state as a JSON-serializable dict.

        Returns:
            A dict with keys: agents, plugins, bindings, calls, workflows, audit_events.
        """
        return {
            "agents": sorted(self.agents),
            "plugins": [self._to_dict(p) for p in self.plugins.values()],
            "bindings": [self._to_dict(b) for b in self.bindings.values()],
            "calls": [self._to_dict(c) for c in self.calls],
            "workflows": [self._to_dict(w) for w in self.workflows.values()],
            "audit_events": list(self.audit_events),
        }

    def import_(self, data: dict[str, Any]) -> None:
        """Import store state from an exported dict. Replaces all current data.

        Parses ISO 8601 datetime strings back to ``datetime`` objects for
        ``ToolPlugin``, ``AgentToolBinding``, ``ToolCall``, and ``Workflow``
        entries so that round-tripping through ``export()`` / ``import_()``
        preserves full type fidelity.

        Args:
            data: Dict produced by export().

        Raises:
            ValueError: If required top-level keys are missing or data is malformed.
            TypeError: If data is not a dict.
        """
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict for import, got {type(data).__name__}")
        required_keys = {"agents", "plugins", "bindings", "calls", "workflows", "audit_events"}
        missing = required_keys - data.keys()
        if missing:
            raise ValueError(f"Import data missing required keys: {sorted(missing)}")
        self.clear()
        for agent_id in data.get("agents", []):
            if not isinstance(agent_id, str) or not agent_id.strip():
                raise ValueError(f"Invalid agent_id in import data: {agent_id!r}")
            self.agents.add(agent_id.strip())
        for plugin_dict in data.get("plugins", []):
            plugin = self._parse_dataclass(ToolPlugin, plugin_dict)
            self.plugins[plugin.id] = plugin
        for binding_dict in data.get("bindings", []):
            binding = self._parse_dataclass(AgentToolBinding, binding_dict)
            self.bindings[(binding.agent_id, binding.tool_id)] = binding
        for call_dict in data.get("calls", []):
            call = self._parse_dataclass(ToolCall, call_dict)
            self.calls.append(call)
        for wf_dict in data.get("workflows", []):
            wf_data = dict(wf_dict)
            steps = [WorkflowStep(**s) for s in wf_data.pop("steps", [])]
            workflow = self._parse_dataclass(Workflow, wf_data, extra={"steps": steps})
            self.workflows[workflow.id] = workflow
        for event in data.get("audit_events", []):
            self.audit_events.append(event)

    @staticmethod
    def _parse_dataclass(cls: type, data: dict[str, Any], extra: dict[str, Any] | None = None) -> Any:
        """Parse a dict into a dataclass, converting ISO datetime strings.

        Args:
            cls: The dataclass type to construct.
            data: The dict with string values (possibly ISO datetimes).
            extra: Additional keyword arguments to pass to the constructor.

        Returns:
            An instance of the dataclass with proper datetime fields.
        """
        from datetime import datetime
        parsed = dict(data)
        # Convert known datetime fields
        for field_name in ("registered_at", "bound_at", "called_at", "created_at"):
            if field_name in parsed and isinstance(parsed[field_name], str):
                parsed[field_name] = datetime.fromisoformat(parsed[field_name])
        if extra:
            parsed.update(extra)
        return cls(**parsed)

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

        Prefers the model's own ``to_dict()`` method when available
        (handles datetime serialization correctly), falling back to
        ``dataclasses.asdict()`` for other dataclasses.

        Args:
            value: The value to convert.

        Returns:
            A dict if the value is a dataclass, otherwise the original value.
        """
        if is_dataclass(value):
            if hasattr(value, "to_dict"):
                return value.to_dict()
            return asdict(value)
        return value
