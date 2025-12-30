"""Context management API endpoints."""

import base64
import logging

from fastapi import APIRouter, HTTPException, Request, status

from browser_scraper_pool.models.schemas import (
    ContentResponse,
    ContextCreate,
    ContextListResponse,
    ContextResponse,
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


def get_pool(request: Request) -> ContextPool:
    """Get the context pool from app state."""
    return request.app.state.context_pool


# =============================================================================
# Context CRUD
# =============================================================================


@router.post("", response_model=ContextResponse, status_code=status.HTTP_201_CREATED)
async def create_context(request: Request, body: ContextCreate):
    """Create a new browser context.

    Creates an isolated browser context with optional proxy and persistence settings.
    The context includes a clean default page ready for navigation.
    """
    pool = get_pool(request)
    ctx = await pool.create_context(proxy=body.proxy, persistent=body.persistent)

    logger.info("Created context %s (proxy=%s, persistent=%s)", ctx.id, ctx.proxy, ctx.persistent)

    return ContextResponse(
        id=ctx.id,
        proxy=ctx.proxy,
        persistent=ctx.persistent,
        in_use=ctx.in_use,
        created_at=ctx.created_at,
    )


@router.get("", response_model=ContextListResponse)
async def list_contexts(request: Request):
    """List all contexts in the pool."""
    pool = get_pool(request)
    contexts = pool.list_contexts()

    return ContextListResponse(
        contexts=[
            ContextResponse(
                id=c["id"],
                proxy=c["proxy"],
                persistent=c["persistent"],
                in_use=c["in_use"],
                created_at=c["created_at"],
            )
            for c in contexts
        ],
        total=len(contexts),
    )


@router.get("/{context_id}", response_model=ContextResponse)
async def get_context(request: Request, context_id: str):
    """Get information about a specific context."""
    pool = get_pool(request)
    ctx = pool.get_context(context_id)

    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context not found: {context_id}",
        )

    return ContextResponse(
        id=ctx.id,
        proxy=ctx.proxy,
        persistent=ctx.persistent,
        in_use=ctx.in_use,
        created_at=ctx.created_at,
    )


@router.delete("/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(request: Request, context_id: str):
    """Remove and close a context.

    The context must not be in use (acquired) when deleting.
    """
    pool = get_pool(request)

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
async def acquire_context(request: Request, context_id: str):
    """Acquire a context for exclusive use.

    Once acquired, the context cannot be acquired by another caller until released.
    This is useful for operations that require exclusive access, like captcha solving.
    """
    pool = get_pool(request)

    try:
        ctx = await pool.acquire_context(context_id)
        logger.info("Acquired context %s", context_id)

        return ContextResponse(
            id=ctx.id,
            proxy=ctx.proxy,
            persistent=ctx.persistent,
            in_use=ctx.in_use,
            created_at=ctx.created_at,
        )
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
async def release_context(request: Request, context_id: str):
    """Release a context back to the pool.

    After release, the context can be acquired again by any caller.
    """
    pool = get_pool(request)
    ctx = pool.get_context(context_id)

    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context not found: {context_id}",
        )

    await pool.release_context(context_id)
    logger.info("Released context %s", context_id)

    return ContextResponse(
        id=ctx.id,
        proxy=ctx.proxy,
        persistent=ctx.persistent,
        in_use=ctx.in_use,
        created_at=ctx.created_at,
    )


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
async def goto(request: Request, context_id: str, body: GotoRequest):
    """Navigate to a URL.

    The context must be acquired before navigation.
    """
    pool = get_pool(request)
    ctx = _require_acquired(pool, context_id)

    try:
        response = await ctx.page.goto(
            body.url,
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
async def get_content(request: Request, context_id: str):
    """Get the current page HTML content.

    The context must be acquired before getting content.
    """
    pool = get_pool(request)
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
async def execute_script(request: Request, context_id: str, body: ExecuteRequest):
    """Execute JavaScript in the page context.

    The context must be acquired before executing scripts.
    Returns the result of the script execution (must be JSON-serializable).
    """
    pool = get_pool(request)
    ctx = _require_acquired(pool, context_id)

    try:
        result = await ctx.page.evaluate(body.script)
        return ExecuteResponse(result=result)
    except Exception as e:
        logger.warning("Script execution failed for context %s: %s", context_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Script execution failed: {e}",
        ) from e


@router.post("/{context_id}/screenshot", response_model=ScreenshotResponse)
async def take_screenshot(request: Request, context_id: str, body: ScreenshotRequest):
    """Take a screenshot of the current page.

    The context must be acquired before taking screenshots.
    Returns base64-encoded image data.
    """
    pool = get_pool(request)
    ctx = _require_acquired(pool, context_id)

    try:
        screenshot_bytes = await ctx.page.screenshot(
            full_page=body.full_page,
            type=body.type,
            quality=body.quality if body.type == "jpeg" else None,
        )

        return ScreenshotResponse(
            data=base64.b64encode(screenshot_bytes).decode("utf-8"),
            type=body.type,
        )
    except Exception as e:
        logger.warning("Screenshot failed for context %s: %s", context_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screenshot failed: {e}",
        ) from e
