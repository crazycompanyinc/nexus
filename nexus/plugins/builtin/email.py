from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class EmailPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="email",
        name="Email",
        description="Send, receive, and search email.",
        version="1.0.0",
        plugin_type="api",
        capabilities=["email.send", "email.receive", "email.search"],
        auth_required=True,
        auth_type="smtp",
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute an email action (email.send, email.receive, email.search)."""
        if action == "email.send":
            return {"sent": True, "to": params.get("to"), "subject": params.get("subject", "")}
        if action == "email.receive":
            return [{"from": "ops@example.com", "subject": "Deploy complete"}]
        if action == "email.search":
            return [{"subject": params.get("query", "nexus"), "matched": True}]
        raise ValueError(f"Unsupported email action: {action}")
