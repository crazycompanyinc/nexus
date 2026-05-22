from __future__ import annotations

from typing import Any, Callable

from nexus.api.unified import UnifiedToolAPI


class ToolAdapter:
    """Adapts Nexus UnifiedToolAPI calls into framework-specific tool formats.

    Supports LangChain tools and AutoGen function dictionaries.
    """

    def __init__(self, api: UnifiedToolAPI) -> None:
        self.api = api

    def as_langchain_tool(self, agent_id: str, tool_id: str, action: str) -> Callable[..., Any]:
        """Wrap a Nexus tool call as a LangChain-compatible callable.

        Args:
            agent_id: The agent making the tool call.
            tool_id: The tool plugin identifier.
            action: The action to invoke on the tool.

        Returns:
            A callable that accepts keyword params and returns the tool result.
        """
        def tool(**params: Any) -> Any:
            """Execute a Nexus tool call with the configured agent, tool, and action.

            Args:
                **params: Keyword arguments forwarded as tool parameters.

            Returns:
                The result returned by the Nexus UnifiedToolAPI.
            """
            return self.api.call(agent_id, tool_id, action, params)

        tool.__name__ = f"nexus_{tool_id}_{action.replace('.', '_')}"
        return tool

    def as_autogen_function(self, agent_id: str, tool_id: str, action: str) -> dict[str, Any]:
        """Wrap a Nexus tool call as an AutoGen function dictionary.

        Args:
            agent_id: The agent making the tool call.
            tool_id: The tool plugin identifier.
            action: The action to invoke on the tool.

        Returns:
            Dict with 'name', 'description', and 'callable' keys.
        """
        return {
            "name": f"nexus_{tool_id}_{action.replace('.', '_')}",
            "description": f"Call Nexus tool {tool_id}.{action}",
            "callable": self.as_langchain_tool(agent_id, tool_id, action),
        }


class APIMapper:
    """Maps Nexus API capabilities to external framework formats."""

    def __init__(self, api: UnifiedToolAPI) -> None:
        self.api = api

    def map_capabilities(self) -> dict[str, list[str]]:
        """Return all available tool capabilities as a dict of tool_id -> actions.

        Returns:
            Dict mapping each tool ID to its list of supported capability strings.
        """
        return self.api.discover()
