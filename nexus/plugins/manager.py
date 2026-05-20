from __future__ import annotations

from typing import Any

from nexus.core.db import NexusStore
from nexus.core.models import ToolPlugin
from nexus.plugins.loader import PluginLoader
from nexus.plugins.registry import PluginRegistry
from nexus.plugins.sdk import Plugin, registered_plugins


class PluginManager:
    def __init__(self, store: NexusStore | None = None, registry: PluginRegistry | None = None) -> None:
        self.store = store or NexusStore()
        self.registry = registry or PluginRegistry()
        self.loader = PluginLoader()

    def register(self, plugin: Plugin) -> ToolPlugin:
        metadata = self.registry.register(plugin)
        self.store.upsert_plugin(metadata)
        self.store.audit("plugin.registered", tool_id=metadata.id)
        return metadata

    def install_builtin(self, plugin_id: str) -> ToolPlugin:
        for plugin in self.loader.load_builtins():
            if plugin.metadata.id == plugin_id:
                return self.register(plugin)
        raise KeyError(f"Unknown built-in plugin: {plugin_id}")

    def install_all_builtins(self) -> list[ToolPlugin]:
        return [self.register(plugin) for plugin in self.loader.load_builtins()]

    def install_global_plugins(self) -> list[ToolPlugin]:
        return [self.register(plugin) for plugin in registered_plugins().values()]

    def hot_load(self, directory: str) -> list[ToolPlugin]:
        return [self.register(plugin) for plugin in self.loader.load_directory(directory)]

    def get(self, plugin_id: str) -> Plugin:
        plugin = self.registry.get(plugin_id)
        if plugin is None:
            raise KeyError(f"Plugin not installed: {plugin_id}")
        return plugin

    def list_plugins(self) -> list[ToolPlugin]:
        return self.registry.metadata()

    def list_plugins_by_status(self, status: str) -> list[ToolPlugin]:
        """Filter plugins by lifecycle status.

        Args:
            status: PluginStatus value to filter by (e.g. 'active', 'error').

        Returns:
            List of ToolPlugin instances matching the given status.
        """
        return [p for p in self.registry.metadata() if p.status == status]

    def discover(self) -> dict[str, list[str]]:
        return self.registry.capabilities()

    def health(self) -> dict[str, Any]:
        return {plugin.metadata.id: plugin.health() for plugin in self.registry.list()}

    def unregister(self, plugin_id: str) -> bool:
        """Unregister a plugin by ID. Returns True if removed, False if not found.

        Args:
            plugin_id: The plugin identifier to remove.

        Returns:
            True if the plugin was unregistered, False if it wasn't found.
        """
        plugin = self.registry.get(plugin_id)
        if plugin is None:
            return False
        self.registry.unregister(plugin_id)
        self.store.plugins.pop(plugin_id, None)
        self.store.audit("plugin.unregistered", tool_id=plugin_id)
        return True

    def __repr__(self) -> str:
        plugins = self.registry.metadata()
        active = sum(1 for p in plugins if p.status == "active")
        return (
            f"PluginManager(plugins={len(plugins)}, active={active}, "
            f"error={len(plugins) - active})"
        )
