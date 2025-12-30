"""Integration tests with real Chrome browser.

These tests launch actual browser instances to verify real-world behavior.
Run with: pytest tests/test_context_pool_integration.py -v

Note: Requires Chromium installed (patchright install chromium)
"""

import asyncio

import pytest

from browser_scraper_pool.pool.context_pool import ContextPool


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    ContextPool.reset_instance()
    yield
    ContextPool.reset_instance()


# =============================================================================
# Basic Context Operations
# =============================================================================


class TestRealContextOperations:
    """Tests with real browser contexts."""

    async def test_pool_starts_browser(self):
        """Pool should start a real browser."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            assert pool.is_started is True

    async def test_create_context(self):
        """Should create a real browser context."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx = await pool.create_context()

            assert ctx.id is not None
            assert ctx.context is not None
            assert ctx.page is not None
            assert pool.size == 1

    async def test_navigate_to_url(self):
        """Context should navigate to URLs and get content."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx = await pool.create_context()
            await pool.acquire_context(ctx.id)

            response = await ctx.page.goto("https://example.com")

            assert response is not None
            assert response.status == 200

            title = await ctx.page.title()
            assert "Example" in title

            content = await ctx.page.content()
            assert "<html" in content.lower()

            await pool.release_context(ctx.id)

    async def test_execute_javascript(self):
        """Context should execute JavaScript and return results."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx = await pool.create_context()
            await pool.acquire_context(ctx.id)

            await ctx.page.goto("https://example.com")

            # Simple JS
            result = await ctx.page.evaluate("1 + 2")
            assert result == 3

            # Object return
            result = await ctx.page.evaluate("({ name: 'test', value: 42 })")
            assert result == {"name": "test", "value": 42}

            # DOM access
            result = await ctx.page.evaluate("document.title")
            assert "Example" in result

            await pool.release_context(ctx.id)

    async def test_multiple_contexts(self):
        """Multiple contexts should work independently."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx1 = await pool.create_context()
            ctx2 = await pool.create_context()

            await pool.acquire_context(ctx1.id)
            await pool.acquire_context(ctx2.id)

            await ctx1.page.goto("https://example.com")
            await ctx2.page.goto("https://httpbin.org/html")

            title1 = await ctx1.page.title()
            title2 = await ctx2.page.title()

            # Different pages should have different titles
            assert title1 != title2
            assert "Example" in title1

            await pool.release_context(ctx1.id)
            await pool.release_context(ctx2.id)


# =============================================================================
# Pool Behavior Tests
# =============================================================================


class TestRealPoolBehavior:
    """Tests for pool behavior with real browser."""

    async def test_acquire_release_cycle(self):
        """Context should be reusable after release."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx = await pool.create_context()

            # First acquire
            await pool.acquire_context(ctx.id)
            await pool.release_context(ctx.id)

            # Second acquire - should work
            await pool.acquire_context(ctx.id)
            await ctx.page.goto("https://example.com")

            await pool.release_context(ctx.id)

    async def test_concurrent_contexts(self):
        """Multiple contexts should work concurrently."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async def fetch_title(ctx_instance) -> str:
            await ctx_instance.page.goto("https://example.com", timeout=30000)
            return await ctx_instance.page.title()

        async with pool:
            ctx1 = await pool.create_context()
            ctx2 = await pool.create_context()

            await pool.acquire_context(ctx1.id)
            await pool.acquire_context(ctx2.id)

            # Run two fetches concurrently
            results = await asyncio.gather(
                fetch_title(ctx1),
                fetch_title(ctx2),
            )

            assert len(results) == 2
            assert all("Example" in r for r in results)

            await pool.release_context(ctx1.id)
            await pool.release_context(ctx2.id)

    async def test_cdp_port_is_valid(self):
        """Browser should have a valid CDP port."""
        pool = ContextPool(headless=True, use_virtual_display=False, cdp_port=9222)

        async with pool:
            assert pool.cdp_port == 9222
            endpoint = pool.get_cdp_endpoint()
            assert "9222" in endpoint


# =============================================================================
# Error and Recovery Tests
# =============================================================================


class TestErrorAndRecovery:
    """Tests for error scenarios and recovery."""

    async def test_navigation_timeout_handling(self):
        """Pool should handle navigation timeouts gracefully."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx = await pool.create_context()
            await pool.acquire_context(ctx.id)

            # Try to navigate to a non-responsive URL with short timeout
            # Patchright raises its own TimeoutError, not Python's built-in
            with pytest.raises(Exception, match="Timeout"):
                await ctx.page.goto("http://10.255.255.1", timeout=1000)

            # Context should still be usable
            response = await ctx.page.goto("https://example.com", timeout=30000)
            assert response.status == 200

            await pool.release_context(ctx.id)

    async def test_invalid_url_handling(self):
        """Pool should handle invalid URLs."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx = await pool.create_context()
            await pool.acquire_context(ctx.id)

            # Navigate to invalid URL should raise
            with pytest.raises(Exception):
                await ctx.page.goto("not-a-valid-url")

            # Context should still be usable
            response = await ctx.page.goto("https://example.com")
            assert response.status == 200

            await pool.release_context(ctx.id)

    async def test_context_close_and_recreate(self):
        """Removing context should allow creating new ones."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            # Create and remove contexts
            for _ in range(3):
                ctx = await pool.create_context()
                await pool.acquire_context(ctx.id)
                await ctx.page.goto("https://example.com")
                await pool.release_context(ctx.id)
                await pool.remove_context(ctx.id)

            assert pool.size == 0

    async def test_page_crash_recovery(self):
        """Browser should handle page crashes."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            ctx = await pool.create_context()
            await pool.acquire_context(ctx.id)

            # Crash the page
            with pytest.raises(Exception):
                await ctx.page.goto("chrome://crash", timeout=5000)

            # Create new page in same context - should work
            new_page = await ctx.context.new_page()
            response = await new_page.goto("https://example.com")
            assert response.status == 200

            await pool.release_context(ctx.id)


# =============================================================================
# Persistent Context Tests
# =============================================================================


class TestPersistentContexts:
    """Tests for persistent context storage."""

    async def test_persistent_context_creates_storage_dir(self, tmp_path):
        """Persistent context should create storage directory."""
        pool = ContextPool(
            headless=True,
            use_virtual_display=False,
            persistent_contexts_dir=tmp_path,
        )

        async with pool:
            ctx = await pool.create_context(persistent=True)

            assert ctx.persistent is True
            assert ctx.storage_path is not None
            assert ctx.storage_path.exists()

    async def test_persistent_context_saves_state_on_release(self, tmp_path):
        """Persistent context should save state on release."""
        pool = ContextPool(
            headless=True,
            use_virtual_display=False,
            persistent_contexts_dir=tmp_path,
        )

        async with pool:
            ctx = await pool.create_context(persistent=True)
            await pool.acquire_context(ctx.id)

            # Navigate to set some cookies
            await ctx.page.goto("https://example.com")

            await pool.release_context(ctx.id)

            # State file should exist
            state_file = ctx.storage_path / "state.json"
            assert state_file.exists()


# =============================================================================
# Resource Cleanup Tests
# =============================================================================


class TestResourceCleanup:
    """Tests for proper resource cleanup."""

    async def test_contexts_cleaned_on_pool_stop(self):
        """All contexts should be closed when pool stops."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        async with pool:
            await pool.create_context()
            await pool.create_context()
            assert pool.size == 2

        # After pool stops, contexts should be cleaned
        assert pool.size == 0

    async def test_multiple_start_stop_cycles(self):
        """Pool should handle multiple start/stop cycles."""
        pool = ContextPool(headless=True, use_virtual_display=False)

        for _ in range(3):
            async with pool:
                ctx = await pool.create_context()
                await pool.acquire_context(ctx.id)
                await ctx.page.goto("https://example.com")
                await pool.release_context(ctx.id)

            assert pool.is_started is False
            assert pool.size == 0
