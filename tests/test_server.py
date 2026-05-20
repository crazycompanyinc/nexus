from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus.server.app import create_app, RateLimitMiddleware


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestVersionEndpoint:
    def test_version_returns_semver(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)


class TestPagination:
    def test_plugins_pagination_default(self, client):
        resp = client.get("/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert "has_more" in data
        assert data["offset"] == 0

    def test_plugins_pagination_offset(self, client):
        resp = client.get("/plugins?offset=0&limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 1
        assert len(data["items"]) <= 1

    def test_workflows_pagination_default(self, client):
        resp = client.get("/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "has_more" in data


class TestRateLimitMiddleware:
    def test_allows_under_limit(self):
        rl = RateLimitMiddleware(max_requests=5, window_seconds=60)
        # Simulate 4 requests — all should pass
        import asyncio

        async def simulate():
            from starlette.requests import Request
            from starlette.datastructures import Address

            results = []
            for _ in range(4):
                scope = {
                    "type": "http",
                    "client": Address("127.0.0.1", 12345),
                    "method": "GET",
                    "path": "/test",
                    "query_string": b"",
                    "headers": [],
                }
                req = Request(scope)
                result = await rl.check(req)
                results.append(result)
            return results

        results = asyncio.run(simulate())
        assert all(r is None for r in results), "All requests under limit should pass"

    def test_blocks_over_limit(self):
        rl = RateLimitMiddleware(max_requests=3, window_seconds=60)
        import asyncio

        async def simulate():
            from starlette.requests import Request
            from starlette.datastructures import Address

            results = []
            for _ in range(5):
                scope = {
                    "type": "http",
                    "client": Address("127.0.0.1", 12345),
                    "method": "GET",
                    "path": "/test",
                    "query_string": b"",
                    "headers": [],
                }
                req = Request(scope)
                result = await rl.check(req)
                results.append(result)
            return results

        results = asyncio.run(simulate())
        # First 3 should pass, last 2 should be blocked
        assert results[0] is None
        assert results[1] is None
        assert results[2] is None
        assert results[3] is not None  # blocked
        assert results[4] is not None  # blocked
        assert results[3].status_code == 429
