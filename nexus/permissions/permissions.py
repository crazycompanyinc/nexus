from __future__ import annotations

from nexus.core.models import PermissionLevel


class PermissionModel:
    """Defines permission levels and maps actions to required access levels."""

    ORDER = {
        PermissionLevel.READ.value: 1,
        PermissionLevel.WRITE.value: 2,
        PermissionLevel.ADMIN.value: 3,
    }

    ACTION_REQUIREMENTS = {
        "list": PermissionLevel.READ.value,
        "read": PermissionLevel.READ.value,
        "get": PermissionLevel.READ.value,
        "find": PermissionLevel.READ.value,
        "search": PermissionLevel.READ.value,
        "status": PermissionLevel.READ.value,
        "watch": PermissionLevel.READ.value,
        "send": PermissionLevel.WRITE.value,
        "write": PermissionLevel.WRITE.value,
        "create": PermissionLevel.WRITE.value,
        "update": PermissionLevel.WRITE.value,
        "insert": PermissionLevel.WRITE.value,
        "post": PermissionLevel.WRITE.value,
        "put": PermissionLevel.WRITE.value,
        "invoke": PermissionLevel.WRITE.value,
        "restart": PermissionLevel.ADMIN.value,
        "delete": PermissionLevel.ADMIN.value,
        "down": PermissionLevel.ADMIN.value,
    }

    def required_for_action(self, action: str) -> str:
        """Determine the minimum permission level required for a given action.

        Extracts the verb from the action string (e.g. 'list' from 'repos.list')
        and looks it up in ACTION_REQUIREMENTS. Falls back to READ if unknown.

        Args:
            action: The action string, typically in 'resource.verb' format.

        Returns:
            The PermissionLevel value string required for this action.
        """
        verb = action.rsplit(".", 1)[-1]
        return self.ACTION_REQUIREMENTS.get(verb, PermissionLevel.READ.value)

    def allows(self, granted: str, required: str) -> bool:
        """Check if a granted permission level satisfies a required level.

        Args:
            granted: The permission level the agent currently holds.
            required: The minimum permission level needed.

        Returns:
            True if granted level is >= required level.
        """
        return self.ORDER[granted] >= self.ORDER[required]

    def __repr__(self) -> str:
        """Return a summary of the permission model configuration.

        Returns:
            String with the number of levels and mapped actions.
        """
        return (
            f"PermissionModel(levels={len(self.ORDER)}, "
            f"actions={len(self.ACTION_REQUIREMENTS)})"
        )
