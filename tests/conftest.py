"""Shared pytest fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from browser_scraper_pool.main import app


@pytest.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
