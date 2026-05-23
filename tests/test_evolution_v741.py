"""Tests for OMEGA Evolution v7.41 — New features:
- CallRequest input validation (agent_id, action)
- GET /agents/{agent_id}/calls paginated endpoint
- GET /workflows/{id}/runs endpoint
- PATCH /workflows/{id} partial update endpoint
- StepResult.to_dict()
- WorkflowBuilder __repr__
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus.composition.workflow import StepResult, WorkflowBuilder
from nexus.core.db import NexusStore
from nexus.core.models import WorkflowStep
from nexus.server.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a fresh test client with initialized app."""
    app = create_app()
    # Initialize plugins
    client = TestClient(app)
    client.post("/init")
    return client


@pytest.fixture
def client_with_agent(client: TestClient) -> TestClient:
    """Client with a registered agent and binding."""
    client.post("/bindings", json={"agent_id": "agent-1", "tool_id": "http", "level": "admin"})
    return client


class TestCallRequestValidation:
    """Test that CallRequest validates agent_id and action fields."""

    def test_empty_agent_id_rejected(self, client_with_agent: TestClient):
        """Test: empty agent id rejected."""
        resp = client_with_agent.post("/tools/http/call", json={
            "agent_id": "",
            "tool_id": "http",
            "action": "get",
        })
        assert resp.status_code == 422

    def test_whitespace_agent_id_rejected(self, client_with_agent: TestClient):
        """Test: whitespace agent id rejected."""
        resp = client_with_agent.post("/tools/http/call", json={
            "agent_id": "   ",
            "tool_id": "http",
            "action": "get",
        })
        assert resp.status_code == 422

    def test_empty_action_rejected(self, client_with_agent: TestClient):
        """Test: empty action rejected."""
        resp = client_with_agent.post("/tools/http/call", json={
            "agent_id": "agent-1",
            "tool_id": "http",
            "action": "",
        })
        assert resp.status_code == 422

    def test_whitespace_action_rejected(self, client_with_agent: TestClient):
        """Test: whitespace action rejected."""
        resp = client_with_agent.post("/tools/http/call", json={
            "agent_id": "agent-1",
            "tool_id": "http",
            "action": "   ",
        })
        assert resp.status_code == 422

    def test_valid_call_request_accepted(self, client_with_agent: TestClient):
        """Test: valid call request accepted."""
        resp = client_with_agent.post("/tools/http/call", json={
            "agent_id": "agent-1",
            "tool_id": "http",
            "action": "get",
            "params": {"url": "https://example.com"},
        })
        # Should not be a validation error (may be 200 or 400 depending on actual HTTP)
        assert resp.status_code != 422


class TestAgentCallsEndpoint:
    """Test GET /agents/{agent_id}/calls paginated endpoint."""

    def test_agent_not_found(self, client: TestClient):
        """Test: agent not found."""
        resp = client.get("/agents/nonexistent/calls")
        assert resp.status_code == 404

    def test_empty_calls(self, client_with_agent: TestClient):
        """Test: empty calls."""
        resp = client_with_agent.get("/agents/agent-1/calls")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    def test_pagination(self, client_with_agent: TestClient):
        """Test: pagination."""
        # Make some calls
        for i in range(5):
            client_with_agent.post("/tools/http/call", json={
                "agent_id": "agent-1",
                "tool_id": "http",
                "action": "get",
                "params": {"url": f"https://example.com/{i}"},
            })
        # Get first page
        resp = client_with_agent.get("/agents/agent-1/calls?offset=0&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] >= 2
        assert data["has_more"] is True

    def test_status_filter(self, client_with_agent: TestClient):
        """Test: status filter."""
        # Make a call
        client_with_agent.post("/tools/http/call", json={
            "agent_id": "agent-1",
            "tool_id": "http",
            "action": "get",
            "params": {"url": "https://example.com"},
        })
        resp = client_with_agent.get("/agents/agent-1/calls?status=success")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["status"] == "success"

    def test_response_structure(self, client_with_agent: TestClient):
        """Test: response structure."""
        client_with_agent.post("/tools/http/call", json={
            "agent_id": "agent-1",
            "tool_id": "http",
            "action": "get",
            "params": {"url": "https://example.com"},
        })
        resp = client_with_agent.get("/agents/agent-1/calls")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert "has_more" in data
        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "tool_id" in item
            assert "action" in item
            assert "status" in item
            assert "duration_ms" in item
            assert "called_at" in item


class TestWorkflowRunsEndpoint:
    """Test GET /workflows/{id}/runs endpoint."""

    def test_workflow_not_found(self, client: TestClient):
        """Test: workflow not found."""
        resp = client.get("/workflows/nonexistent/runs")
        assert resp.status_code == 404

    def test_empty_runs(self, client_with_agent: TestClient):
        """Test: empty runs."""
        # Create a workflow
        resp = client_with_agent.post("/workflows", json={
            "name": "test-wf",
            "steps": [{"tool_id": "http", "action": "get"}],
            "created_by": "test",
        })
        wf_id = resp.json()["id"]
        # Get runs (should be empty)
        resp = client_with_agent.get(f"/workflows/{wf_id}/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_runs_after_execution(self, client_with_agent: TestClient):
        """Test: runs after execution."""
        # Create and run a workflow
        resp = client_with_agent.post("/workflows", json={
            "name": "test-wf",
            "steps": [{"tool_id": "http", "action": "get", "params": {"url": "https://example.com"}}],
            "created_by": "test",
        })
        wf_id = resp.json()["id"]
        client_with_agent.post(f"/workflows/{wf_id}/run?agent_id=agent-1")
        # Get runs
        resp = client_with_agent.get(f"/workflows/{wf_id}/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1


class TestPatchWorkflowEndpoint:
    """Test PATCH /workflows/{id} partial update endpoint."""

    @pytest.fixture
    def workflow_id(self, client_with_agent: TestClient) -> str:
        """workflow id."""
        resp = client_with_agent.post("/workflows", json={
            "name": "original-name",
            "description": "original-desc",
            "steps": [{"tool_id": "http", "action": "get"}],
            "created_by": "test",
        })
        return resp.json()["id"]

    def test_patch_name_only(self, client_with_agent: TestClient, workflow_id: str):
        """Test: patch name only."""
        resp = client_with_agent.patch(f"/workflows/{workflow_id}", json={
            "name": "updated-name",
            "steps": [],
            "created_by": "test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated-name"

    def test_patch_description_only(self, client_with_agent: TestClient, workflow_id: str):
        """Test: patch description only."""
        resp = client_with_agent.patch(f"/workflows/{workflow_id}", json={
            "description": "updated-desc",
            "steps": [],
            "created_by": "test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "updated-desc"

    def test_patch_not_found(self, client_with_agent: TestClient):
        """Test: patch not found."""
        resp = client_with_agent.patch("/workflows/nonexistent", json={
            "name": "new-name",
            "steps": [],
            "created_by": "test",
        })
        assert resp.status_code == 404

    def test_patch_preserves_unmodified_fields(self, client_with_agent: TestClient, workflow_id: str):
        """Test: patch preserves unmodified fields."""
        # Get original
        resp = client_with_agent.get(f"/workflows/{workflow_id}")
        original_name = resp.json()["name"]
        # Patch only description
        resp = client_with_agent.patch(f"/workflows/{workflow_id}", json={
            "description": "new-desc",
            "steps": [],
            "created_by": "test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == original_name
        assert data["description"] == "new-desc"


class TestStepResultToDict:
    """Test StepResult.to_dict() method."""

    def test_success_result(self):
        """Test: success result."""
        r = StepResult(step_index=0, tool_id="http", action="get", result="ok", duration_ms=42.5, success=True)
        d = r.to_dict()
        assert d["step_index"] == 0
        assert d["tool_id"] == "http"
        assert d["action"] == "get"
        assert d["result"] == "ok"
        assert d["duration_ms"] == 42.5
        assert d["success"] is True
        assert d["error"] is None

    def test_failure_result(self):
        """Test: failure result."""
        r = StepResult(step_index=1, tool_id="db", action="query", error="timeout", duration_ms=100.0, success=False)
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "timeout"
        assert d["result"] is None


class TestWorkflowBuilderRepr:
    """Test WorkflowBuilder.__repr__."""

    def test_repr_empty(self):
        """Test: repr empty."""
        store = NexusStore()
        wb = WorkflowBuilder(store)
        assert "workflows=0" in repr(wb)

    def test_repr_with_workflows(self):
        """Test: repr with workflows."""
        store = NexusStore()
        wb = WorkflowBuilder(store)
        wb.create("test", [{"tool_id": "http", "action": "get"}], "admin")
        assert "workflows=1" in repr(wb)
