"""API endpoint tests using httpx AsyncClient."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from browser_scraper_pool.main import app
from browser_scraper_pool.pool.context_pool import (
    ContextInUseError,
    ContextNotAvailableError,
    ContextNotFoundError,
    ContextPool,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    ContextPool.reset_instance()
    yield
    ContextPool.reset_instance()


@pytest.fixture
def mock_pool():
    """Create a mock pool with common methods."""
    pool = MagicMock(spec=ContextPool)
    pool.size = 0
    pool.available_count = 0
    pool.cdp_port = 9222
    pool.is_started = True
    pool.get_cdp_endpoint.return_value = (
        "ws://127.0.0.1:9222/devtools/browser/mock-guid"
    )
    pool.list_contexts.return_value = []
    pool.get_context.return_value = None
    return pool


@pytest.fixture
async def client(mock_pool):
    """Create test client with mocked pool."""
    app.state.context_pool = mock_pool
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Root and Health Endpoints
# =============================================================================


class TestRootEndpoints:
    """Tests for root and health check endpoints."""

    async def test_root(self, client):
        """Root endpoint should return welcome message."""
        response = await client.get("/")
        assert response.status_code == 200
        assert "Browser Scraper Pool API" in response.json()["message"]

    async def test_healthz(self, client, mock_pool):
        """Health endpoint should return pool status."""
        mock_pool.size = 2
        mock_pool.available_count = 1
        mock_pool.cdp_port = 9222

        response = await client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["contexts"] == 2
        assert data["available_contexts"] == 1
        assert data["cdp_port"] == 9222


# =============================================================================
# Pool Endpoints
# =============================================================================


class TestPoolEndpoints:
    """Tests for pool status endpoints."""

    async def test_get_status(self, client, mock_pool):
        """Should return pool status."""
        mock_pool.size = 3
        mock_pool.available_count = 2

        response = await client.get("/pool/status")

        assert response.status_code == 200
        data = response.json()
        assert data["size"] == 3
        assert data["available"] == 2
        assert data["in_use"] == 1
        assert data["cdp_port"] == 9222
        # CDP endpoint includes browser GUID for connect_over_cdp
        assert data["cdp_endpoint"].startswith("ws://127.0.0.1:9222/devtools/browser/")
        assert data["is_started"] is True

    async def test_get_cdp(self, client, mock_pool):
        """Should return CDP endpoint info."""
        response = await client.get("/pool/cdp")

        assert response.status_code == 200
        data = response.json()
        # CDP endpoint includes browser GUID for connect_over_cdp
        assert data["endpoint"].startswith("ws://127.0.0.1:9222/devtools/browser/")
        assert data["port"] == 9222


# =============================================================================
# Context CRUD Endpoints
# =============================================================================


class TestContextCRUD:
    """Tests for context CRUD operations."""

    async def test_create_context(self, client, mock_pool):
        """Should create a new context."""
        mock_ctx = MagicMock()
        mock_ctx.id = "ctx-123"
        mock_ctx.proxy = None
        mock_ctx.persistent = False
        mock_ctx.in_use = False
        mock_ctx.created_at = datetime.now(UTC)
        mock_ctx.tags = set()
        mock_ctx.last_used_at = None
        mock_ctx.total_requests = 0
        mock_ctx.error_count = 0
        mock_ctx.consecutive_errors = 0
        mock_ctx.cdp_target_url = "ws://127.0.0.1:9222/devtools/page/test-target"

        mock_pool.create_context = AsyncMock(return_value=mock_ctx)

        response = await client.post("/contexts", json={})

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "ctx-123"
        assert data["proxy"] is None
        assert data["persistent"] is False
        assert data["in_use"] is False
        mock_pool.create_context.assert_called_once_with(
            proxy=None, persistent=False, tags=[]
        )

    async def test_create_context_with_proxy(self, client, mock_pool):
        """Should create context with proxy."""
        mock_ctx = MagicMock()
        mock_ctx.id = "ctx-456"
        mock_ctx.proxy = "http://proxy:8080"
        mock_ctx.persistent = False
        mock_ctx.in_use = False
        mock_ctx.created_at = datetime.now(UTC)
        mock_ctx.tags = {"proxy:http://proxy:8080"}
        mock_ctx.last_used_at = None
        mock_ctx.total_requests = 0
        mock_ctx.error_count = 0
        mock_ctx.consecutive_errors = 0
        mock_ctx.cdp_target_url = "ws://127.0.0.1:9222/devtools/page/test-target"

        mock_pool.create_context = AsyncMock(return_value=mock_ctx)

        response = await client.post("/contexts", json={"proxy": "http://proxy:8080"})

        assert response.status_code == 201
        data = response.json()
        assert data["proxy"] == "http://proxy:8080"
        mock_pool.create_context.assert_called_once_with(
            proxy="http://proxy:8080", persistent=False, tags=[]
        )

    async def test_create_context_persistent(self, client, mock_pool):
        """Should create persistent context."""
        mock_ctx = MagicMock()
        mock_ctx.id = "ctx-789"
        mock_ctx.proxy = None
        mock_ctx.persistent = True
        mock_ctx.in_use = False
        mock_ctx.created_at = datetime.now(UTC)
        mock_ctx.tags = set()
        mock_ctx.last_used_at = None
        mock_ctx.total_requests = 0
        mock_ctx.error_count = 0
        mock_ctx.consecutive_errors = 0
        mock_ctx.cdp_target_url = "ws://127.0.0.1:9222/devtools/page/test-target"

        mock_pool.create_context = AsyncMock(return_value=mock_ctx)

        response = await client.post("/contexts", json={"persistent": True})

        assert response.status_code == 201
        data = response.json()
        assert data["persistent"] is True

    async def test_list_contexts_empty(self, client, mock_pool):
        """Should return empty list when no contexts."""
        response = await client.get("/contexts")

        assert response.status_code == 200
        data = response.json()
        assert data["contexts"] == []
        assert data["total"] == 0

    async def test_list_contexts(self, client, mock_pool):
        """Should return all contexts."""
        mock_pool.list_contexts.return_value = [
            {
                "id": "ctx-1",
                "proxy": None,
                "proxy_config": None,
                "persistent": False,
                "in_use": True,
                "created_at": "2025-01-15T10:00:00+00:00",
                "tags": [],
                "last_used_at": None,
                "total_requests": 0,
                "error_count": 0,
                "consecutive_errors": 0,
                "cdp_url": "ws://127.0.0.1:9222/devtools/page/target-1",
            },
            {
                "id": "ctx-2",
                "proxy": "http://proxy:8080",
                "proxy_config": {"server": "http://proxy:8080"},
                "persistent": True,
                "in_use": False,
                "created_at": "2025-01-15T11:00:00+00:00",
                "tags": ["proxy:http://proxy:8080"],
                "last_used_at": None,
                "total_requests": 5,
                "error_count": 1,
                "consecutive_errors": 0,
                "cdp_url": "ws://127.0.0.1:9222/devtools/page/target-2",
            },
        ]

        response = await client.get("/contexts")

        assert response.status_code == 200
        data = response.json()
        assert len(data["contexts"]) == 2
        assert data["total"] == 2
        assert data["contexts"][0]["id"] == "ctx-1"
        assert data["contexts"][1]["proxy"] == "http://proxy:8080"
        assert data["contexts"][1]["tags"] == ["proxy:http://proxy:8080"]

    async def test_get_context(self, client, mock_pool):
        """Should return specific context."""
        mock_ctx = MagicMock()
        mock_ctx.id = "ctx-123"
        mock_ctx.proxy = None
        mock_ctx.persistent = False
        mock_ctx.in_use = True
        mock_ctx.created_at = datetime.now(UTC)
        mock_ctx.tags = set()
        mock_ctx.last_used_at = None
        mock_ctx.total_requests = 0
        mock_ctx.error_count = 0
        mock_ctx.consecutive_errors = 0
        mock_ctx.cdp_target_url = "ws://127.0.0.1:9222/devtools/page/test-target"

        mock_pool.get_context.return_value = mock_ctx

        response = await client.get("/contexts/ctx-123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ctx-123"
        assert data["in_use"] is True

    async def test_get_context_not_found(self, client, mock_pool):
        """Should return 404 for unknown context."""
        mock_pool.get_context.return_value = None

        response = await client.get("/contexts/unknown")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_list_contexts_with_tag_filter(self, client, mock_pool):
        """Should filter contexts by tags."""
        mock_pool.list_contexts.return_value = [
            {
                "id": "ctx-1",
                "proxy": "http://proxy:8080",
                "proxy_config": {"server": "http://proxy:8080"},
                "persistent": False,
                "in_use": False,
                "created_at": "2025-01-15T10:00:00+00:00",
                "tags": ["premium", "proxy:http://proxy:8080"],
                "last_used_at": None,
                "total_requests": 0,
                "error_count": 0,
                "consecutive_errors": 0,
                "cdp_url": "ws://127.0.0.1:9222/devtools/page/target-1",
            },
        ]

        response = await client.get("/contexts?tags=premium")

        assert response.status_code == 200
        data = response.json()
        assert len(data["contexts"]) == 1
        assert "premium" in data["contexts"][0]["tags"]
        mock_pool.list_contexts.assert_called_once_with(tags=["premium"])

    async def test_update_tags(self, client, mock_pool):
        """Should add and remove tags."""
        mock_ctx = MagicMock()
        mock_ctx.id = "ctx-123"
        mock_ctx.proxy = None
        mock_ctx.persistent = False
        mock_ctx.in_use = False
        mock_ctx.created_at = datetime.now(UTC)
        mock_ctx.tags = {"new-tag"}
        mock_ctx.last_used_at = None
        mock_ctx.total_requests = 0
        mock_ctx.error_count = 0
        mock_ctx.consecutive_errors = 0
        mock_ctx.cdp_target_url = "ws://127.0.0.1:9222/devtools/page/test-target"

        mock_pool.get_context.return_value = mock_ctx
        mock_pool.add_tags.return_value = True
        mock_pool.remove_tags.return_value = True

        response = await client.patch(
            "/contexts/ctx-123/tags",
            json={"add": ["new-tag"], "remove": ["old-tag"]},
        )

        assert response.status_code == 200
        mock_pool.add_tags.assert_called_once_with("ctx-123", ["new-tag"])
        mock_pool.remove_tags.assert_called_once_with("ctx-123", ["old-tag"])

    async def test_update_tags_not_found(self, client, mock_pool):
        """Should return 404 when updating tags on unknown context."""
        mock_pool.get_context.return_value = None

        response = await client.patch(
            "/contexts/unknown/tags",
            json={"add": ["new-tag"]},
        )

        assert response.status_code == 404

    async def test_delete_context(self, client, mock_pool):
        """Should delete context."""
        mock_pool.remove_context = AsyncMock(return_value=True)

        response = await client.delete("/contexts/ctx-123")

        assert response.status_code == 204
        mock_pool.remove_context.assert_called_once_with("ctx-123")

    async def test_delete_context_not_found(self, client, mock_pool):
        """Should return 404 when deleting unknown context."""
        mock_pool.remove_context = AsyncMock(return_value=False)

        response = await client.delete("/contexts/unknown")

        assert response.status_code == 404

    async def test_delete_context_in_use(self, client, mock_pool):
        """Should return 409 when deleting context in use."""
        mock_pool.remove_context = AsyncMock(side_effect=ContextInUseError())

        response = await client.delete("/contexts/ctx-123")

        assert response.status_code == 409
        assert "in use" in response.json()["detail"].lower()


# =============================================================================
# Acquire/Release Endpoints
# =============================================================================


class TestAcquireRelease:
    """Tests for acquire and release operations."""

    async def test_acquire_context(self, client, mock_pool):
        """Should acquire context."""
        mock_ctx = MagicMock()
        mock_ctx.id = "ctx-123"
        mock_ctx.proxy = None
        mock_ctx.persistent = False
        mock_ctx.in_use = True
        mock_ctx.created_at = datetime.now(UTC)
        mock_ctx.tags = set()
        mock_ctx.last_used_at = None
        mock_ctx.total_requests = 0
        mock_ctx.error_count = 0
        mock_ctx.consecutive_errors = 0
        mock_ctx.cdp_target_url = "ws://127.0.0.1:9222/devtools/page/test-target"

        mock_pool.acquire_context = AsyncMock(return_value=mock_ctx)

        response = await client.post("/contexts/ctx-123/acquire")

        assert response.status_code == 200
        data = response.json()
        assert data["in_use"] is True
        mock_pool.acquire_context.assert_called_once_with("ctx-123")

    async def test_acquire_context_not_found(self, client, mock_pool):
        """Should return 404 when acquiring unknown context."""
        mock_pool.acquire_context = AsyncMock(
            side_effect=ContextNotFoundError("ctx-123")
        )

        response = await client.post("/contexts/unknown/acquire")

        assert response.status_code == 404

    async def test_acquire_context_already_in_use(self, client, mock_pool):
        """Should return 409 when context already in use."""
        mock_pool.acquire_context = AsyncMock(side_effect=ContextNotAvailableError())

        response = await client.post("/contexts/ctx-123/acquire")

        assert response.status_code == 409
        assert "already in use" in response.json()["detail"].lower()

    async def test_release_context(self, client, mock_pool):
        """Should release context."""
        mock_ctx = MagicMock()
        mock_ctx.id = "ctx-123"
        mock_ctx.proxy = None
        mock_ctx.persistent = False
        mock_ctx.in_use = False
        mock_ctx.created_at = datetime.now(UTC)
        mock_ctx.tags = set()
        mock_ctx.last_used_at = None
        mock_ctx.total_requests = 0
        mock_ctx.error_count = 0
        mock_ctx.consecutive_errors = 0
        mock_ctx.cdp_target_url = "ws://127.0.0.1:9222/devtools/page/test-target"

        mock_pool.get_context.return_value = mock_ctx
        mock_pool.release_context = AsyncMock()

        response = await client.post("/contexts/ctx-123/release")

        assert response.status_code == 200
        mock_pool.release_context.assert_called_once_with("ctx-123")

    async def test_release_context_not_found(self, client, mock_pool):
        """Should return 404 when releasing unknown context."""
        mock_pool.get_context.return_value = None

        response = await client.post("/contexts/unknown/release")

        assert response.status_code == 404


# =============================================================================
# Scraping Endpoints
# =============================================================================


class TestScrapingEndpoints:
    """Tests for scraping operations."""

    async def test_goto_requires_acquired(self, client, mock_pool):
        """Should return 409 when context not acquired."""
        mock_ctx = MagicMock()
        mock_ctx.in_use = False
        mock_pool.get_context.return_value = mock_ctx

        response = await client.post(
            "/contexts/ctx-123/goto", json={"url": "https://example.com"}
        )

        assert response.status_code == 409
        assert "acquire" in response.json()["detail"].lower()

    async def test_goto_not_found(self, client, mock_pool):
        """Should return 404 for unknown context."""
        mock_pool.get_context.return_value = None

        response = await client.post(
            "/contexts/unknown/goto", json={"url": "https://example.com"}
        )

        assert response.status_code == 404

    async def test_goto_success(self, client, mock_pool):
        """Should navigate and return response."""
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.ok = True
        mock_page.goto = AsyncMock(return_value=mock_response)

        mock_ctx = MagicMock()
        mock_ctx.in_use = True
        mock_ctx.page = mock_page
        mock_pool.get_context.return_value = mock_ctx

        response = await client.post(
            "/contexts/ctx-123/goto", json={"url": "https://example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://example.com"
        assert data["status"] == 200
        assert data["ok"] is True

    async def test_content_success(self, client, mock_pool):
        """Should return page content."""
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.content = AsyncMock(return_value="<html><body>Hello</body></html>")

        mock_ctx = MagicMock()
        mock_ctx.in_use = True
        mock_ctx.page = mock_page
        mock_pool.get_context.return_value = mock_ctx

        response = await client.post("/contexts/ctx-123/content")

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://example.com"
        assert "<html>" in data["content"]

    async def test_execute_success(self, client, mock_pool):
        """Should execute JS and return result."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=42)

        mock_ctx = MagicMock()
        mock_ctx.in_use = True
        mock_ctx.page = mock_page
        mock_pool.get_context.return_value = mock_ctx

        response = await client.post(
            "/contexts/ctx-123/execute", json={"script": "1 + 41"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == 42

    async def test_execute_timeout(self, client, mock_pool):
        """Should return 504 on script timeout."""
        mock_page = AsyncMock()

        async def slow_evaluate(*args, **kwargs):
            await asyncio.sleep(10)  # Simulate slow script

        mock_page.evaluate = slow_evaluate

        mock_ctx = MagicMock()
        mock_ctx.in_use = True
        mock_ctx.page = mock_page
        mock_pool.get_context.return_value = mock_ctx

        response = await client.post(
            "/contexts/ctx-123/execute",
            json={"script": "slow()", "timeout": 1000},  # 1 second timeout
        )

        assert response.status_code == 504
        assert "timed out" in response.json()["detail"].lower()

    async def test_screenshot_success(self, client, mock_pool):
        """Should take screenshot and return base64."""
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")

        mock_ctx = MagicMock()
        mock_ctx.in_use = True
        mock_ctx.page = mock_page
        mock_pool.get_context.return_value = mock_ctx

        response = await client.post(
            "/contexts/ctx-123/screenshot", json={"full_page": False, "format": "png"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "png"
        assert len(data["data"]) > 0  # Base64 encoded

    async def test_goto_navigation_error(self, client, mock_pool):
        """Should return 502 on navigation failure."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Connection refused"))

        mock_ctx = MagicMock()
        mock_ctx.in_use = True
        mock_ctx.page = mock_page
        mock_pool.get_context.return_value = mock_ctx

        response = await client.post(
            "/contexts/ctx-123/goto", json={"url": "https://example.com"}
        )

        assert response.status_code == 502
        assert "Navigation failed" in response.json()["detail"]
