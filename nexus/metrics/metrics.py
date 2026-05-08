from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from nexus.core.db import NexusStore


class UsageMetrics:
    def __init__(self, store: NexusStore) -> None:
        self.store = store

    def summary(self) -> dict[str, Any]:
        by_tool = Counter(call.tool_id for call in self.store.calls)
        by_agent = Counter(call.agent_id for call in self.store.calls)
        by_status = Counter(call.status for call in self.store.calls)
        return {
            "total_calls": len(self.store.calls),
            "by_tool": dict(by_tool),
            "by_agent": dict(by_agent),
            "by_status": dict(by_status),
        }

    def tool_usage(self, tool_id: str) -> dict[str, Any]:
        calls = [call for call in self.store.calls if call.tool_id == tool_id]
        return {"tool_id": tool_id, "calls": len(calls), "agents": sorted({call.agent_id for call in calls})}

    def agent_usage(self, agent_id: str) -> dict[str, Any]:
        calls = [call for call in self.store.calls if call.agent_id == agent_id]
        actions: dict[str, list[str]] = defaultdict(list)
        for call in calls:
            actions[call.tool_id].append(call.action)
        return {"agent_id": agent_id, "calls": len(calls), "actions": dict(actions)}
