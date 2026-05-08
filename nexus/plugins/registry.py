from __future__ import annotations

from nexus.core.models import ToolPlugin
from nexus.plugins.sdk import Plugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> ToolPlugin:
        self._plugins[plugin.metadata.id] = plugin
        return plugin.metadata.to_model()

    def unregister(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)

    def get(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def list(self) -> list[Plugin]:
        return list(self._plugins.values())

    def metadata(self) -> list[ToolPlugin]:
        return [plugin.metadata.to_model() for plugin in self._plugins.values()]

    def capabilities(self) -> dict[str, list[str]]:
        return {plugin.metadata.id: plugin.get_capabilities() for plugin in self._plugins.values()}
