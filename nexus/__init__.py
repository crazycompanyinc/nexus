"""Nexus universal agent integration hub."""

from nexus.api.unified import UnifiedToolAPI
from nexus.api.async_unified import AsyncUnifiedToolAPI
from nexus.core.models import AgentToolBinding, ToolCall, ToolPlugin, Workflow
from nexus.core.db import NexusStore
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager
from nexus.metrics.metrics import UsageMetrics
from nexus.metrics.performance import PerformanceTracker
from nexus.composition.workflow import WorkflowBuilder, Pipeline

__all__ = [
    "AgentToolBinding",
    "AsyncUnifiedToolAPI",
    "AccessControl",
    "NexusStore",
    "PerformanceTracker",
    "Pipeline",
    "PluginManager",
    "ToolCall",
    "ToolPlugin",
    "UnifiedToolAPI",
    "UsageMetrics",
    "Workflow",
    "WorkflowBuilder",
    "self_evaluate",
]

__version__ = "1.1.1"


def self_evaluate() -> dict:
    """Run Nexus self-evaluation and return the report as a dict.

    Quick health check for the Nexus project. Returns a dict with:
    - total_score: float (0-10)
    - all_passed: bool
    - results: list of dimension results

    Usage:
        import nexus
        report = nexus.self_evaluate()
        if report["total_score"] < 7:
            print("Needs improvement!")
    """
    from nexus.self_evaluate import nexus_self_evaluate
    return nexus_self_evaluate().to_dict()
