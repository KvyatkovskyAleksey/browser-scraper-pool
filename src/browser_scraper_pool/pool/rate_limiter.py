"""Domain rate limiting for browser contexts."""

from datetime import UTC, datetime
from urllib.parse import urlparse

from browser_scraper_pool.pool.context_pool import ContextInstance


class DomainRateLimiter:
    """Per-context domain request tracking.

    Each context tracks when it last made a request to each domain.
    This prevents hammering the same domain from a single context.
    """

    def __init__(self, default_delay_ms: int = 1000) -> None:
        """Initialize rate limiter.

        Args:
            default_delay_ms: Default delay between requests to same domain (milliseconds).
        """
        self.default_delay_ms = default_delay_ms

    def can_request(
        self,
        ctx: ContextInstance,
        domain: str,
        delay_ms: int | None = None,
    ) -> bool:
        """Check if enough time passed since last request to domain.

        Args:
            ctx: The context to check.
            domain: The domain to check (e.g., "example.com").
            delay_ms: Override delay in milliseconds. Uses default if None.

        Returns:
            True if request can proceed, False if still rate-limited.
        """
        delay = delay_ms if delay_ms is not None else self.default_delay_ms
        last_request = ctx.domain_last_request.get(domain)

        if last_request is None:
            return True

        elapsed_ms = (datetime.now(UTC) - last_request).total_seconds() * 1000
        return elapsed_ms >= delay

    def record_request(self, ctx: ContextInstance, domain: str) -> None:
        """Record request timestamp for domain.

        Args:
            ctx: The context making the request.
            domain: The domain being requested.
        """
        ctx.domain_last_request[domain] = datetime.now(UTC)
        ctx.last_used_at = datetime.now(UTC)
        ctx.total_requests += 1

    def time_until_available(
        self,
        ctx: ContextInstance,
        domain: str,
        delay_ms: int | None = None,
    ) -> float:
        """Calculate seconds until context can request this domain again.

        Args:
            ctx: The context to check.
            domain: The domain to check.
            delay_ms: Override delay in milliseconds. Uses default if None.

        Returns:
            Seconds until available. Returns 0 if already available.
        """
        delay = delay_ms if delay_ms is not None else self.default_delay_ms
        last_request = ctx.domain_last_request.get(domain)

        if last_request is None:
            return 0.0

        elapsed_ms = (datetime.now(UTC) - last_request).total_seconds() * 1000
        remaining_ms = delay - elapsed_ms

        if remaining_ms <= 0:
            return 0.0

        return remaining_ms / 1000.0

    def record_error(self, ctx: ContextInstance) -> None:
        """Record an error on a context.

        Args:
            ctx: The context that experienced an error.
        """
        ctx.error_count += 1
        ctx.consecutive_errors += 1

    def record_success(self, ctx: ContextInstance) -> None:
        """Record a successful request on a context.

        Args:
            ctx: The context that completed successfully.
        """
        ctx.consecutive_errors = 0

    @staticmethod
    def extract_domain(url: str) -> str:
        """Extract domain from URL.

        Args:
            url: Full URL (e.g., "https://www.example.com/path").

        Returns:
            Domain (e.g., "www.example.com").
        """
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0]
