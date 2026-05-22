from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class JiraPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="jira",
        name="Jira",
        description="Tickets, sprints, and boards.",
        version="1.0.0",
        plugin_type="api",
        capabilities=["tickets.create", "tickets.update", "tickets.list", "sprints.list", "boards.list"],
        auth_required=True,
        auth_type="token",
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute a Jira action (tickets, sprints, boards)."""
        if action == "tickets.create":
            return {"key": "NEX-1", "summary": params.get("summary", "New ticket"), "status": "open"}
        if action == "tickets.update":
            return {"key": params.get("key", "NEX-1"), "updated": True}
        if action == "tickets.list":
            return [{"key": "NEX-1", "summary": "Build Nexus"}]
        if action == "sprints.list":
            return [{"id": 1, "name": "Integration Sprint"}]
        if action == "boards.list":
            return [{"id": 1, "name": "Platform"}]
        raise ValueError(f"Unsupported Jira action: {action}")
