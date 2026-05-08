from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from nexus.core.models import ToolPlugin


@dataclass(slots=True)
class PluginMetadata:
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


class Plugin(Protocol):
    metadata: PluginMetadata

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        ...

    def health(self) -> dict[str, Any]:
        ...


class BasePlugin:
    metadata = PluginMetadata(
        id="base",
        name="base",
        description="Base Nexus plugin",
        version="0.0.0",
        plugin_type="library",
        capabilities=[],
    )

    def get_capabilities(self) -> list[str]:
        return list(self.metadata.capabilities)

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        raise NotImplementedError(f"{self.metadata.id} does not implement {action}")

    def health(self) -> dict[str, Any]:
        return {"plugin": self.metadata.id, "status": self.metadata.status}


_GLOBAL_REGISTRY: dict[str, Plugin] = {}


def register(plugin: Plugin) -> Plugin:
    _GLOBAL_REGISTRY[plugin.metadata.id] = plugin
    return plugin


def registered_plugins() -> dict[str, Plugin]:
    return dict(_GLOBAL_REGISTRY)
