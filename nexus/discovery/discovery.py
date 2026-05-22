from __future__ import annotations

from nexus.plugins.manager import PluginManager


class CapabilityRegistry:
    """Registry for discovering tools by capability.

    Wraps a PluginManager to provide capability-based lookups.
    """

    def __init__(self, manager: PluginManager) -> None:
        self.manager = manager

    def all(self) -> dict[str, list[str]]:
        """Return all capabilities as a dict of tool_id -> list of actions.

        Returns:
            Dict mapping each tool ID to its supported capability strings.
        """
        return self.manager.discover()

    def find(self, capability: str) -> list[str]:
        """Find all tool IDs that support a given capability.

        Args:
            capability: The capability string to search for.

        Returns:
            List of tool IDs that include the given capability.
        """
        return [tool_id for tool_id, actions in self.all().items() if capability in actions]

    def __repr__(self) -> str:
        caps = self.all()
        return f"CapabilityRegistry(tools={len(caps)}, capabilities={sum(len(v) for v in caps.values())})"


class ToolDiscovery:
    """Discovers available tools and their capabilities from the plugin manager."""

    def __init__(self, manager: PluginManager) -> None:
        self.manager = manager
        self.capabilities = CapabilityRegistry(manager)

    def available_tools(self) -> list[dict[str, object]]:
        """List all registered plugins with their metadata.

        Returns:
            List of dicts with keys: id, name, description, capabilities, status.
        """
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
        """Find tool IDs that support a specific capability.

        Args:
            capability: The capability string to filter by.

        Returns:
            List of tool IDs supporting the capability.
        """
        return self.capabilities.find(capability)

    def __repr__(self) -> str:
        tools = self.available_tools()
        return f"ToolDiscovery(tools={len(tools)})"
