import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from browser_scraper_pool.api import contexts_router, pool_router
from browser_scraper_pool.pool.context_pool import ContextPool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - start/stop context pool."""
    pool = ContextPool.get_instance()
    async with pool:
        app.state.context_pool = pool
        logger.info(
            "Context pool started: headless=%s, virtual_display=%s, cdp_port=%d",
            pool.headless,
            pool.use_virtual_display,
            pool.cdp_port,
        )
        yield
        logger.info("Context pool stopped")


app = FastAPI(
    title="Browser Scraper Pool",
    description="Web scraping context pool service using Patchright + FastAPI",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(contexts_router)
app.include_router(pool_router)


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {"message": "Browser Scraper Pool API. See /docs for endpoints."}


@app.get("/healthz", tags=["root"])
async def healthz():
    """Health check endpoint."""
    pool: ContextPool = app.state.context_pool
    return {
        "status": "ok",
        "contexts": pool.size,
        "available_contexts": pool.available_count,
        "cdp_port": pool.cdp_port,
    }
