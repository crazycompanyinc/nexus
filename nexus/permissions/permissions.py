from __future__ import annotations

from nexus.core.models import PermissionLevel


class PermissionModel:
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
        verb = action.rsplit(".", 1)[-1]
        return self.ACTION_REQUIREMENTS.get(verb, PermissionLevel.READ.value)

    def allows(self, granted: str, required: str) -> bool:
        return self.ORDER[granted] >= self.ORDER[required]
