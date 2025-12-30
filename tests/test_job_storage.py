"""Tests for job storage."""

import pytest

from browser_scraper_pool.models.schemas import JobCreate, JobResult
from browser_scraper_pool.queue.job_storage import JobStorage


@pytest.fixture
def storage():
    """Create a fresh storage for each test."""
    return JobStorage(max_jobs=10)


@pytest.fixture
def sample_request():
    """Sample job request."""
    return JobCreate(url="https://example.com")


class TestJobCreation:
    """Tests for job creation."""

    def test_create_returns_job_with_id(self, storage, sample_request):
        """Should create job with unique ID."""
        job = storage.create(sample_request)

        assert job.id.startswith("job-")
        assert len(job.id) == 16  # "job-" + 12 hex chars
        assert job.status == "pending"
        assert job.request == sample_request
        assert job.result is None

    def test_create_multiple_unique_ids(self, storage, sample_request):
        """Should create unique IDs for each job."""
        job1 = storage.create(sample_request)
        job2 = storage.create(sample_request)

        assert job1.id != job2.id

    def test_create_increments_size(self, storage, sample_request):
        """Should increment storage size."""
        assert storage.size == 0
        storage.create(sample_request)
        assert storage.size == 1
        storage.create(sample_request)
        assert storage.size == 2


class TestJobRetrieval:
    """Tests for getting jobs."""

    def test_get_existing_job(self, storage, sample_request):
        """Should return job by ID."""
        created = storage.create(sample_request)

        job = storage.get(created.id)

        assert job is not None
        assert job.id == created.id

    def test_get_unknown_returns_none(self, storage):
        """Should return None for unknown ID."""
        job = storage.get("job-nonexistent")

        assert job is None


class TestStatusUpdate:
    """Tests for status updates."""

    def test_update_to_processing(self, storage, sample_request):
        """Should set status and started_at."""
        job = storage.create(sample_request)

        updated = storage.update_status(job.id, "processing")

        assert updated is not None
        assert updated.status == "processing"
        assert updated.started_at is not None
        assert updated.completed_at is None

    def test_update_to_completed(self, storage, sample_request):
        """Should set status, result, and completed_at."""
        job = storage.create(sample_request)
        result = JobResult(url="https://example.com", status=200)

        updated = storage.update_status(job.id, "completed", result)

        assert updated is not None
        assert updated.status == "completed"
        assert updated.result == result
        assert updated.completed_at is not None

    def test_update_to_failed(self, storage, sample_request):
        """Should set status and error result."""
        job = storage.create(sample_request)
        result = JobResult(url="https://example.com", status=None, error="Timeout")

        updated = storage.update_status(job.id, "failed", result)

        assert updated is not None
        assert updated.status == "failed"
        assert updated.result.error == "Timeout"

    def test_update_unknown_returns_none(self, storage):
        """Should return None for unknown ID."""
        updated = storage.update_status("job-nonexistent", "processing")

        assert updated is None


class TestJobListing:
    """Tests for listing jobs."""

    def test_list_empty(self, storage):
        """Should return empty list when no jobs."""
        jobs = storage.list_all()

        assert jobs == []

    def test_list_all_jobs(self, storage, sample_request):
        """Should return all jobs."""
        storage.create(sample_request)
        storage.create(sample_request)

        jobs = storage.list_all()

        assert len(jobs) == 2

    def test_list_with_status_filter(self, storage, sample_request):
        """Should filter by status."""
        job1 = storage.create(sample_request)
        job2 = storage.create(sample_request)
        storage.update_status(job1.id, "processing")

        pending = storage.list_all(status="pending")
        processing = storage.list_all(status="processing")

        assert len(pending) == 1
        assert pending[0].id == job2.id
        assert len(processing) == 1
        assert processing[0].id == job1.id

    def test_list_with_limit(self, storage, sample_request):
        """Should limit results."""
        for _ in range(5):
            storage.create(sample_request)

        jobs = storage.list_all(limit=2)

        assert len(jobs) == 2

    def test_list_with_offset(self, storage, sample_request):
        """Should skip results with offset."""
        for _ in range(5):
            storage.create(sample_request)

        all_jobs = storage.list_all()
        offset_jobs = storage.list_all(offset=2)

        assert len(offset_jobs) == 3
        assert offset_jobs[0].id == all_jobs[2].id

    def test_list_ordered_newest_first(self, storage):
        """Should return jobs newest first."""
        job1 = storage.create(JobCreate(url="https://first.com"))
        job2 = storage.create(JobCreate(url="https://second.com"))

        jobs = storage.list_all()

        assert jobs[0].id == job2.id
        assert jobs[1].id == job1.id


class TestEviction:
    """Tests for job eviction when storage is full."""

    def test_evicts_completed_jobs_first(self):
        """Should evict oldest completed jobs when full."""
        storage = JobStorage(max_jobs=5)

        # Create 5 jobs
        jobs = [storage.create(JobCreate(url=f"https://example{i}.com")) for i in range(5)]

        # Complete first 2
        storage.update_status(jobs[0].id, "completed", JobResult(url="", status=200))
        storage.update_status(jobs[1].id, "completed", JobResult(url="", status=200))

        # Add one more (should evict completed jobs)
        new_job = storage.create(JobCreate(url="https://new.com"))

        # Should still have new job and pending jobs
        assert storage.get(new_job.id) is not None
        assert storage.get(jobs[2].id) is not None
        assert storage.get(jobs[3].id) is not None
        assert storage.get(jobs[4].id) is not None


class TestClear:
    """Tests for clearing storage."""

    def test_clear_removes_all_jobs(self, storage, sample_request):
        """Should remove all jobs."""
        storage.create(sample_request)
        storage.create(sample_request)

        storage.clear()

        assert storage.size == 0
        assert storage.list_all() == []


class TestToResponse:
    """Tests for converting to API response."""

    def test_to_response_pending(self, storage, sample_request):
        """Should convert pending job to response."""
        job = storage.create(sample_request)

        response = job.to_response()

        assert response.id == job.id
        assert response.status == "pending"
        assert response.request == sample_request
        assert response.result is None
        assert response.started_at is None
        assert response.completed_at is None

    def test_to_response_completed(self, storage, sample_request):
        """Should convert completed job to response."""
        job = storage.create(sample_request)
        result = JobResult(url="https://example.com", status=200, content="<html>")
        storage.update_status(job.id, "completed", result)

        response = job.to_response()

        assert response.status == "completed"
        assert response.result == result
        assert response.completed_at is not None
