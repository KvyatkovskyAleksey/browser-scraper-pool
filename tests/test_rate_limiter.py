"""Tests for domain rate limiter."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from browser_scraper_pool.pool.rate_limiter import DomainRateLimiter


@pytest.fixture
def mock_context():
    """Create a mock context with rate limiting fields."""
    ctx = MagicMock()
    ctx.domain_last_request = {}
    ctx.last_used_at = None
    ctx.total_requests = 0
    ctx.error_count = 0
    ctx.consecutive_errors = 0
    return ctx


class TestCanRequest:
    """Tests for can_request()."""

    def test_first_request_allowed(self, mock_context):
        """First request to domain should be allowed."""
        limiter = DomainRateLimiter(default_delay_ms=1000)

        result = limiter.can_request(mock_context, "example.com")

        assert result is True

    def test_request_blocked_within_delay(self, mock_context):
        """Request within delay window should be blocked."""
        limiter = DomainRateLimiter(default_delay_ms=1000)
        mock_context.domain_last_request["example.com"] = datetime.now(UTC)

        result = limiter.can_request(mock_context, "example.com")

        assert result is False

    def test_request_allowed_after_delay(self, mock_context):
        """Request after delay window should be allowed."""
        limiter = DomainRateLimiter(default_delay_ms=1000)
        mock_context.domain_last_request["example.com"] = datetime.now(UTC) - timedelta(
            seconds=2
        )

        result = limiter.can_request(mock_context, "example.com")

        assert result is True

    def test_different_domains_independent(self, mock_context):
        """Different domains should have independent rate limits."""
        limiter = DomainRateLimiter(default_delay_ms=1000)
        mock_context.domain_last_request["example.com"] = datetime.now(UTC)

        result = limiter.can_request(mock_context, "other.com")

        assert result is True

    def test_custom_delay_override(self, mock_context):
        """Custom delay should override default."""
        limiter = DomainRateLimiter(default_delay_ms=1000)
        mock_context.domain_last_request["example.com"] = datetime.now(UTC) - timedelta(
            milliseconds=500
        )

        # Default 1000ms - should be blocked
        assert limiter.can_request(mock_context, "example.com") is False

        # Custom 400ms - should be allowed
        assert limiter.can_request(mock_context, "example.com", delay_ms=400) is True


class TestRecordRequest:
    """Tests for record_request()."""

    def test_records_timestamp(self, mock_context):
        """Should record request timestamp for domain."""
        limiter = DomainRateLimiter()

        limiter.record_request(mock_context, "example.com")

        assert "example.com" in mock_context.domain_last_request
        assert isinstance(mock_context.domain_last_request["example.com"], datetime)

    def test_updates_last_used_at(self, mock_context):
        """Should update context's last_used_at."""
        limiter = DomainRateLimiter()

        limiter.record_request(mock_context, "example.com")

        assert mock_context.last_used_at is not None

    def test_increments_total_requests(self, mock_context):
        """Should increment total_requests counter."""
        limiter = DomainRateLimiter()
        mock_context.total_requests = 5

        limiter.record_request(mock_context, "example.com")

        assert mock_context.total_requests == 6


class TestTimeUntilAvailable:
    """Tests for time_until_available()."""

    def test_returns_zero_for_new_domain(self, mock_context):
        """Should return 0 for domain with no previous request."""
        limiter = DomainRateLimiter(default_delay_ms=1000)

        result = limiter.time_until_available(mock_context, "example.com")

        assert result == 0.0

    def test_returns_zero_when_delay_passed(self, mock_context):
        """Should return 0 when delay has passed."""
        limiter = DomainRateLimiter(default_delay_ms=1000)
        mock_context.domain_last_request["example.com"] = datetime.now(UTC) - timedelta(
            seconds=2
        )

        result = limiter.time_until_available(mock_context, "example.com")

        assert result == 0.0

    def test_returns_remaining_time(self, mock_context):
        """Should return remaining time in seconds."""
        limiter = DomainRateLimiter(default_delay_ms=1000)
        mock_context.domain_last_request["example.com"] = datetime.now(UTC) - timedelta(
            milliseconds=400
        )

        result = limiter.time_until_available(mock_context, "example.com")

        # Should be approximately 0.6 seconds remaining
        assert 0.5 <= result <= 0.7


class TestErrorTracking:
    """Tests for error and success tracking."""

    def test_record_error(self, mock_context):
        """record_error() should increment error counters."""
        limiter = DomainRateLimiter()

        limiter.record_error(mock_context)

        assert mock_context.error_count == 1
        assert mock_context.consecutive_errors == 1

    def test_record_multiple_errors(self, mock_context):
        """Multiple errors should accumulate."""
        limiter = DomainRateLimiter()

        limiter.record_error(mock_context)
        limiter.record_error(mock_context)
        limiter.record_error(mock_context)

        assert mock_context.error_count == 3
        assert mock_context.consecutive_errors == 3

    def test_record_success_resets_consecutive(self, mock_context):
        """record_success() should reset consecutive_errors."""
        limiter = DomainRateLimiter()
        mock_context.consecutive_errors = 5
        mock_context.error_count = 10

        limiter.record_success(mock_context)

        assert mock_context.consecutive_errors == 0
        # Total error_count stays the same
        assert mock_context.error_count == 10


class TestExtractDomain:
    """Tests for extract_domain()."""

    def test_extract_from_https(self):
        """Should extract domain from HTTPS URL."""
        result = DomainRateLimiter.extract_domain("https://example.com/path")
        assert result == "example.com"

    def test_extract_from_http(self):
        """Should extract domain from HTTP URL."""
        result = DomainRateLimiter.extract_domain("http://example.com/path")
        assert result == "example.com"

    def test_extract_with_port(self):
        """Should include port in domain."""
        result = DomainRateLimiter.extract_domain("https://example.com:8080/path")
        assert result == "example.com:8080"

    def test_extract_with_subdomain(self):
        """Should include subdomain."""
        result = DomainRateLimiter.extract_domain("https://www.example.com/path")
        assert result == "www.example.com"


class TestRateLimitIntegration:
    """Integration tests for rate limiting workflow."""

    async def test_full_workflow(self, mock_context):
        """Test complete rate limiting workflow."""
        limiter = DomainRateLimiter(default_delay_ms=100)  # 100ms for fast test
        domain = "example.com"

        # First request should be allowed
        assert limiter.can_request(mock_context, domain) is True

        # Record the request
        limiter.record_request(mock_context, domain)

        # Immediate second request should be blocked
        assert limiter.can_request(mock_context, domain) is False

        # Wait for rate limit to expire
        await asyncio.sleep(0.15)  # 150ms > 100ms delay

        # Now should be allowed
        assert limiter.can_request(mock_context, domain) is True
