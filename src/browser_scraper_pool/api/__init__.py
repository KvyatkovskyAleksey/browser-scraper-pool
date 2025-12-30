"""API endpoints."""

from browser_scraper_pool.api.contexts import router as contexts_router
from browser_scraper_pool.api.pool import router as pool_router

__all__ = [
    "contexts_router",
    "pool_router",
]
