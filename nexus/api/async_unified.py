from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any

from nexus.core.models import CallStatus, ToolCall
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager
from nexus.core.db import NexusStore

logger = logging.getLogger(__name__)


class AsyncUnifiedToolAPI:
    """Async variant of UnifiedToolAPI for non-blocking tool calls.

    Provides the same retry, fallback, and access control semantics
    as UnifiedToolAPI but uses asyncio for concurrent execution.

    Example:
        >>> api = AsyncUnifiedToolAPI()
        >>> result = await api.call("agent-1", "http", "fetch", {"url": "https://example.com"})
    """

    def __init__(
        self,
        store: NexusStore | None = None,
        plugin_manager: PluginManager | None = None,
        access_control: AccessControl | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 0.1,
    ) -> None:
        """Initialize the async API with optional store, plugin manager, and access control.

        Args:
            store: NexusStore instance for persistence. Created if not provided.
            plugin_manager: PluginManager for tool resolution. Created if not provided.
            access_control: AccessControl for permission checks. Created if not provided.
            max_retries: Maximum retry attempts per tool candidate (>= 0).
            retry_base_delay: Base delay in seconds for exponential backoff (>= 0.0).
        """
        self.store = store or NexusStore()
        self.plugins = plugin_manager if plugin_manager is not None else PluginManager(self.store)
        self.access = access_control if access_control is not None else AccessControl(self.store)
        self.max_retries = max(max_retries, 0)
        self.retry_base_delay = max(retry_base_delay, 0.0)

    def __repr__(self) -> str:
        """Return a summary of the async API's current state.

        Returns:
            String with agent count, plugin count, call count, and retry config.
        """
        return (
            f"AsyncUnifiedToolAPI(agents={len(self.store.agents)}, "
            f"plugins={len(self.store.plugins)}, "
            f"calls={len(self.store.calls)}, "
            f"max_retries={self.max_retries}, "
            f"retry_base_delay={self.retry_base_delay}s)"
        )

    async def call(
        self,
        agent_id: str,
        tool_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        fallback_tools: list[str] | None = None,
    ) -> Any:
        """Execute a tool call asynchronously with retry and fallback support.

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
                    return await self._call_one(agent_id, candidate, action, params)
                except PermissionError:
                    raise
                except Exception as exc:
                    last_error = exc
                    if attempt < self.max_retries:
                        delay = self.retry_base_delay * (2 ** attempt)
                        logger.warning(
                            "Async retry %d/%d for %s.%s (agent=%s) after %.2fs: %s",
                            attempt + 1, self.max_retries, candidate, action, agent_id, delay, exc,
                        )
                        await asyncio.sleep(delay)
                    continue

        raise RuntimeError(
            f"All tool candidates failed for {action}: tried {candidates}, "
            f"{self.max_retries + 1} attempts each. Last error: {last_error}"
        )

    async def _call_one(
        self, agent_id: str, tool_id: str, action: str, params: dict[str, Any]
    ) -> Any:
        """Execute a single async tool call with permission checking and timing.

        Runs the blocking plugin execute in a thread pool via asyncio.to_thread.

        Args:
            agent_id: The agent making the call.
            tool_id: The target tool plugin identifier.
            action: The action to invoke.
            params: Key-value parameters for the action.

        Returns:
            The result returned by the tool plugin.

        Raises:
            PermissionError: If the agent lacks access for the requested action.
            TimeoutError: If the tool execution exceeds the timeout.
            Exception: Any exception raised by the tool plugin execution.
        """
        started = perf_counter()
        call = ToolCall(agent_id=agent_id, tool_id=tool_id, action=action, params=params)
        try:
            plugin = self.plugins.get(tool_id)
            self.access.require(agent_id, tool_id, action)
            # Run the (potentially blocking) plugin execute in a thread pool
            result = await asyncio.to_thread(plugin.execute, action, params)
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

    async def batch_call(
        self,
        agent_id: str,
        calls: list[dict[str, Any]],
        fail_fast: bool = False,
        max_concurrency: int = 10,
    ) -> list[dict[str, Any]]:
        """Execute multiple tool calls concurrently with bounded parallelism.

        Args:
            agent_id: Unique identifier for the calling agent.
            calls: List of call dicts with tool_id, action, optional params/fallback_tools.
            fail_fast: If True, cancel all on first failure.
            max_concurrency: Maximum number of concurrent calls.

        Returns:
            List of result dicts in the same order as input.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded_call(idx: int, call_spec: dict[str, Any]) -> tuple[int, dict[str, Any]]:
            """Execute a single batched call with semaphore-bounded concurrency.

            Args:
                idx: Original index in the batch for result ordering.
                call_spec: Dict with tool_id, action, optional params/fallback_tools.

            Returns:
                Tuple of (original_index, result_dict) with success/error info.
            """
            async with semaphore:
                tool_id = call_spec["tool_id"]
                action = call_spec["action"]
                params = call_spec.get("params", {})
                fallback_tools = call_spec.get("fallback_tools", [])
                started = perf_counter()
                try:
                    result = await self.call(agent_id, tool_id, action, params, fallback_tools)
                    return idx, {
                        "tool_id": tool_id,
                        "action": action,
                        "result": result,
                        "success": True,
                        "error": None,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }
                except PermissionError:
                    raise
                except Exception as exc:
                    return idx, {
                        "tool_id": tool_id,
                        "action": action,
                        "result": None,
                        "success": False,
                        "error": str(exc),
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }

        tasks = [asyncio.create_task(_bounded_call(i, c)) for i, c in enumerate(calls)]

        if fail_fast:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            # Cancel all pending tasks immediately
            for t in pending:
                t.cancel()
            # Wait for cancellations to settle
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            results = [None] * len(calls)
            for t in done:
                idx, result = await t
                results[idx] = result
                if not result["success"]:
                    # Already cancelled pending above, just break
                    break
            # Fill any remaining None slots (from cancellations) with error entries
            for i, r in enumerate(results):
                if r is None:
                    results[i] = {
                        "tool_id": calls[i].get("tool_id", "unknown"),
                        "action": calls[i].get("action", "unknown"),
                        "result": None,
                        "success": False,
                        "error": "Cancelled due to fail_fast",
                        "duration_ms": 0,
                    }
            return results

        ordered = await asyncio.gather(*tasks, return_exceptions=False)
        results = [None] * len(calls)
        for idx, result in ordered:
            results[idx] = result
        return results

    def grant(self, agent_id: str, tool_id: str, level: str) -> None:
        """Grant a permission level to an agent for a specific tool.

        Args:
            agent_id: The agent to grant permissions to.
            tool_id: The tool identifier.
            level: Permission level (read, write, admin).
        """
        self.access.grant(agent_id, tool_id, level)

    def discover(self) -> dict[str, list[str]]:
        """Discover all available tool capabilities.

        Returns:
            Dict mapping each tool ID to its list of supported capability strings.
        """
        return self.plugins.discover()
