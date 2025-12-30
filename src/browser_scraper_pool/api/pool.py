"""Pool status API endpoints."""

from fastapi import APIRouter, Request

from browser_scraper_pool.models.schemas import CDPResponse, PoolStatusResponse
from browser_scraper_pool.pool.context_pool import ContextPool

router = APIRouter(prefix="/pool", tags=["pool"])


def get_pool(request: Request) -> ContextPool:
    """Get the context pool from app state."""
    return request.app.state.context_pool


@router.get("/status", response_model=PoolStatusResponse)
async def get_status(request: Request):
    """Get the current pool status.

    Returns information about the pool including:
    - Number of contexts (total, available, in use)
    - CDP connection details
    - Whether the pool is started
    """
    pool = get_pool(request)

    return PoolStatusResponse(
        size=pool.size,
        available=pool.available_count,
        in_use=pool.size - pool.available_count,
        cdp_port=pool.cdp_port,
        cdp_endpoint=pool.get_cdp_endpoint(),
        is_started=pool.is_started,
    )


@router.get("/cdp", response_model=CDPResponse)
async def get_cdp(request: Request):
    """Get the CDP (Chrome DevTools Protocol) endpoint.

    Use this endpoint to get the WebSocket URL for connecting external tools
    (like captcha solvers) to the browser via CDP.
    """
    pool = get_pool(request)

    return CDPResponse(
        endpoint=pool.get_cdp_endpoint(),
        port=pool.cdp_port,
    )
