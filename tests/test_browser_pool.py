"""Comprehensive tests for BrowserPool.

Test categories:
1. Singleton pattern behavior
2. Lifecycle management (start/stop)
3. Browser acquisition and release
4. Browser pool operations (add/remove/list)
5. Edge cases and error handling
6. Concurrent operations
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_scraper_pool.pool.browser_pool import (
    BrowserInstance,
    BrowserInUseError,
    BrowserPool,
    NoBrowserAvailableError,
    PoolNotStartedError,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    BrowserPool.reset_instance()
    yield
    BrowserPool.reset_instance()


@pytest.fixture
def mock_playwright():
    """Mock playwright and browser for testing without real browsers."""
    with patch(
        "browser_scraper_pool.pool.browser_pool.async_playwright"
    ) as mock_async_pw:
        # Create mock playwright instance
        mock_pw_instance = AsyncMock()
        mock_async_pw.return_value.start = AsyncMock(return_value=mock_pw_instance)

        # Create mock browser
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()
        mock_browser.contexts = []

        # Configure chromium.launch to return mock browser
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_pw_instance.stop = AsyncMock()

        yield {
            "async_playwright": mock_async_pw,
            "playwright": mock_pw_instance,
            "browser": mock_browser,
        }


@pytest.fixture
def mock_display():
    """Mock virtual display."""
    with patch("browser_scraper_pool.pool.browser_pool.Display") as mock_display_cls:
        mock_display_instance = MagicMock()
        mock_display_cls.return_value = mock_display_instance
        yield mock_display_instance


# =============================================================================
# Singleton Pattern Tests
# =============================================================================


class TestSingletonPattern:
    """Tests for singleton pattern behavior."""

    def test_get_instance_returns_same_instance(self):
        """get_instance() should always return the same instance."""
        instance1 = BrowserPool.get_instance()
        instance2 = BrowserPool.get_instance()

        assert instance1 is instance2

    def test_get_instance_with_params_creates_with_first_params(self):
        """First call to get_instance() sets the configuration."""
        instance1 = BrowserPool.get_instance(max_browsers=5, headless=True)
        instance2 = BrowserPool.get_instance(max_browsers=10, headless=False)

        assert instance1 is instance2
        assert instance1.max_browsers == 5
        assert instance1.headless is True

    def test_reset_instance_clears_singleton(self):
        """reset_instance() should clear the singleton."""
        instance1 = BrowserPool.get_instance(max_browsers=5)
        BrowserPool.reset_instance()
        instance2 = BrowserPool.get_instance(max_browsers=10)

        assert instance1 is not instance2
        assert instance2.max_browsers == 10

    def test_direct_instantiation_creates_new_instance(self):
        """Direct instantiation bypasses singleton."""
        singleton = BrowserPool.get_instance(max_browsers=5)
        direct = BrowserPool(max_browsers=10)

        assert singleton is not direct
        assert singleton.max_browsers == 5
        assert direct.max_browsers == 10


# =============================================================================
# Lifecycle Tests
# =============================================================================


class TestLifecycle:
    """Tests for pool lifecycle (start/stop)."""

    async def test_start_launches_browsers(self, mock_playwright, mock_display):
        """start() should launch configured number of browsers."""
        pool = BrowserPool(max_browsers=3, headless=True, use_virtual_display=False)

        await pool.start()

        assert pool.is_started is True
        assert pool.size == 3
        assert mock_playwright["playwright"].chromium.launch.call_count == 3

    async def test_start_is_idempotent(self, mock_playwright, mock_display):
        """Multiple start() calls should not launch more browsers."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)

        await pool.start()
        await pool.start()
        await pool.start()

        assert pool.size == 2
        assert mock_playwright["playwright"].chromium.launch.call_count == 2

    async def test_stop_closes_all_browsers(self, mock_playwright, mock_display):
        """stop() should close all browsers and playwright."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()

        await pool.stop()

        assert pool.is_started is False
        assert pool.size == 0
        assert mock_playwright["browser"].close.call_count == 2
        mock_playwright["playwright"].stop.assert_called_once()

    async def test_stop_is_idempotent(self, mock_playwright, mock_display):
        """Multiple stop() calls should be safe."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        await pool.stop()
        await pool.stop()
        await pool.stop()

        # Should only close once
        assert mock_playwright["playwright"].stop.call_count == 1

    async def test_stop_without_start_is_safe(self, mock_playwright):
        """stop() on never-started pool should not raise."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        await pool.stop()  # Should not raise

        assert pool.is_started is False

    async def test_context_manager_starts_and_stops(
        self, mock_playwright, mock_display
    ):
        """Context manager should start on enter and stop on exit."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            assert pool.is_started is True
            assert pool.size == 1

        assert pool.is_started is False
        assert pool.size == 0

    async def test_context_manager_stops_on_exception(
        self, mock_playwright, mock_display
    ):
        """Context manager should cleanup even if exception occurs."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async def raise_in_context():
            async with pool:
                assert pool.is_started is True
                raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await raise_in_context()

        assert pool.is_started is False
        mock_playwright["playwright"].stop.assert_called_once()

    async def test_start_with_virtual_display(self, mock_playwright, mock_display):
        """start() should initialize virtual display when configured."""
        pool = BrowserPool(
            max_browsers=1,
            headless=False,
            use_virtual_display=True,
            virtual_display_size=(1920, 1080),
        )

        await pool.start()

        mock_display.start.assert_called_once()

    async def test_start_without_virtual_display_when_headless(
        self, mock_playwright, mock_display
    ):
        """Virtual display should not start in headless mode."""
        pool = BrowserPool(
            max_browsers=1,
            headless=True,
            use_virtual_display=True,
        )

        await pool.start()

        mock_display.start.assert_not_called()

    async def test_cleanup_on_browser_launch_failure(
        self, mock_playwright, mock_display
    ):
        """If browser launch fails, cleanup should still happen."""
        mock_playwright["playwright"].chromium.launch = AsyncMock(
            side_effect=RuntimeError("Launch failed")
        )
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)

        with pytest.raises(RuntimeError, match="Launch failed"):
            await pool.start()

        assert pool.is_started is False
        mock_playwright["playwright"].stop.assert_called_once()


# =============================================================================
# Browser Acquisition Tests
# =============================================================================


class TestBrowserAcquisition:
    """Tests for acquiring and releasing browsers."""

    async def test_acquire_browser_returns_instance(
        self, mock_playwright, mock_display
    ):
        """acquire_browser() should return a BrowserInstance."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        browser = await pool.acquire_browser()

        assert isinstance(browser, BrowserInstance)
        assert browser.in_use is True

    async def test_acquire_marks_browser_in_use(self, mock_playwright, mock_display):
        """Acquired browser should be marked as in_use."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()

        browser = await pool.acquire_browser()

        assert browser.in_use is True
        assert pool.available_count == 1

    async def test_release_browser_makes_available(self, mock_playwright, mock_display):
        """release_browser() should make browser available again."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        browser = await pool.acquire_browser()
        assert pool.available_count == 0

        await pool.release_browser(browser.id)

        assert pool.available_count == 1
        assert browser.in_use is False

    async def test_acquire_timeout_when_no_browsers_available(
        self, mock_playwright, mock_display
    ):
        """acquire_browser() should timeout if all browsers are in use."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        await pool.acquire_browser()  # Take the only browser

        with pytest.raises(NoBrowserAvailableError):
            await pool.acquire_browser(timeout=0.1)

    async def test_acquire_waits_for_release(self, mock_playwright, mock_display):
        """acquire_browser() should wait and succeed when browser is released."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        browser1 = await pool.acquire_browser()

        async def release_later():
            await asyncio.sleep(0.1)
            await pool.release_browser(browser1.id)

        task = asyncio.create_task(release_later())
        browser2 = await pool.acquire_browser(timeout=1.0)
        await task  # Ensure task completes

        assert browser2.id == browser1.id

    async def test_release_unknown_browser_is_safe(self, mock_playwright, mock_display):
        """release_browser() with unknown id should not raise."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        await pool.release_browser("unknown-id")  # Should not raise

    async def test_multiple_acquire_release_cycles(self, mock_playwright, mock_display):
        """Multiple acquire/release cycles should work correctly."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()

        # Acquire all
        b1 = await pool.acquire_browser()
        b2 = await pool.acquire_browser()
        assert pool.available_count == 0

        # Release all
        await pool.release_browser(b1.id)
        await pool.release_browser(b2.id)
        assert pool.available_count == 2

        # Acquire again
        b3 = await pool.acquire_browser()
        b4 = await pool.acquire_browser()
        assert {b3.id, b4.id} == {b1.id, b2.id}


# =============================================================================
# Pool Operations Tests
# =============================================================================


class TestPoolOperations:
    """Tests for add/remove/list browser operations."""

    async def test_add_browser_increases_pool_size(self, mock_playwright, mock_display):
        """add_browser() should add a new browser to the pool."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()
        initial_size = pool.size

        new_browser = await pool.add_browser()

        assert pool.size == initial_size + 1
        assert new_browser.id in [b["id"] for b in pool.list_browsers()]

    async def test_add_browser_with_proxy(self, mock_playwright, mock_display):
        """add_browser() should support proxy configuration."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        new_browser = await pool.add_browser(proxy="http://proxy.example.com:8080")

        assert new_browser.proxy == "http://proxy.example.com:8080"
        # Check proxy was passed in launch call
        call_kwargs = mock_playwright["playwright"].chromium.launch.call_args.kwargs
        assert call_kwargs["proxy"] == {"server": "http://proxy.example.com:8080"}
        assert call_kwargs["headless"] is True
        assert "args" in call_kwargs  # CDP port arg

    async def test_remove_browser_decreases_pool_size(
        self, mock_playwright, mock_display
    ):
        """remove_browser() should remove browser from pool."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()
        browsers = pool.list_browsers()

        result = await pool.remove_browser(browsers[0]["id"])

        assert result is True
        assert pool.size == 1

    async def test_remove_browser_allows_acquire_after(
        self, mock_playwright, mock_display
    ):
        """acquire_browser() should work after remove_browser()."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()
        browsers = pool.list_browsers()
        removed_id = browsers[0]["id"]
        remaining_id = browsers[1]["id"]

        await pool.remove_browser(removed_id)

        # Should be able to acquire remaining browser without error
        browser = await pool.acquire_browser()
        assert browser.id == remaining_id
        assert pool.available_count == 0

    async def test_remove_browser_unknown_id_returns_false(
        self, mock_playwright, mock_display
    ):
        """remove_browser() with unknown id should return False."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        result = await pool.remove_browser("unknown-id")

        assert result is False

    async def test_remove_browser_in_use_raises(self, mock_playwright, mock_display):
        """remove_browser() should raise if browser is in use."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        browser = await pool.acquire_browser()

        with pytest.raises(BrowserInUseError):
            await pool.remove_browser(browser.id)

    async def test_list_browsers_returns_all_info(self, mock_playwright, mock_display):
        """list_browsers() should return all browser info."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()

        browsers = pool.list_browsers()

        assert len(browsers) == 2
        for b in browsers:
            assert "id" in b
            assert "proxy" in b
            assert "in_use" in b
            assert "cdp_port" in b
            assert isinstance(b["cdp_port"], int)

    async def test_list_browsers_shows_in_use_status(
        self, mock_playwright, mock_display
    ):
        """list_browsers() should reflect in_use status."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()

        browser = await pool.acquire_browser()
        browsers = pool.list_browsers()

        in_use_count = sum(1 for b in browsers if b["in_use"])
        assert in_use_count == 1

        await pool.release_browser(browser.id)
        browsers = pool.list_browsers()

        in_use_count = sum(1 for b in browsers if b["in_use"])
        assert in_use_count == 0


# =============================================================================
# Properties Tests
# =============================================================================


class TestProperties:
    """Tests for pool properties."""

    async def test_size_property(self, mock_playwright, mock_display):
        """size property should return number of browsers."""
        pool = BrowserPool(max_browsers=3, headless=True, use_virtual_display=False)

        assert pool.size == 0

        await pool.start()
        assert pool.size == 3

        await pool.stop()
        assert pool.size == 0

    async def test_available_count_property(self, mock_playwright, mock_display):
        """available_count should return number of available browsers."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)
        await pool.start()

        assert pool.available_count == 2

        b1 = await pool.acquire_browser()
        assert pool.available_count == 1

        await pool.acquire_browser()
        assert pool.available_count == 0

        await pool.release_browser(b1.id)
        assert pool.available_count == 1

    async def test_is_started_property(self, mock_playwright, mock_display):
        """is_started should reflect pool state."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        assert pool.is_started is False

        await pool.start()
        assert pool.is_started is True

        await pool.stop()
        assert pool.is_started is False


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error conditions."""

    async def test_create_browser_before_start_raises(self):
        """_create_browser() should raise if pool not started."""
        pool = BrowserPool(max_browsers=1)

        with pytest.raises(PoolNotStartedError):
            await pool._create_browser()

    async def test_cleanup_handles_browser_close_errors(
        self, mock_playwright, mock_display
    ):
        """_cleanup() should handle errors when closing browsers."""
        mock_playwright["browser"].close = AsyncMock(
            side_effect=RuntimeError("Close failed")
        )
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        # Should not raise even if browser.close() fails
        await pool.stop()

        assert pool.is_started is False

    async def test_cleanup_handles_playwright_stop_errors(
        self, mock_playwright, mock_display
    ):
        """_cleanup() should handle errors when stopping playwright."""
        mock_playwright["playwright"].stop = AsyncMock(
            side_effect=RuntimeError("Stop failed")
        )
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)
        await pool.start()

        # Should not raise even if playwright.stop() fails
        await pool.stop()

        assert pool.is_started is False


# =============================================================================
# Concurrent Operations Tests
# =============================================================================


class TestConcurrentOperations:
    """Tests for concurrent access patterns."""

    async def test_concurrent_acquire_respects_pool_size(
        self, mock_playwright, mock_display
    ):
        """Concurrent acquire calls should respect pool size."""
        pool = BrowserPool(max_browsers=3, headless=True, use_virtual_display=False)
        await pool.start()

        # Try to acquire 5 browsers concurrently (only 3 available)
        async def try_acquire():
            try:
                return await pool.acquire_browser(timeout=0.5)
            except RuntimeError:
                return None

        results = await asyncio.gather(*[try_acquire() for _ in range(5)])

        acquired = [r for r in results if r is not None]
        assert len(acquired) == 3

    async def test_concurrent_release_is_safe(self, mock_playwright, mock_display):
        """Concurrent release calls should be safe."""
        pool = BrowserPool(max_browsers=3, headless=True, use_virtual_display=False)
        await pool.start()

        browsers = [await pool.acquire_browser() for _ in range(3)]

        # Release all concurrently
        await asyncio.gather(*[pool.release_browser(b.id) for b in browsers])

        assert pool.available_count == 3
