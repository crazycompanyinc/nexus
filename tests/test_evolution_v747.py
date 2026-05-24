#!/usr/bin/env python3
"""Tests for v7.44 evolution: AgentToolBinding.from_dict, WorkflowStep.from_dict, Workflow.from_dict, __all__ exports."""

from __future__ import annotations

import pytest

from nexus.core.models import (
    AgentToolBinding,
    CallStatus,
    PermissionLevel,
    PluginStatus,
    PluginType,
    ToolCall,
    ToolPlugin,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
    utcnow,
)


# ---------------------------------------------------------------------------
# AgentToolBinding.from_dict()
# ---------------------------------------------------------------------------

class TestAgentToolBindingFromDict:
    """Tests for AgentToolBinding.from_dict() deserialization."""

    def test_basic_roundtrip(self):
        """from_dict(to_dict()) should produce an equivalent object."""
        original = AgentToolBinding(
            agent_id="agent-1",
            tool_id="tool-1",
            permissions=PermissionLevel.WRITE.value,
            config={"timeout": 30},
        )
        data = original.to_dict()
        restored = AgentToolBinding.from_dict(data)
        assert restored.agent_id == original.agent_id
        assert restored.tool_id == original.tool_id
        assert restored.permissions == original.permissions
        assert restored.config == original.config

    def test_minimal_fields(self):
        """from_dict works with only required fields."""
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "permissions": "read",
        }
        binding = AgentToolBinding.from_dict(data)
        assert binding.agent_id == "a1"
        assert binding.tool_id == "t1"
        assert binding.permissions == "read"
        assert binding.config == {}

    def test_config_is_copied(self):
        """from_dict copies config dict, not references."""
        config = {"key": "value"}
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "permissions": "admin",
            "config": config,
        }
        binding = AgentToolBinding.from_dict(data)
        config["new_key"] = "new_value"
        assert "new_key" not in binding.config

    def test_extra_keys_ignored(self):
        """from_dict silently ignores extra keys for forward compatibility."""
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "permissions": "read",
            "future_field": "ignored",
        }
        binding = AgentToolBinding.from_dict(data)
        assert binding.agent_id == "a1"


# ---------------------------------------------------------------------------
# WorkflowStep.from_dict()
# ---------------------------------------------------------------------------

class TestWorkflowStepFromDict:
    """Tests for WorkflowStep.from_dict() deserialization."""

    def test_basic_roundtrip(self):
        """from_dict(to_dict()) should produce an equivalent object."""
        original = WorkflowStep(
            tool_id="deploy-tool",
            action="deploy",
            params={"env": "production"},
            condition="previous_step == success",
            fallback_tools=["backup-tool"],
            max_retries=3,
            retry_delay_ms=500.0,
        )
        data = original.to_dict()
        restored = WorkflowStep.from_dict(data)
        assert restored.tool_id == original.tool_id
        assert restored.action == original.action
        assert restored.params == original.params
        assert restored.condition == original.condition
        assert restored.fallback_tools == original.fallback_tools
        assert restored.max_retries == original.max_retries
        assert restored.retry_delay_ms == original.retry_delay_ms

    def test_minimal_fields(self):
        """from_dict works with only required fields."""
        data = {"tool_id": "t1", "action": "read"}
        step = WorkflowStep.from_dict(data)
        assert step.tool_id == "t1"
        assert step.action == "read"
        assert step.params == {}
        assert step.condition is None
        assert step.fallback_tools == []
        assert step.max_retries == 0
        assert step.retry_delay_ms == 100.0

    def test_params_copied(self):
        """from_dict copies params dict."""
        params = {"key": "value"}
        data = {"tool_id": "t1", "action": "read", "params": params}
        step = WorkflowStep.from_dict(data)
        params["new"] = "added"
        assert "new" not in step.params

    def test_fallback_tools_copied(self):
        """from_dict copies fallback_tools list."""
        fallbacks = ["backup-1"]
        data = {"tool_id": "t1", "action": "read", "fallback_tools": fallbacks}
        step = WorkflowStep.from_dict(data)
        fallbacks.append("backup-2")
        assert "backup-2" not in step.fallback_tools


# ---------------------------------------------------------------------------
# Workflow.from_dict()
# ---------------------------------------------------------------------------

class TestWorkflowFromDict:
    """Tests for Workflow.from_dict() deserialization."""

    def test_basic_roundtrip(self):
        """from_dict(to_dict()) should produce an equivalent object."""
        original = Workflow(
            id="wf-001",
            name="Deploy Pipeline",
            description="Full deployment workflow",
            steps=[
                WorkflowStep(tool_id="build-tool", action="build", params={"target": "prod"}),
                WorkflowStep(tool_id="test-tool", action="run_tests"),
                WorkflowStep(tool_id="deploy-tool", action="deploy"),
            ],
            trigger=WorkflowTrigger.MANUAL.value,
            status=WorkflowStatus.ACTIVE.value,
            created_by="admin",
        )
        data = original.to_dict()
        restored = Workflow.from_dict(data)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.description == original.description
        assert len(restored.steps) == len(original.steps)
        assert restored.trigger == original.trigger
        assert restored.status == original.status
        assert restored.created_by == original.created_by

    def test_minimal_fields(self):
        """from_dict works with only required fields."""
        data = {
            "id": "wf-min",
            "name": "Minimal",
            "steps": [{"tool_id": "t1", "action": "read"}],
        }
        wf = Workflow.from_dict(data)
        assert wf.id == "wf-min"
        assert wf.name == "Minimal"
        assert wf.description == ""
        assert wf.trigger == WorkflowTrigger.MANUAL.value
        assert wf.status == WorkflowStatus.ACTIVE.value
        assert wf.created_by == "system"
        assert len(wf.steps) == 1

    def test_steps_are_workflowstep_instances(self):
        """from_dict reconstructs steps as WorkflowStep objects."""
        data = {
            "id": "wf-002",
            "name": "Multi-step",
            "steps": [
                {"tool_id": "t1", "action": "a1"},
                {"tool_id": "t2", "action": "a2"},
            ],
        }
        wf = Workflow.from_dict(data)
        assert all(isinstance(s, WorkflowStep) for s in wf.steps)
        assert wf.steps[0].tool_id == "t1"
        assert wf.steps[1].action == "a2"

    def test_empty_steps(self):
        """from_dict handles empty steps list."""
        data = {"id": "wf-empty", "name": "Empty", "steps": []}
        wf = Workflow.from_dict(data)
        assert wf.steps == []

    def test_validate_after_from_dict(self):
        """Workflows created via from_dict should be validatable."""
        data = {
            "id": "wf-valid",
            "name": "Valid Workflow",
            "steps": [{"tool_id": "t1", "action": "read"}],
        }
        wf = Workflow.from_dict(data)
        errors = wf.validate()
        assert errors == []

    def test_validate_catches_empty_name(self):
        """from_dict with empty name should fail validation."""
        data = {"id": "wf-bad", "name": "", "steps": [{"tool_id": "t1", "action": "read"}]}
        wf = Workflow.from_dict(data)
        errors = wf.validate()
        assert any("name" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------

class TestModuleExports:
    """Verify __all__ exports are correct and complete."""

    def test_models_all_exports(self):
        """models.__all__ should list all public model classes."""
        from nexus.core import models
        expected = {
            "AgentToolBinding", "CallStatus", "PermissionLevel",
            "PluginStatus", "PluginType", "ToolCall", "ToolPlugin",
            "Workflow", "WorkflowStatus", "WorkflowStep",
            "WorkflowTrigger", "utcnow",
        }
        assert set(models.__all__) == expected

    def test_metrics_all_exports(self):
        """metrics.__all__ should export UsageMetrics."""
        from nexus.metrics import metrics
        assert "UsageMetrics" in metrics.__all__

    def test_all_exports_are_importable(self):
        """Every name in models.__all__ should be importable from the module."""
        from nexus.core import models
        for name in models.__all__:
            assert hasattr(models, name), f"{name} listed in __all__ but not in module"

    def test_key_classes_importable_from_top_level(self):
        """Key classes should be importable from nexus package."""
        from nexus import AgentToolBinding, ToolPlugin, Workflow, WorkflowStep
        assert AgentToolBinding is not None
        assert ToolPlugin is not None
        assert Workflow is not None
        assert WorkflowStep is not None
