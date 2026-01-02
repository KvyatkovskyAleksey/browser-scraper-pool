"""Unit tests for ContextPool with mocked Playwright."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from browser_scraper_pool.pool.context_pool import (
    ContextInUseError,
    ContextNotAvailableError,
    ContextNotFoundError,
    ContextPool,
    PoolNotStartedError,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    ContextPool.reset_instance()
    yield
    ContextPool.reset_instance()


@pytest.fixture
def mock_httpx():
    """Mock httpx.Client for CDP endpoint fetching."""
    with patch("browser_scraper_pool.pool.context_pool.httpx") as mock:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/mock-guid"
        }
        mock_response.raise_for_status = MagicMock()

        # Mock httpx.Client() context manager pattern
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock.Client.return_value = mock_client

        yield {"httpx": mock, "client": mock_client, "response": mock_response}


@pytest.fixture
def mock_playwright(mock_httpx):
    """Mock playwright and browser for unit tests."""
    with patch(
        "browser_scraper_pool.pool.context_pool.async_playwright"
    ) as mock_async_pw:
        # Create mock objects
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.storage_state = AsyncMock(return_value={"cookies": []})
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_pw.stop = AsyncMock()

        mock_async_pw.return_value.start = AsyncMock(return_value=mock_pw)

        yield {
            "async_playwright": mock_async_pw,
            "playwright": mock_pw,
            "browser": mock_browser,
            "context": mock_context,
            "page": mock_page,
            "httpx_mock": mock_httpx,
        }


@pytest.fixture
def mock_display():
    """Mock pyvirtualdisplay."""
    with patch("browser_scraper_pool.pool.context_pool.Display") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock


# =============================================================================
# Singleton Pattern Tests
# =============================================================================


class TestSingletonPattern:
    """Tests for singleton behavior."""

    def test_get_instance_returns_same_instance(self):
        """get_instance() should return the same instance."""
        pool1 = ContextPool.get_instance()
        pool2 = ContextPool.get_instance()
        assert pool1 is pool2

    def test_reset_instance_clears_singleton(self):
        """reset_instance() should clear the singleton."""
        pool1 = ContextPool.get_instance()
        ContextPool.reset_instance()
        pool2 = ContextPool.get_instance()
        assert pool1 is not pool2

    def test_direct_instantiation_creates_new_instance(self):
        """Direct instantiation should create new instances."""
        pool1 = ContextPool()
        pool2 = ContextPool()
        assert pool1 is not pool2

    def test_get_instance_uses_first_params(self):
        """First call to get_instance() sets the params."""
        pool1 = ContextPool.get_instance(headless=True, cdp_port=9999)
        pool2 = ContextPool.get_instance(headless=False, cdp_port=8888)
        assert pool1 is pool2
        assert pool1.headless is True
        assert pool1.cdp_port == 9999


# =============================================================================
# Lifecycle Tests
# =============================================================================


class TestLifecycle:
    """Tests for pool lifecycle management."""

    async def test_start_launches_browser(self, mock_playwright, mock_display):
        """start() should launch a browser."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        mock_playwright["playwright"].chromium.launch.assert_called_once()
        assert pool.is_started is True

    async def test_start_is_idempotent(self, mock_playwright, mock_display):
        """Calling start() twice should not launch another browser."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.start()

        assert mock_playwright["playwright"].chromium.launch.call_count == 1

    async def test_stop_closes_browser(self, mock_playwright, mock_display):
        """stop() should close the browser."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.stop()

        mock_playwright["browser"].close.assert_called_once()
        assert pool.is_started is False

    async def test_stop_is_idempotent(self, mock_playwright, mock_display):
        """Calling stop() twice should not raise."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.stop()
        await pool.stop()

        assert mock_playwright["browser"].close.call_count == 1

    async def test_context_manager_starts_and_stops(self, mock_playwright, mock_display):
        """async with should start and stop the pool."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            assert pool.is_started is True

        assert pool.is_started is False

    async def test_context_manager_stops_on_exception(self, mock_playwright, mock_display):
        """Pool should stop even if exception is raised."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        with pytest.raises(ValueError, match="test"):
            async with pool:
                raise ValueError("test")

        assert pool.is_started is False

    async def test_start_with_virtual_display(self, mock_playwright, mock_display):
        """start() should start virtual display when configured."""
        pool = ContextPool(headless=False, use_virtual_display=True)
        await pool.start()

        mock_display.assert_called_once()
        mock_display.return_value.start.assert_called_once()

    async def test_stop_stops_virtual_display(self, mock_playwright, mock_display):
        """stop() should stop virtual display."""
        pool = ContextPool(headless=False, use_virtual_display=True)
        await pool.start()
        await pool.stop()

        mock_display.return_value.stop.assert_called_once()

    async def test_no_virtual_display_when_headless(self, mock_playwright, mock_display):
        """Virtual display should not start when headless."""
        pool = ContextPool(headless=True, use_virtual_display=True)
        await pool.start()

        mock_display.assert_not_called()


# =============================================================================
# Context Creation Tests
# =============================================================================


class TestContextCreation:
    """Tests for context creation."""

    async def test_create_context_returns_instance(self, mock_playwright, mock_display):
        """create_context() should return a ContextInstance."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        ctx = await pool.create_context()

        assert ctx.id is not None
        assert ctx.context is not None
        assert ctx.page is not None
        assert ctx.in_use is False

    async def test_create_context_with_proxy(self, mock_playwright, mock_display):
        """create_context() should pass proxy to browser context."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        ctx = await pool.create_context(proxy="http://proxy:8080")

        assert ctx.proxy == "http://proxy:8080"
        mock_playwright["browser"].new_context.assert_called_with(
            proxy={"server": "http://proxy:8080"}
        )

    async def test_create_context_persistent(self, mock_playwright, mock_display, tmp_path):
        """create_context(persistent=True) should set storage path."""
        pool = ContextPool(
            headless=True,
            use_virtual_display=False,
            persistent_contexts_dir=tmp_path,
        )
        await pool.start()

        ctx = await pool.create_context(persistent=True)

        assert ctx.persistent is True
        assert ctx.storage_path is not None
        assert ctx.storage_path.parent == tmp_path

    async def test_create_context_not_started_raises(self):
        """create_context() should raise if pool not started."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        with pytest.raises(PoolNotStartedError):
            await pool.create_context()

    async def test_create_multiple_contexts(self, mock_playwright, mock_display):
        """Multiple contexts can be created."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        ctx1 = await pool.create_context()
        ctx2 = await pool.create_context()
        ctx3 = await pool.create_context()

        assert pool.size == 3
        assert len({ctx1.id, ctx2.id, ctx3.id}) == 3  # All unique IDs


# =============================================================================
# Acquire/Release Tests
# =============================================================================


class TestAcquireRelease:
    """Tests for acquire and release operations."""

    async def test_acquire_context_marks_in_use(self, mock_playwright, mock_display):
        """acquire_context() should mark context as in use."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()

        acquired = await pool.acquire_context(ctx.id)

        assert acquired.in_use is True
        assert acquired.id == ctx.id

    async def test_acquire_already_in_use_raises(self, mock_playwright, mock_display):
        """acquire_context() on in-use context should raise."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()
        await pool.acquire_context(ctx.id)

        with pytest.raises(ContextNotAvailableError):
            await pool.acquire_context(ctx.id)

    async def test_acquire_unknown_id_raises(self, mock_playwright, mock_display):
        """acquire_context() with unknown ID should raise."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        with pytest.raises(ContextNotFoundError):
            await pool.acquire_context("unknown-id")

    async def test_release_context_marks_available(self, mock_playwright, mock_display):
        """release_context() should mark context as not in use."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()
        await pool.acquire_context(ctx.id)

        await pool.release_context(ctx.id)

        assert ctx.in_use is False

    async def test_release_unknown_id_no_error(self, mock_playwright, mock_display):
        """release_context() with unknown ID should not raise."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        await pool.release_context("unknown-id")  # Should not raise

    async def test_acquire_release_cycle(self, mock_playwright, mock_display):
        """Context can be acquired and released multiple times."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()

        for _ in range(3):
            await pool.acquire_context(ctx.id)
            assert ctx.in_use is True
            await pool.release_context(ctx.id)
            assert ctx.in_use is False


# =============================================================================
# Remove Context Tests
# =============================================================================


class TestRemoveContext:
    """Tests for context removal."""

    async def test_remove_context_closes_it(self, mock_playwright, mock_display):
        """remove_context() should close the context."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()

        result = await pool.remove_context(ctx.id)

        assert result is True
        assert pool.size == 0
        mock_playwright["context"].close.assert_called_once()

    async def test_remove_unknown_id_returns_false(self, mock_playwright, mock_display):
        """remove_context() with unknown ID should return False."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        result = await pool.remove_context("unknown-id")

        assert result is False

    async def test_remove_in_use_context_raises(self, mock_playwright, mock_display):
        """remove_context() on in-use context should raise."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()
        await pool.acquire_context(ctx.id)

        with pytest.raises(ContextInUseError):
            await pool.remove_context(ctx.id)


# =============================================================================
# Get Context Tests
# =============================================================================


class TestGetContext:
    """Tests for get_context()."""

    async def test_get_context_returns_instance(self, mock_playwright, mock_display):
        """get_context() should return the context instance."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()

        result = pool.get_context(ctx.id)

        assert result is ctx

    async def test_get_context_unknown_returns_none(self, mock_playwright, mock_display):
        """get_context() with unknown ID should return None."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        result = pool.get_context("unknown-id")

        assert result is None


# =============================================================================
# List Contexts Tests
# =============================================================================


class TestListContexts:
    """Tests for list_contexts()."""

    async def test_list_contexts_empty(self, mock_playwright, mock_display):
        """list_contexts() should return empty list when no contexts."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        result = pool.list_contexts()

        assert result == []

    async def test_list_contexts_returns_all_info(self, mock_playwright, mock_display):
        """list_contexts() should return all context info."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context(proxy="http://proxy:8080")
        await pool.acquire_context(ctx.id)

        result = pool.list_contexts()

        assert len(result) == 1
        assert result[0]["id"] == ctx.id
        assert result[0]["proxy"] == "http://proxy:8080"
        assert result[0]["in_use"] is True
        assert "created_at" in result[0]

    async def test_list_contexts_filter_by_tags(self, mock_playwright, mock_display):
        """list_contexts() should filter by tags."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx1 = await pool.create_context(tags=["premium"])
        await pool.create_context(tags=["basic"])

        result = pool.list_contexts(tags=["premium"])

        assert len(result) == 1
        assert result[0]["id"] == ctx1.id
        assert "premium" in result[0]["tags"]


# =============================================================================
# Tags Tests
# =============================================================================


class TestTags:
    """Tests for tag management."""

    async def test_create_context_with_tags(self, mock_playwright, mock_display):
        """create_context() should accept and store tags."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        ctx = await pool.create_context(tags=["premium", "fast"])

        assert "premium" in ctx.tags
        assert "fast" in ctx.tags

    async def test_create_context_proxy_auto_tag(self, mock_playwright, mock_display):
        """create_context() should auto-add proxy as tag."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        ctx = await pool.create_context(proxy="http://proxy:8080")

        assert "proxy:http://proxy:8080" in ctx.tags

    async def test_add_tags(self, mock_playwright, mock_display):
        """add_tags() should add tags to context."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()

        result = pool.add_tags(ctx.id, ["new-tag", "another"])

        assert result is True
        assert "new-tag" in ctx.tags
        assert "another" in ctx.tags

    async def test_add_tags_unknown_context(self, mock_playwright, mock_display):
        """add_tags() on unknown context should return False."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        result = pool.add_tags("unknown-id", ["tag"])

        assert result is False

    async def test_remove_tags(self, mock_playwright, mock_display):
        """remove_tags() should remove tags from context."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context(tags=["keep", "remove-me"])

        result = pool.remove_tags(ctx.id, ["remove-me"])

        assert result is True
        assert "keep" in ctx.tags
        assert "remove-me" not in ctx.tags

    async def test_remove_tags_unknown_context(self, mock_playwright, mock_display):
        """remove_tags() on unknown context should return False."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        result = pool.remove_tags("unknown-id", ["tag"])

        assert result is False


# =============================================================================
# Context Selection Tests
# =============================================================================


class TestContextSelection:
    """Tests for smart context selection."""

    async def test_select_context_returns_available(self, mock_playwright, mock_display):
        """select_context() should return available context."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx = await pool.create_context()

        result = pool.select_context()

        assert result is ctx

    async def test_select_context_skips_in_use(self, mock_playwright, mock_display):
        """select_context() should skip contexts in use."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx1 = await pool.create_context()
        ctx2 = await pool.create_context()
        await pool.acquire_context(ctx1.id)

        result = pool.select_context()

        assert result is ctx2

    async def test_select_context_filters_by_tags(self, mock_playwright, mock_display):
        """select_context() should filter by tags."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.create_context(tags=["basic"])
        ctx2 = await pool.create_context(tags=["premium"])

        result = pool.select_context(tags=["premium"])

        assert result is ctx2

    async def test_select_context_returns_none_when_no_match(
        self, mock_playwright, mock_display
    ):
        """select_context() should return None when no match."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.create_context(tags=["basic"])

        result = pool.select_context(tags=["premium"])

        assert result is None

    async def test_select_context_prefers_healthier(self, mock_playwright, mock_display):
        """select_context() should prefer healthier contexts."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx1 = await pool.create_context()
        ctx2 = await pool.create_context()

        # Make ctx1 less healthy
        ctx1.consecutive_errors = 3
        ctx1.error_count = 5
        ctx1.total_requests = 10

        result = pool.select_context()

        assert result is ctx2

    async def test_get_available_contexts(self, mock_playwright, mock_display):
        """get_available_contexts() should return all available contexts."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        ctx1 = await pool.create_context()
        ctx2 = await pool.create_context()
        await pool.acquire_context(ctx1.id)

        result = pool.get_available_contexts()

        assert len(result) == 1
        assert result[0] is ctx2

    async def test_get_available_contexts_with_tags(self, mock_playwright, mock_display):
        """get_available_contexts() should filter by tags."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.create_context(tags=["basic"])
        ctx2 = await pool.create_context(tags=["premium"])

        result = pool.get_available_contexts(tags=["premium"])

        assert len(result) == 1
        assert result[0] is ctx2


# =============================================================================
# CDP Endpoint Tests
# =============================================================================


class TestCDPEndpoint:
    """Tests for CDP endpoint."""

    async def test_get_cdp_endpoint(self, mock_playwright, mock_display):
        """get_cdp_endpoint() should return browser's WebSocket URL from Chrome DevTools API."""
        pool = ContextPool(headless=True, use_virtual_display=False, cdp_port=9222)
        await pool.start()

        result = pool.get_cdp_endpoint()

        # Returns the WebSocket URL from mock httpx response
        assert result == "ws://127.0.0.1:9222/devtools/browser/mock-guid"
        # Verify httpx.Client was created with trust_env=False
        mock_playwright["httpx_mock"]["httpx"].Client.assert_called_with(trust_env=False)
        # Verify client.get was called with correct URL
        mock_playwright["httpx_mock"]["client"].get.assert_called_with(
            "http://127.0.0.1:9222/json/version"
        )

    async def test_cdp_port_custom(self, mock_playwright, mock_display):
        """Custom CDP port should be used in httpx request."""
        pool = ContextPool(headless=True, use_virtual_display=False, cdp_port=9999)
        await pool.start()

        assert pool.cdp_port == 9999
        pool.get_cdp_endpoint()
        # Verify client.get was called with custom port
        mock_playwright["httpx_mock"]["client"].get.assert_called_with(
            "http://127.0.0.1:9999/json/version"
        )

    async def test_get_cdp_endpoint_raises_when_not_started(self, mock_playwright, mock_display):
        """get_cdp_endpoint() should raise PoolNotStartedError when not started."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        with pytest.raises(PoolNotStartedError):
            pool.get_cdp_endpoint()


# =============================================================================
# Properties Tests
# =============================================================================


class TestProperties:
    """Tests for pool properties."""

    async def test_size_reflects_context_count(self, mock_playwright, mock_display):
        """size should reflect number of contexts."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        assert pool.size == 0

        await pool.create_context()
        assert pool.size == 1

        await pool.create_context()
        assert pool.size == 2

    async def test_available_count(self, mock_playwright, mock_display):
        """available_count should reflect available contexts."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()

        ctx1 = await pool.create_context()
        ctx2 = await pool.create_context()

        assert pool.available_count == 2

        await pool.acquire_context(ctx1.id)
        assert pool.available_count == 1

        await pool.acquire_context(ctx2.id)
        assert pool.available_count == 0

        await pool.release_context(ctx1.id)
        assert pool.available_count == 1

    async def test_is_started(self, mock_playwright, mock_display):
        """is_started should reflect pool state."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        assert pool.is_started is False

        await pool.start()
        assert pool.is_started is True

        await pool.stop()
        assert pool.is_started is False


# =============================================================================
# Cleanup Tests
# =============================================================================


class TestCleanup:
    """Tests for cleanup behavior."""

    async def test_stop_closes_all_contexts(self, mock_playwright, mock_display):
        """stop() should close all contexts."""
        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.create_context()
        await pool.create_context()

        await pool.stop()

        assert pool.size == 0
        assert mock_playwright["context"].close.call_count == 2

    async def test_cleanup_handles_context_close_error(self, mock_playwright, mock_display):
        """Cleanup should continue even if context close fails."""
        mock_playwright["context"].close.side_effect = Exception("close error")

        pool = ContextPool(headless=True, use_virtual_display=False)
        await pool.start()
        await pool.create_context()

        await pool.stop()  # Should not raise

        assert pool.is_started is False


# =============================================================================
# Repr Tests
# =============================================================================


class TestRepr:
    """Tests for string representation."""

    def test_repr(self):
        """__repr__ should return useful info."""
        pool = ContextPool(headless=True, use_virtual_display=False, cdp_port=9222)

        result = repr(pool)

        assert "ContextPool" in result
        assert "headless=True" in result
        assert "cdp_port=9222" in result
