"""In-memory job storage for tracking job status and results."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from browser_scraper_pool.models.schemas import (
    JobCreate,
    JobResponse,
    JobResult,
    JobStatus,
)


@dataclass
class Job:
    """Internal job representation."""

    id: str
    request: JobCreate
    status: JobStatus = "pending"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: JobResult | None = None

    def to_response(self) -> JobResponse:
        """Convert to API response model."""
        return JobResponse(
            id=self.id,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            request=self.request,
            result=self.result,
        )


class JobStorage:
    """In-memory storage for jobs.

    Thread-safe for asyncio (single-threaded event loop).
    For production, consider using Redis or a database.
    """

    def __init__(self, max_jobs: int = 1000) -> None:
        """Initialize storage.

        Args:
            max_jobs: Maximum number of jobs to keep in memory.
                      Oldest completed jobs are evicted when limit is reached.
        """
        self._jobs: dict[str, Job] = {}
        self._max_jobs = max_jobs

    def create(self, request: JobCreate) -> Job:
        """Create a new job.

        Args:
            request: Job request parameters.

        Returns:
            Created job with generated ID.
        """
        self._evict_if_needed()

        job = Job(
            id=f"job-{uuid.uuid4().hex[:12]}",
            request=request,
        )
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        """Get a job by ID.

        Args:
            job_id: Job identifier.

        Returns:
            Job if found, None otherwise.
        """
        return self._jobs.get(job_id)

    def list_all(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        """List jobs with optional filtering.

        Args:
            status: Filter by status (optional).
            limit: Maximum number of jobs to return.
            offset: Number of jobs to skip.

        Returns:
            List of jobs sorted by creation time (newest first).
        """
        jobs = list(self._jobs.values())

        if status:
            jobs = [j for j in jobs if j.status == status]

        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[offset : offset + limit]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: JobResult | None = None,
    ) -> Job | None:
        """Update job status.

        Args:
            job_id: Job identifier.
            status: New status.
            result: Job result (for completed/failed status).

        Returns:
            Updated job if found, None otherwise.
        """
        job = self._jobs.get(job_id)
        if not job:
            return None

        job.status = status

        if status == "processing" and job.started_at is None:
            job.started_at = datetime.now(UTC)
        elif status in ("completed", "failed"):
            job.completed_at = datetime.now(UTC)
            job.result = result

        return job

    def _evict_if_needed(self) -> None:
        """Evict oldest completed jobs if storage limit is reached."""
        if len(self._jobs) < self._max_jobs:
            return

        # Get completed jobs sorted by completion time
        completed = [
            j for j in self._jobs.values() if j.status in ("completed", "failed")
        ]
        completed.sort(key=lambda j: j.completed_at or j.created_at)

        # Remove oldest completed jobs
        to_remove = len(self._jobs) - self._max_jobs + 100  # Keep 100 slots free
        for job in completed[:to_remove]:
            del self._jobs[job.id]

    @property
    def size(self) -> int:
        """Total number of jobs in storage."""
        return len(self._jobs)

    def clear(self) -> None:
        """Clear all jobs from storage."""
        self._jobs.clear()


# Global job storage instance
job_storage = JobStorage()
