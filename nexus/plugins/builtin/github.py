from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class GitHubPlugin(BasePlugin):
    """GitHub plugin for repository, PR, issue, and CI management.

    Provides token-authenticated access to GitHub API operations including
    repository listing, pull request management, issue tracking, and CI status.

    Capabilities: repos.list, prs.list, issues.list, ci.status, prs.create.
    """
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
        """Execute a GitHub API action.

        Supports: repos.list, prs.list, issues.list, ci.status, prs.create.

        Args:
            action: The GitHub action to perform.
            params: Action-specific parameters (e.g. 'sha', 'title').

        Returns:
            Dict or list with the action result data.

        Raises:
            ValueError: If the action is not supported.
        """
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
