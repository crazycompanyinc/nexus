"""Tests for OMEGA Evolution v7.45 — CircuitBreaker & PluginMetadata.from_dict().

New features:
- CircuitBreaker: full test suite (state transitions, thresholds, reset, async)
- PluginMetadata.from_dict(): factory method to reconstruct from dict
- PluginMetadata.to_json(): JSON string serialization
- CLI status command: formatted health + metrics summary
"""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.core.circuit_breaker import CircuitBreaker, CircuitState
from nexus.plugins.sdk import PluginMetadata


# ── CircuitBreaker: State Transitions ───────────────────────────────────

class TestCircuitBreakerStateTransitions:
    """CircuitBreaker should transition CLOSED → OPEN → HALF_OPEN → CLOSED."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.CLOSED  # not yet at threshold
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN  # now at threshold

    def test_raises_runtime_error_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        with pytest.raises(RuntimeError, match="OPEN"):
            cb.call(lambda: "should not run")

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail again")))
        assert cb.state == CircuitState.OPEN


# ── CircuitBreaker: Reset & Config ──────────────────────────────────────

class TestCircuitBreakerReset:
    """CircuitBreaker.reset() should restore to initial state."""

    def test_reset_clears_all_state(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0
        assert cb._success_count == 0

    def test_reset_allows_calls_again(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        with pytest.raises(RuntimeError):
            cb.call(lambda: "blocked")
        cb.reset()
        result = cb.call(lambda: "works")
        assert result == "works"

    def test_invalid_failure_threshold(self):
        with pytest.raises(ValueError, match="failure_threshold"):
            CircuitBreaker(failure_threshold=0)

    def test_invalid_recovery_timeout(self):
        with pytest.raises(ValueError, match="recovery_timeout"):
            CircuitBreaker(recovery_timeout=-1.0)


# ── CircuitBreaker: Async ───────────────────────────────────────────────

class TestCircuitBreakerAsync:
    """CircuitBreaker.acall() should work identically for async functions."""

    def test_async_success(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        async_fn = AsyncMock(return_value="async result")
        result = asyncio.run(cb.acall(async_fn))
        assert result == "async result"

    def test_async_failure_opens_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        async_fn = AsyncMock(side_effect=RuntimeError("async fail"))
        with pytest.raises(RuntimeError, match="async fail"):
            asyncio.run(cb.acall(async_fn))
        assert cb.state == CircuitState.OPEN

    def test_async_blocked_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        async_fn = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            asyncio.run(cb.acall(async_fn))
        with pytest.raises(RuntimeError, match="OPEN"):
            asyncio.run(cb.acall(AsyncMock(return_value="nope")))


# ── CircuitBreaker: Repr ────────────────────────────────────────────────

class TestCircuitBreakerRepr:
    """CircuitBreaker.__repr__ should show state, failures, and timeout."""

    def test_repr_closed(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        r = repr(cb)
        assert "closed" in r
        assert "0/5" in r
        assert "30.0s" in r

    def test_repr_after_failures(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        r = repr(cb)
        assert "1/5" in r


# ── PluginMetadata.from_dict() ──────────────────────────────────────────

class TestPluginMetadataFromDict:
    """PluginMetadata.from_dict() should reconstruct from a dict."""

    def test_from_dict_basic(self):
        data = {
            "id": "test-plugin",
            "name": "Test Plugin",
            "description": "A test",
            "version": "1.0.0",
            "plugin_type": "api",
            "capabilities": ["read"],
        }
        meta = PluginMetadata.from_dict(data)
        assert meta.id == "test-plugin"
        assert meta.name == "Test Plugin"
        assert meta.capabilities == ["read"]

    def test_from_dict_all_fields(self):
        data = {
            "id": "full",
            "name": "Full",
            "description": "All fields",
            "version": "2.0.0",
            "plugin_type": "cli",
            "capabilities": ["read", "write"],
            "endpoint": "https://example.com",
            "auth_required": True,
            "auth_type": "bearer",
            "config_schema": {"type": "object"},
            "health_check_endpoint": "/health",
            "status": "inactive",
        }
        meta = PluginMetadata.from_dict(data)
        assert meta.endpoint == "https://example.com"
        assert meta.auth_required is True
        assert meta.auth_type == "bearer"
        assert meta.config_schema == {"type": "object"}
        assert meta.health_check_endpoint == "/health"
        assert meta.status == "inactive"

    def test_from_dict_defaults(self):
        data = {
            "id": "minimal",
            "name": "Min",
            "description": "d",
            "version": "0.1.0",
            "plugin_type": "library",
            "capabilities": [],
        }
        meta = PluginMetadata.from_dict(data)
        assert meta.endpoint is None
        assert meta.auth_required is False
        assert meta.auth_type is None
        assert meta.config_schema == {}
        assert meta.health_check_endpoint is None
        assert meta.status == "active"

    def test_from_dict_roundtrip(self):
        original = PluginMetadata(
            id="roundtrip",
            name="RT",
            description="round trip test",
            version="3.0.0",
            plugin_type="api",
            capabilities=["read", "write"],
            endpoint="https://rt.com",
            auth_required=True,
            auth_type="basic",
            config_schema={"key": "val"},
            health_check_endpoint="/status",
            status="active",
        )
        data = original.to_dict()
        restored = PluginMetadata.from_dict(data)
        assert original == restored
        assert hash(original) == hash(restored)


# ── PluginMetadata.to_json() ────────────────────────────────────────────

class TestPluginMetadataToJson:
    """PluginMetadata.to_json() should return a JSON string."""

    def test_to_json_returns_string(self):
        meta = PluginMetadata(
            id="json-test", name="JSON", description="test",
            version="1.0.0", plugin_type="api", capabilities=["read"],
        )
        result = meta.to_json()
        assert isinstance(result, str)

    def test_to_json_is_valid_json(self):
        meta = PluginMetadata(
            id="json-test", name="JSON", description="test",
            version="1.0.0", plugin_type="api", capabilities=["read"],
        )
        parsed = json.loads(meta.to_json())
        assert parsed["id"] == "json-test"
        assert parsed["name"] == "JSON"

    def test_to_json_roundtrip(self):
        original = PluginMetadata(
            id="rt", name="RT", description="d",
            version="1.0.0", plugin_type="api", capabilities=["read"],
        )
        json_str = original.to_json()
        data = json.loads(json_str)
        restored = PluginMetadata.from_dict(data)
        assert original == restored
