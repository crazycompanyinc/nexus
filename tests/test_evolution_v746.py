#!/usr/bin/env python3
"""Tests for v7.46 evolution: ToolPlugin.from_dict, PluginMetadata.from_model, Registry.find_by_capability."""

from __future__ import annotations

import pytest

from nexus.core.models import ToolPlugin, PluginStatus, PluginType
from nexus.plugins.sdk import PluginMetadata, BasePlugin, Plugin
from nexus.plugins.registry import PluginRegistry


# ---------------------------------------------------------------------------
# ToolPlugin.from_dict()
# ---------------------------------------------------------------------------

class TestToolPluginFromDict:
    """Tests for ToolPlugin.from_dict() deserialization."""

    def test_basic_roundtrip(self):
        """from_dict(to_dict()) should produce an equivalent object."""
        original = ToolPlugin(
            id="test-plugin",
            name="Test Plugin",
            description="A test plugin",
            version="1.2.0",
            plugin_type=PluginType.API.value,
            capabilities=["read", "write"],
            endpoint="https://api.example.com",
            auth_required=True,
            auth_type="bearer",
            config_schema={"url": {"type": "string"}},
            health_check_endpoint="/health",
            status=PluginStatus.ACTIVE.value,
        )
        data = original.to_dict()
        restored = ToolPlugin.from_dict(data)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.version == original.version
        assert restored.plugin_type == original.plugin_type
        assert restored.capabilities == original.capabilities
        assert restored.endpoint == original.endpoint
        assert restored.auth_required == original.auth_required
        assert restored.auth_type == original.auth_type
        assert restored.config_schema == original.config_schema
        assert restored.health_check_endpoint == original.health_check_endpoint
        assert restored.status == original.status

    def test_minimal_fields(self):
        """from_dict works with only required fields."""
        data = {
            "id": "minimal",
            "name": "Minimal",
            "description": "Minimal plugin",
            "version": "0.1.0",
            "plugin_type": "library",
            "capabilities": [],
        }
        plugin = ToolPlugin.from_dict(data)
        assert plugin.id == "minimal"
        assert plugin.endpoint is None
        assert plugin.auth_required is False
        assert plugin.auth_type is None
        assert plugin.config_schema == {}
        assert plugin.health_check_endpoint is None
        assert plugin.status == PluginStatus.ACTIVE.value

    def test_extra_keys_ignored(self):
        """from_dict silently ignores extra keys for forward compatibility."""
        data = {
            "id": "extra",
            "name": "Extra",
            "description": "Has extra fields",
            "version": "1.0.0",
            "plugin_type": "api",
            "capabilities": [],
            "future_field": "should be ignored",
            "another_new_thing": 42,
        }
        plugin = ToolPlugin.from_dict(data)
        assert plugin.id == "extra"

    def test_capabilities_are_copied(self):
        """from_dict copies the capabilities list, not references."""
        caps = ["read", "write"]
        data = {
            "id": "copy-test",
            "name": "Copy Test",
            "description": "Test cap copy",
            "version": "1.0.0",
            "plugin_type": "api",
            "capabilities": caps,
        }
        plugin = ToolPlugin.from_dict(data)
        caps.append("admin")
        assert "admin" not in plugin.capabilities

    def test_config_schema_copied(self):
        """from_dict copies config_schema dict."""
        schema = {"key": "value"}
        data = {
            "id": "schema-test",
            "name": "Schema Test",
            "description": "Test schema copy",
            "version": "1.0.0",
            "plugin_type": "api",
            "capabilities": [],
            "config_schema": schema,
        }
        plugin = ToolPlugin.from_dict(data)
        schema["new_key"] = "new_value"
        assert "new_key" not in plugin.config_schema


# ---------------------------------------------------------------------------
# PluginMetadata.from_model()
# ---------------------------------------------------------------------------

class TestPluginMetadataFromModel:
    """Tests for PluginMetadata.from_model() deserialization."""

    def test_basic_roundtrip(self):
        """from_model(to_model()) should produce equivalent metadata."""
        original = PluginMetadata(
            id="roundtrip",
            name="Roundtrip",
            description="Test roundtrip",
            version="2.0.0",
            plugin_type="service",
            capabilities=["read", "write", "delete"],
            endpoint="https://svc.example.com",
            auth_required=True,
            auth_type="api_key",
            config_schema={"timeout": {"type": "integer"}},
            health_check_endpoint="/status",
            status="active",
        )
        model = original.to_model()
        restored = PluginMetadata.from_model(model)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.version == original.version
        assert restored.plugin_type == original.plugin_type
        assert restored.capabilities == original.capabilities
        assert restored.endpoint == original.endpoint
        assert restored.auth_required == original.auth_required
        assert restored.auth_type == original.auth_type
        assert restored.config_schema == original.config_schema
        assert restored.health_check_endpoint == original.health_check_endpoint
        assert restored.status == original.status

    def test_minimal_model(self):
        """from_model works with a minimal ToolPlugin."""
        model = ToolPlugin(
            id="min",
            name="Min",
            description="Minimal",
            version="0.0.1",
            plugin_type="library",
            capabilities=[],
        )
        meta = PluginMetadata.from_model(model)
        assert meta.id == "min"
        assert meta.endpoint is None
        assert meta.auth_required is False
        assert meta.config_schema == {}
        assert meta.status == "active"

    def test_capabilities_copied(self):
        """from_model copies capabilities list."""
        caps = ["read"]
        model = ToolPlugin(
            id="cap-copy",
            name="Cap Copy",
            description="Test",
            version="1.0.0",
            plugin_type="api",
            capabilities=caps,
        )
        meta = PluginMetadata.from_model(model)
        caps.append("write")
        assert "write" not in meta.capabilities


# ---------------------------------------------------------------------------
# PluginRegistry.find_by_capability()
# ---------------------------------------------------------------------------

class _FakePlugin(BasePlugin):
    """Minimal concrete plugin for testing."""

    def __init__(self, plugin_id: str, caps: list[str]) -> None:
        self._meta = PluginMetadata(
            id=plugin_id,
            name=plugin_id,
            description=f"Plugin {plugin_id}",
            version="1.0.0",
            plugin_type="api",
            capabilities=caps,
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def execute(self, action: str, params: dict) -> object:
        return None


class TestRegistryFindByCapability:
    """Tests for PluginRegistry.find_by_capability()."""

    def setup_method(self) -> None:
        self.registry = PluginRegistry()

    def test_find_single_match(self):
        """Returns only plugins matching the capability."""
        p1 = _FakePlugin("reader", ["read"])
        p2 = _FakePlugin("writer", ["write"])
        self.registry.register(p1)
        self.registry.register(p2)
        results = self.registry.find_by_capability("read")
        assert len(results) == 1
        assert results[0].metadata.id == "reader"

    def test_find_multiple_matches(self):
        """Returns all plugins matching the capability."""
        p1 = _FakePlugin("multi-a", ["read", "write"])
        p2 = _FakePlugin("multi-b", ["read", "delete"])
        p3 = _FakePlugin("other", ["write"])
        self.registry.register(p1)
        self.registry.register(p2)
        self.registry.register(p3)
        results = self.registry.find_by_capability("read")
        ids = {p.metadata.id for p in results}
        assert ids == {"multi-a", "multi-b"}

    def test_no_match(self):
        """Returns empty list when no plugin matches."""
        p = _FakePlugin("only-write", ["write"])
        self.registry.register(p)
        assert self.registry.find_by_capability("read") == []

    def test_empty_registry(self):
        """Returns empty list on empty registry."""
        assert self.registry.find_by_capability("read") == []

    def test_wildcard_matches_all(self):
        """Plugins with '*' capability match any query."""
        p = _FakePlugin("wildcard", ["*"])
        self.registry.register(p)
        assert len(self.registry.find_by_capability("read")) == 1
        assert len(self.registry.find_by_capability("write")) == 1
        assert len(self.registry.find_by_capability("anything")) == 1

    def test_does_not_mutate_registry(self):
        """find_by_capability does not modify the registry."""
        p = _FakePlugin("stable", ["read"])
        self.registry.register(p)
        self.registry.find_by_capability("read")
        assert len(self.registry.list()) == 1
