"""Shared API dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from browser_scraper_pool.pool.context_pool import ContextInstance, ContextPool


def get_pool(request: Request) -> ContextPool:
    """Get the context pool from app state.

    This is the single source of truth for accessing the pool.
    The pool is stored in app.state during the lifespan context.
    """
    return request.app.state.context_pool  # type: ignore[return-value]


# Type alias for dependency injection
PoolDep = Annotated[ContextPool, Depends(get_pool)]


def context_response_from_instance(ctx: ContextInstance) -> dict:
    """Convert a ContextInstance to a response dict.

    This avoids repeating the same field mapping everywhere.
    """
    return {
        "id": ctx.id,
        "proxy": ctx.proxy,
        "persistent": ctx.persistent,
        "in_use": ctx.in_use,
        "created_at": ctx.created_at,
    }
