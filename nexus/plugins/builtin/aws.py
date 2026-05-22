from __future__ import annotations

from typing import Any

from nexus.plugins.sdk import BasePlugin, PluginMetadata


class AWSPlugin(BasePlugin):
    metadata = PluginMetadata(
        id="aws",
        name="AWS",
        description="EC2, S3, Lambda, and CloudWatch operations.",
        version="1.0.0",
        plugin_type="api",
        capabilities=["ec2.list", "s3.list", "lambda.invoke", "cloudwatch.metrics"],
        auth_required=True,
        auth_type="iam",
    )

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute an AWS service action.

        Supports: ec2.list, s3.list, lambda.invoke, cloudwatch.metrics.

        Args:
            action: The AWS service action to perform.
            params: Action-specific parameters.

        Returns:
            Dict or list with the action result data.

        Raises:
            ValueError: If the action is not supported.
        """
        if action == "ec2.list":
            return [{"id": "i-123", "state": "running"}]
        if action == "s3.list":
            return [{"bucket": "nexus-artifacts"}]
        if action == "lambda.invoke":
            return {"function": params.get("function"), "status_code": 200}
        if action == "cloudwatch.metrics":
            return {"metric": params.get("metric", "Invocations"), "points": [1, 2, 3]}
        raise ValueError(f"Unsupported AWS action: {action}")
