"""Tests for jobs API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from browser_scraper_pool.main import app
from browser_scraper_pool.pool.context_pool import ContextPool
from browser_scraper_pool.queue.job_storage import job_storage
from browser_scraper_pool.queue.publisher import JobPublisher


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before and after each test."""
    ContextPool.reset_instance()
    JobPublisher.reset_instance()
    job_storage.clear()
    yield
    ContextPool.reset_instance()
    JobPublisher.reset_instance()
    job_storage.clear()


@pytest.fixture
def mock_pool():
    """Create a mock pool."""
    pool = MagicMock(spec=ContextPool)
    pool.size = 0
    pool.available_count = 0
    pool.cdp_port = 9222
    pool.is_started = True
    pool.get_cdp_endpoint.return_value = "ws://127.0.0.1:9222"
    pool.list_contexts.return_value = []
    return pool


@pytest.fixture
def mock_publisher():
    """Create a mock publisher."""
    publisher = MagicMock(spec=JobPublisher)
    publisher.publish = AsyncMock()
    publisher.is_connected = True
    return publisher


@pytest.fixture
async def client(mock_pool, mock_publisher):
    """Create test client with mocked dependencies."""
    app.state.context_pool = mock_pool

    with patch(
        "browser_scraper_pool.api.jobs.JobPublisher.get_instance",
        return_value=mock_publisher,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestCreateJob:
    """Tests for job creation endpoint."""

    async def test_create_job_returns_202(self, client, mock_publisher):
        """Should return 202 with job info."""
        response = await client.post("/jobs", json={"url": "https://example.com"})

        assert response.status_code == 202
        data = response.json()
        assert data["id"].startswith("job-")
        assert data["status"] == "pending"
        assert data["request"]["url"] == "https://example.com/"
        mock_publisher.publish.assert_called_once()

    async def test_create_job_with_options(self, client, mock_publisher):
        """Should create job with all options."""
        response = await client.post(
            "/jobs",
            json={
                "url": "https://example.com",
                "proxy": "http://proxy:8080",
                "timeout": 60000,
                "get_content": False,
                "script": "document.title",
                "screenshot": True,
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["request"]["proxy"] == "http://proxy:8080"
        assert data["request"]["timeout"] == 60000
        assert data["request"]["get_content"] is False
        assert data["request"]["script"] == "document.title"
        assert data["request"]["screenshot"] is True

    async def test_create_job_publishes_to_queue(self, client, mock_publisher):
        """Should publish job ID to queue."""
        response = await client.post("/jobs", json={"url": "https://example.com"})

        job_id = response.json()["id"]
        mock_publisher.publish.assert_called_once_with(job_id)

    async def test_create_job_rabbitmq_unavailable(self, client, mock_publisher):
        """Should return 503 when RabbitMQ fails."""
        mock_publisher.publish.side_effect = Exception("Connection refused")

        response = await client.post("/jobs", json={"url": "https://example.com"})

        assert response.status_code == 503
        assert "RabbitMQ" in response.json()["detail"]

    async def test_create_job_invalid_url(self, client):
        """Should reject invalid URL."""
        response = await client.post("/jobs", json={"url": "not-a-url"})

        assert response.status_code == 422


class TestGetJob:
    """Tests for get job endpoint."""

    async def test_get_job(self, client, mock_publisher):
        """Should return job by ID."""
        # Create job first
        create_response = await client.post(
            "/jobs", json={"url": "https://example.com"}
        )
        job_id = create_response.json()["id"]

        # Get job
        response = await client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["status"] == "pending"

    async def test_get_job_not_found(self, client):
        """Should return 404 for unknown job."""
        response = await client.get("/jobs/job-nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestListJobs:
    """Tests for list jobs endpoint."""

    async def test_list_jobs_empty(self, client):
        """Should return empty list when no jobs."""
        response = await client.get("/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0

    async def test_list_jobs(self, client, mock_publisher):
        """Should return all jobs."""
        # Create jobs
        await client.post("/jobs", json={"url": "https://example1.com"})
        await client.post("/jobs", json={"url": "https://example2.com"})

        response = await client.get("/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2
        assert data["total"] == 2

    async def test_list_jobs_with_status_filter(self, client, mock_publisher):
        """Should filter by status."""
        # Create jobs
        create1 = await client.post("/jobs", json={"url": "https://example1.com"})
        await client.post("/jobs", json={"url": "https://example2.com"})

        # Update one to processing
        job1_id = create1.json()["id"]
        job_storage.update_status(job1_id, "processing")

        # List pending only
        response = await client.get("/jobs?status=pending")

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["status"] == "pending"

    async def test_list_jobs_with_pagination(self, client, mock_publisher):
        """Should paginate results."""
        # Create jobs
        for i in range(5):
            await client.post("/jobs", json={"url": f"https://example{i}.com"})

        # Get first 2
        response = await client.get("/jobs?limit=2&offset=0")
        data = response.json()
        assert len(data["jobs"]) == 2

        # Get next 2
        response = await client.get("/jobs?limit=2&offset=2")
        data = response.json()
        assert len(data["jobs"]) == 2

        # Get last 1
        response = await client.get("/jobs?limit=2&offset=4")
        data = response.json()
        assert len(data["jobs"]) == 1
