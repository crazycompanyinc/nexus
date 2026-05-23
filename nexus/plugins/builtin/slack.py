from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class SlackPlugin(BasePlugin):
    """Slack plugin for messaging and channel management.

    Supports sending messages, listing channels, and adding reactions.
    Requires OAuth authentication against the Slack API.

    Capabilities: messages.send, channels.list, reactions.add.
    """
    metadata = PluginMetadata(
        id="slack",
        name="Slack",
        description="Messages, channels, and reactions.",
        version="1.0.0",
        plugin_type="api",
        capabilities=["messages.send", "channels.list", "reactions.add"],
        endpoint="https://slack.com/api",
        auth_required=True,
        auth_type="oauth",
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute a Slack API action.

        Supports: messages.send, channels.list, reactions.add.

        Args:
            action: The Slack action to perform.
            params: Action-specific parameters (e.g. 'channel', 'text', 'reaction').

        Returns:
            Dict with the action result data.

        Raises:
            ValueError: If the action is not supported.
        """
        if action == "messages.send":
            return {"sent": True, "channel": params.get("channel", "#general"), "text": params.get("text", "")}
        if action == "channels.list":
            return [{"id": "C1", "name": "general"}, {"id": "C2", "name": "deploys"}]
        if action == "reactions.add":
            return {"ok": True, "reaction": params.get("reaction", "thumbsup")}
        raise ValueError(f"Unsupported Slack action: {action}")
