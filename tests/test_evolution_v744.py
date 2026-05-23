"""Tests for OMEGA Evolution v7.44 — PluginMetadata improvements & BasePlugin ABC.

New features:
- PluginMetadata.to_dict() for JSON serialization
- PluginMetadata.__eq__ for identity comparison by id
- PluginMetadata.__hash__ for use in sets/dicts
- BasePlugin is now ABC — cannot be instantiated directly
- BasePlugin.execute is @abstractmethod — subclasses must implement
"""
from __future__ import annotations

import pytest

from nexus.plugins.sdk import BasePlugin, PluginMetadata


# ── PluginMetadata.to_dict() ───────────────────────────────────────────

class TestPluginMetadataToDict:
    """PluginMetadata.to_dict() should return a JSON-serializable dict."""

    def test_to_dict_returns_dict(self):
        meta = PluginMetadata(
            id="test-plugin",
            name="Test Plugin",
            description="A test plugin",
            version="1.0.0",
            plugin_type="api",
            capabilities=["read", "write"],
        )
        result = meta.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_has_all_fields(self):
        meta = PluginMetadata(
            id="test-plugin",
            name="Test Plugin",
            description="A test plugin",
            version="1.0.0",
            plugin_type="api",
            capabilities=["read", "write"],
            endpoint="https://example.com",
            auth_required=True,
            auth_type="bearer",
            config_schema={"type": "object"},
            health_check_endpoint="/health",
            status="active",
        )
        result = meta.to_dict()
        assert result["id"] == "test-plugin"
        assert result["name"] == "Test Plugin"
        assert result["description"] == "A test plugin"
        assert result["version"] == "1.0.0"
        assert result["plugin_type"] == "api"
        assert result["capabilities"] == ["read", "write"]
        assert result["endpoint"] == "https://example.com"
        assert result["auth_required"] is True
        assert result["auth_type"] == "bearer"
        assert result["config_schema"] == {"type": "object"}
        assert result["health_check_endpoint"] == "/health"
        assert result["status"] == "active"

    def test_to_dict_capabilities_are_copy(self):
        meta = PluginMetadata(
            id="test", name="Test", description="d", version="1.0.0",
            plugin_type="api", capabilities=["read"],
        )
        result = meta.to_dict()
        result["capabilities"].append("write")
        assert meta.capabilities == ["read"]  # original unchanged

    def test_to_dict_config_schema_is_copy(self):
        meta = PluginMetadata(
            id="test", name="Test", description="d", version="1.0.0",
            plugin_type="api", capabilities=[], config_schema={"key": "val"},
        )
        result = meta.to_dict()
        result["config_schema"]["new_key"] = "new_val"
        assert "new_key" not in meta.config_schema


# ── PluginMetadata.__eq__ ──────────────────────────────────────────────

class TestPluginMetadataEquality:
    """PluginMetadata equality is based on id field."""

    def test_same_id_equal(self):
        a = PluginMetadata(
            id="plugin-x", name="A", description="d", version="1.0.0",
            plugin_type="api", capabilities=["read"],
        )
        b = PluginMetadata(
            id="plugin-x", name="B", description="different", version="2.0.0",
            plugin_type="cli", capabilities=["write"],
        )
        assert a == b

    def test_different_id_not_equal(self):
        a = PluginMetadata(
            id="plugin-a", name="Same", description="d", version="1.0.0",
            plugin_type="api", capabilities=[],
        )
        b = PluginMetadata(
            id="plugin-b", name="Same", description="d", version="1.0.0",
            plugin_type="api", capabilities=[],
        )
        assert a != b

    def test_not_equal_to_non_metadata(self):
        meta = PluginMetadata(
            id="test", name="Test", description="d", version="1.0.0",
            plugin_type="api", capabilities=[],
        )
        assert meta != "test"
        assert meta != 42
        assert meta != None


# ── PluginMetadata.__hash__ ────────────────────────────────────────────

class TestPluginMetadataHash:
    """PluginMetadata is hashable and can be used in sets and dicts."""

    def test_hash_is_int(self):
        meta = PluginMetadata(
            id="test", name="Test", description="d", version="1.0.0",
            plugin_type="api", capabilities=[],
        )
        assert isinstance(hash(meta), int)

    def test_same_id_same_hash(self):
        a = PluginMetadata(
            id="plugin-x", name="A", description="d", version="1.0.0",
            plugin_type="api", capabilities=["read"],
        )
        b = PluginMetadata(
            id="plugin-x", name="B", description="different", version="2.0.0",
            plugin_type="cli", capabilities=["write"],
        )
        assert hash(a) == hash(b)

    def test_can_add_to_set(self):
        a = PluginMetadata(
            id="plugin-a", name="A", description="d", version="1.0.0",
            plugin_type="api", capabilities=[],
        )
        b = PluginMetadata(
            id="plugin-b", name="B", description="d", version="1.0.0",
            plugin_type="api", capabilities=[],
        )
        s = {a, b}
        assert len(s) == 2

    def test_duplicate_ids_deduplicated_in_set(self):
        a = PluginMetadata(
            id="plugin-x", name="A", description="d", version="1.0.0",
            plugin_type="api", capabilities=["read"],
        )
        b = PluginMetadata(
            id="plugin-x", name="B", description="different", version="2.0.0",
            plugin_type="cli", capabilities=["write"],
        )
        s = {a, b}
        assert len(s) == 1

    def test_can_use_as_dict_key(self):
        meta = PluginMetadata(
            id="test", name="Test", description="d", version="1.0.0",
            plugin_type="api", capabilities=[],
        )
        d = {meta: "value"}
        assert d[meta] == "value"


# ── BasePlugin ABC Enforcement ─────────────────────────────────────────

class TestBasePluginABC:
    """BasePlugin should be abstract and not instantiable directly."""

    def test_cannot_instantiate_base_plugin(self):
        with pytest.raises(TypeError, match="abstract"):
            BasePlugin()

    def test_can_instantiate_subclass_with_execute(self):
        class MyPlugin(BasePlugin):
            metadata = PluginMetadata(
                id="my-plugin", name="My Plugin", description="d",
                version="1.0.0", plugin_type="library", capabilities=["ping"],
            )

            def execute(self, action: str, params: dict) -> str:
                return f"{action} ok"

        plugin = MyPlugin()
        assert plugin.metadata.id == "my-plugin"
        assert plugin.execute("ping", {}) == "ping ok"

    def test_subclass_without_execute_cannot_be_instantiated(self):
        class IncompletePlugin(BasePlugin):
            metadata = PluginMetadata(
                id="bad", name="Bad", description="d",
                version="1.0.0", plugin_type="library", capabilities=[],
            )
            # Missing execute() — should fail

        with pytest.raises(TypeError, match="abstract"):
            IncompletePlugin()

    def test_subclass_inherits_health(self):
        class MyPlugin(BasePlugin):
            metadata = PluginMetadata(
                id="my-plugin", name="My Plugin", description="d",
                version="1.0.0", plugin_type="library", capabilities=[],
            )

            def execute(self, action: str, params: dict) -> str:
                return "ok"

        plugin = MyPlugin()
        health = plugin.health()
        assert health["plugin"] == "my-plugin"
        assert health["status"] == "active"

    def test_subclass_inherits_get_capabilities(self):
        class MyPlugin(BasePlugin):
            metadata = PluginMetadata(
                id="my-plugin", name="My Plugin", description="d",
                version="1.0.0", plugin_type="library",
                capabilities=["read", "write"],
            )

            def execute(self, action: str, params: dict) -> str:
                return "ok"

        plugin = MyPlugin()
        assert plugin.get_capabilities() == ["read", "write"]
