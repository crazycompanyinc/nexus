from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class DockerPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="docker",
        name="Docker",
        description="Containers, images, and compose.",
        version="1.0.0",
        plugin_type="cli",
        capabilities=["containers.list", "images.list", "compose.up", "compose.down"],
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        if action == "containers.list":
            return [{"name": "nexus-api", "status": "running"}]
        if action == "images.list":
            return [{"repository": "nexus", "tag": "latest"}]
        if action == "compose.up":
            return {"project": params.get("project", "nexus"), "started": True}
        if action == "compose.down":
            return {"project": params.get("project", "nexus"), "stopped": True}
        raise ValueError(f"Unsupported Docker action: {action}")
