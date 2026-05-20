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
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Workflow name must be a non-empty string, got {name!r}")
        if not isinstance(created_by, str) or not created_by.strip():
            raise ValueError(f"created_by must be a non-empty string, got {created_by!r}")
        if not isinstance(steps, list):
            raise TypeError(f"steps must be a list, got {type(steps).__name__}")
        if not steps:
            raise ValueError("steps must contain at least one step")
        workflow_steps = [
            WorkflowStep(
                tool_id=step["tool_id"],
                action=step["action"],
                params=step.get("params", {}),
                condition=step.get("condition"),
                fallback_tools=step.get("fallback_tools", []),
                max_retries=step.get("max_retries", 0),
                retry_delay_ms=step.get("retry_delay_ms", 100.0),
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
        errors = workflow.validate()
        if errors:
            raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")
        self.store.save_workflow(workflow)
        self.store.audit("workflow.created", workflow_id=workflow.id, created_by=created_by)
        return workflow

    def get(self, workflow_id: str) -> Workflow | None:
        return self.store.workflows.get(workflow_id)

    def update(
        self,
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> Workflow:
        workflow = self.store.workflows.get(workflow_id)
        if workflow is None:
            raise KeyError(f"Workflow not found: {workflow_id}")
        if name is not None:
            workflow.name = name
        if description is not None:
            workflow.description = description
        if status is not None:
            workflow.status = status
        if steps is not None:
            workflow.steps = [
                WorkflowStep(
                    tool_id=step["tool_id"],
                    action=step["action"],
                    params=step.get("params", {}),
                    condition=step.get("condition"),
                    fallback_tools=step.get("fallback_tools", []),
                    max_retries=step.get("max_retries", 0),
                    retry_delay_ms=step.get("retry_delay_ms", 100.0),
                )
                for step in steps
            ]
        # Re-validate after all mutations
        errors = workflow.validate()
        if errors:
            raise ValueError(f"Workflow validation failed after update: {'; '.join(errors)}")
        self.store.audit("workflow.updated", workflow_id=workflow.id)
        return workflow

    def list(self) -> list[Workflow]:
        return list(self.store.workflows.values())

    def delete(self, workflow_id: str) -> bool:
        if self.store.delete_workflow(workflow_id):
            self.store.audit("workflow.deleted", workflow_id=workflow_id)
            return True
        return False


@dataclass(slots=True)
class StepResult:
    step_index: int
    tool_id: str
    action: str
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    success: bool = True

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        status = "ok" if self.success else "FAIL"
        return f"StepResult(#{self.step_index}, {self.tool_id}.{self.action}, {status}, {self.duration_ms:.1f}ms)"


class Pipeline:
    def __init__(self, api: UnifiedToolAPI, store: NexusStore) -> None:
        self.api = api
        self.store = store

    def run(self, workflow_id: str, agent_id: str, fail_fast: bool = False) -> list[StepResult]:
        from time import perf_counter, sleep
        workflow = self.store.workflows[workflow_id]
        results: list[StepResult] = []
        run_started = perf_counter()
        for idx, step in enumerate(workflow.steps):
            # Conditional step execution: skip if condition is "previous_failed" and last step succeeded
            if step.condition and results:
                last = results[-1]
                if step.condition == "previous_failed" and last.success:
                    logger.info("Workflow %s step %d skipped (condition: previous_failed, but previous succeeded)", workflow_id, idx)
                    continue
                if step.condition == "previous_succeeded" and not last.success:
                    logger.info("Workflow %s step %d skipped (condition: previous_succeeded, but previous failed)", workflow_id, idx)
                    continue
            started = perf_counter()
            step_result = StepResult(step_index=idx, tool_id=step.tool_id, action=step.action)
            attempt = 0
            max_attempts = 1 + step.max_retries
            while attempt < max_attempts:
                try:
                    params = self._resolve_params(step.params, [r.result for r in results if r.success])
                    result = self.api.call(agent_id, step.tool_id, step.action, params, step.fallback_tools)
                    step_result.result = result
                    step_result.success = True
                    if attempt > 0:
                        logger.info("Workflow %s step %d succeeded on attempt %d/%d", workflow_id, idx, attempt + 1, max_attempts)
                    break
                except Exception as exc:
                    attempt += 1
                    step_result.error = str(exc)
                    step_result.success = False
                    if attempt < max_attempts:
                        delay = step.retry_delay_ms * (2 ** (attempt - 1)) / 1000.0
                        logger.warning("Workflow %s step %d attempt %d/%d failed, retrying in %.1fms: %s", workflow_id, idx, attempt, max_attempts, delay * 1000, exc)
                        sleep(delay)
                    else:
                        logger.error("Workflow %s step %d failed after %d attempts (%s.%s): %s", workflow_id, idx, max_attempts, step.tool_id, step.action, exc)
            step_result.duration_ms = (perf_counter() - started) * 1000
            if not step_result.success:
                self.store.audit("workflow.step_failed", workflow_id=workflow_id, step_index=idx, tool_id=step.tool_id, action=step.action, error=step_result.error, attempts=max_attempts)
            results.append(step_result)
            if fail_fast and not step_result.success:
                logger.error("Workflow %s fail_fast: stopping after step %d failure", workflow_id, idx)
                break
        run_duration_ms = (perf_counter() - run_started) * 1000
        succeeded = sum(1 for r in results if r.success)
        self.store.audit("workflow.ran", workflow_id=workflow_id, agent_id=agent_id, steps=len(results), succeeded=succeeded, failed=len(results) - succeeded, duration_ms=round(run_duration_ms, 2))
        return results

    def _resolve_params(self, params: dict[str, Any], results: list[Any]) -> dict[str, Any]:
        import re
        resolved = dict(params)
        if "$previous" in resolved:
            resolved["previous"] = results[-1] if results else None
            del resolved["$previous"]
        if "$all" in resolved:
            resolved["all"] = list(results)
            del resolved["$all"]
        # Support $step{N} references (e.g., $step0, $step1)
        for key, value in list(resolved.items()):
            if isinstance(value, str):
                match = re.match(r"^\$step(\d+)$", value)
                if match:
                    step_idx = int(match.group(1))
                    resolved[key] = results[step_idx] if step_idx < len(results) else None
        return resolved
