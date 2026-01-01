"""Tests for request queue."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from browser_scraper_pool.pool.request_queue import QueuedRequest, RequestQueue


class TestQueuedRequest:
    """Tests for QueuedRequest dataclass."""

    def test_create(self):
        """Should create request with defaults."""
        req = QueuedRequest.create()

        assert req.id is not None
        assert req.tags == set()
        assert req.domain == ""
        assert req.domain_delay_ms is None
        assert not req.future.done()

    def test_create_with_params(self):
        """Should create request with specified params."""
        req = QueuedRequest.create(
            tags={"premium"},
            domain="example.com",
            domain_delay_ms=2000,
        )

        assert req.tags == {"premium"}
        assert req.domain == "example.com"
        assert req.domain_delay_ms == 2000

    def test_is_expired_false(self):
        """Fresh request should not be expired."""
        req = QueuedRequest.create()

        assert req.is_expired() is False

    def test_is_expired_true(self):
        """Old request should be expired."""
        req = QueuedRequest.create()
        # Make request old
        req.created_at = datetime.now(UTC) - timedelta(minutes=10)

        assert req.is_expired() is True

    def test_time_remaining(self):
        """Should return remaining time."""
        req = QueuedRequest.create()

        # Fresh request should have close to max wait time
        remaining = req.time_remaining()
        assert remaining > 200  # Should have at least 200 seconds left


class TestRequestQueue:
    """Tests for RequestQueue."""

    async def test_enqueue(self):
        """Should add request to queue."""
        queue = RequestQueue()

        req = await queue.enqueue(tags={"premium"}, domain="example.com")

        assert len(queue) == 1
        assert req.tags == {"premium"}
        assert req.domain == "example.com"

    async def test_dequeue(self):
        """Should remove request from queue."""
        queue = RequestQueue()
        req = await queue.enqueue()

        result = await queue.dequeue(req.id)

        assert result is True
        assert len(queue) == 0

    async def test_dequeue_not_found(self):
        """Should return False for unknown request."""
        queue = RequestQueue()

        result = await queue.dequeue("unknown")

        assert result is False

    async def test_get_pending(self):
        """Should return only pending requests."""
        queue = RequestQueue()
        req1 = await queue.enqueue()
        req2 = await queue.enqueue()

        # Resolve req1
        req1.future.set_result("done")

        pending = queue.get_pending()

        assert len(pending) == 1
        assert pending[0].id == req2.id

    async def test_get_pending_count(self):
        """Should count pending requests."""
        queue = RequestQueue()
        await queue.enqueue()
        await queue.enqueue()

        count = queue.get_pending_count()

        assert count == 2

    async def test_get_pending_count_with_tags(self):
        """Should filter count by tags."""
        queue = RequestQueue()
        await queue.enqueue(tags={"premium"})
        await queue.enqueue(tags={"basic"})
        await queue.enqueue(tags={"premium", "fast"})

        count = queue.get_pending_count(tags={"premium"})

        assert count == 2  # Only requests with "premium" tag

    async def test_cleanup_expired(self):
        """Should remove and reject expired requests."""
        queue = RequestQueue()
        req = await queue.enqueue()

        # Make request expired
        req.created_at = datetime.now(UTC) - timedelta(minutes=10)

        expired_count = await queue.cleanup_expired()

        assert expired_count == 1
        assert len(queue) == 0
        assert req.future.done()
        with pytest.raises(TimeoutError):
            req.future.result()

    async def test_resolve(self):
        """Should resolve request future."""
        queue = RequestQueue()
        req = await queue.enqueue()

        result = await queue.resolve(req.id, "context")

        assert result is True
        assert req.future.done()
        assert req.future.result() == "context"

    async def test_resolve_not_found(self):
        """Should return False for unknown request."""
        queue = RequestQueue()

        result = await queue.resolve("unknown", "context")

        assert result is False

    async def test_reject(self):
        """Should reject request future with error."""
        queue = RequestQueue()
        req = await queue.enqueue()

        error = ValueError("test error")
        result = await queue.reject(req.id, error)

        assert result is True
        assert req.future.done()
        with pytest.raises(ValueError, match="test error"):
            req.future.result()

    async def test_find_match_by_tags(self):
        """Should find request matching available tags."""
        queue = RequestQueue()
        await queue.enqueue(tags={"basic"})
        req2 = await queue.enqueue(tags={"premium"})

        match = queue.find_match(available_tags={"premium", "fast"})

        assert match is req2

    async def test_find_match_no_match(self):
        """Should return None when no match."""
        queue = RequestQueue()
        await queue.enqueue(tags={"premium"})

        match = queue.find_match(available_tags={"basic"})

        assert match is None

    async def test_find_match_empty_queue(self):
        """Should return None for empty queue."""
        queue = RequestQueue()

        match = queue.find_match(available_tags={"premium"})

        assert match is None

    async def test_concurrent_operations(self):
        """Should handle concurrent enqueue/dequeue."""
        queue = RequestQueue()

        async def enqueue_many():
            for _ in range(10):
                await queue.enqueue()

        async def dequeue_many():
            for _ in range(5):
                pending = queue.get_pending()
                if pending:
                    await queue.dequeue(pending[0].id)

        await asyncio.gather(enqueue_many(), dequeue_many())

        # Should have some requests left
        assert len(queue) >= 5


class TestQueueIntegration:
    """Integration tests for queue workflow."""

    async def test_wait_for_context(self):
        """Test waiting for context via queue."""
        queue = RequestQueue()
        req = await queue.enqueue(tags={"premium"})

        # Simulate context becoming available
        async def resolve_after_delay():
            await asyncio.sleep(0.1)
            await queue.resolve(req.id, "context-123")

        asyncio.create_task(resolve_after_delay())  # noqa: RUF006

        # Wait for the future
        result = await asyncio.wait_for(req.future, timeout=1.0)

        assert result == "context-123"

    async def test_timeout_waiting(self):
        """Test timeout when no context available."""
        queue = RequestQueue()
        req = await queue.enqueue()

        # Make request expire immediately
        req.created_at = datetime.now(UTC) - timedelta(minutes=10)

        # Cleanup should expire it
        await queue.cleanup_expired()

        with pytest.raises(TimeoutError):
            req.future.result()
