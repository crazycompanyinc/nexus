from __future__ import annotations

from typing import Any, Self

from nexus.api.unified import UnifiedToolAPI


class ToolChain:
    def __init__(self, api: UnifiedToolAPI, agent_id: str) -> None:
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
        self.steps.append((tool_id, action, params or {}, fallback_tools or []))
        return self

    def run(self) -> list[Any]:
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
