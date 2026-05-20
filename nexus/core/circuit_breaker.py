from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass(slots=True)
class CircuitBreaker:
    """Circuit breaker for plugin tool calls.

    Prevents cascading failures by tracking consecutive errors and
    temporarily blocking calls to a failing tool.

    Args:
        failure_threshold: Number of consecutive failures before opening circuit.
        recovery_timeout: Seconds to wait before transitioning to half-open.
        expected_exception: Exception type(s) that count as failures.

    Example:
        >>> cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        >>> result = cb.call(plugin.execute, "read", {"path": "/tmp/file"})
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    expected_exception: type[BaseException] = Exception

    _state: str = field(default=CircuitState.CLOSED.value, init=False, repr=False)
    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _success_count: int = field(default=0, init=False, repr=False)

    @property
    def state(self) -> CircuitState:
        """Current circuit state, auto-transitioning from OPEN to HALF_OPEN when timeout expires."""
        if self._state == CircuitState.OPEN.value:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                logger.info("Circuit breaker transitioning to HALF_OPEN (timeout expired)")
                self._state = CircuitState.HALF_OPEN.value
        return CircuitState(self._state)

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a function through the circuit breaker.

        Args:
            fn: The function to call.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function call.

        Raises:
            RuntimeError: If the circuit is open.
            Exception: Any exception raised by the function.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise RuntimeError(
                f"Circuit breaker is OPEN — tool temporarily disabled. "
                f"Retry after {self.recovery_timeout}s. "
                f"Consecutive failures: {self._failure_count}"
            )

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as exc:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN.value:
            logger.info("Circuit breaker CLOSED — tool recovered")
            self._state = CircuitState.CLOSED.value
        self._failure_count = 0
        self._success_count += 1

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN.value:
                logger.warning(
                    "Circuit breaker OPEN after %d consecutive failures (threshold=%d)",
                    self._failure_count,
                    self.failure_threshold,
                )
            self._state = CircuitState.OPEN.value

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED.value
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self.state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold}, "
            f"recovery={self.recovery_timeout}s)"
        )
