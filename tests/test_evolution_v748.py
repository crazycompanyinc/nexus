"""Tests for ToolCall.from_dict serialization roundtrip."""
from __future__ import annotations

from datetime import datetime, timezone

from nexus.core.models import CallStatus, ToolCall


class TestToolCallFromDict:
    """Tests for ToolCall.from_dict() reconstruction."""

    def test_basic_from_dict(self) -> None:
        data = {
            "agent_id": "agent-1",
            "tool_id": "http",
            "action": "fetch",
            "params": {"url": "https://example.com"},
        }
        call = ToolCall.from_dict(data)
        assert call.agent_id == "agent-1"
        assert call.tool_id == "http"
        assert call.action == "fetch"
        assert call.params == {"url": "https://example.com"}

    def test_from_dict_preserves_id(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
            "id": "custom-id-123",
        }
        call = ToolCall.from_dict(data)
        assert call.id == "custom-id-123"

    def test_from_dict_generates_id_if_missing(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
        }
        call = ToolCall.from_dict(data)
        assert call.id is not None
        assert len(call.id) > 0

    def test_from_dict_parses_iso_timestamp(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
            "called_at": "2024-06-15T12:30:00+00:00",
        }
        call = ToolCall.from_dict(data)
        assert call.called_at.year == 2024
        assert call.called_at.month == 6
        assert call.called_at.tzinfo is not None

    def test_from_dict_default_status(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
        }
        call = ToolCall.from_dict(data)
        assert call.status == CallStatus.SUCCESS.value

    def test_from_dict_preserves_status(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
            "status": "error",
        }
        call = ToolCall.from_dict(data)
        assert call.status == "error"

    def test_roundtrip(self) -> None:
        original = ToolCall(
            agent_id="agent-x",
            tool_id="slack",
            action="send",
            params={"channel": "#general", "message": "hello"},
            duration_ms=42.5,
            status=CallStatus.SUCCESS.value,
        )
        data = original.to_dict()
        restored = ToolCall.from_dict(data)
        assert restored.agent_id == original.agent_id
        assert restored.tool_id == original.tool_id
        assert restored.action == original.action
        assert restored.params == original.params
        assert restored.duration_ms == original.duration_ms
        assert restored.status == original.status

    def test_from_dict_with_result(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
            "result": {"data": "some result"},
        }
        call = ToolCall.from_dict(data)
        assert call.result == {"data": "some result"}

    def test_from_dict_generates_timestamp_if_missing(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
        }
        call = ToolCall.from_dict(data)
        assert call.called_at is not None
        assert isinstance(call.called_at, datetime)

    def test_from_dict_ignores_extra_keys(self) -> None:
        data = {
            "agent_id": "a1",
            "tool_id": "t1",
            "action": "read",
            "params": {},
            "extra_field": "should be ignored",
            "another_extra": 123,
        }
        call = ToolCall.from_dict(data)
        assert call.agent_id == "a1"
