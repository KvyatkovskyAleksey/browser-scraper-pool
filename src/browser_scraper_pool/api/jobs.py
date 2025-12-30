"""Job submission API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from browser_scraper_pool.models.schemas import (
    JobCreate,
    JobListResponse,
    JobResponse,
    JobStatus,
)
from browser_scraper_pool.queue.job_storage import job_storage
from browser_scraper_pool.queue.publisher import JobPublisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_publisher() -> JobPublisher:
    """Get the job publisher instance."""
    return JobPublisher.get_instance()


PublisherDep = Annotated[JobPublisher, Depends(get_publisher)]


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(publisher: PublisherDep, body: JobCreate):
    """Submit a new scraping job to the queue.

    The job will be processed asynchronously by a worker.
    Poll GET /jobs/{id} to check status and get results.
    """
    # Create job in storage
    job = job_storage.create(body)

    # Publish to queue
    try:
        await publisher.publish(job.id)
    except Exception as e:
        # If publishing fails, mark job as failed
        logger.warning("Failed to publish job %s: %s", job.id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue job. RabbitMQ may be unavailable.",
        ) from e

    logger.info("Job submitted: %s -> %s", job.id, body.url)
    return job.to_response()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get job status and results.

    Returns the current status of the job. If completed, includes results.
    If failed, includes error details.
    """
    job = job_storage.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    return job.to_response()


@router.get("", response_model=JobListResponse)
async def list_jobs(
    job_status: Annotated[
        JobStatus | None,
        Query(alias="status", description="Filter by job status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Max jobs to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Number of jobs to skip")] = 0,
):
    """List jobs with optional filtering.

    Jobs are returned in reverse chronological order (newest first).
    """
    jobs = job_storage.list_all(status=job_status, limit=limit, offset=offset)
    return JobListResponse(
        jobs=[j.to_response() for j in jobs],
        total=job_storage.size,
    )
