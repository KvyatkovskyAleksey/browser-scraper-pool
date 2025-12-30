"""API endpoints."""

from browser_scraper_pool.api.contexts import router as contexts_router
from browser_scraper_pool.api.dependencies import PoolDep, get_pool
from browser_scraper_pool.api.jobs import router as jobs_router
from browser_scraper_pool.api.pool import router as pool_router

__all__ = [
    "PoolDep",
    "contexts_router",
    "get_pool",
    "jobs_router",
    "pool_router",
]
