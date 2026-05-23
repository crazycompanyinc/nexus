from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from nexus.api.unified import UnifiedToolAPI
from nexus.core.db import NexusStore
from nexus.core.models import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

__all__ = ["Pipeline", "StepResult", "Workflow", "WorkflowBuilder", "WorkflowStep"]


def _parse_step_dict(step: dict[str, Any]) -> WorkflowStep:
    """Parse a step dict into a WorkflowStep, applying defaults for missing fields.

    Centralises step parsing so that create(), update(), and PATCH all
    use the same validation logic.

    Args:
        step: Dict with 'tool_id', 'action', and optional fields.

    Returns:
        A validated WorkflowStep instance.

    Raises:
        KeyError: If 'tool_id' or 'action' is missing.
        TypeError: If step is not a dict.
    """
    if not isinstance(step, dict):
        raise TypeError(f"Each step must be a dict, got {type(step).__name__}")
    return WorkflowStep(
        tool_id=step["tool_id"],
        action=step["action"],
        params=step.get("params", {}),
        condition=step.get("condition"),
        fallback_tools=step.get("fallback_tools", []),
        max_retries=step.get("max_retries", 0),
        retry_delay_ms=step.get("retry_delay_ms", 100.0),
    )


class WorkflowBuilder:
    """Creates, updates, and manages workflow definitions.

    Workflows are ordered sequences of tool calls with per-step retry,
    fallback, and conditional execution support.

    Example:
        >>> builder = WorkflowBuilder(store)
        >>> wf = builder.create("deploy", steps, "admin")
    """

    def __init__(self, store: NexusStore) -> None:
        """Initialize the WorkflowBuilder.

        Args:
            store: NexusStore instance for persistence.
        """
        self.store = store

    def create(
        self,
        name: str,
        steps: list[dict[str, Any]],
        created_by: str,
        description: str = "",
        trigger: str = "manual",
    ) -> Workflow:
        """Create and persist a new workflow.

        Validates the workflow structure before saving. Each step must
        contain 'tool_id' and 'action' keys.

        Args:
            name: Human-readable workflow name.
            steps: List of step dicts with tool_id, action, and optional params.
            created_by: Identifier of the user/system creating the workflow.
            description: Optional workflow description.
            trigger: Workflow trigger type (manual, scheduled, event).

        Returns:
            The created Workflow instance.

        Raises:
            ValueError: If name/created_by is empty, steps is empty, or validation fails.
            TypeError: If steps is not a list.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Workflow name must be a non-empty string, got {name!r}")
        if not isinstance(created_by, str) or not created_by.strip():
            raise ValueError(f"created_by must be a non-empty string, got {created_by!r}")
        if not isinstance(steps, list):
            raise TypeError(f"steps must be a list, got {type(steps).__name__}")
        if not steps:
            raise ValueError("steps must contain at least one step")
        workflow_steps = [_parse_step_dict(step) for step in steps]
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
        """Retrieve a workflow by its ID.

        Args:
            workflow_id: The unique workflow identifier.

        Returns:
            The Workflow if found, None otherwise.
        """
        return self.store.get_workflow(workflow_id)

    def update(
        self,
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> Workflow:
        """Update an existing workflow's properties.

        Re-validates the workflow after applying changes.

        Args:
            workflow_id: The workflow to update.
            name: New name (optional).
            description: New description (optional).
            status: New status (optional).
            steps: New steps list (optional).

        Returns:
            The updated Workflow instance.

        Raises:
            KeyError: If workflow_id is not found.
            ValueError: If validation fails after update.
        """
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
            workflow.steps = [_parse_step_dict(step) for step in steps]
        # Re-validate after all mutations
        errors = workflow.validate()
        if errors:
            raise ValueError(f"Workflow validation failed after update: {'; '.join(errors)}")
        self.store.audit("workflow.updated", workflow_id=workflow.id)
        return workflow

    def list(self) -> list[Workflow]:
        """List all stored workflows.

        Returns:
            List of all Workflow instances.
        """
        return list(self.store.workflows.values())

    def patch(
        self,
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        created_by: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> Workflow:
        """Partially update a workflow (PATCH semantics — all fields optional).

        Only provided (non-None, non-empty) fields are applied. Re-validates
        the workflow after applying changes and records an audit event.

        Args:
            workflow_id: The workflow to patch.
            name: New name (optional, applied if non-empty).
            description: New description (optional, applied if non-empty).
            created_by: New creator (optional, applied if non-empty).
            steps: New steps list (optional, applied if non-empty).

        Returns:
            The patched Workflow instance.

        Raises:
            KeyError: If workflow_id is not found.
            ValueError: If validation fails after patching.
        """
        workflow = self.store.workflows.get(workflow_id)
        if workflow is None:
            raise KeyError(f"Workflow not found: {workflow_id}")
        if name is not None and name.strip():
            workflow.name = name
        if description is not None and description.strip():
            workflow.description = description
        if created_by is not None and created_by.strip():
            workflow.created_by = created_by
        if steps is not None and steps:
            workflow.steps = [_parse_step_dict(s) for s in steps]
        errors = workflow.validate()
        if errors:
            raise ValueError(f"Workflow validation failed after patch: {'; '.join(errors)}")
        self.store.audit("workflow.patched", workflow_id=workflow.id)
        return workflow

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow by its ID.

        Args:
            workflow_id: The workflow to delete.

        Returns:
            True if deleted, False if not found.
        """
        if self.store.delete_workflow(workflow_id):
            self.store.audit("workflow.deleted", workflow_id=workflow_id)
            return True
        return False

    def __repr__(self) -> str:
        return f"WorkflowBuilder(workflows={len(self.store.workflows)})"


@dataclass(slots=True)
class StepResult:
    """Result of a single workflow step execution.

    Attributes:
        step_index: Zero-based position of the step in the workflow.
        tool_id: The tool plugin that was invoked.
        action: The action that was executed.
        result: The return value from the tool, None on failure.
        error: Error message string if the step failed, None otherwise.
        duration_ms: Wall-clock execution time in milliseconds.
        success: Whether the step completed without error.
    """
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

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "step_index": self.step_index,
            "tool_id": self.tool_id,
            "action": self.action,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "success": self.success,
        }


class Pipeline:
    """Executes workflows by running each step through the UnifiedToolAPI.

    Supports fail_fast mode, per-step retry with exponential backoff,
    conditional step execution, and parameter resolution from previous
    step results.
    """

    def __init__(self, api: UnifiedToolAPI, store: NexusStore) -> None:
        """Initialize the Pipeline.

        Args:
            api: UnifiedToolAPI instance for executing tool calls.
            store: NexusStore instance for persistence and workflow retrieval.
        """
        self.api = api
        self.store = store

    def run(self, workflow_id: str, agent_id: str, fail_fast: bool = False) -> list[StepResult]:
        """Execute a workflow by running each step in sequence.

        Steps can be conditionally skipped based on previous step outcomes.
        Each step is retried up to max_retries times with exponential backoff.
        Parameter references ($previous, $all, $stepN) are resolved from
        previous step results.

        Args:
            workflow_id: The workflow to execute.
            agent_id: The agent executing the workflow.
            fail_fast: If True, stop on first step failure.

        Returns:
            List of StepResult instances, one per executed step.
        """
        from time import perf_counter, sleep
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(f"Workflow not found: {workflow_id}")
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
