from __future__ import annotations

from typing import Any
from uuid import uuid4

from nexus.api.unified import UnifiedToolAPI
from nexus.core.db import NexusStore
from nexus.core.models import Workflow, WorkflowStep


class WorkflowBuilder:
    def __init__(self, store: NexusStore) -> None:
        self.store = store

    def create(
        self,
        name: str,
        steps: list[dict[str, Any]],
        created_by: str,
        description: str = "",
        trigger: str = "manual",
    ) -> Workflow:
        workflow_steps = [
            WorkflowStep(
                tool_id=step["tool_id"],
                action=step["action"],
                params=step.get("params", {}),
                condition=step.get("condition"),
                fallback_tools=step.get("fallback_tools", []),
            )
            for step in steps
        ]
        workflow = Workflow(
            id=str(uuid4()),
            name=name,
            description=description,
            steps=workflow_steps,
            trigger=trigger,
            created_by=created_by,
        )
        self.store.save_workflow(workflow)
        self.store.audit("workflow.created", workflow_id=workflow.id, created_by=created_by)
        return workflow


class Pipeline:
    def __init__(self, api: UnifiedToolAPI, store: NexusStore) -> None:
        self.api = api
        self.store = store

    def run(self, workflow_id: str, agent_id: str) -> list[Any]:
        workflow = self.store.workflows[workflow_id]
        results: list[Any] = []
        for step in workflow.steps:
            params = self._resolve_params(step.params, results)
            result = self.api.call(agent_id, step.tool_id, step.action, params, step.fallback_tools)
            results.append(result)
        self.store.audit("workflow.ran", workflow_id=workflow_id, agent_id=agent_id, steps=len(results))
        return results

    def _resolve_params(self, params: dict[str, Any], results: list[Any]) -> dict[str, Any]:
        resolved = dict(params)
        if "$previous" in resolved:
            resolved["previous"] = results[-1] if results else None
            del resolved["$previous"]
        return resolved
