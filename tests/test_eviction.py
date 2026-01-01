"""Tests for eviction strategy."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from browser_scraper_pool.pool.eviction import (
    calculate_eviction_score,
    find_eviction_candidate,
    should_recreate,
)


@pytest.fixture
def mock_context():
    """Create a mock context with eviction-relevant fields."""
    ctx = MagicMock()
    ctx.id = "ctx-123"
    ctx.in_use = False
    ctx.tags = set()
    ctx.created_at = datetime.now(UTC)
    ctx.last_used_at = None
    ctx.total_requests = 0
    ctx.error_count = 0
    ctx.consecutive_errors = 0
    return ctx


class TestCalculateEvictionScore:
    """Tests for calculate_eviction_score()."""

    def test_protected_context_never_evicted(self, mock_context):
        """Protected contexts should return -inf."""
        mock_context.tags = {"protected"}

        score = calculate_eviction_score(mock_context)

        assert score == float("-inf")

    def test_in_use_context_never_evicted(self, mock_context):
        """In-use contexts should return -inf."""
        mock_context.in_use = True

        score = calculate_eviction_score(mock_context)

        assert score == float("-inf")

    def test_idle_context_gets_higher_score(self, mock_context):
        """Idle contexts should get higher eviction scores."""
        # Fresh context
        mock_context.created_at = datetime.now(UTC)
        score_fresh = calculate_eviction_score(mock_context)

        # Idle context (created 1 hour ago)
        mock_context.created_at = datetime.now(UTC) - timedelta(hours=1)
        score_idle = calculate_eviction_score(mock_context)

        assert score_idle > score_fresh

    def test_error_rate_increases_score(self, mock_context):
        """High error rate should increase eviction score."""
        mock_context.total_requests = 100
        mock_context.error_count = 0
        score_no_errors = calculate_eviction_score(mock_context)

        mock_context.error_count = 50  # 50% error rate
        score_with_errors = calculate_eviction_score(mock_context)

        assert score_with_errors > score_no_errors

    def test_age_increases_score(self, mock_context):
        """Older contexts should have higher eviction scores."""
        mock_context.created_at = datetime.now(UTC)
        score_new = calculate_eviction_score(mock_context)

        mock_context.created_at = datetime.now(UTC) - timedelta(days=1)
        score_old = calculate_eviction_score(mock_context)

        assert score_old > score_new


class TestFindEvictionCandidate:
    """Tests for find_eviction_candidate()."""

    def test_returns_highest_scoring_context(self):
        """Should return context with highest eviction score."""
        old_ctx = MagicMock()
        old_ctx.id = "old"
        old_ctx.in_use = False
        old_ctx.tags = set()
        old_ctx.created_at = datetime.now(UTC) - timedelta(hours=2)
        old_ctx.last_used_at = None
        old_ctx.total_requests = 0
        old_ctx.error_count = 0

        new_ctx = MagicMock()
        new_ctx.id = "new"
        new_ctx.in_use = False
        new_ctx.tags = set()
        new_ctx.created_at = datetime.now(UTC)
        new_ctx.last_used_at = None
        new_ctx.total_requests = 0
        new_ctx.error_count = 0

        contexts = {"old": old_ctx, "new": new_ctx}

        result = find_eviction_candidate(contexts)

        assert result is old_ctx

    def test_skips_protected_contexts(self):
        """Should skip protected contexts."""
        protected_ctx = MagicMock()
        protected_ctx.id = "protected"
        protected_ctx.in_use = False
        protected_ctx.tags = {"protected"}
        protected_ctx.created_at = datetime.now(UTC) - timedelta(hours=10)
        protected_ctx.last_used_at = None
        protected_ctx.total_requests = 0
        protected_ctx.error_count = 0

        normal_ctx = MagicMock()
        normal_ctx.id = "normal"
        normal_ctx.in_use = False
        normal_ctx.tags = set()
        normal_ctx.created_at = datetime.now(UTC)
        normal_ctx.last_used_at = None
        normal_ctx.total_requests = 0
        normal_ctx.error_count = 0

        contexts = {"protected": protected_ctx, "normal": normal_ctx}

        result = find_eviction_candidate(contexts)

        assert result is normal_ctx

    def test_skips_in_use_contexts(self):
        """Should skip in-use contexts."""
        in_use_ctx = MagicMock()
        in_use_ctx.id = "in_use"
        in_use_ctx.in_use = True
        in_use_ctx.tags = set()
        in_use_ctx.created_at = datetime.now(UTC) - timedelta(hours=10)
        in_use_ctx.last_used_at = None

        available_ctx = MagicMock()
        available_ctx.id = "available"
        available_ctx.in_use = False
        available_ctx.tags = set()
        available_ctx.created_at = datetime.now(UTC)
        available_ctx.last_used_at = None
        available_ctx.total_requests = 0
        available_ctx.error_count = 0

        contexts = {"in_use": in_use_ctx, "available": available_ctx}

        result = find_eviction_candidate(contexts)

        assert result is available_ctx

    def test_returns_none_when_all_protected(self):
        """Should return None when all contexts are protected."""
        protected_ctx = MagicMock()
        protected_ctx.id = "protected"
        protected_ctx.in_use = False
        protected_ctx.tags = {"protected"}
        protected_ctx.created_at = datetime.now(UTC)
        protected_ctx.last_used_at = None

        contexts = {"protected": protected_ctx}

        result = find_eviction_candidate(contexts)

        assert result is None

    def test_exclude_tags(self):
        """Should skip contexts with excluded tags."""
        premium_ctx = MagicMock()
        premium_ctx.id = "premium"
        premium_ctx.in_use = False
        premium_ctx.tags = {"premium"}
        premium_ctx.created_at = datetime.now(UTC) - timedelta(hours=10)
        premium_ctx.last_used_at = None
        premium_ctx.total_requests = 0
        premium_ctx.error_count = 0

        basic_ctx = MagicMock()
        basic_ctx.id = "basic"
        basic_ctx.in_use = False
        basic_ctx.tags = {"basic"}
        basic_ctx.created_at = datetime.now(UTC)
        basic_ctx.last_used_at = None
        basic_ctx.total_requests = 0
        basic_ctx.error_count = 0

        contexts = {"premium": premium_ctx, "basic": basic_ctx}

        result = find_eviction_candidate(contexts, exclude_tags={"premium"})

        assert result is basic_ctx


class TestShouldRecreate:
    """Tests for should_recreate()."""

    def test_returns_false_below_threshold(self, mock_context):
        """Should return False when below error threshold."""
        mock_context.consecutive_errors = 2

        result = should_recreate(mock_context)

        assert result is False

    def test_returns_true_at_threshold(self, mock_context):
        """Should return True at error threshold."""
        mock_context.consecutive_errors = 5  # Default threshold

        result = should_recreate(mock_context)

        assert result is True

    def test_returns_true_above_threshold(self, mock_context):
        """Should return True above error threshold."""
        mock_context.consecutive_errors = 10

        result = should_recreate(mock_context)

        assert result is True
