"""Pydantic models for API requests and responses."""

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field

# =============================================================================
# Context Models
# =============================================================================


class ContextCreate(BaseModel):
    """Request to create a new context."""

    proxy: str | None = Field(
        default=None,
        description="Proxy server URL (e.g., http://user:pass@host:port)",
        examples=["http://user:pass@proxy.example.com:8080"],
    )
    persistent: bool = Field(
        default=False,
        description="If True, saves cookies/storage to disk for reuse",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for context selection (proxy is auto-added)",
        examples=[["premium", "protected"]],
    )


class ContextResponse(BaseModel):
    """Response containing context information."""

    id: str = Field(description="Unique context identifier")
    proxy: str | None = Field(description="Proxy server URL if configured")
    persistent: bool = Field(description="Whether context persists storage to disk")
    in_use: bool = Field(description="Whether context is currently acquired")
    created_at: datetime = Field(description="When the context was created")
    tags: list[str] = Field(default_factory=list, description="Context tags")
    last_used_at: datetime | None = Field(
        default=None, description="When context was last used"
    )
    total_requests: int = Field(default=0, description="Total requests made")
    error_count: int = Field(default=0, description="Total errors encountered")
    consecutive_errors: int = Field(default=0, description="Consecutive errors")


class ContextTagsUpdate(BaseModel):
    """Request to update context tags."""

    add: list[str] = Field(
        default_factory=list,
        description="Tags to add",
    )
    remove: list[str] = Field(
        default_factory=list,
        description="Tags to remove",
    )


class ContextListResponse(BaseModel):
    """Response containing list of contexts."""

    contexts: list[ContextResponse]
    total: int


# =============================================================================
# Pool Models
# =============================================================================


class PoolStatusResponse(BaseModel):
    """Response containing pool status information."""

    size: int = Field(description="Total number of contexts in the pool")
    available: int = Field(description="Number of contexts not in use")
    in_use: int = Field(description="Number of contexts currently acquired")
    cdp_port: int = Field(description="Chrome DevTools Protocol port")
    cdp_endpoint: str = Field(description="CDP WebSocket endpoint URL")
    is_started: bool = Field(description="Whether the pool is started")


class CDPResponse(BaseModel):
    """Response containing CDP endpoint information."""

    endpoint: str = Field(description="CDP WebSocket endpoint URL")
    port: int = Field(description="CDP port number")


# =============================================================================
# Scraping Models
# =============================================================================


WaitUntilType = Literal["load", "domcontentloaded", "networkidle", "commit"]


class GotoRequest(BaseModel):
    """Request to navigate to a URL."""

    url: AnyHttpUrl = Field(description="URL to navigate to")
    timeout: int = Field(
        default=30000,
        description="Navigation timeout in milliseconds",
        ge=1000,
        le=120000,
    )
    wait_until: WaitUntilType = Field(
        default="load",
        description="When to consider navigation succeeded",
    )


class GotoResponse(BaseModel):
    """Response from navigation."""

    url: str = Field(description="Final URL after navigation")
    status: int | None = Field(description="HTTP response status code")
    ok: bool = Field(description="Whether navigation was successful (2xx status)")


class ContentResponse(BaseModel):
    """Response containing page content."""

    url: str = Field(description="Current page URL")
    content: str = Field(description="Page HTML content")


class ExecuteRequest(BaseModel):
    """Request to execute JavaScript."""

    script: str = Field(
        description="JavaScript code to execute",
        examples=["document.title", "1 + 2", "({ name: 'test', value: 42 })"],
    )
    timeout: int = Field(
        default=30000,
        description="Script execution timeout in milliseconds",
        ge=1000,
        le=120000,
    )


class ExecuteResponse(BaseModel):
    """Response from JavaScript execution."""

    result: str | int | float | bool | dict | list | None = Field(
        description="Result of script execution (serializable values only)"
    )


ScreenshotFormat = Literal["png", "jpeg"]


class ScreenshotRequest(BaseModel):
    """Request to take a screenshot."""

    full_page: bool = Field(
        default=False,
        description="Whether to capture the full page or just viewport",
    )
    format: ScreenshotFormat = Field(
        default="png",
        description="Screenshot format (png or jpeg)",
    )
    quality: int | None = Field(
        default=None,
        description="Quality (0-100) for jpeg format only",
        ge=0,
        le=100,
    )


class ScreenshotResponse(BaseModel):
    """Response containing screenshot data."""

    data: str = Field(description="Base64-encoded screenshot data")
    format: ScreenshotFormat = Field(description="Screenshot format (png or jpeg)")


# =============================================================================
# Unified Scrape Models
# =============================================================================


class ScrapeRequest(BaseModel):
    """Request for unified scrape endpoint."""

    url: AnyHttpUrl = Field(description="URL to navigate to")

    # Context selection
    tags: list[str] = Field(
        default_factory=list,
        description="Required tags (all must match). Empty means any context.",
    )
    proxy: str | None = Field(
        default=None,
        description="Shorthand for tag 'proxy:{value}'. Context with this proxy will be selected.",
    )

    # Behavior
    timeout: int = Field(
        default=30000,
        description="Navigation timeout in milliseconds",
        ge=1000,
        le=120000,
    )
    wait_until: WaitUntilType = Field(
        default="load",
        description="When to consider navigation succeeded",
    )
    get_content: bool = Field(
        default=True,
        description="Whether to return page HTML content",
    )
    script: str | None = Field(
        default=None,
        description="JavaScript code to execute after navigation",
    )
    screenshot: bool = Field(
        default=False,
        description="Whether to take a screenshot",
    )
    screenshot_full_page: bool = Field(
        default=False,
        description="Whether to capture full page (if screenshot=True)",
    )

    # Rate limiting
    domain_delay: int | None = Field(
        default=None,
        description="Override default delay between requests to same domain (ms)",
    )


class ScrapeResponse(BaseModel):
    """Response from unified scrape endpoint."""

    success: bool = Field(description="Whether the scrape succeeded")
    url: str = Field(description="Final URL after navigation")
    status: int | None = Field(description="HTTP response status code")
    content: str | None = Field(default=None, description="Page HTML content")
    script_result: str | int | float | bool | dict | list | None = Field(
        default=None, description="Result of script execution"
    )
    screenshot: str | None = Field(
        default=None, description="Base64-encoded screenshot"
    )
    context_id: str = Field(description="ID of the context used")
    queue_wait_ms: int = Field(
        default=0,
        description="Time spent waiting for context in queue (ms)",
    )
    error: str | None = Field(default=None, description="Error message if failed")


# =============================================================================
# Job Models (Queued Scraping) - DEPRECATED
# =============================================================================


JobStatus = Literal["pending", "processing", "completed", "failed"]


class JobCreate(BaseModel):
    """Request to create a scraping job."""

    url: AnyHttpUrl = Field(description="URL to navigate to")
    proxy: str | None = Field(
        default=None,
        description="Proxy server URL for this job",
    )
    timeout: int = Field(
        default=30000,
        description="Navigation timeout in milliseconds",
        ge=1000,
        le=120000,
    )
    wait_until: WaitUntilType = Field(
        default="load",
        description="When to consider navigation succeeded",
    )
    get_content: bool = Field(
        default=True,
        description="Whether to return page HTML content",
    )
    script: str | None = Field(
        default=None,
        description="JavaScript code to execute after navigation",
    )
    screenshot: bool = Field(
        default=False,
        description="Whether to take a screenshot",
    )
    screenshot_full_page: bool = Field(
        default=False,
        description="Whether to capture full page (if screenshot=True)",
    )


class JobResult(BaseModel):
    """Result of a completed job."""

    url: str = Field(description="Final URL after navigation")
    status: int | None = Field(description="HTTP response status code")
    content: str | None = Field(default=None, description="Page HTML content")
    script_result: str | int | float | bool | dict | list | None = Field(
        default=None, description="Result of script execution"
    )
    screenshot: str | None = Field(
        default=None, description="Base64-encoded screenshot"
    )
    error: str | None = Field(default=None, description="Error message if failed")


class JobResponse(BaseModel):
    """Response containing job information."""

    id: str = Field(description="Unique job identifier")
    status: JobStatus = Field(description="Current job status")
    created_at: datetime = Field(description="When the job was created")
    started_at: datetime | None = Field(
        default=None, description="When processing started"
    )
    completed_at: datetime | None = Field(
        default=None, description="When job completed"
    )
    request: JobCreate = Field(description="Original job request")
    result: JobResult | None = Field(default=None, description="Job result if complete")


class JobListResponse(BaseModel):
    """Response containing list of jobs."""

    jobs: list[JobResponse]
    total: int


# =============================================================================
# Error Models
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(description="Error message")
