"""Context pool management with a singleton pattern and virtual display support."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import ClassVar

from patchright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from pyvirtualdisplay import Display

from browser_scraper_pool.config import settings

logger = logging.getLogger(__name__)


class PoolNotStartedError(RuntimeError):
    """Raised when attempting operations on a pool that hasn't been started."""

    def __init__(self) -> None:
        super().__init__("Pool not started")


class ContextNotFoundError(RuntimeError):
    """Raised when a context is not found in the pool."""

    def __init__(self, context_id: str) -> None:
        super().__init__(f"Context not found: {context_id}")


class ContextInUseError(RuntimeError):
    """Raised when attempting to remove a context that is in use."""

    def __init__(self) -> None:
        super().__init__("Cannot remove context that is in use")


class ContextNotAvailableError(RuntimeError):
    """Raised when trying to acquire a context that is already in use."""

    def __init__(self) -> None:
        super().__init__("Context is not available (already in use)")


@dataclass
class ContextInstance:
    """Wrapper for a browser context with metadata."""

    id: str
    context: BrowserContext
    page: Page
    proxy: str | None = None
    persistent: bool = False
    storage_path: Path | None = None

    # Tags for context selection (e.g., {"proxy:1.1.1.1", "premium", "protected"})
    tags: set[str] = field(default_factory=set)

    # State tracking
    in_use: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None

    # Health tracking
    total_requests: int = 0
    error_count: int = 0
    consecutive_errors: int = 0

    # Domain rate limiting - tracks last request time per domain
    domain_last_request: dict[str, datetime] = field(default_factory=dict)

    # CDP target URL for external CDP connections
    cdp_target_url: str | None = None


class ContextPool:
    """Singleton context pool managing a single browser with multiple contexts.

    Usage as context manager (recommended):

        async with ContextPool() as pool:
            ctx = await pool.create_context(proxy="http://...")
            await pool.acquire_context(ctx.id)
            # use context
            await pool.release_context(ctx.id)

    Or manually:

        pool = ContextPool.get_instance()
        await pool.start()
        # ... use pool ...
        await pool.stop()
    """

    _instance: ClassVar["ContextPool | None"] = None

    def __init__(
        self,
        headless: bool | None = None,
        use_virtual_display: bool | None = None,
        virtual_display_size: tuple[int, int] | None = None,
        cdp_port: int | None = None,
        persistent_contexts_dir: str | Path | None = None,
    ) -> None:
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
        self._cdp_port = cdp_port if cdp_port is not None else settings.cdp_port
        self.persistent_contexts_dir = Path(
            persistent_contexts_dir
            if persistent_contexts_dir is not None
            else settings.persistent_contexts_path
        )

        self._playwright: Playwright | None = None
        self._display: Display | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, ContextInstance] = {}
        self._started: bool = False

    def __repr__(self) -> str:
        return (
            f"ContextPool(headless={self.headless}, "
            f"use_virtual_display={self.use_virtual_display}, "
            f"cdp_port={self._cdp_port})"
        )

    @classmethod
    def get_instance(
        cls,
        headless: bool | None = None,
        use_virtual_display: bool | None = None,
        cdp_port: int | None = None,
    ) -> "ContextPool":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls(
                headless=headless,
                use_virtual_display=use_virtual_display,
                cdp_port=cdp_port,
            )
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (mainly for testing)."""
        cls._instance = None

    async def __aenter__(self) -> "ContextPool":
        """Start pool when entering context."""
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
        """Start the browser and prepare for context creation."""
        if self._started:
            return

        # Start virtual display if configured and not headless
        if self.use_virtual_display and not self.headless:
            self._display = Display(
                visible=False,
                size=self.virtual_display_size,
            )
            self._display.start()

        self._playwright = await async_playwright().start()

        try:
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[f"--remote-debugging-port={self._cdp_port}"],
            )
            self._started = True
        except Exception:
            await self._cleanup()
            raise

    async def stop(self) -> None:
        """Stop all contexts and the browser."""
        if not self._started:
            return
        await self._cleanup()
        self._started = False

    async def _cleanup(self) -> None:
        """Internal cleanup - close all contexts, browser, playwright, and display."""
        # Close all contexts
        for ctx_instance in list(self._contexts.values()):
            try:
                await ctx_instance.context.close()
            except Exception:
                logger.debug(
                    "Error closing context %s during cleanup",
                    ctx_instance.id,
                    exc_info=True,
                )

        self._contexts.clear()

        # Close browser
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                logger.debug("Error closing browser during cleanup", exc_info=True)
            self._browser = None

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

    async def create_context(
        self,
        proxy: str | None = None,
        persistent: bool = False,
        tags: set[str] | list[str] | None = None,
    ) -> ContextInstance:
        """Create a new browser context.

        Args:
            proxy: Optional proxy server URL (e.g., "http://user:pass@host:port")
            persistent: If True, saves cookies/storage to disk for reuse
            tags: Optional tags for context selection (proxy is auto-added as tag)

        Returns:
            ContextInstance with a ready-to-use page
        """
        if not self._started or not self._browser:
            raise PoolNotStartedError

        context_id = str(uuid.uuid4())
        storage_path: Path | None = None

        context_options: dict = {}
        if proxy:
            context_options["proxy"] = {"server": proxy}

        if persistent:
            storage_path = self.persistent_contexts_dir / context_id
            storage_path.mkdir(parents=True, exist_ok=True)
            # For persistent contexts, we use storage_state if it exists
            state_file = storage_path / "state.json"
            if state_file.exists():
                context_options["storage_state"] = str(state_file)

        context = await self._browser.new_context(**context_options)
        page = await context.new_page()

        # Get CDP target URL for this page
        cdp_target_url: str | None = None
        try:
            cdp_session = await context.new_cdp_session(page)
            target_info = await cdp_session.send("Target.getTargetInfo")
            target_id = target_info["targetInfo"]["targetId"]
            cdp_target_url = f"ws://127.0.0.1:{self._cdp_port}/devtools/page/{target_id}"
            await cdp_session.detach()
        except Exception:
            logger.debug("Failed to get CDP target URL", exc_info=True)

        # Build tags set - auto-add proxy as tag
        context_tags: set[str] = set(tags) if tags else set()
        if proxy:
            context_tags.add(f"proxy:{proxy}")

        instance = ContextInstance(
            id=context_id,
            context=context,
            page=page,
            proxy=proxy,
            persistent=persistent,
            storage_path=storage_path,
            tags=context_tags,
            cdp_target_url=cdp_target_url,
        )

        self._contexts[context_id] = instance
        return instance

    async def acquire_context(self, context_id: str) -> ContextInstance:
        """Acquire a context for exclusive use.

        Args:
            context_id: The ID of the context to acquire

        Returns:
            The acquired ContextInstance

        Raises:
            ContextNotFoundError: If context doesn't exist
            ContextNotAvailableError: If context is already in use
        """
        if context_id not in self._contexts:
            raise ContextNotFoundError(context_id)

        instance = self._contexts[context_id]
        if instance.in_use:
            raise ContextNotAvailableError

        instance.in_use = True
        return instance

    async def release_context(self, context_id: str) -> None:
        """Release a context back to the pool.

        Args:
            context_id: The ID of the context to release
        """
        if context_id not in self._contexts:
            return

        instance = self._contexts[context_id]

        # Save state for persistent contexts before releasing
        if instance.persistent and instance.storage_path:
            try:
                state_file = instance.storage_path / "state.json"
                storage_state = await instance.context.storage_state()
                state_file.write_text(
                    __import__("json").dumps(storage_state, indent=2)
                )
            except Exception:
                logger.debug(
                    "Error saving storage state for context %s",
                    context_id,
                    exc_info=True,
                )

        instance.in_use = False

    async def remove_context(self, context_id: str) -> bool:
        """Remove and close a context from the pool.

        Args:
            context_id: The ID of the context to remove

        Returns:
            True if removed, False if not found

        Raises:
            ContextInUseError: If context is currently in use
        """
        if context_id not in self._contexts:
            return False

        instance = self._contexts[context_id]
        if instance.in_use:
            raise ContextInUseError

        # Remove from pool before await (atomic in asyncio)
        del self._contexts[context_id]

        # Save final state for persistent contexts
        if instance.persistent and instance.storage_path:
            try:
                state_file = instance.storage_path / "state.json"
                storage_state = await instance.context.storage_state()
                state_file.write_text(
                    __import__("json").dumps(storage_state, indent=2)
                )
            except Exception:
                logger.debug(
                    "Error saving storage state for context %s",
                    context_id,
                    exc_info=True,
                )

        await instance.context.close()
        return True

    def get_context(self, context_id: str) -> ContextInstance | None:
        """Get a context by ID without acquiring it.

        Args:
            context_id: The ID of the context

        Returns:
            ContextInstance if found, None otherwise
        """
        return self._contexts.get(context_id)

    def list_contexts(
        self,
        tags: set[str] | list[str] | None = None,
    ) -> list[dict]:
        """List all contexts in the pool, optionally filtered by tags.

        Args:
            tags: If provided, only return contexts that have ALL these tags

        Returns:
            List of context info dictionaries
        """
        required_tags = set(tags) if tags else None

        results = []
        for instance in self._contexts.values():
            # Filter by tags if specified
            if required_tags and not required_tags.issubset(instance.tags):
                continue

            results.append({
                "id": instance.id,
                "proxy": instance.proxy,
                "persistent": instance.persistent,
                "in_use": instance.in_use,
                "created_at": instance.created_at.isoformat(),
                "tags": list(instance.tags),
                "last_used_at": (
                    instance.last_used_at.isoformat() if instance.last_used_at else None
                ),
                "total_requests": instance.total_requests,
                "error_count": instance.error_count,
                "consecutive_errors": instance.consecutive_errors,
                "cdp_url": instance.cdp_target_url,
            })

        return results

    def add_tags(self, context_id: str, tags: set[str] | list[str]) -> bool:
        """Add tags to a context.

        Args:
            context_id: The ID of the context
            tags: Tags to add

        Returns:
            True if context found and tags added, False if context not found
        """
        instance = self._contexts.get(context_id)
        if not instance:
            return False
        instance.tags.update(tags)
        return True

    def remove_tags(self, context_id: str, tags: set[str] | list[str]) -> bool:
        """Remove tags from a context.

        Args:
            context_id: The ID of the context
            tags: Tags to remove

        Returns:
            True if context found and tags removed, False if context not found
        """
        instance = self._contexts.get(context_id)
        if not instance:
            return False
        instance.tags.difference_update(tags)
        return True

    def select_context(
        self,
        tags: set[str] | list[str] | None = None,
        domain: str | None = None,
        domain_delay_ms: int | None = None,
    ) -> ContextInstance | None:
        """Find best available context matching criteria.

        Selection order:
        1. Filter by tags (all must match)
        2. Filter by availability (not in_use)
        3. Filter by rate limit (domain not rate-limited)
        4. Sort by health score (prefer healthier contexts)

        Args:
            tags: Required tags (all must match). None means no tag filter.
            domain: Domain for rate limit check. None skips rate limit check.
            domain_delay_ms: Override delay for rate limit check.

        Returns:
            Best available ContextInstance, or None if no match.
        """
        # Import here to avoid circular dependency
        from browser_scraper_pool.config import settings  # noqa: PLC0415, I001
        from browser_scraper_pool.pool.rate_limiter import DomainRateLimiter  # noqa: PLC0415

        required_tags = set(tags) if tags else None
        candidates: list[ContextInstance] = []

        for ctx in self._contexts.values():
            # Filter: must not be in use
            if ctx.in_use:
                continue

            # Filter: must have all required tags
            if required_tags and not required_tags.issubset(ctx.tags):
                continue

            # Filter: must not be rate-limited for domain
            if domain:
                limiter = DomainRateLimiter(
                    default_delay_ms=settings.default_domain_delay_ms
                )
                if not limiter.can_request(ctx, domain, domain_delay_ms):
                    continue

            candidates.append(ctx)

        if not candidates:
            return None

        # Sort by health score (lower is better - fewer errors preferred)
        def health_score(ctx: ContextInstance) -> float:
            error_rate = (
                ctx.error_count / ctx.total_requests if ctx.total_requests > 0 else 0
            )
            return ctx.consecutive_errors * 10 + error_rate * 5

        candidates.sort(key=health_score)
        return candidates[0]

    def get_available_contexts(
        self,
        tags: set[str] | list[str] | None = None,
    ) -> list[ContextInstance]:
        """Get all available (not in use) contexts, optionally filtered by tags.

        Args:
            tags: Required tags (all must match). None means no tag filter.

        Returns:
            List of available ContextInstance objects.
        """
        required_tags = set(tags) if tags else None
        results = []

        for ctx in self._contexts.values():
            if ctx.in_use:
                continue
            if required_tags and not required_tags.issubset(ctx.tags):
                continue
            results.append(ctx)

        return results

    async def evict_and_replace(
        self,
        tags: set[str] | list[str] | None = None,
        proxy: str | None = None,
    ) -> ContextInstance | None:
        """Evict worst-scoring context and create a new one with given tags.

        Used when pool is full and no matching context available.

        Args:
            tags: Tags for the new context.
            proxy: Proxy for the new context.

        Returns:
            New ContextInstance, or None if no context could be evicted.
        """
        from browser_scraper_pool.config import settings  # noqa: PLC0415, I001
        from browser_scraper_pool.pool.eviction import find_eviction_candidate  # noqa: PLC0415

        # Check if pool is at capacity
        if self.size < settings.max_contexts:
            # Pool not full, just create a new context
            return await self.create_context(proxy=proxy, tags=tags)

        # Find eviction candidate
        candidate = find_eviction_candidate(self._contexts)
        if not candidate:
            return None

        # Evict the candidate
        logger.info(
            "Evicting context %s (score-based replacement)",
            candidate.id,
        )
        await self.remove_context(candidate.id)

        # Create new context with requested tags
        return await self.create_context(proxy=proxy, tags=tags)

    async def recreate_context(self, context_id: str) -> ContextInstance | None:
        """Recreate a context, preserving its tags and proxy.

        Used when a context has too many consecutive errors.

        Args:
            context_id: The ID of the context to recreate.

        Returns:
            New ContextInstance, or None if original context not found.
        """
        ctx = self.get_context(context_id)
        if not ctx:
            return None

        # Save properties to recreate
        proxy = ctx.proxy
        persistent = ctx.persistent
        tags = ctx.tags.copy()

        # Remove proxy auto-tag since create_context will add it
        if proxy:
            tags.discard(f"proxy:{proxy}")

        # Close old context
        logger.info("Recreating context %s due to consecutive errors", context_id)
        ctx.in_use = False  # Force release so we can remove it
        await self.remove_context(context_id)

        # Create new context with same properties
        return await self.create_context(
            proxy=proxy,
            persistent=persistent,
            tags=tags,
        )

    def get_cdp_endpoint(self) -> str:
        """Get the CDP WebSocket endpoint URL.

        Returns:
            WebSocket URL for CDP connection (e.g., ws://localhost:9222)
        """
        return f"ws://127.0.0.1:{self._cdp_port}"

    @property
    def size(self) -> int:
        """Return the number of contexts in the pool."""
        return len(self._contexts)

    @property
    def available_count(self) -> int:
        """Return the number of available (not in use) contexts."""
        return sum(1 for ctx in self._contexts.values() if not ctx.in_use)

    @property
    def is_started(self) -> bool:
        """Return whether the pool is started."""
        return self._started

    @property
    def cdp_port(self) -> int:
        """Return the CDP port."""
        return self._cdp_port
