from __future__ import annotations

import asyncio
from typing import Any, Self

from nexus.api.unified import UnifiedToolAPI
from nexus.api.async_unified import AsyncUnifiedToolAPI


class ToolChain:
    """Chains multiple tool calls into a sequential pipeline.

    Each step calls a tool with optional fallback tools and params.
    Supports conditional execution with fail-fast mode.
    """

    def __init__(self, api: UnifiedToolAPI, agent_id: str) -> None:
        """Initialize the chain with a UnifiedToolAPI and agent ID.

        Args:
            api: The tool API to use for executing steps.
            agent_id: The agent ID to use for all calls in the chain.
        """
        self.api = api
        self.agent_id = agent_id
        self.steps: list[tuple[str, str, dict[str, Any], list[str]]] = []

    def add(
        self,
        tool_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        fallback_tools: list[str] | None = None,
    ) -> Self:
        """Add a tool call step to the chain.

        Args:
            tool_id: The tool plugin identifier.
            action: The action to invoke.
            params: Optional parameters dict for the call.
            fallback_tools: Optional list of fallback tool IDs.

        Returns:
            Self, for method chaining.
        """
        self.steps.append((tool_id, action, params or {}, fallback_tools or []))
        return self

    def run(self) -> list[Any]:
        """Execute all steps sequentially and return their results.

        Returns:
            List of results from each step in order.
        """
        results: list[Any] = []
        for tool_id, action, params, fallback_tools in self.steps:
            results.append(
                self.api.call(self.agent_id, tool_id, action, params, fallback_tools)
            )
        return results

    def run_conditional(self, fail_fast: bool = True) -> list[Any]:
        """Run steps, optionally stopping on first failure (fail-fast mode).

        Args:
            fail_fast: If True, stop execution on first failed step.
        """
        results: list[Any] = []
        for tool_id, action, params, fallback_tools in self.steps:
            try:
                result = self.api.call(self.agent_id, tool_id, action, params, fallback_tools)
                results.append(result)
            except Exception as exc:
                if fail_fast:
                    raise
                results.append({"error": str(exc)})
        return results

    def __repr__(self) -> str:
        return f"ToolChain(agent={self.agent_id!r}, steps={len(self.steps)})"


class AsyncToolChain:
    """Async version of ToolChain for non-blocking concurrent tool calls.

    Supports both sequential and concurrent execution modes.
    When running concurrently, uses asyncio.gather for parallel execution.

    Example:
        >>> chain = AsyncToolChain(async_api, "agent-1")
        >>> chain.add("http", "fetch", {"url": "https://example.com"})
        >>> chain.add("slack", "send", {"channel": "#general", "message": "hi"})
        >>> results = await chain.run()           # sequential
        >>> results = await chain.run_concurrent()  # parallel
    """

    def __init__(self, api: AsyncUnifiedToolAPI, agent_id: str) -> None:
        """Initialize the async chain with an AsyncUnifiedToolAPI and agent ID.

        Args:
            api: The async tool API to use for executing steps.
            agent_id: The agent ID to use for all calls in the chain.
        """
        self.api = api
        self.agent_id = agent_id
        self.steps: list[tuple[str, str, dict[str, Any], list[str]]] = []

    def add(
        self,
        tool_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        fallback_tools: list[str] | None = None,
    ) -> Self:
        """Add a tool call step to the chain.

        Args:
            tool_id: The tool plugin identifier.
            action: The action to invoke.
            params: Optional parameters dict for the call.
            fallback_tools: Optional list of fallback tool IDs.

        Returns:
            Self, for method chaining.
        """
        self.steps.append((tool_id, action, params or {}, fallback_tools or []))
        return self

    async def run(self) -> list[Any]:
        """Execute all steps sequentially (async) and return their results.

        Returns:
            List of results from each step in order.
        """
        results: list[Any] = []
        for tool_id, action, params, fallback_tools in self.steps:
            result = await self.api.call(self.agent_id, tool_id, action, params, fallback_tools)
            results.append(result)
        return results

    async def run_concurrent(self, *, return_exceptions: bool = False) -> list[Any]:
        """Execute all steps concurrently using asyncio.gather.

        Args:
            return_exceptions: If True, exceptions are returned as results
                instead of raising. Default: False.

        Returns:
            List of results from each step.
        """
        tasks = [
            self.api.call(self.agent_id, tool_id, action, params, fallback_tools)
            for tool_id, action, params, fallback_tools in self.steps
        ]
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)

    async def run_with_limit(self, *, max_concurrency: int = 5) -> list[Any]:
        """Execute steps with a concurrency limit using a semaphore.

        Useful when you want parallelism but need to avoid overwhelming
        external services.

        Args:
            max_concurrency: Maximum number of concurrent tool calls.

        Returns:
            List of results from each step in order.
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _limited_call(tool_id: str, action: str, params: dict[str, Any], fallback_tools: list[str]) -> Any:
            async with sem:
                return await self.api.call(self.agent_id, tool_id, action, params, fallback_tools)

        tasks = [
            _limited_call(tool_id, action, params, fallback_tools)
            for tool_id, action, params, fallback_tools in self.steps
        ]
        return await asyncio.gather(*tasks)

    def __repr__(self) -> str:
        return f"AsyncToolChain(agent={self.agent_id!r}, steps={len(self.steps)})"
