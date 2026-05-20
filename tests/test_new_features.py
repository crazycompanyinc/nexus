from __future__ import annotations

import asyncio
import logging
import time

import pytest

from nexus.core.circuit_breaker import CircuitBreaker, CircuitState
from nexus.core.logging_config import (
    CorrelationFilter,
    configure_logging,
    get_correlation_id,
    set_correlation_id,
)


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_successful_call(self):
        cb = CircuitBreaker()
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb._failure_count == 0

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

    def test_raises_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
            cb.call(lambda: 42)

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_reopens_on_failure_in_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("still failing")))

        assert cb.state == CircuitState.OPEN

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_repr(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        r = repr(cb)
        assert "closed" in r
        assert "0/5" in r
        assert "30.0s" in r


class TestAsyncUnifiedToolAPI:
    def test_async_call_success(self):
        from nexus.api.async_unified import AsyncUnifiedToolAPI
        from nexus.core.db import NexusStore
        from nexus.plugins.manager import PluginManager
        from nexus.plugins.sdk import BasePlugin, PluginMetadata, register

        store = NexusStore()
        pm = PluginManager(store)

        class FakePlugin(BasePlugin):
            metadata = PluginMetadata(
                id="fake", name="Fake", description="Test",
                version="1.0", plugin_type="library", capabilities=["ping"],
            )

            def execute(self, action, params):
                return {"pong": True}

        plugin = FakePlugin()
        pm.register(plugin)
        api = AsyncUnifiedToolAPI(store, pm)
        api.grant("agent", "fake", "read")

        result = asyncio.run(api.call("agent", "fake", "ping"))
        assert result == {"pong": True}

    def test_async_call_permission_denied(self):
        from nexus.api.async_unified import AsyncUnifiedToolAPI
        from nexus.core.db import NexusStore
        from nexus.plugins.manager import PluginManager
        from nexus.plugins.sdk import BasePlugin, PluginMetadata

        store = NexusStore()
        pm = PluginManager(store)

        class FakePlugin(BasePlugin):
            metadata = PluginMetadata(
                id="fake2", name="Fake2", description="Test",
                version="1.0", plugin_type="library", capabilities=["ping"],
            )

            def execute(self, action, params):
                return {"pong": True}

        plugin = FakePlugin()
        pm.register(plugin)
        api = AsyncUnifiedToolAPI(store, pm)

        with pytest.raises(PermissionError):
            asyncio.run(api.call("agent", "fake2", "ping"))

    def test_async_batch_call(self):
        from nexus.api.async_unified import AsyncUnifiedToolAPI
        from nexus.core.db import NexusStore
        from nexus.plugins.manager import PluginManager
        from nexus.plugins.sdk import BasePlugin, PluginMetadata

        store = NexusStore()
        pm = PluginManager(store)

        class FakePlugin(BasePlugin):
            metadata = PluginMetadata(
                id="batch-fake", name="BatchFake", description="Test",
                version="1.0", plugin_type="library", capabilities=["echo"],
            )

            def execute(self, action, params):
                return params

        pm.register(FakePlugin())
        api = AsyncUnifiedToolAPI(store, pm)
        api.grant("agent", "batch-fake", "write")

        calls = [
            {"tool_id": "batch-fake", "action": "echo", "params": {"i": i}}
            for i in range(5)
        ]
        results = asyncio.run(api.batch_call("agent", calls))
        assert len(results) == 5
        assert all(r["success"] for r in results)
        assert [r["result"]["i"] for r in results] == list(range(5))


class TestCorrelationId:
    def test_generates_id(self):
        set_correlation_id("")
        cid = get_correlation_id()
        assert len(cid) == 12

    def test_returns_existing_id(self):
        set_correlation_id("test-12345678")
        assert get_correlation_id() == "test-12345678"

    def test_filter_adds_correlation_id(self):
        set_correlation_id("abc123def456")
        f = CorrelationFilter(component="test")
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="hello", args=(), exc_info=None,
        )
        assert f.filter(record)
        assert record.correlation_id == "abc123def456"  # type: ignore[attr-defined]
        assert record.component == "test"  # type: ignore[attr-defined]

    def test_configure_logging(self):
        configure_logging(level=logging.DEBUG, component="nexus-test")
        logger = logging.getLogger("nexus")
        assert logger.level == logging.DEBUG
