from __future__ import annotations

from nexus.plugins.manager import PluginManager


class CapabilityRegistry:
    def __init__(self, manager: PluginManager) -> None:
        self.manager = manager

    def all(self) -> dict[str, list[str]]:
        return self.manager.discover()

    def find(self, capability: str) -> list[str]:
        return [tool_id for tool_id, actions in self.all().items() if capability in actions]


class ToolDiscovery:
    def __init__(self, manager: PluginManager) -> None:
        self.manager = manager
        self.capabilities = CapabilityRegistry(manager)

    def available_tools(self) -> list[dict[str, object]]:
        return [
            {
                "id": plugin.id,
                "name": plugin.name,
                "description": plugin.description,
                "capabilities": plugin.capabilities,
                "status": plugin.status,
            }
            for plugin in self.manager.list_plugins()
        ]

    def by_capability(self, capability: str) -> list[str]:
        return self.capabilities.find(capability)
