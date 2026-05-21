from __future__ import annotations

from nexus.core.db import NexusStore
from nexus.core.models import AgentToolBinding, PermissionLevel
from nexus.permissions.permissions import PermissionModel


class AccessControl:
    def __init__(self, store: NexusStore, model: PermissionModel | None = None) -> None:
        self.store = store
        self.model = model or PermissionModel()

    def grant(self, agent_id: str, tool_id: str, level: str, config: dict | None = None) -> AgentToolBinding:
        """Grant a permission level to an agent for a specific tool.

        Args:
            agent_id: Unique identifier for the agent.
            tool_id: Unique identifier for the tool.
            level: Permission level (read, write, admin).
            config: Optional configuration dict for this binding.

        Returns:
            The created AgentToolBinding.

        Raises:
            ValueError: If agent_id/tool_id is empty or level is unknown.
            TypeError: If config is provided but is not a dict.
        """
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError(f"agent_id must be a non-empty string, got {agent_id!r}")
        if not isinstance(tool_id, str) or not tool_id.strip():
            raise ValueError(f"tool_id must be a non-empty string, got {tool_id!r}")
        if level not in PermissionModel.ORDER:
            raise ValueError(f"Unknown permission level: {level}")
        if config is not None and not isinstance(config, dict):
            raise TypeError(f"config must be a dict or None, got {type(config).__name__}")
        binding = AgentToolBinding(agent_id=agent_id.strip(), tool_id=tool_id.strip(), permissions=level, config=config or {})
        self.store.bind_tool(binding)
        self.store.audit("permission.granted", agent_id=agent_id, tool_id=tool_id, level=level)
        return binding

    def revoke(self, agent_id: str, tool_id: str) -> None:
        self.store.unbind_tool(agent_id, tool_id)
        self.store.audit("permission.revoked", agent_id=agent_id, tool_id=tool_id)

    def check(self, agent_id: str, tool_id: str, action: str) -> bool:
        binding = self.store.get_binding(agent_id, tool_id)
        if binding is None:
            return False
        required = self.model.required_for_action(action)
        return self.model.allows(binding.permissions, required)

    def require(self, agent_id: str, tool_id: str, action: str) -> None:
        if not self.check(agent_id, tool_id, action):
            self.store.audit("permission.denied", agent_id=agent_id, tool_id=tool_id, action=action)
            raise PermissionError(f"{agent_id} cannot call {tool_id}.{action}")

    def list_agent_permissions(self, agent_id: str) -> list[AgentToolBinding]:
        return [binding for binding in self.store.bindings.values() if binding.agent_id == agent_id]

    def is_admin(self, agent_id: str, tool_id: str) -> bool:
        binding = self.store.get_binding(agent_id, tool_id)
        return bool(binding and binding.permissions == PermissionLevel.ADMIN.value)

    def __repr__(self) -> str:
        return (
            f"AccessControl(agents={len(self.store.agents)}, "
            f"bindings={len(self.store.bindings)})"
        )
