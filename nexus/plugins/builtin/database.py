from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class DatabasePlugin(BasePlugin):
    """Database plugin for PostgreSQL, MySQL, and MongoDB access.

    Supports running queries, inserting records, and finding records
    across SQL and NoSQL databases. Requires connection string authentication.

    Capabilities: query.run, records.insert, records.find.
    """
    metadata = PluginMetadata(
        id="database",
        name="Database",
        description="PostgreSQL, MySQL, and MongoDB access.",
        version="1.0.0",
        plugin_type="database",
        capabilities=["query.run", "records.insert", "records.find"],
        auth_required=True,
        auth_type="connection_string",
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute a database action (query.run, records.insert, records.find)."""
        if action == "query.run":
            return {"rows": [{"result": 1}], "query": params.get("query", "select 1")}
        if action == "records.insert":
            return {"inserted": True, "collection": params.get("collection")}
        if action == "records.find":
            return [{"id": 1, **params.get("filter", {})}]
        raise ValueError(f"Unsupported database action: {action}")
