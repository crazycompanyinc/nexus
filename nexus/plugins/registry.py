from __future__ import annotations

from nexus.core.models import ToolPlugin
from nexus.plugins.sdk import Plugin


class PluginRegistry:
    """In-memory registry for plugin instances.

    Provides register/unregister/get/list operations for Plugin objects.
    """

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> ToolPlugin:
        """Register a plugin instance in the registry.

        Args:
            plugin: The plugin instance to register.

        Returns:
            The plugin's ToolPlugin metadata model.
        """
        self._plugins[plugin.metadata.id] = plugin
        return plugin.metadata.to_model()

    def unregister(self, plugin_id: str) -> None:
        """Remove a plugin from the registry by ID.

        Args:
            plugin_id: The unique identifier of the plugin to remove.
        """
        self._plugins.pop(plugin_id, None)

    def get(self, plugin_id: str) -> Plugin | None:
        """Retrieve a plugin by its ID.

        Args:
            plugin_id: The unique identifier of the plugin.

        Returns:
            The plugin instance, or None if not found.
        """
        return self._plugins.get(plugin_id)

    def list(self) -> list[Plugin]:
        """Return all registered plugins.

        Returns:
            List of all registered plugin instances.
        """
        return list(self._plugins.values())

    def metadata(self) -> list[ToolPlugin]:
        """Return metadata models for all registered plugins.

        Returns:
            List of ToolPlugin metadata dicts.
        """
        return [plugin.metadata.to_model() for plugin in self._plugins.values()]

    def capabilities(self) -> dict[str, list[str]]:
        """Return capabilities for all registered plugins.

        Returns:
            Dict mapping plugin ID to its list of capability strings.
        """
        return {plugin.metadata.id: plugin.get_capabilities() for plugin in self._plugins.values()}

    def find_by_capability(self, capability: str) -> list[Plugin]:
        """Find all plugins that support a given capability.

        Args:
            capability: The capability string to search for (e.g. 'read', 'write').

        Returns:
            List of Plugin instances that support the capability.
        """
        return [p for p in self._plugins.values() if capability in p.get_capabilities() or "*" in p.get_capabilities()]
