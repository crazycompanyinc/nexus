from __future__ import annotations

from typing import Any, Callable

from nexus.api.unified import UnifiedToolAPI


class ToolAdapter:
    def __init__(self, api: UnifiedToolAPI) -> None:
        self.api = api

    def as_langchain_tool(self, agent_id: str, tool_id: str, action: str) -> Callable[..., Any]:
        def tool(**params: Any) -> Any:
            return self.api.call(agent_id, tool_id, action, params)

        tool.__name__ = f"nexus_{tool_id}_{action.replace('.', '_')}"
        return tool

    def as_autogen_function(self, agent_id: str, tool_id: str, action: str) -> dict[str, Any]:
        return {
            "name": f"nexus_{tool_id}_{action.replace('.', '_')}",
            "description": f"Call Nexus tool {tool_id}.{action}",
            "callable": self.as_langchain_tool(agent_id, tool_id, action),
        }


class APIMapper:
    def __init__(self, api: UnifiedToolAPI) -> None:
        self.api = api

    def map_capabilities(self) -> dict[str, list[str]]:
        return self.api.discover()
