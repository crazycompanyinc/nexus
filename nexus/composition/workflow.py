from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from nexus.api.unified import UnifiedToolAPI
from nexus.core.db import NexusStore
from nexus.core.models import Workflow, WorkflowStep

logger = logging.getLogger(__name__)


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


@dataclass
class StepResult:
    step_index: int
    tool_id: str
    action: str
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    success: bool = True


class Pipeline:
    def __init__(self, api: UnifiedToolAPI, store: NexusStore) -> None:
        self.api = api
        self.store = store

    def run(self, workflow_id: str, agent_id: str) -> list[StepResult]:
        workflow = self.store.workflows[workflow_id]
        results: list[StepResult] = []
        for idx, step in enumerate(workflow.steps):
            from time import perf_counter
            started = perf_counter()
            step_result = StepResult(step_index=idx, tool_id=step.tool_id, action=step.action)
            try:
                params = self._resolve_params(step.params, [r.result for r in results if r.success])
                result = self.api.call(agent_id, step.tool_id, step.action, params, step.fallback_tools)
                step_result.result = result
                step_result.success = True
            except Exception as exc:
                step_result.error = str(exc)
                step_result.success = False
                logger.error(
                    "Workflow %s step %d failed (%s.%s): %s",
                    workflow_id, idx, step.tool_id, step.action, exc,
                )
                self.store.audit(
                    "workflow.step_failed",
                    workflow_id=workflow_id,
                    step_index=idx,
                    tool_id=step.tool_id,
                    action=step.action,
                    error=str(exc),
                )
            finally:
                step_result.duration_ms = (perf_counter() - started) * 1000
            results.append(step_result)
        succeeded = sum(1 for r in results if r.success)
        self.store.audit(
            "workflow.ran",
            workflow_id=workflow_id,
            agent_id=agent_id,
            steps=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
        )
        return results

    def _resolve_params(self, params: dict[str, Any], results: list[Any]) -> dict[str, Any]:
        resolved = dict(params)
        if "$previous" in resolved:
            resolved["previous"] = results[-1] if results else None
            del resolved["$previous"]
        return resolved
