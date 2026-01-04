"""Unified scrape API endpoint."""

import asyncio
import base64
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from patchright._impl._errors import TargetClosedError

from browser_scraper_pool.api.dependencies import PoolDep
from browser_scraper_pool.config import settings
from browser_scraper_pool.models.schemas import ScrapeRequest, ScrapeResponse
from browser_scraper_pool.pool.eviction import should_recreate
from browser_scraper_pool.pool.rate_limiter import DomainRateLimiter
from browser_scraper_pool.pool.request_queue import RequestQueue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scrape"])

# Global request queue
_request_queue = RequestQueue()


def get_request_queue() -> RequestQueue:
    """Get the global request queue."""
    return _request_queue


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape(pool: PoolDep, body: ScrapeRequest) -> ScrapeResponse:
    """Unified scrape endpoint with smart context selection.

    This endpoint:
    1. Selects the best available context matching tags/proxy
    2. If no context available, waits in queue (up to max_queue_wait_seconds)
    3. If pool is full, evicts worst context and creates a new one
    4. Executes the scrape request
    5. Returns the result immediately

    The context is automatically acquired and released.
    """
    queue = get_request_queue()
    limiter = DomainRateLimiter(default_delay_ms=settings.default_domain_delay_ms)

    # Tags for SELECTION (user's tags only, no proxy filter)
    selection_tags: set[str] = set(body.tags) if body.tags else set()

    # Tags for CREATION (user's tags, proxy auto-added by create_context)
    creation_tags: list[str] = list(body.tags) if body.tags else []

    # Extract domain from URL
    domain = limiter.extract_domain(str(body.url))

    # Track queue wait time
    queue_start = datetime.now(UTC)
    queue_wait_ms = 0

    # Try to select a context by tags only (no proxy filter)
    ctx = pool.select_context(
        tags=selection_tags if selection_tags else None,
        domain=domain,
        domain_delay_ms=body.domain_delay,
    )

    # If no context available, create one (or evict and replace if pool full)
    if ctx is None:
        # evict_and_replace handles both cases:
        # - pool not full: creates new context
        # - pool full: evicts the worst candidate, creates new
        try:
            ctx = await pool.evict_and_replace(
                tags=creation_tags if creation_tags else None,
                proxy=body.proxy,
            )
        except TargetClosedError:
            logger.warning("Browser crashed and could not be restarted")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Browser crashed and could not be restarted. Please try again.",
            ) from None

        # If still no context, queue the request
        if ctx is None:
            queued = await queue.enqueue(
                tags=selection_tags if selection_tags else None,
                domain=domain,
                domain_delay_ms=body.domain_delay,
            )

            try:
                # Wait for context with timeout
                ctx = await asyncio.wait_for(
                    queued.future,
                    timeout=settings.max_queue_wait_seconds,
                )
            except TimeoutError:
                await queue.dequeue(queued.id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"No context available after {settings.max_queue_wait_seconds}s",
                ) from None

            queue_wait_ms = int(
                (datetime.now(UTC) - queue_start).total_seconds() * 1000
            )

    # Acquire the context
    try:
        ctx = await pool.acquire_context(ctx.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to acquire context: {e}",
        ) from e

    # Execute the scrape
    try:
        result = await _execute_scrape(ctx, body, limiter, domain)
        result.queue_wait_ms = queue_wait_ms
        return result
    finally:
        # Always release the context
        await pool.release_context(ctx.id)

        # Check if context needs recreation
        if should_recreate(ctx):
            logger.info(
                "Context %s has %d consecutive errors, scheduling recreation",
                ctx.id,
                ctx.consecutive_errors,
            )
            # Recreate in background to not block the response
            asyncio.create_task(pool.recreate_context(ctx.id))  # noqa: RUF006


async def _execute_scrape(
    ctx, body: ScrapeRequest, limiter: DomainRateLimiter, domain: str
) -> ScrapeResponse:
    """Execute the scrape request on a context.

    Args:
        ctx: The acquired context.
        body: The scrape request.
        limiter: Rate limiter instance.
        domain: Domain being scraped.

    Returns:
        ScrapeResponse with results.
    """
    try:
        # Record request for rate limiting
        limiter.record_request(ctx, domain)

        # Navigate to URL
        response = await ctx.page.goto(
            str(body.url),
            timeout=body.timeout,
            wait_until=body.wait_until,
        )

        final_url = ctx.page.url
        status_code = response.status if response else None

        # Get content if requested
        content = None
        if body.get_content:
            content = await ctx.page.content()

        # Execute script if provided
        script_result = None
        if body.script:
            try:
                script_result = await ctx.page.evaluate(body.script)
            except Exception as e:
                logger.warning("Script execution failed for context %s: %s", ctx.id, e)
                # Don't fail the whole request, just note the error
                script_result = None

        # Take screenshot if requested
        screenshot = None
        if body.screenshot:
            screenshot_bytes = await ctx.page.screenshot(
                full_page=body.screenshot_full_page,
                type="png",
            )
            screenshot = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Record success
        limiter.record_success(ctx)

        return ScrapeResponse(
            success=True,
            url=final_url,
            status=status_code,
            content=content,
            script_result=script_result,
            screenshot=screenshot,
            context_id=ctx.id,
            queue_wait_ms=0,
            error=None,
        )

    except Exception as e:
        # Record error
        limiter.record_error(ctx)
        logger.warning("Scrape failed for context %s: %s", ctx.id, e)

        return ScrapeResponse(
            success=False,
            url=str(body.url),
            status=None,
            content=None,
            script_result=None,
            screenshot=None,
            context_id=ctx.id,
            queue_wait_ms=0,
            error=str(e),
        )
