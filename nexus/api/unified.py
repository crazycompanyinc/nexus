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

    def __repr__(self) -> str:
        return (
            f"UnifiedToolAPI(agents={len(self.store.agents)}, "
            f"plugins={len(self.store.plugins)}, "
            f"calls={len(self.store.calls)}, "
            f"max_retries={self.max_retries}, "
            f"retry_base_delay={self.retry_base_delay}s)"
        )

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

    def batch_call(
        self,
        agent_id: str,
        calls: list[dict[str, Any]],
        fail_fast: bool = False,
    ) -> list[dict[str, Any]]:
        """Execute multiple tool calls in sequence.

        Each call dict must contain 'tool_id' and 'action', and may contain
        'params' and 'fallback_tools'. Results are returned in the same order.

        Args:
            agent_id: Unique identifier for the calling agent.
            calls: List of call dicts, each with tool_id, action, optional params/fallback_tools.
            fail_fast: If True, stop on first failure and raise.

        Returns:
            List of result dicts with 'result', 'success', 'error', 'duration_ms' keys.

        Raises:
            PermissionError: If agent lacks permission (always raised immediately).
            RuntimeError: If fail_fast is True and a call fails.
        """
        results: list[dict[str, Any]] = []
        for call_spec in calls:
            tool_id = call_spec["tool_id"]
            action = call_spec["action"]
            params = call_spec.get("params", {})
            fallback_tools = call_spec.get("fallback_tools", [])
            started = perf_counter()
            try:
                result = self.call(agent_id, tool_id, action, params, fallback_tools)
                results.append({
                    "tool_id": tool_id,
                    "action": action,
                    "result": result,
                    "success": True,
                    "error": None,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                })
            except PermissionError:
                raise
            except Exception as exc:
                results.append({
                    "tool_id": tool_id,
                    "action": action,
                    "result": None,
                    "success": False,
                    "error": str(exc),
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                })
                if fail_fast:
                    raise RuntimeError(
                        f"Batch call failed at {tool_id}.{action}: {exc}"
                    ) from exc
        return results

    def grant(self, agent_id: str, tool_id: str, level: str) -> None:
        self.access.grant(agent_id, tool_id, level)

    def discover(self) -> dict[str, list[str]]:
        return self.plugins.discover()
