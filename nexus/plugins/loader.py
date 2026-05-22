from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Iterable

from nexus.plugins.sdk import BasePlugin, Plugin


class PluginLoader:
    BUILTIN_MODULES = [
        "nexus.plugins.builtin.github",
        "nexus.plugins.builtin.slack",
        "nexus.plugins.builtin.jira",
        "nexus.plugins.builtin.aws",
        "nexus.plugins.builtin.database",
        "nexus.plugins.builtin.email",
        "nexus.plugins.builtin.http",
        "nexus.plugins.builtin.filesystem",
        "nexus.plugins.builtin.docker",
        "nexus.plugins.builtin.kubernetes",
    ]

    def load_builtins(self) -> list[Plugin]:
        """Load all built-in plugins from the predefined BUILTIN_MODULES list.

        Returns:
            List of Plugin instances discovered across all built-in modules.
        """
        plugins: list[Plugin] = []
        for module_name in self.BUILTIN_MODULES:
            module = importlib.import_module(module_name)
            plugins.extend(self._plugins_from_module(module))
        return plugins

    def load_module(self, module_name: str) -> list[Plugin]:
        """Load plugins from a single Python module by name.

        Args:
            module_name: Fully qualified module name to import.

        Returns:
            List of Plugin instances found in the module.
        """
        module = importlib.import_module(module_name)
        return self._plugins_from_module(module)

    def load_directory(self, directory: str | Path, *, recursive: bool = True) -> list[Plugin]:
        """Load plugins from all Python files in a directory.

        Args:
            directory: Path to the directory to scan for plugin files.
            recursive: If True, scan subdirectories recursively.

        Returns:
            List of Plugin instances discovered across all files.
        """
        directory = Path(directory)
        plugins: list[Plugin] = []
        pattern = "**/*.py" if recursive else "*.py"
        for path in sorted(directory.glob(pattern)):
            if path.name.startswith("_"):
                continue
            spec_name = f"nexus_hot_{path.stem}"
            loader = importlib.machinery.SourceFileLoader(spec_name, str(path))
            module = importlib.util.module_from_spec(importlib.util.spec_from_loader(spec_name, loader))
            loader.exec_module(module)
            plugins.extend(self._plugins_from_module(module))
        return plugins

    def _plugins_from_module(self, module: object) -> list[Plugin]:
        if hasattr(module, "plugin"):
            return [module.plugin()]
        discovered: list[Plugin] = []
        for _, value in inspect.getmembers(module, inspect.isclass):
            if value is BasePlugin or not issubclass(value, BasePlugin):
                continue
            discovered.append(value())
        return discovered


def plugin_ids(plugins: Iterable[Plugin]) -> list[str]:
    """Extract metadata IDs from an iterable of plugins.

    Args:
        plugins: Plugin instances to extract IDs from.

    Returns:
        List of plugin ID strings.
    """
    return [plugin.metadata.id for plugin in plugins]
