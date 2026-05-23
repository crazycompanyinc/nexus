"""Tests for the Nexus permissions and access control system.

Covers PermissionLevel checks, agent-tool binding permissions,
access denial for insufficient privileges, and admin override.
"""
from __future__ import annotations

import pytest

from nexus.permissions.permissions import PermissionModel


def test_permission_model_maps_read_action():
    """Test: permission model maps read action."""
    assert PermissionModel().required_for_action("repos.list") == "read"


def test_permission_model_maps_write_action():
    """Test: permission model maps write action."""
    assert PermissionModel().required_for_action("messages.send") == "write"


def test_permission_model_maps_admin_action():
    """Test: permission model maps admin action."""
    assert PermissionModel().required_for_action("deployments.restart") == "admin"


def test_grant_allows_read_call(hub):
    """Test: grant allows read call."""
    _, _, api = hub
    api.grant("agent", "github", "read")
    assert api.call("agent", "github", "repos.list", {})[0]["name"] == "nexus"


def test_read_cannot_write(hub):
    """Test: read cannot write."""
    _, _, api = hub
    api.grant("agent", "slack", "read")
    with pytest.raises(PermissionError):
        api.call("agent", "slack", "messages.send", {"text": "no"})


def test_write_allows_read_and_write(hub):
    """Test: write allows read and write."""
    _, _, api = hub
    api.grant("agent", "slack", "write")
    assert api.call("agent", "slack", "channels.list", {})
    assert api.call("agent", "slack", "messages.send", {"text": "yes"})["sent"]


def test_admin_required_for_delete(hub):
    """Test: admin required for delete."""
    _, _, api = hub
    api.grant("agent", "http", "write")
    with pytest.raises(PermissionError):
        api.call("agent", "http", "request.delete", {"url": "https://example.test"})


def test_denied_call_is_recorded(hub):
    """Test: denied call is recorded."""
    store, _, api = hub
    api.grant("agent", "slack", "read")
    with pytest.raises(PermissionError):
        api.call("agent", "slack", "messages.send", {})
    assert store.calls[-1].status == "denied"


def test_revoke_removes_access(hub):
    """Test: revoke removes access."""
    _, _, api = hub
    api.grant("agent", "github", "read")
    api.access.revoke("agent", "github")
    with pytest.raises(PermissionError):
        api.call("agent", "github", "repos.list", {})
