"""Tests for the Nexus plugin system (loader, registry, and SDK).

Covers plugin discovery, registration, lifecycle management,
and the plugin SDK for building custom integrations.
"""
from __future__ import annotations

from pathlib import Path

from nexus.plugins.loader import PluginLoader
from nexus.plugins.manager import PluginManager
from nexus.plugins.sdk import BasePlugin, PluginMetadata, register, registered_plugins


def test_installs_all_builtin_plugins(hub):
    _, manager, _ = hub
    assert len(manager.list_plugins()) == 10


def test_discovers_builtin_capabilities(hub):
    _, manager, _ = hub
    assert "repos.list" in manager.discover()["github"]


def test_health_reports_plugins(hub):
    _, manager, _ = hub
    assert manager.health()["slack"]["status"] == "active"


def test_builtin_github_executes(hub):
    _, manager, _ = hub
    result = manager.get("github").execute("repos.list", {})
    assert result[0]["name"] == "nexus"


def test_builtin_filesystem_write_then_read(hub):
    _, manager, _ = hub
    fs = manager.get("filesystem")
    fs.execute("file.write", {"path": "x.txt", "content": "ok"})
    assert fs.execute("file.read", {"path": "x.txt"})["content"] == "ok"


def test_install_single_builtin():
    manager = PluginManager()
    plugin = manager.install_builtin("http")
    assert plugin.id == "http"


def test_plugin_sdk_global_registration():
    class SamplePlugin(BasePlugin):
        metadata = PluginMetadata("sample", "Sample", "desc", "1", "library", ["sample.read"])

        def execute(self, action, params):
            return {"ok": True}

    register(SamplePlugin())
    assert "sample" in registered_plugins()


def test_hot_loads_plugin_directory(tmp_path: Path):
    plugin_file = tmp_path / "external.py"
    plugin_file.write_text(
        "from nexus.plugins.sdk import BasePlugin, PluginMetadata\n"
        "class ExternalPlugin(BasePlugin):\n"
        "    metadata = PluginMetadata('external','External','desc','1','library',['external.read'])\n"
        "    def execute(self, action, params):\n"
        "        return {'external': True}\n",
        encoding="utf-8",
    )
    manager = PluginManager()
    loaded = manager.hot_load(str(tmp_path))
    assert loaded[0].id == "external"


def test_plugin_loader_returns_ids():
    plugins = PluginLoader().load_builtins()
    assert {plugin.metadata.id for plugin in plugins} >= {"github", "slack", "jira"}
