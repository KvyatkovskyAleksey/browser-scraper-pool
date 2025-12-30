"""API integration tests with real browser.

These tests use actual browser instances to verify end-to-end behavior.
Run with: pytest tests/test_api_integration.py -v
"""

import pytest
from httpx import ASGITransport, AsyncClient

from browser_scraper_pool.main import app
from browser_scraper_pool.pool.context_pool import ContextPool


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    ContextPool.reset_instance()
    yield
    ContextPool.reset_instance()


@pytest.fixture
async def client():
    """Create test client with real browser pool."""
    # Start the pool manually for testing
    pool = ContextPool.get_instance(headless=True, use_virtual_display=False)
    await pool.start()
    app.state.context_pool = pool

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await pool.stop()


# =============================================================================
# Pool Endpoints
# =============================================================================


class TestPoolIntegration:
    """Integration tests for pool endpoints."""

    async def test_pool_status(self, client):
        """Should return real pool status."""
        response = await client.get("/pool/status")

        assert response.status_code == 200
        data = response.json()
        assert data["size"] == 0
        assert data["available"] == 0
        assert data["is_started"] is True
        assert data["cdp_port"] == 9222

    async def test_cdp_endpoint(self, client):
        """Should return valid CDP endpoint."""
        response = await client.get("/pool/cdp")

        assert response.status_code == 200
        data = response.json()
        assert "ws://127.0.0.1:" in data["endpoint"]


# =============================================================================
# Context Lifecycle
# =============================================================================


class TestContextLifecycleIntegration:
    """Integration tests for context lifecycle."""

    async def test_create_and_list_context(self, client):
        """Should create a real context and list it."""
        # Create context
        response = await client.post("/contexts", json={})
        assert response.status_code == 201
        ctx = response.json()
        assert ctx["id"] is not None
        assert ctx["in_use"] is False

        # List contexts
        response = await client.get("/contexts")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["contexts"][0]["id"] == ctx["id"]

    async def test_acquire_release_cycle(self, client):
        """Should acquire and release context."""
        # Create
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]

        # Acquire
        response = await client.post(f"/contexts/{ctx_id}/acquire")
        assert response.status_code == 200
        assert response.json()["in_use"] is True

        # Release
        response = await client.post(f"/contexts/{ctx_id}/release")
        assert response.status_code == 200
        assert response.json()["in_use"] is False

    async def test_delete_context(self, client):
        """Should delete context."""
        # Create
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]

        # Delete
        response = await client.delete(f"/contexts/{ctx_id}")
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/contexts/{ctx_id}")
        assert response.status_code == 404


# =============================================================================
# Scraping Operations
# =============================================================================


class TestScrapingIntegration:
    """Integration tests for scraping operations."""

    async def test_navigate_and_get_content(self, client):
        """Should navigate to URL and get content."""
        # Create and acquire
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]
        await client.post(f"/contexts/{ctx_id}/acquire")

        # Navigate
        response = await client.post(
            f"/contexts/{ctx_id}/goto",
            json={"url": "https://example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == 200
        assert data["ok"] is True

        # Get content
        response = await client.post(f"/contexts/{ctx_id}/content")
        assert response.status_code == 200
        data = response.json()
        assert "Example Domain" in data["content"]

        # Cleanup
        await client.post(f"/contexts/{ctx_id}/release")

    async def test_execute_javascript(self, client):
        """Should execute JavaScript and return result."""
        # Create and acquire
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]
        await client.post(f"/contexts/{ctx_id}/acquire")

        # Navigate first
        await client.post(
            f"/contexts/{ctx_id}/goto",
            json={"url": "https://example.com"},
        )

        # Execute JS
        response = await client.post(
            f"/contexts/{ctx_id}/execute",
            json={"script": "document.title"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "Example" in data["result"]

        # Execute with object return
        response = await client.post(
            f"/contexts/{ctx_id}/execute",
            json={"script": "({ a: 1, b: 2 })"},
        )
        assert response.status_code == 200
        assert response.json()["result"] == {"a": 1, "b": 2}

        # Cleanup
        await client.post(f"/contexts/{ctx_id}/release")

    async def test_take_screenshot(self, client):
        """Should take screenshot and return base64."""
        # Create and acquire
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]
        await client.post(f"/contexts/{ctx_id}/acquire")

        # Navigate
        await client.post(
            f"/contexts/{ctx_id}/goto",
            json={"url": "https://example.com"},
        )

        # Screenshot
        response = await client.post(
            f"/contexts/{ctx_id}/screenshot",
            json={"format": "png"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "png"
        assert len(data["data"]) > 100  # Base64 should be substantial

        # Cleanup
        await client.post(f"/contexts/{ctx_id}/release")


# =============================================================================
# Error Handling
# =============================================================================


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""

    async def test_scraping_without_acquire(self, client):
        """Should return 409 when scraping without acquire."""
        # Create but don't acquire
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]

        # Try to navigate
        response = await client.post(
            f"/contexts/{ctx_id}/goto",
            json={"url": "https://example.com"},
        )
        assert response.status_code == 409
        assert "acquire" in response.json()["detail"].lower()

    async def test_invalid_url_validation(self, client):
        """Should reject invalid URLs at validation."""
        # Create and acquire
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]
        await client.post(f"/contexts/{ctx_id}/acquire")

        # Try invalid URL
        response = await client.post(
            f"/contexts/{ctx_id}/goto",
            json={"url": "not-a-valid-url"},
        )
        assert response.status_code == 422  # Validation error

        # Cleanup
        await client.post(f"/contexts/{ctx_id}/release")

    async def test_navigation_timeout(self, client):
        """Should handle navigation timeout."""
        # Create and acquire
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]
        await client.post(f"/contexts/{ctx_id}/acquire")

        # Try to navigate to non-responsive IP with short timeout
        response = await client.post(
            f"/contexts/{ctx_id}/goto",
            json={"url": "http://10.255.255.1", "timeout": 2000},
        )
        assert response.status_code == 502
        assert "failed" in response.json()["detail"].lower()

        # Cleanup
        await client.post(f"/contexts/{ctx_id}/release")

    async def test_delete_context_in_use(self, client):
        """Should reject deleting context in use."""
        # Create and acquire
        response = await client.post("/contexts", json={})
        ctx_id = response.json()["id"]
        await client.post(f"/contexts/{ctx_id}/acquire")

        # Try to delete
        response = await client.delete(f"/contexts/{ctx_id}")
        assert response.status_code == 409

        # Cleanup
        await client.post(f"/contexts/{ctx_id}/release")
