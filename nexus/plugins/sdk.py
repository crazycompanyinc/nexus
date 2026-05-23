from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from nexus.core.models import ToolPlugin


@dataclass(slots=True)
class PluginMetadata:
    """Metadata describing a Nexus plugin.

    Attributes:
        id: Unique plugin identifier (used as lookup key).
        name: Human-readable plugin name.
        description: Short description of what the plugin does.
        version: Semantic version string.
        plugin_type: Category of the plugin (e.g., 'service', 'library').
        capabilities: List of action strings the plugin supports.
        endpoint: Optional HTTP endpoint URL for remote plugins.
        auth_required: Whether authentication is needed for this plugin.
        auth_type: Type of authentication required (e.g., 'bearer', 'basic').
        config_schema: JSON schema dict for plugin configuration.
        health_check_endpoint: Optional URL path for plugin health checks.
        status: Current plugin status ('active', 'inactive', etc.).
    """
    id: str
    name: str
    description: str
    version: str
    plugin_type: str
    capabilities: list[str]
    endpoint: str | None = None
    auth_required: bool = False
    auth_type: str | None = None
    config_schema: dict[str, Any] = field(default_factory=dict)
    health_check_endpoint: str | None = None
    status: str = "active"

    def to_model(self) -> ToolPlugin:
        """Convert this metadata to a ToolPlugin model instance.

        Returns:
            A ToolPlugin populated with this metadata's fields.
        """
        return ToolPlugin(
            id=self.id,
            name=self.name,
            description=self.description,
            version=self.version,
            plugin_type=self.plugin_type,
            capabilities=list(self.capabilities),
            endpoint=self.endpoint,
            auth_required=self.auth_required,
            auth_type=self.auth_type,
            config_schema=dict(self.config_schema),
            health_check_endpoint=self.health_check_endpoint,
            status=self.status,
        )

    def to_dict(self) -> dict[str, object]:
        """Convert to a JSON-serializable dict.

        Returns:
            A dict representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "plugin_type": self.plugin_type,
            "capabilities": list(self.capabilities),
            "endpoint": self.endpoint,
            "auth_required": self.auth_required,
            "auth_type": self.auth_type,
            "config_schema": dict(self.config_schema),
            "health_check_endpoint": self.health_check_endpoint,
            "status": self.status,
        }

    def __eq__(self, other: object) -> bool:
        """Check equality by plugin id.

        Args:
            other: Another PluginMetadata to compare with.

        Returns:
            True if both have the same id.
        """
        if not isinstance(other, PluginMetadata):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash by plugin id for use in sets and dicts.

        Returns:
            Hash of the plugin id.
        """
        return hash(self.id)


class Plugin(Protocol):
    """Protocol that all Nexus plugins must implement.

    Plugins must provide a metadata attribute and execute/health methods.
    """

    metadata: PluginMetadata

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute an action on this plugin.

        Args:
            action: The action to perform.
            params: Parameters for the action.

        Returns:
            The result of the action execution.

        Raises:
            NotImplementedError: If the action is not supported.
        """
        ...

    def health(self) -> dict[str, Any]:
        """Return the health status of this plugin.

        Returns:
            Dict with at minimum a 'status' key indicating plugin health.
        """
        ...


class BasePlugin(ABC):
    """Base class for plugins providing default capability and health methods.

    Subclasses must override ``metadata`` and implement ``execute()``.
    """

    metadata = PluginMetadata(
        id="base",
        name="base",
        description="Base Nexus plugin",
        version="0.0.0",
        plugin_type="library",
        capabilities=[],
    )

    def get_capabilities(self) -> list[str]:
        """Return the list of capabilities this plugin supports.

        Returns:
            List of capability strings from the plugin metadata.
        """
        return list(self.metadata.capabilities)

    @abstractmethod
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute an action — must be implemented by subclasses.

        Args:
            action: The action to perform.
            params: Parameters for the action.
        """
        ...

    def health(self) -> dict[str, Any]:
        """Return basic health status.

        Returns:
            Dict with plugin id and status string.
        """
        return {"plugin": self.metadata.id, "status": self.metadata.status}


_GLOBAL_REGISTRY: dict[str, Plugin] = {}


def register(plugin: Plugin) -> Plugin:
    """Register a plugin in the global registry.

    Args:
        plugin: The plugin instance to register.

    Returns:
        The same plugin instance, for use as a decorator.
    """
    _GLOBAL_REGISTRY[plugin.metadata.id] = plugin
    return plugin


def registered_plugins() -> dict[str, Plugin]:
    """Return a copy of the global plugin registry.

    Returns:
        Dict mapping plugin IDs to plugin instances.
    """
    return dict(_GLOBAL_REGISTRY)
