from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class FileSystemPlugin(BasePlugin):
    """File system plugin providing read, write, list, and watch operations.

    An in-memory filesystem implementation for testing and development.
    Supports the file.read, file.write, file.list, and file.watch capabilities.

    Example:
        >>> plugin = FileSystemPlugin()
        >>> plugin.execute("file.read", {"path": "README.md"})
        {'path': 'README.md', 'content': '# Nexus\\n'}
    """
    metadata = PluginMetadata(
        id="filesystem",
        name="FileSystem",
        description="Read, write, list, and watch files.",
        version="1.0.0",
        plugin_type="library",
        capabilities=["file.read", "file.write", "file.list", "file.watch"],
    )

    def __init__(self) -> None:
        """Initialize the FileSystemPlugin with a default README.md file."""
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
