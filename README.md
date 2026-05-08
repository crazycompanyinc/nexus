# Nexus

Nexus is a universal agent integration hub: plugins expose a single interface, agents bind to those plugins with explicit permissions, and all tool calls flow through one API for auditing, metrics, composition, and fallback handling.

## Features

- Plugin architecture for APIs, CLIs, libraries, webhooks, and databases
- Unified call API with agent-aware permission checks
- Runtime discovery of plugin capabilities
- Usage tracking and performance statistics
- Workflow composition across multiple tools
- Built-in plugins for GitHub, Slack, Jira, AWS, databases, email, HTTP, filesystem, Docker, and Kubernetes
- FastAPI server and Click CLI

## Quick Start

```bash
pip install -e ".[test]"
nexus demo
nexus serve --port 8000
```

## Plugin SDK

```python
from nexus.plugins import BasePlugin, PluginMetadata, register

class MyPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="my-tool",
        name="my-tool",
        description="Example plugin",
        version="1.0.0",
        plugin_type="library",
        capabilities=["read", "write"],
    )

    def execute(self, action, params):
        return {"action": action, "params": params}

register(MyPlugin())
```

## CLI

```bash
nexus init
nexus register Felix-CTO
nexus install github
nexus bind Felix-CTO --tool github --level admin
nexus call github --agent Felix-CTO --action repos.list
nexus metrics
```
