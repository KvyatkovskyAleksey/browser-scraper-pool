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


class ContextResponse(BaseModel):
    """Response containing context information."""

    id: str = Field(description="Unique context identifier")
    proxy: str | None = Field(description="Proxy server URL if configured")
    persistent: bool = Field(description="Whether context persists storage to disk")
    in_use: bool = Field(description="Whether context is currently acquired")
    created_at: datetime = Field(description="When the context was created")


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
# Error Models
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(description="Error message")
