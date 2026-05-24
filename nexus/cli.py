from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import click
import uvicorn

from nexus.api.unified import UnifiedToolAPI
from nexus.composition.workflow import Pipeline, WorkflowBuilder
from nexus.core.db import NexusStore
from nexus.discovery.discovery import ToolDiscovery
from nexus.metrics.metrics import UsageMetrics
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager
from nexus.server.app import create_app


class Runtime:
    """Holds the shared runtime state for CLI commands.

    Manages the store, plugin manager, API, workflow builder, and pipeline
    used by all CLI command handlers.
    """

    def __init__(self) -> None:
        """Initialize the runtime with store, plugin manager, API, and workflow components.

        Creates all shared Nexus components with default configuration.
        """
        self.store = NexusStore()
        self.manager = PluginManager(self.store)
        self.api = UnifiedToolAPI(self.store, self.manager, AccessControl(self.store))
        self.workflows = WorkflowBuilder(self.store)
        self.pipeline = Pipeline(self.api, self.store)


runtime = Runtime()


def emit(value: Any) -> None:
    """Pretty-print a value as JSON to stdout.

    Args:
        value: The value to serialize and print.
    """
    click.echo(json.dumps(value, default=str, indent=2))


@click.group()
def cli() -> None:
    """Nexus universal agent integration hub."""


@cli.command()
def init() -> None:
    """Install all built-in plugins."""
    emit({"installed": [plugin.id for plugin in runtime.manager.install_all_builtins()]})


@cli.command()
@click.argument("agent_id")
def register(agent_id: str) -> None:
    """Register a new agent.

    Args:
        agent_id: Unique identifier for the agent.
    """
    runtime.store.register_agent(agent_id)
    runtime.store.audit("agent.registered", agent_id=agent_id)
    emit({"agent_id": agent_id, "registered": True})


@cli.command()
@click.argument("plugin")
def install(plugin: str) -> None:
    """Install a built-in plugin by ID.

    Args:
        plugin: The plugin identifier to install.
    """
    emit(asdict(runtime.manager.install_builtin(plugin)))


@cli.command("plugins")
@click.option("--discover", is_flag=True)
def list_plugins(discover: bool) -> None:
    """List installed plugins or discover available tools.

    Args:
        discover: If set, show all discoverable tools instead of installed plugins.
    """
    if discover:
        emit(ToolDiscovery(runtime.manager).available_tools())
    else:
        emit([asdict(plugin) for plugin in runtime.manager.list_plugins()])


@cli.command()
@click.argument("agent")
@click.option("--tool", "tool_id", required=True)
@click.option("--level", default="read", type=click.Choice(["read", "write", "admin"]))
def bind(agent: str, tool_id: str, level: str) -> None:
    """Bind a tool to an agent with a permission level.

    Args:
        agent: The agent identifier.
        tool_id: The tool identifier.
        level: Permission level (read, write, admin).
    """
    emit(asdict(runtime.api.access.grant(agent, tool_id, level)))


@cli.command()
@click.argument("agent")
@click.option("--tool", "tool_id", required=True)
def unbind(agent: str, tool_id: str) -> None:
    """Remove a tool binding from an agent.

    Args:
        agent: The agent identifier.
        tool_id: The tool identifier.
    """
    runtime.api.access.revoke(agent, tool_id)
    emit({"agent_id": agent, "tool_id": tool_id, "bound": False})


@cli.command("call")
@click.argument("tool")
@click.option("--agent", "agent_id", default="cli-agent")
@click.option("--action", required=True)
@click.option("--params", default="{}")
def call_tool(tool: str, agent_id: str, action: str, params: str) -> None:
    """Invoke a tool action as an agent.

    Args:
        tool: The tool identifier.
        agent_id: The agent making the call (default: cli-agent).
        action: The action to execute.
        params: JSON string of parameters.
    """
    emit(runtime.api.call(agent_id, tool, action, json.loads(params)))


@cli.group()
def workflow() -> None:
    """Manage workflows."""


@workflow.command("create")
@click.option("--name", required=True)
@click.option("--steps", required=True)
@click.option("--created-by", default="cli-agent")
def workflow_create(name: str, steps: str, created_by: str) -> None:
    """Create a new workflow.

    Args:
        name: Human-readable workflow name.
        steps: JSON array of step definitions.
        created_by: Agent identifier for the creator.
    """
    emit(asdict(runtime.workflows.create(name, json.loads(steps), created_by)))


@workflow.command("run")
@click.argument("workflow_id")
@click.option("--agent", "agent_id", default="cli-agent")
def workflow_run(workflow_id: str, agent_id: str) -> None:
    """Execute a workflow by its ID.

    Args:
        workflow_id: The unique workflow identifier.
        agent_id: The agent to run the workflow as.
    """
    step_results = runtime.pipeline.run(workflow_id, agent_id)
    emit(
        {
            "results": [
                {
                    "step": r.step_index,
                    "tool_id": r.tool_id,
                    "action": r.action,
                    "success": r.success,
                    "result": r.result,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
                for r in step_results
            ],
            "succeeded": sum(1 for r in step_results if r.success),
            "failed": sum(1 for r in step_results if not r.success),
        }
    )


@cli.command()
def workflows() -> None:
    """List all workflows."""
    emit([asdict(workflow) for workflow in runtime.store.workflows.values()])


@cli.command()
@click.argument("agent")
def permissions(agent: str) -> None:
    """List permissions for an agent.

    Args:
        agent: The agent identifier.
    """
    emit([asdict(binding) for binding in runtime.api.access.list_agent_permissions(agent)])


@cli.command()
@click.argument("agent")
@click.option("--tool", "tool_id", required=True)
@click.option("--level", required=True, type=click.Choice(["read", "write", "admin"]))
def grant(agent: str, tool_id: str, level: str) -> None:
    """Grant a permission level on a tool to an agent.

    Args:
        agent: The agent identifier.
        tool_id: The tool identifier.
        level: Permission level (read, write, admin).
    """
    emit(asdict(runtime.api.access.grant(agent, tool_id, level)))


@cli.command()
def metrics() -> None:
    """Display current usage metrics summary."""
    emit(UsageMetrics(runtime.store).summary())


@cli.command()
def health() -> None:
    """Display plugin health status."""
    emit(runtime.manager.health())


@cli.command()
def status() -> None:
    """Display a formatted overview: plugins, agents, metrics, and health."""
    try:
        plugins = runtime.manager.list_plugins()
        agents = sorted(runtime.store.agents)
        health_info = runtime.manager.health()
        metrics_info = UsageMetrics(runtime.store).summary()
    except Exception as exc:
        click.echo(f"❌ Error collecting status: {exc}", err=True)
        raise SystemExit(1) from exc

    # Plugin summary table
    plugin_lines = []
    for p in plugins:
        status_icon = "🟢" if p.status == "active" else "🔴"
        caps = ", ".join(p.capabilities[:3])
        if len(p.capabilities) > 3:
            caps += f" (+{len(p.capabilities) - 3})"
        plugin_lines.append(f"  {status_icon} {p.id:<20} {p.version:<8} [{caps}]")

    # Health summary
    health_entries = health_info if isinstance(health_info, list) else []
    healthy = sum(1 for h in health_entries if isinstance(h, dict) and h.get("status") == "active")
    unhealthy = len(health_entries) - healthy

    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        "║                   NEXUS STATUS OVERVIEW                 ║",
        "╠══════════════════════════════════════════════════════════╣",
        f"║  Agents:   {len(agents):<46}║",
        f"║  Plugins:  {len(plugins):<46}║",
        f"║  Healthy:  {healthy:<46}║",
        f"║  Issues:   {unhealthy:<46}║",
        "╠══════════════════════════════════════════════════════════╣",
        "║  PLUGINS                                               ║",
        "╠══════════════════════════════════════════════════════════╣",
    ]
    for pl in plugin_lines:
        # Pad to fit box width (58 chars inside box)
        padded = pl[:56].ljust(56)
        lines.append(f"║{padded}  ║")
    lines.append("╚══════════════════════════════════════════════════════════╝")

    click.echo("\n".join(lines))

    # Emit raw data as JSON below the formatted output
    emit({
        "agents": agents,
        "plugins": [p.to_dict() for p in plugins],
        "health": health_info,
        "metrics": metrics_info,
    })


@cli.command()
@click.option("--port", default=8000)
def serve(port: int) -> None:
    """Start the Nexus FastAPI server.

    Args:
        port: Port number to bind the server to (default: 8000).
    """
    uvicorn.run(create_app(), host="127.0.0.1", port=port)


@cli.command()
def demo() -> None:
    """Run a demo: install builtins, register agents, grant permissions, and call tools."""
    try:
        _run_demo()
    except Exception as exc:
        click.echo(f"❌ Demo failed: {exc}", err=True)
        raise SystemExit(1) from exc


def _run_demo() -> None:
    """Internal demo implementation (separated for error handling)."""
    runtime.manager.install_all_builtins()
    for agent in ["Felix-CTO", "Agent-Alpha", "Felix-Jim"]:
        runtime.store.register_agent(agent)
    runtime.api.grant("Felix-CTO", "github", "admin")
    runtime.api.grant("Felix-CTO", "jira", "write")
    runtime.api.grant("Agent-Alpha", "github", "read")
    runtime.api.grant("Agent-Alpha", "filesystem", "write")
    runtime.api.grant("Felix-Jim", "slack", "write")
    runtime.api.grant("Felix-Jim", "filesystem", "read")
    calls = [
        runtime.api.call("Felix-CTO", "github", "repos.list", {}),
        runtime.api.call("Agent-Alpha", "filesystem", "file.read", {"path": "README.md"}),
        runtime.api.call("Felix-Jim", "slack", "messages.send", {"channel": "#deploys", "text": "Deploy started"}),
    ]
    workflow = runtime.workflows.create(
        "Deploy notification",
        [
            {"tool_id": "github", "action": "prs.create", "params": {"title": "Release Nexus"}},
            {"tool_id": "slack", "action": "messages.send", "params": {"channel": "#deploys", "text": "PR created"}},
            {"tool_id": "jira", "action": "tickets.update", "params": {"key": "NEX-1"}},
        ],
        created_by="Felix-CTO",
    )
    runtime.api.grant("Felix-CTO", "slack", "write")
    workflow_results = runtime.pipeline.run(workflow.id, "Felix-CTO")
    emit(
        {
            "agents": sorted(runtime.store.agents),
            "calls": calls,
            "workflow": asdict(workflow),
            "workflow_results": [
                {
                    "step": r.step_index,
                    "tool_id": r.tool_id,
                    "action": r.action,
                    "success": r.success,
                    "result": r.result,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
                for r in workflow_results
            ],
            "metrics": UsageMetrics(runtime.store).summary(),
            "audit": runtime.store.audit_events,
        }
    )


if __name__ == "__main__":
    cli()
