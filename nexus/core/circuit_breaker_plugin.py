from __future__ import annotations

import logging
from typing import Any

from nexus.core.circuit_breaker import CircuitBreaker
from nexus.plugins.sdk import BasePlugin

logger = logging.getLogger(__name__)


class CircuitBreakerPlugin(BasePlugin):
    """Plugin wrapper that adds circuit breaker protection to any plugin.

    Wraps an existing plugin and routes all calls through a CircuitBreaker,
    preventing cascading failures when a downstream service is unhealthy.

    Args:
        plugin: The plugin to wrap with circuit breaker protection.
        failure_threshold: Consecutive failures before opening circuit.
        recovery_timeout: Seconds to wait before trying half-open.

    Example:
        >>> http_plugin = HttpPlugin()
        >>> protected = CircuitBreakerPlugin(http_plugin, failure_threshold=3, recovery_timeout=30)
        >>> result = protected.execute("fetch", {"url": "https://example.com"})
    """

    def __init__(
        self,
        plugin: BasePlugin,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._plugin = plugin
        self._breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        # Copy metadata from wrapped plugin
        self._metadata = plugin.metadata

    @property
    def metadata(self) -> Any:
        """Return the wrapped plugin's metadata."""
        return self._metadata

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Access the underlying circuit breaker for monitoring/reset."""
        return self._breaker

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute an action through the circuit breaker.

        Args:
            action: The action to execute.
            params: Parameters for the action.

        Returns:
            The result from the wrapped plugin.

        Raises:
            RuntimeError: If the circuit breaker is open.
            Exception: Any exception from the wrapped plugin.
        """
        return self._breaker.call(self._plugin.execute, action, params)

    async def aexecute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute an action asynchronously through the circuit breaker.

        Args:
            action: The action to execute.
            params: Parameters for the action.

        Returns:
            The result from the wrapped plugin.

        Raises:
            RuntimeError: If the circuit breaker is open.
            Exception: Any exception from the wrapped plugin.
        """
        return await self._breaker.acall(self._plugin.aexecute, action, params)

    def __repr__(self) -> str:
        return (
            f"CircuitBreakerPlugin(plugin={self._plugin!r}, "
            f"state={self._breaker.state.value})"
        )
