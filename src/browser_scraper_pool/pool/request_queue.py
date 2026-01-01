"""Internal request queue for context allocation."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from browser_scraper_pool.config import settings

logger = logging.getLogger(__name__)


@dataclass
class QueuedRequest:
    """Request waiting for a context."""

    id: str
    tags: set[str]
    domain: str
    domain_delay_ms: int | None
    created_at: datetime
    future: asyncio.Future[Any]

    @classmethod
    def create(
        cls,
        tags: set[str] | None = None,
        domain: str | None = None,
        domain_delay_ms: int | None = None,
    ) -> "QueuedRequest":
        """Create a new queued request."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        return cls(
            id=str(uuid4()),
            tags=tags or set(),
            domain=domain or "",
            domain_delay_ms=domain_delay_ms,
            created_at=datetime.now(UTC),
            future=loop.create_future(),
        )

    def is_expired(self) -> bool:
        """Check if request has exceeded max wait time."""
        elapsed = (datetime.now(UTC) - self.created_at).total_seconds()
        return elapsed >= settings.max_queue_wait_seconds

    def time_remaining(self) -> float:
        """Return seconds remaining before timeout."""
        elapsed = (datetime.now(UTC) - self.created_at).total_seconds()
        return max(0, settings.max_queue_wait_seconds - elapsed)


class RequestQueue:
    """Internal queue for requests waiting for context.

    Requests are queued when no suitable context is available.
    A background task processes the queue when contexts become available.
    """

    def __init__(self) -> None:
        self._queue: list[QueuedRequest] = []
        self._lock = asyncio.Lock()

    async def enqueue(
        self,
        tags: set[str] | None = None,
        domain: str | None = None,
        domain_delay_ms: int | None = None,
    ) -> QueuedRequest:
        """Add request to queue.

        Args:
            tags: Required tags for context selection.
            domain: Domain for rate limit check.
            domain_delay_ms: Override delay for rate limit check.

        Returns:
            QueuedRequest with future that resolves to ContextInstance or raises.
        """
        request = QueuedRequest.create(
            tags=tags,
            domain=domain,
            domain_delay_ms=domain_delay_ms,
        )

        async with self._lock:
            self._queue.append(request)

        logger.debug(
            "Enqueued request %s (tags=%s, domain=%s)",
            request.id,
            request.tags,
            request.domain,
        )

        return request

    async def dequeue(self, request_id: str) -> bool:
        """Remove a request from the queue.

        Args:
            request_id: The ID of the request to remove.

        Returns:
            True if removed, False if not found.
        """
        async with self._lock:
            for i, req in enumerate(self._queue):
                if req.id == request_id:
                    self._queue.pop(i)
                    return True
        return False

    def get_pending(self) -> list[QueuedRequest]:
        """Get all pending requests (not yet resolved)."""
        return [r for r in self._queue if not r.future.done()]

    def get_pending_count(self, tags: set[str] | None = None) -> int:
        """Count pending requests, optionally filtered by tags.

        Args:
            tags: If provided, only count requests with matching tags.

        Returns:
            Number of pending requests.
        """
        pending = self.get_pending()
        if not tags:
            return len(pending)

        required = set(tags)
        return sum(1 for r in pending if required.issubset(r.tags))

    async def cleanup_expired(self) -> int:
        """Remove expired requests and cancel their futures.

        Returns:
            Number of expired requests removed.
        """
        expired_count = 0

        async with self._lock:
            remaining = []
            for req in self._queue:
                if req.is_expired() and not req.future.done():
                    req.future.set_exception(
                        TimeoutError(
                            f"Request timed out after {settings.max_queue_wait_seconds}s"
                        )
                    )
                    expired_count += 1
                    logger.debug("Request %s expired", req.id)
                else:
                    remaining.append(req)
            self._queue = remaining

        return expired_count

    async def resolve(self, request_id: str, result: Any) -> bool:
        """Resolve a queued request with a result.

        Args:
            request_id: The ID of the request to resolve.
            result: The result to set on the future.

        Returns:
            True if resolved, False if not found or already done.
        """
        async with self._lock:
            for req in self._queue:
                if req.id == request_id and not req.future.done():
                    req.future.set_result(result)
                    return True
        return False

    async def reject(self, request_id: str, error: Exception) -> bool:
        """Reject a queued request with an error.

        Args:
            request_id: The ID of the request to reject.
            error: The exception to set on the future.

        Returns:
            True if rejected, False if not found or already done.
        """
        async with self._lock:
            for req in self._queue:
                if req.id == request_id and not req.future.done():
                    req.future.set_exception(error)
                    return True
        return False

    def find_match(
        self,
        available_tags: set[str],
        domain: str | None = None,
    ) -> QueuedRequest | None:
        """Find first queued request that matches available context.

        Args:
            available_tags: Tags of the available context.
            domain: Domain the context is ready for (for rate limit check).

        Returns:
            First matching QueuedRequest, or None.
        """
        for req in self.get_pending():
            # Check if context's tags satisfy request's requirements
            if req.tags and not req.tags.issubset(available_tags):
                continue
            # Check domain match if specified
            if req.domain and domain and req.domain != domain:
                continue
            return req
        return None

    def __len__(self) -> int:
        """Return total queue size (including resolved)."""
        return len(self._queue)
