from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class HTTPPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="http",
        name="HTTP",
        description="Generic REST API caller.",
        version="1.0.0",
        plugin_type="api",
        capabilities=["request.get", "request.post", "request.put", "request.delete"],
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        if action.startswith("request."):
            return {
                "method": action.split(".", 1)[1].upper(),
                "url": params.get("url", "https://example.test"),
                "status_code": 200,
                "json": params.get("json", {}),
            }
        raise ValueError(f"Unsupported HTTP action: {action}")
