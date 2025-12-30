"""Browser pool management with a singleton pattern and virtual display support."""

import asyncio
import logging
import socket
import uuid
from dataclasses import dataclass
from types import TracebackType
from typing import ClassVar

from patchright.async_api import Browser, Playwright, async_playwright
from pyvirtualdisplay import Display

from browser_scraper_pool.config import settings

logger = logging.getLogger(__name__)


class PoolNotStartedError(RuntimeError):
    """Raised when attempting operations on a pool that hasn't been started."""

    def __init__(self) -> None:
        super().__init__("Pool not started")


class NoBrowserAvailableError(RuntimeError):
    """Raised when no browser is available in the pool."""

    def __init__(self) -> None:
        super().__init__("No browser available in pool")


class BrowserInUseError(RuntimeError):
    """Raised when attempting to remove a browser in use."""

    def __init__(self) -> None:
        super().__init__("Cannot remove browser that is in use")


def _find_free_port() -> int:
    """Find a free port by letting the OS assign one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


@dataclass
class BrowserInstance:
    """Wrapper for a browser instance with metadata."""

    id: str
    browser: Browser
    cdp_port: int
    proxy: str | None = None
    in_use: bool = False


class BrowserPool:
    """Singleton browser pool with virtual display support.

    Usage as context manager (recommended):

        Async with BrowserPool.get_instance() as pool:
            browser = await pool.acquire_browser()
            # use browser
            await pool.release_browser(browser.id)

    Or get existing instance:

        pool = BrowserPool.get_instance()
        await pool.start()
        # ... use pool ...
        await pool.stop()
    """

    _instance: ClassVar["BrowserPool | None"] = None

    def __init__(
        self,
        max_browsers: int | None = None,
        headless: bool | None = None,
        use_virtual_display: bool | None = None,
        virtual_display_size: tuple[int, int] | None = None,
    ) -> None:
        self.max_browsers = (
            max_browsers if max_browsers is not None else settings.browser_pool_size
        )
        self.headless = headless if headless is not None else settings.browser_headless
        self.use_virtual_display = (
            use_virtual_display
            if use_virtual_display is not None
            else settings.use_virtual_display
        )
        self.virtual_display_size = (
            virtual_display_size
            if virtual_display_size is not None
            else settings.virtual_display_size
        )

        self._playwright: Playwright | None = None
        self._display: Display | None = None
        self._browsers: dict[str, BrowserInstance] = {}
        self._available: asyncio.Queue[str] = asyncio.Queue()
        self._started: bool = False

    def __repr__(self) -> str:
        return (
            f"BrowserPool(max_browsers={self.max_browsers}, "
            f"headless={self.headless}, "
            f"use_virtual_display={self.use_virtual_display})"
        )

    @classmethod
    def get_instance(
        cls,
        max_browsers: int | None = None,
        headless: bool | None = None,
        use_virtual_display: bool | None = None,
    ) -> "BrowserPool":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls(
                max_browsers=max_browsers,
                headless=headless,
                use_virtual_display=use_virtual_display,
            )
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (mainly for testing)."""
        cls._instance = None

    async def __aenter__(self) -> "BrowserPool":
        """Start a pool when entering context."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop pool when exiting context, even on exception."""
        await self.stop()

    async def start(self) -> None:
        """Start the browser pool and launch initial browsers."""
        if self._started:
            return

        # Start a virtual display if configured and not headless
        if self.use_virtual_display and not self.headless:
            self._display = Display(
                visible=False,
                size=self.virtual_display_size,
            )
            self._display.start()

        self._playwright = await async_playwright().start()

        try:
            for _ in range(self.max_browsers):
                await self._create_browser()
            self._started = True
        except Exception:
            # Cleanup on failure
            await self._cleanup()
            raise

    async def stop(self) -> None:
        """Stop all browsers and cleanup."""
        if not self._started:
            return
        await self._cleanup()
        self._started = False

    async def _cleanup(self) -> None:
        """Internal cleanup - close all browsers, playwright, and display."""
        # Close all browsers
        for browser_instance in list(self._browsers.values()):
            try:
                await browser_instance.browser.close()
            except Exception:
                logger.debug(
                    "Error closing browser %s during cleanup",
                    browser_instance.id,
                    exc_info=True,
                )

        self._browsers.clear()

        # Clear the queue
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Stop playwright
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                logger.debug("Error stopping playwright during cleanup", exc_info=True)
            self._playwright = None

        # Stop virtual display
        if self._display:
            try:
                self._display.stop()
            except Exception:
                logger.debug(
                    "Error stopping virtual display during cleanup", exc_info=True
                )
            self._display = None

    async def _create_browser(self, proxy: str | None = None) -> BrowserInstance:
        """Create a new browser instance."""
        if not self._playwright:
            raise PoolNotStartedError

        browser_id = str(uuid.uuid4())
        cdp_port = _find_free_port()

        launch_options: dict = {
            "headless": self.headless,
            "args": [f"--remote-debugging-port={cdp_port}"],
        }
        if proxy:
            launch_options["proxy"] = {"server": proxy}

        browser = await self._playwright.chromium.launch(**launch_options)

        instance = BrowserInstance(
            id=browser_id,
            browser=browser,
            cdp_port=cdp_port,
            proxy=proxy,
        )

        self._browsers[browser_id] = instance
        await self._available.put(browser_id)

        return instance

    async def acquire_browser(self, timeout: float = 30.0) -> BrowserInstance:
        """Acquire an available browser from the pool."""
        try:
            browser_id = await asyncio.wait_for(
                self._available.get(),
                timeout=timeout,
            )
        except TimeoutError:
            raise NoBrowserAvailableError from None

        instance = self._browsers[browser_id]
        instance.in_use = True
        return instance

    async def release_browser(self, browser_id: str) -> None:
        """Release a browser back to the pool."""
        if browser_id not in self._browsers:
            return

        instance = self._browsers[browser_id]
        instance.in_use = False
        await self._available.put(browser_id)

    async def add_browser(self, proxy: str | None = None) -> BrowserInstance:
        """Add a new browser to the pool."""
        return await self._create_browser(proxy=proxy)

    async def remove_browser(self, browser_id: str) -> bool:
        """Remove a browser from the pool."""
        if browser_id not in self._browsers:
            return False

        instance = self._browsers[browser_id]
        if instance.in_use:
            raise BrowserInUseError

        # Remove from the pool BEFORE await (atomic in asyncio - no yield points)
        del self._browsers[browser_id]
        self._rebuild_available_queue()

        # Safe to await now - browser already removed from the pool
        await instance.browser.close()
        return True

    def _rebuild_available_queue(self) -> None:
        """Rebuild the available queue from current browsers not in use."""
        # Drain existing queue
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Re-add all available browsers
        for browser_id, instance in self._browsers.items():
            if not instance.in_use:
                self._available.put_nowait(browser_id)

    def list_browsers(self) -> list[dict]:
        """List all browsers in the pool."""
        return [
            {
                "id": instance.id,
                "proxy": instance.proxy,
                "in_use": instance.in_use,
                "cdp_port": instance.cdp_port,
            }
            for instance in self._browsers.values()
        ]

    @property
    def size(self) -> int:
        """Return the number of browsers in the pool."""
        return len(self._browsers)

    @property
    def available_count(self) -> int:
        """Return the number of available browsers."""
        return self._available.qsize()

    @property
    def is_started(self) -> bool:
        """Return whether the pool is started."""
        return self._started
