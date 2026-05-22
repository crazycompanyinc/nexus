from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class FileSystemPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="filesystem",
        name="FileSystem",
        description="Read, write, list, and watch files.",
        version="1.0.0",
        plugin_type="library",
        capabilities=["file.read", "file.write", "file.list", "file.watch"],
    )

    def __init__(self) -> None:
        self.files = {"README.md": "# Nexus\n"}

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute a filesystem action (file.read, file.write, file.list, file.watch)."""
        path = params.get("path", "README.md")
        if action == "file.read":
            return {"path": path, "content": self.files.get(path, "")}
        if action == "file.write":
            self.files[path] = params.get("content", "")
            return {"path": path, "written": True}
        if action == "file.list":
            return sorted(self.files)
        if action == "file.watch":
            return {"path": path, "watching": True}
        raise ValueError(f"Unsupported filesystem action: {action}")
