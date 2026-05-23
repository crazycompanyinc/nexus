from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class DockerPlugin(BasePlugin):
    """Docker plugin for container and image management.

    Provides operations for listing containers and images, as well as
    Docker Compose up/down orchestration. No authentication required.

    Capabilities: containers.list, images.list, compose.up, compose.down.
    """
    metadata = PluginMetadata(
        id="docker",
        name="Docker",
        description="Containers, images, and compose.",
        version="1.0.0",
        plugin_type="cli",
        capabilities=["containers.list", "images.list", "compose.up", "compose.down"],
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute a Docker action (containers.list, images.list, compose.up, compose.down)."""
        if action == "containers.list":
            return [{"name": "nexus-api", "status": "running"}]
        if action == "images.list":
            return [{"repository": "nexus", "tag": "latest"}]
        if action == "compose.up":
            return {"project": params.get("project", "nexus"), "started": True}
        if action == "compose.down":
            return {"project": params.get("project", "nexus"), "stopped": True}
        raise ValueError(f"Unsupported Docker action: {action}")
