"""Tests for unified /scrape endpoint."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

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
def mock_context():
    """Create a mock context."""
    ctx = MagicMock()
    ctx.id = "ctx-123"
    ctx.proxy = None
    ctx.persistent = False
    ctx.in_use = True
    ctx.created_at = datetime.now(UTC)
    ctx.tags = set()
    ctx.last_used_at = None
    ctx.total_requests = 0
    ctx.error_count = 0
    ctx.consecutive_errors = 0
    ctx.domain_last_request = {}

    # Mock page
    mock_page = AsyncMock()
    mock_page.url = "https://example.com"
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.ok = True
    mock_page.goto = AsyncMock(return_value=mock_response)
    mock_page.content = AsyncMock(return_value="<html><body>Hello</body></html>")
    mock_page.evaluate = AsyncMock(return_value="Example Domain")
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
    ctx.page = mock_page

    return ctx


@pytest.fixture
def mock_pool(mock_context):
    """Create a mock pool."""
    pool = MagicMock(spec=ContextPool)
    pool.size = 1
    pool.available_count = 1
    pool.cdp_port = 9222
    pool.is_started = True
    pool.get_cdp_endpoint.return_value = "ws://127.0.0.1:9222"
    pool.select_context.return_value = mock_context
    pool.acquire_context = AsyncMock(return_value=mock_context)
    pool.release_context = AsyncMock()
    pool.evict_and_replace = AsyncMock(return_value=None)
    pool.recreate_context = AsyncMock(return_value=None)
    return pool


@pytest.fixture
async def client(mock_pool):
    """Create test client with mocked pool."""
    app.state.context_pool = mock_pool
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestScrapeEndpoint:
    """Tests for POST /scrape endpoint."""

    async def test_scrape_success(self, client, mock_pool, mock_context):
        """Should successfully scrape URL."""
        response = await client.post(
            "/scrape",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["url"] == "https://example.com"
        assert data["status"] == 200
        assert data["content"] == "<html><body>Hello</body></html>"
        assert data["context_id"] == "ctx-123"

    async def test_scrape_with_script(self, client, mock_pool, mock_context):
        """Should execute script and return result."""
        response = await client.post(
            "/scrape",
            json={"url": "https://example.com", "script": "document.title"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["script_result"] == "Example Domain"

    async def test_scrape_with_screenshot(self, client, mock_pool, mock_context):
        """Should take screenshot and return base64."""
        response = await client.post(
            "/scrape",
            json={"url": "https://example.com", "screenshot": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["screenshot"] is not None
        assert len(data["screenshot"]) > 0

    async def test_scrape_without_content(self, client, mock_pool, mock_context):
        """Should skip content when get_content=False."""
        response = await client.post(
            "/scrape",
            json={"url": "https://example.com", "get_content": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["content"] is None

    async def test_scrape_with_tags(self, client, mock_pool, mock_context):
        """Should pass tags to context selection."""
        response = await client.post(
            "/scrape",
            json={"url": "https://example.com", "tags": ["premium"]},
        )

        assert response.status_code == 200
        mock_pool.select_context.assert_called_once()
        call_args = mock_pool.select_context.call_args
        assert "premium" in call_args.kwargs["tags"]

    async def test_scrape_with_proxy(self, client, mock_pool, mock_context):
        """Proxy should NOT be used for selection, only for creation."""
        response = await client.post(
            "/scrape",
            json={"url": "https://example.com", "proxy": "http://proxy:8080"},
        )

        assert response.status_code == 200
        mock_pool.select_context.assert_called_once()
        call_args = mock_pool.select_context.call_args
        # Proxy is NOT added to selection tags - only user tags are used
        assert call_args.kwargs["tags"] is None or "proxy:http://proxy:8080" not in call_args.kwargs["tags"]

    async def test_scrape_creates_context_with_proxy(self, client, mock_pool):
        """Should create context with proxy when no match found."""
        mock_pool.select_context.return_value = None

        new_ctx = MagicMock()
        new_ctx.id = "ctx-new"
        new_ctx.in_use = True
        new_ctx.consecutive_errors = 0
        new_ctx.domain_last_request = {}
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.content = AsyncMock(return_value="<html></html>")
        new_ctx.page = mock_page

        mock_pool.evict_and_replace = AsyncMock(return_value=new_ctx)
        mock_pool.acquire_context = AsyncMock(return_value=new_ctx)

        response = await client.post(
            "/scrape",
            json={"url": "https://example.com", "proxy": "http://proxy:8080", "tags": ["spider1"]},
        )

        assert response.status_code == 200
        # evict_and_replace should be called with the proxy
        mock_pool.evict_and_replace.assert_called_once()
        call_args = mock_pool.evict_and_replace.call_args
        assert call_args.kwargs["proxy"] == "http://proxy:8080"
        assert "spider1" in call_args.kwargs["tags"]

    async def test_scrape_navigation_error(self, client, mock_pool, mock_context):
        """Should return error response on navigation failure."""
        mock_context.page.goto = AsyncMock(side_effect=Exception("Connection refused"))

        response = await client.post(
            "/scrape",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 200  # Still 200, but success=False
        data = response.json()
        assert data["success"] is False
        assert "Connection refused" in data["error"]

    async def test_scrape_no_context_available(self, client, mock_pool):
        """Should evict and create when no context available."""
        mock_pool.select_context.return_value = None
        mock_pool.size = 10  # At capacity

        new_ctx = MagicMock()
        new_ctx.id = "ctx-new"
        new_ctx.in_use = True
        new_ctx.consecutive_errors = 0
        new_ctx.domain_last_request = {}
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.content = AsyncMock(return_value="<html></html>")
        new_ctx.page = mock_page

        mock_pool.evict_and_replace = AsyncMock(return_value=new_ctx)
        mock_pool.acquire_context = AsyncMock(return_value=new_ctx)

        response = await client.post(
            "/scrape",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["context_id"] == "ctx-new"
        mock_pool.evict_and_replace.assert_called_once()

    async def test_scrape_context_released_after_error(
        self, client, mock_pool, mock_context
    ):
        """Should release context even after error."""
        mock_context.page.goto = AsyncMock(side_effect=Exception("Error"))

        await client.post(
            "/scrape",
            json={"url": "https://example.com"},
        )

        mock_pool.release_context.assert_called_once_with("ctx-123")


class TestScrapeErrorTracking:
    """Tests for error tracking in scrape endpoint."""

    async def test_records_success(self, client, mock_pool, mock_context):
        """Should reset consecutive errors on success."""
        mock_context.consecutive_errors = 3

        await client.post(
            "/scrape",
            json={"url": "https://example.com"},
        )

        # After success, consecutive_errors should be reset
        assert mock_context.consecutive_errors == 0

    async def test_records_error(self, client, mock_pool, mock_context):
        """Should increment error counters on failure."""
        mock_context.page.goto = AsyncMock(side_effect=Exception("Error"))

        await client.post(
            "/scrape",
            json={"url": "https://example.com"},
        )

        assert mock_context.error_count == 1
        assert mock_context.consecutive_errors == 1
