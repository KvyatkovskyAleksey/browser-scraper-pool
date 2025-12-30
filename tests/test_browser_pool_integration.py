"""Integration tests with real Chrome browser.

These tests launch actual browser instances to verify real-world behavior.
Run with: pytest tests/test_browser_pool_integration.py -v

Note: Requires Chromium installed (patchright install chromium)
"""

import asyncio

import pytest

from browser_scraper_pool.pool.browser_pool import BrowserPool


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    BrowserPool.reset_instance()
    yield
    BrowserPool.reset_instance()


# =============================================================================
# Basic Browser Operations
# =============================================================================


class TestRealBrowserOperations:
    """Tests with real browser instances."""

    async def test_pool_starts_real_browsers(self):
        """Pool should start real browser instances."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            assert pool.size == 1
            assert pool.is_started is True

            browser = await pool.acquire_browser()
            assert browser.browser is not None

    async def test_browser_has_valid_cdp_port(self):
        """Browser should have a valid CDP port assigned."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)

        async with pool:
            browsers = pool.list_browsers()
            assert len(browsers) == 2

            # Each browser should have a unique, valid port
            ports = [b["cdp_port"] for b in browsers]
            assert all(isinstance(p, int) for p in ports)
            assert all(1024 < p < 65536 for p in ports)  # Valid port range
            assert len(set(ports)) == 2  # All ports unique

    async def test_navigate_to_url(self):
        """Browser should navigate to URLs and get content."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()
            page = await context.new_page()

            # Navigate to a simple page
            response = await page.goto("https://example.com")

            assert response is not None
            assert response.status == 200

            # Check content
            title = await page.title()
            assert "Example" in title

            content = await page.content()
            assert "<html" in content.lower()

            await context.close()
            await pool.release_browser(browser.id)

    async def test_navigate_to_multiple_urls(self):
        """Browser should handle multiple navigations."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        urls = [
            "https://example.com",
            "https://httpbin.org/html",
            "https://example.org",
        ]

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()
            page = await context.new_page()

            for url in urls:
                response = await page.goto(url, timeout=30000)
                assert response is not None
                assert response.status == 200

            await context.close()
            await pool.release_browser(browser.id)

    async def test_execute_javascript(self):
        """Browser should execute JavaScript and return results."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()
            page = await context.new_page()

            await page.goto("https://example.com")

            # Execute simple JS
            result = await page.evaluate("1 + 2")
            assert result == 3

            # Execute JS that returns object
            result = await page.evaluate("({ name: 'test', value: 42 })")
            assert result == {"name": "test", "value": 42}

            # Get document info
            result = await page.evaluate("document.title")
            assert "Example" in result

            await context.close()
            await pool.release_browser(browser.id)

    async def test_multiple_pages_in_context(self):
        """Context should handle multiple pages."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()

            # Create multiple pages
            page1 = await context.new_page()
            page2 = await context.new_page()

            await page1.goto("https://example.com")
            await page2.goto("https://httpbin.org/html")

            title1 = await page1.title()
            title2 = await page2.title()

            # Different pages should have different titles
            assert title1 != title2
            assert "Example" in title1

            await context.close()
            await pool.release_browser(browser.id)


# =============================================================================
# Pool Behavior Tests
# =============================================================================


class TestRealPoolBehavior:
    """Tests for pool behavior with real browsers."""

    async def test_acquire_release_cycle(self):
        """Browsers should be reusable after release."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            # First acquire
            browser1 = await pool.acquire_browser()
            browser1_id = browser1.id
            await pool.release_browser(browser1.id)

            # Second acquire should get same browser
            browser2 = await pool.acquire_browser()
            assert browser2.id == browser1_id

            await pool.release_browser(browser2.id)

    async def test_multiple_browsers_in_pool(self):
        """Pool should manage multiple browser instances."""
        pool = BrowserPool(max_browsers=3, headless=True, use_virtual_display=False)

        async with pool:
            assert pool.size == 3

            # Acquire all browsers
            browsers = []
            for _ in range(3):
                b = await pool.acquire_browser()
                browsers.append(b)

            assert pool.available_count == 0

            # All should be different
            ids = [b.id for b in browsers]
            assert len(set(ids)) == 3

            # Release all
            for b in browsers:
                await pool.release_browser(b.id)

            assert pool.available_count == 3

    async def test_concurrent_page_operations(self):
        """Multiple browsers should work concurrently."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)

        async def fetch_title(pool: BrowserPool, url: str) -> str:
            browser = await pool.acquire_browser()
            try:
                context = await browser.browser.new_context()
                page = await context.new_page()
                await page.goto(url, timeout=30000)
                title = await page.title()
                await context.close()
                return title
            finally:
                await pool.release_browser(browser.id)

        async with pool:
            # Run two fetches concurrently
            results = await asyncio.gather(
                fetch_title(pool, "https://example.com"),
                fetch_title(pool, "https://example.org"),
            )

            assert len(results) == 2
            assert all("Example" in r for r in results)


# =============================================================================
# Error and Recovery Tests
# =============================================================================


class TestErrorAndRecovery:
    """Tests for error scenarios and recovery."""

    async def test_navigation_timeout_handling(self):
        """Pool should handle navigation timeouts gracefully."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()
            page = await context.new_page()

            # Try to navigate to a non-responsive URL with short timeout
            with pytest.raises(TimeoutError):
                await page.goto("http://10.255.255.1", timeout=1000)

            # Browser should still be usable
            response = await page.goto("https://example.com", timeout=30000)
            assert response.status == 200

            await context.close()
            await pool.release_browser(browser.id)

    async def test_invalid_url_handling(self):
        """Pool should handle invalid URLs."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()
            page = await context.new_page()

            # Navigate to invalid URL should raise (Error type varies by Playwright)
            with pytest.raises(Exception):
                await page.goto("not-a-valid-url")

            # Browser should still be usable
            response = await page.goto("https://example.com")
            assert response.status == 200

            await context.close()
            await pool.release_browser(browser.id)

    async def test_context_close_and_recreate(self):
        """Closing context should allow creating new ones."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()

            # Create and close multiple contexts
            for _ in range(3):
                context = await browser.browser.new_context()
                page = await context.new_page()
                await page.goto("https://example.com")
                await context.close()

            await pool.release_browser(browser.id)

    async def test_page_crash_recovery(self):
        """Browser should handle page crashes."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()
            page = await context.new_page()

            # Crash the page by navigating to chrome://crash
            with pytest.raises(Exception):
                await page.goto("chrome://crash", timeout=5000)

            # Create new page - should work
            page2 = await context.new_page()
            response = await page2.goto("https://example.com")
            assert response.status == 200

            await context.close()
            await pool.release_browser(browser.id)

    async def test_browser_disconnect_detection(self):
        """Pool should detect browser disconnection."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        async with pool:
            browser = await pool.acquire_browser()
            context = await browser.browser.new_context()
            page = await context.new_page()

            await page.goto("https://example.com")

            # Forcefully close the browser (simulating crash)
            await browser.browser.close()

            # Browser should be disconnected
            assert not browser.browser.is_connected()

            # Release should still work (no exception)
            await pool.release_browser(browser.id)

    async def test_pool_cleanup_after_browser_crash(self):
        """Pool cleanup should handle crashed browsers."""
        pool = BrowserPool(max_browsers=2, headless=True, use_virtual_display=False)

        async with pool:
            browsers = [await pool.acquire_browser() for _ in range(2)]

            # Close one browser directly (simulating crash)
            await browsers[0].browser.close()

            # Release both - should not raise
            for b in browsers:
                await pool.release_browser(b.id)

        # Pool stop should complete without error
        assert pool.is_started is False


# =============================================================================
# Resource Cleanup Tests
# =============================================================================


class TestResourceCleanup:
    """Tests for proper resource cleanup."""

    async def test_contexts_cleaned_on_pool_stop(self):
        """All contexts should be closed when pool stops."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        context_ref = None
        async with pool:
            browser = await pool.acquire_browser()
            context_ref = await browser.browser.new_context()
            await context_ref.new_page()
            # Don't explicitly close context

        # After pool stops, context should be closed
        # (browser close closes all contexts)

    async def test_multiple_start_stop_cycles(self):
        """Pool should handle multiple start/stop cycles."""
        pool = BrowserPool(max_browsers=1, headless=True, use_virtual_display=False)

        for _ in range(3):
            async with pool:
                browser = await pool.acquire_browser()
                context = await browser.browser.new_context()
                page = await context.new_page()
                await page.goto("https://example.com")
                await context.close()
                await pool.release_browser(browser.id)

            assert pool.is_started is False
            assert pool.size == 0
