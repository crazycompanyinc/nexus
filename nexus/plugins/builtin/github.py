from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class GitHubPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="github",
        name="GitHub",
        description="Repositories, pull requests, issues, and CI status.",
        version="1.0.0",
        plugin_type="api",
        capabilities=["repos.list", "prs.list", "issues.list", "ci.status", "prs.create"],
        endpoint="https://api.github.com",
        auth_required=True,
        auth_type="token",
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        if action == "repos.list":
            return [{"name": "nexus", "private": False}, {"name": "agent-lab", "private": True}]
        if action == "prs.list":
            return [{"id": 101, "title": "Add universal tool adapter", "status": "open"}]
        if action == "issues.list":
            return [{"id": 7, "title": "Permission audit export", "status": "open"}]
        if action == "ci.status":
            return {"sha": params.get("sha", "HEAD"), "state": "success"}
        if action == "prs.create":
            return {"id": 202, "title": params.get("title", "Untitled PR"), "status": "open"}
        raise ValueError(f"Unsupported GitHub action: {action}")
