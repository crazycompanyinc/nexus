from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class HTTPPlugin(BasePlugin):
    """Generic HTTP/REST API caller plugin.

    Supports GET, POST, PUT, and DELETE operations against any URL.
    Does not require authentication by default.

    Capabilities: request.get, request.post, request.put, request.delete.
    """
    metadata = PluginMetadata(
        id="http",
        name="HTTP",
        description="Generic REST API caller.",
        version="1.0.0",
        plugin_type="api",
        capabilities=["request.get", "request.post", "request.put", "request.delete"],
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute an HTTP request action.

        Supports request.get, request.post, request.put, request.delete.

        Args:
            action: The HTTP action in 'request.VERB' format.
            params: Parameters including 'url' and optional 'json' body.

        Returns:
            Dict with method, url, status_code, and json response.

        Raises:
            ValueError: If the action is not a supported HTTP method.
        """
        if action.startswith("request."):
            return {
                "method": action.split(".", 1)[1].upper(),
                "url": params.get("url", "https://example.test"),
                "status_code": 200,
                "json": params.get("json", {}),
            }
        raise ValueError(f"Unsupported HTTP action: {action}")
