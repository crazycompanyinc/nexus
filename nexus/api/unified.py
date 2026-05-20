from __future__ import annotations

import logging
from time import perf_counter, sleep
from typing import Any

from nexus.core.db import NexusStore
from nexus.core.models import CallStatus, ToolCall
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


class UnifiedToolAPI:
    """Unified API surface for agent tool calls with retry, fallback, and access control.

    Provides a single entry point for agents to invoke tools with:
    - Permission checking via AccessControl
    - Automatic retry with exponential backoff
    - Fallback tool chaining
    - Call recording and metrics via NexusStore

    Example:
        >>> api = UnifiedToolAPI()
        >>> api.grant("agent-1", "http", "write")
        >>> result = api.call("agent-1", "http", "fetch", {"url": "https://example.com"})
    """

    def __init__(
        self,
        store: NexusStore | None = None,
        plugin_manager: PluginManager | None = None,
        access_control: AccessControl | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 0.1,
    ) -> None:
        """Initialize the UnifiedToolAPI.

        Args:
            store: NexusStore instance for persistence. Creates default if None.
            plugin_manager: PluginManager instance. Creates default if None.
            access_control: AccessControl instance. Creates default if None.
            max_retries: Maximum retry attempts per tool candidate (>= 0).
            retry_base_delay: Base delay in seconds for exponential backoff (>= 0.0).
        """
        self.store = store or NexusStore()
        self.plugins = plugin_manager or PluginManager(self.store)
        self.access = access_control or AccessControl(self.store)
        self.max_retries = max(max_retries, 0)
        self.retry_base_delay = max(retry_base_delay, 0.0)

    def call(
        self,
        agent_id: str,
        tool_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        fallback_tools: list[str] | None = None,
    ) -> Any:
        """Execute a tool call with retry and fallback support.

        Attempts the primary tool first, then falls back to fallback_tools in order.
        Each candidate is retried up to max_retries times with exponential backoff.
        Permission errors are raised immediately without retry.

        Args:
            agent_id: Unique identifier for the calling agent.
            tool_id: Primary tool identifier to invoke.
            action: Action name to execute on the tool.
            params: Parameters dict passed to the tool action.
            fallback_tools: Ordered list of backup tool IDs if primary fails.

        Returns:
            The result from the tool execution.

        Raises:
            PermissionError: If agent lacks permission for the tool/action.
            RuntimeError: If all candidates and retries are exhausted.
        """
        params = params or {}
        candidates = [tool_id, *(fallback_tools or [])]
        last_error: Exception | None = None
        for candidate in candidates:
            for attempt in range(self.max_retries + 1):
                try:
                    return self._call_one(agent_id, candidate, action, params)
                except PermissionError:
                    raise
                except Exception as exc:
                    last_error = exc
                    if attempt < self.max_retries:
                        delay = self.retry_base_delay * (2 ** attempt)
                        logger.warning(
                            "Retry %d/%d for %s.%s (agent=%s) after %.2fs: %s",
                            attempt + 1, self.max_retries, candidate, action, agent_id, delay, exc,
                        )
                        sleep(delay)
                    continue
        raise RuntimeError(
            f"All tool candidates failed for {action}: tried {candidates}, "
            f"{self.max_retries + 1} attempts each. Last error: {last_error}"
        )

    def _call_one(self, agent_id: str, tool_id: str, action: str, params: dict[str, Any]) -> Any:
        started = perf_counter()
        call = ToolCall(agent_id=agent_id, tool_id=tool_id, action=action, params=params)
        try:
            plugin = self.plugins.get(tool_id)
            self.access.require(agent_id, tool_id, action)
            result = plugin.execute(action, params)
            call.result = result
            call.status = CallStatus.SUCCESS.value
            return result
        except PermissionError as exc:
            call.result = {"error": str(exc)}
            call.status = CallStatus.DENIED.value
            raise
        except TimeoutError as exc:
            call.result = {"error": str(exc)}
            call.status = CallStatus.TIMEOUT.value
            raise
        except Exception as exc:
            call.result = {"error": str(exc)}
            call.status = CallStatus.ERROR.value
            raise
        finally:
            call.duration_ms = (perf_counter() - started) * 1000
            self.store.record_call(call)

    def grant(self, agent_id: str, tool_id: str, level: str) -> None:
        self.access.grant(agent_id, tool_id, level)

    def discover(self) -> dict[str, list[str]]:
        return self.plugins.discover()
