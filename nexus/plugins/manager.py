from __future__ import annotations

from typing import Any

from nexus.core.db import NexusStore
from nexus.core.models import ToolPlugin
from nexus.core.circuit_breaker import CircuitBreaker, CircuitState
from nexus.plugins.loader import PluginLoader
from nexus.plugins.registry import PluginRegistry
from nexus.plugins.sdk import Plugin, registered_plugins


class PluginManager:
    """Manages plugin lifecycle: registration, discovery, installation, and health monitoring.

    Coordinates between the plugin registry (metadata), loader (discovery),
    and store (persistence) to provide a unified plugin management surface.

    Each plugin can optionally have a ``CircuitBreaker`` to prevent cascading
    failures when a tool is unresponsive. When a circuit breaker is configured,
    calls made through ``call()`` are guarded by the breaker.

    Example:
        >>> manager = PluginManager()
        >>> manager.install_all_builtins()
        >>> len(manager.list_plugins())
        11
    """

    def __init__(
        self,
        store: NexusStore | None = None,
        registry: PluginRegistry | None = None,
        default_circuit_breaker: bool = False,
    ) -> None:
        """Initialize the PluginManager.

        Args:
            store: NexusStore instance for persistence. Creates default if None.
            registry: PluginRegistry instance. Creates default if None.
            default_circuit_breaker: If True, auto-create a CircuitBreaker for
                each plugin registered via ``register()``.
        """
        self.store = store or NexusStore()
        self.registry = registry or PluginRegistry()
        self.loader = PluginLoader()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_breakers = default_circuit_breaker

    def set_circuit_breaker(self, plugin_id: str, breaker: CircuitBreaker) -> None:
        """Attach a circuit breaker to a specific plugin.

        Args:
            plugin_id: The plugin identifier.
            breaker: The CircuitBreaker instance to use for that plugin.

        Raises:
            KeyError: If the plugin is not registered.
        """
        if not self.registry.get(plugin_id):
            raise KeyError(f"Plugin not registered: {plugin_id}")
        self._breakers[plugin_id] = breaker

    def get_circuit_breaker(self, plugin_id: str) -> CircuitBreaker | None:
        """Return the circuit breaker for a plugin, if any."""
        return self._breakers.get(plugin_id)

    def call(self, plugin_id: str, action: str, params: dict[str, Any]) -> Any:
        """Execute a plugin action, optionally guarded by a circuit breaker.

        If a circuit breaker is set for the plugin, the call is routed through
        it. When the circuit is open, a RuntimeError is raised immediately
        without calling the plugin.

        Args:
            plugin_id: The plugin identifier.
            action: The action name to execute.
            params: Parameters dict passed to the plugin action.

        Returns:
            The result from the plugin execution.

        Raises:
            KeyError: If the plugin is not registered.
            RuntimeError: If the circuit breaker is open.
        """
        plugin = self.get(plugin_id)
        breaker = self._breakers.get(plugin_id)
        if breaker:
            return breaker.call(plugin.execute, action, params)
        return plugin.execute(action, params)

    def register(self, plugin: Plugin) -> ToolPlugin:
        """Register a plugin, persisting its metadata and recording an audit event.

        Args:
            plugin: The Plugin instance to register.

        Returns:
            The registered ToolPlugin metadata.
        """
        metadata = self.registry.register(plugin)
        self.store.upsert_plugin(metadata)
        self.store.audit("plugin.registered", tool_id=metadata.id)
        return metadata

    def install_builtin(self, plugin_id: str) -> ToolPlugin:
        """Install a single built-in plugin by its ID.

        Args:
            plugin_id: The identifier of the built-in plugin to install.

        Returns:
            The registered ToolPlugin metadata.

        Raises:
            KeyError: If no built-in plugin matches the given ID.
        """
        for plugin in self.loader.load_builtins():
            if plugin.metadata.id == plugin_id:
                return self.register(plugin)
        raise KeyError(f"Unknown built-in plugin: {plugin_id}")

    def install_all_builtins(self) -> list[ToolPlugin]:
        """Install all available built-in plugins.

        Returns:
            List of registered ToolPlugin metadata for all built-ins.
        """
        return [self.register(plugin) for plugin in self.loader.load_builtins()]

    def install_global_plugins(self) -> list[ToolPlugin]:
        """Install all globally registered plugins (via @register_plugin decorator).

        Returns:
            List of registered ToolPlugin metadata for all global plugins.
        """
        return [self.register(plugin) for plugin in registered_plugins().values()]

    def hot_load(self, directory: str) -> list[ToolPlugin]:
        """Dynamically load and register plugins from a directory.

        Args:
            directory: Path to a directory containing plugin modules.

        Returns:
            List of registered ToolPlugin metadata for loaded plugins.
        """
        return [self.register(plugin) for plugin in self.loader.load_directory(directory)]

    def get(self, plugin_id: str) -> Plugin:
        """Retrieve a registered plugin instance by ID.

        Args:
            plugin_id: The plugin identifier.

        Returns:
            The Plugin instance.

        Raises:
            KeyError: If the plugin is not installed.
        """
        plugin = self.registry.get(plugin_id)
        if plugin is None:
            raise KeyError(f"Plugin not installed: {plugin_id}")
        return plugin

    def list_plugins(self) -> list[ToolPlugin]:
        """List all registered plugins' metadata.

        Returns:
            List of ToolPlugin instances for all registered plugins.
        """
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
        """Discover all available capabilities grouped by plugin.

        Returns:
            Dict mapping plugin IDs to their list of capability strings.
        """
        return self.registry.capabilities()

    def health(self) -> dict[str, Any]:
        """Check health status of all registered plugins.

        Returns:
            Dict mapping plugin IDs to their health check results.
        """
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

    def __len__(self) -> int:
        """Return the number of registered plugins.

        Returns:
            Integer count of registered plugins.
        """
        return len(self.registry.metadata())
