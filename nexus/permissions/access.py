from __future__ import annotations

from nexus.core.db import NexusStore
from nexus.core.models import AgentToolBinding, PermissionLevel
from nexus.permissions.permissions import PermissionModel


class AccessControl:
    def __init__(self, store: NexusStore, model: PermissionModel | None = None) -> None:
        self.store = store
        self.model = model or PermissionModel()

    def grant(self, agent_id: str, tool_id: str, level: str, config: dict | None = None) -> AgentToolBinding:
        if level not in PermissionModel.ORDER:
            raise ValueError(f"Unknown permission level: {level}")
        binding = AgentToolBinding(agent_id=agent_id, tool_id=tool_id, permissions=level, config=config or {})
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
