"""Context management API endpoints."""

import asyncio
import base64
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from browser_scraper_pool.api.dependencies import (
    PoolDep,
    context_response_from_instance,
)
from browser_scraper_pool.models.schemas import (
    ContentResponse,
    ContextCreate,
    ContextListResponse,
    ContextResponse,
    ContextTagsUpdate,
    ExecuteRequest,
    ExecuteResponse,
    GotoRequest,
    GotoResponse,
    ScreenshotRequest,
    ScreenshotResponse,
)
from browser_scraper_pool.pool.context_pool import (
    ContextInUseError,
    ContextNotAvailableError,
    ContextNotFoundError,
    ContextPool,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contexts", tags=["contexts"])


# =============================================================================
# Context CRUD
# =============================================================================


@router.post("", response_model=ContextResponse, status_code=status.HTTP_201_CREATED)
async def create_context(pool: PoolDep, body: ContextCreate):
    """Create a new browser context.

    Creates an isolated browser context with optional proxy, persistence, and tags.
    The context includes a clean default page ready for navigation.
    Proxy is automatically added as a tag (e.g., "proxy:http://...").
    """
    ctx = await pool.create_context(
        proxy=body.proxy,
        persistent=body.persistent,
        tags=body.tags,
    )

    logger.info(
        "Created context %s (proxy=%s, persistent=%s, tags=%s)",
        ctx.id,
        ctx.proxy,
        ctx.persistent,
        ctx.tags,
    )

    return ContextResponse(**context_response_from_instance(ctx))


@router.get("", response_model=ContextListResponse)
async def list_contexts(
    pool: PoolDep,
    tags: Annotated[
        str | None,
        Query(description="Comma-separated tags to filter by (all must match)"),
    ] = None,
):
    """List all contexts in the pool, optionally filtered by tags."""
    # Parse comma-separated tags
    tag_filter = tags.split(",") if tags else None

    contexts = pool.list_contexts(tags=tag_filter)

    return ContextListResponse(
        contexts=[
            ContextResponse(
                id=c["id"],
                proxy=c["proxy"],
                proxy_config=c["proxy_config"],
                persistent=c["persistent"],
                in_use=c["in_use"],
                created_at=c["created_at"],
                tags=c["tags"],
                last_used_at=c["last_used_at"],
                total_requests=c["total_requests"],
                error_count=c["error_count"],
                consecutive_errors=c["consecutive_errors"],
                cdp_url=c["cdp_url"],
            )
            for c in contexts
        ],
        total=len(contexts),
    )


@router.get("/{context_id}", response_model=ContextResponse)
async def get_context(pool: PoolDep, context_id: str):
    """Get information about a specific context."""
    ctx = pool.get_context(context_id)

    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context not found: {context_id}",
        )

    return ContextResponse(**context_response_from_instance(ctx))


@router.patch("/{context_id}/tags", response_model=ContextResponse)
async def update_tags(pool: PoolDep, context_id: str, body: ContextTagsUpdate):
    """Update tags on a context.

    Add and/or remove tags from a context. Useful for marking contexts
    as "protected" or adding custom labels.
    """
    ctx = pool.get_context(context_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context not found: {context_id}",
        )

    if body.add:
        pool.add_tags(context_id, body.add)
    if body.remove:
        pool.remove_tags(context_id, body.remove)

    logger.info(
        "Updated tags for context %s: +%s -%s", context_id, body.add, body.remove
    )

    return ContextResponse(**context_response_from_instance(ctx))


@router.delete("/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(pool: PoolDep, context_id: str):
    """Remove and close a context.

    The context must not be in use (acquired) when deleting.
    """
    try:
        removed = await pool.remove_context(context_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Context not found: {context_id}",
            )
        logger.info("Removed context %s", context_id)
    except ContextInUseError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove context that is in use. Release it first.",
        ) from None


# =============================================================================
# Acquire/Release
# =============================================================================


@router.post("/{context_id}/acquire", response_model=ContextResponse)
async def acquire_context(pool: PoolDep, context_id: str):
    """Acquire a context for exclusive use.

    Once acquired, the context cannot be acquired by another caller until released.
    This is useful for operations that require exclusive access, like captcha solving.
    """
    try:
        ctx = await pool.acquire_context(context_id)
        logger.info("Acquired context %s", context_id)

        return ContextResponse(**context_response_from_instance(ctx))
    except ContextNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context not found: {context_id}",
        ) from None
    except ContextNotAvailableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Context is already in use",
        ) from None


@router.post("/{context_id}/release", response_model=ContextResponse)
async def release_context(pool: PoolDep, context_id: str):
    """Release a context back to the pool.

    After release, the context can be acquired again by any caller.
    """
    ctx = pool.get_context(context_id)

    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context not found: {context_id}",
        )

    await pool.release_context(context_id)
    logger.info("Released context %s", context_id)

    return ContextResponse(**context_response_from_instance(ctx))


# =============================================================================
# Scraping Operations
# =============================================================================


def _require_acquired(pool: ContextPool, context_id: str):
    """Ensure context exists and is acquired."""
    ctx = pool.get_context(context_id)

    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context not found: {context_id}",
        )

    if not ctx.in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Context must be acquired before use. Call POST /contexts/{id}/acquire first.",
        )

    return ctx


@router.post("/{context_id}/goto", response_model=GotoResponse)
async def goto(pool: PoolDep, context_id: str, body: GotoRequest):
    """Navigate to a URL.

    The context must be acquired before navigation.
    """
    ctx = _require_acquired(pool, context_id)

    try:
        response = await ctx.page.goto(
            str(body.url),  # Convert AnyHttpUrl to string
            timeout=body.timeout,
            wait_until=body.wait_until,
        )

        return GotoResponse(
            url=ctx.page.url,
            status=response.status if response else None,
            ok=response.ok if response else False,
        )
    except Exception as e:
        logger.warning("Navigation failed for context %s: %s", context_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Navigation failed: {e}",
        ) from e


@router.post("/{context_id}/content", response_model=ContentResponse)
async def get_content(pool: PoolDep, context_id: str):
    """Get the current page HTML content.

    The context must be acquired before getting content.
    """
    ctx = _require_acquired(pool, context_id)

    try:
        content = await ctx.page.content()
        return ContentResponse(url=ctx.page.url, content=content)
    except Exception as e:
        logger.warning("Failed to get content for context %s: %s", context_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get content: {e}",
        ) from e


@router.post("/{context_id}/execute", response_model=ExecuteResponse)
async def execute_script(pool: PoolDep, context_id: str, body: ExecuteRequest):
    """Execute JavaScript in the page context.

    The context must be acquired before executing scripts.
    Returns the result of the script execution (must be JSON-serializable).
    """
    ctx = _require_acquired(pool, context_id)

    try:
        # page.evaluate doesn't have timeout param, use asyncio.wait_for
        timeout_seconds = body.timeout / 1000  # Convert ms to seconds
        result = await asyncio.wait_for(
            ctx.page.evaluate(body.script),
            timeout=timeout_seconds,
        )
        return ExecuteResponse(result=result)
    except TimeoutError:
        logger.warning("Script execution timed out for context %s", context_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Script execution timed out after {body.timeout}ms",
        ) from None
    except Exception as e:
        logger.warning("Script execution failed for context %s: %s", context_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Script execution failed: {e}",
        ) from e


@router.post("/{context_id}/screenshot", response_model=ScreenshotResponse)
async def take_screenshot(pool: PoolDep, context_id: str, body: ScreenshotRequest):
    """Take a screenshot of the current page.

    The context must be acquired before taking screenshots.
    Returns base64-encoded image data.
    """
    ctx = _require_acquired(pool, context_id)

    try:
        screenshot_bytes = await ctx.page.screenshot(
            full_page=body.full_page,
            type=body.format,  # Playwright uses 'type', we renamed to 'format'
            quality=body.quality if body.format == "jpeg" else None,
        )

        return ScreenshotResponse(
            data=base64.b64encode(screenshot_bytes).decode("utf-8"),
            format=body.format,
        )
    except Exception as e:
        logger.warning("Screenshot failed for context %s: %s", context_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screenshot failed: {e}",
        ) from e
