"""Eviction strategy for context pool management."""

from datetime import UTC, datetime

from browser_scraper_pool.config import settings
from browser_scraper_pool.pool.context_pool import ContextInstance


def calculate_eviction_score(ctx: ContextInstance) -> float:
    """Calculate eviction score for a context.

    Higher score = more likely to evict.

    Score = (idle_time_weight * idle_seconds)
          + (error_weight * error_rate)
          + (age_weight * age_seconds)

    Protected contexts (tag "protected") return -inf (never evicted).
    In-use contexts return -inf (never evicted).

    Args:
        ctx: The context to score.

    Returns:
        Eviction score. Higher means more evictable. -inf means never evict.
    """
    # Never evict protected or in-use contexts
    if ctx.in_use or "protected" in ctx.tags:
        return float("-inf")

    now = datetime.now(UTC)

    # Calculate idle time in seconds
    if ctx.last_used_at:
        idle_seconds = (now - ctx.last_used_at).total_seconds()
    else:
        # Never used = use created_at as reference
        idle_seconds = (now - ctx.created_at).total_seconds()

    # Calculate error rate
    error_rate = ctx.error_count / ctx.total_requests if ctx.total_requests > 0 else 0

    # Calculate age in seconds
    age_seconds = (now - ctx.created_at).total_seconds()

    # Weighted score
    return (
        settings.eviction_idle_weight * idle_seconds
        + settings.eviction_error_weight * error_rate * 100  # Scale error_rate
        + settings.eviction_age_weight * age_seconds
    )


def find_eviction_candidate(
    contexts: dict[str, ContextInstance],
    exclude_tags: set[str] | None = None,
) -> ContextInstance | None:
    """Find the best candidate for eviction.

    Args:
        contexts: Dictionary of context_id -> ContextInstance.
        exclude_tags: Don't evict contexts with any of these tags.

    Returns:
        The context with highest eviction score, or None if none can be evicted.
    """
    best_candidate: ContextInstance | None = None
    best_score = float("-inf")

    for ctx in contexts.values():
        # Skip if has excluded tags
        if exclude_tags and ctx.tags & exclude_tags:
            continue

        score = calculate_eviction_score(ctx)

        # Skip unevictable contexts (protected, in_use)
        if score == float("-inf"):
            continue

        if score > best_score:
            best_score = score
            best_candidate = ctx

    return best_candidate


def should_recreate(ctx: ContextInstance) -> bool:
    """Check if context should be recreated due to errors.

    Args:
        ctx: The context to check.

    Returns:
        True if context should be recreated (too many consecutive errors).
    """
    return ctx.consecutive_errors >= settings.max_consecutive_errors
