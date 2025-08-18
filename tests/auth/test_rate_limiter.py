"""
Tests for rate limiting functionality.
"""

import asyncio
import time
import pytest
from funkygibbon.auth.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_rate_limiter_init(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(
            max_attempts=3,
            window_seconds=60,
            lockout_duration=300
        )

        assert limiter.max_attempts == 3
        assert limiter.window_seconds == 60
        assert limiter.lockout_duration == 300

    def test_check_rate_limit_allows_initial_requests(self):
        """Test that initial requests are allowed."""
        limiter = RateLimiter(max_attempts=3)

        allowed, retry_after = limiter.check_rate_limit("test_ip")
        assert allowed is True
        assert retry_after is None

    def test_record_attempt_tracking(self):
        """Test attempt recording."""
        limiter = RateLimiter(max_attempts=3)

        # Record attempts
        for _ in range(2):
            limiter.record_attempt("test_ip")

        # Should still be allowed
        allowed, retry_after = limiter.check_rate_limit("test_ip")
        assert allowed is True
        assert retry_after is None

    def test_rate_limit_exceeded(self):
        """Test rate limit enforcement."""
        limiter = RateLimiter(
            max_attempts=3,
            window_seconds=60,
            lockout_duration=300
        )

        # Record max attempts
        for _ in range(3):
            limiter.record_attempt("test_ip")

        # Next check should be denied
        allowed, retry_after = limiter.check_rate_limit("test_ip")
        assert allowed is False
        assert retry_after == 300  # lockout duration

    def test_progressive_delays(self):
        """Test progressive delay multipliers."""
        limiter = RateLimiter(
            max_attempts=2,
            lockout_duration=100
        )

        # First lockout
        limiter.record_attempt("test_ip")
        limiter.record_attempt("test_ip")
        allowed, retry_after = limiter.check_rate_limit("test_ip")
        assert allowed is False
        assert retry_after == 100  # 1x lockout

        # Simulate time passing and another violation
        limiter._lockouts["test_ip"] = time.time() - 1  # expired
        limiter.record_attempt("test_ip")
        limiter.record_attempt("test_ip")
        allowed, retry_after = limiter.check_rate_limit("test_ip")
        assert allowed is False
        assert retry_after == 200  # 2x lockout

    def test_record_success_clears_counters(self):
        """Test that successful auth clears rate limit."""
        limiter = RateLimiter(max_attempts=3)

        # Record some attempts
        limiter.record_attempt("test_ip")
        limiter.record_attempt("test_ip")

        # Record success
        limiter.record_success("test_ip")

        # Check status - should be cleared
        status = limiter.get_status("test_ip")
        assert status["attempts"] == 0
        assert status["locked_out"] is False

    def test_cleanup_old_entries(self):
        """Test cleanup of old entries."""
        limiter = RateLimiter(
            window_seconds=1,  # 1 second window
            lockout_duration=1
        )

        # Record attempt
        limiter.record_attempt("test_ip")

        # Wait for window to expire
        time.sleep(1.1)

        # Cleanup
        limiter._cleanup_old_entries()

        # Should be no attempts recorded
        status = limiter.get_status("test_ip")
        assert status["attempts"] == 0

    def test_multiple_identifiers(self):
        """Test rate limiting multiple IPs independently."""
        limiter = RateLimiter(max_attempts=2)

        # Record attempts for different IPs
        limiter.record_attempt("ip1")
        limiter.record_attempt("ip1")
        limiter.record_attempt("ip2")

        # ip1 should be locked out
        allowed1, _ = limiter.check_rate_limit("ip1")
        assert allowed1 is False

        # ip2 should still be allowed
        allowed2, _ = limiter.check_rate_limit("ip2")
        assert allowed2 is True

    def test_get_status(self):
        """Test status retrieval."""
        limiter = RateLimiter(
            max_attempts=5,
            window_seconds=300
        )

        # Record some attempts
        limiter.record_attempt("test_ip")
        limiter.record_attempt("test_ip")

        status = limiter.get_status("test_ip")
        assert status["attempts"] == 2
        assert status["max_attempts"] == 5
        assert status["window_seconds"] == 300
        assert status["locked_out"] is False
        assert status["lockout_remaining"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_task_lifecycle(self):
        """Test background cleanup task."""
        limiter = RateLimiter(cleanup_interval=0.1)  # Fast cleanup

        # Start cleanup task
        await limiter.start_cleanup_task()

        # Let it run briefly
        await asyncio.sleep(0.2)

        # Stop cleanup task
        await limiter.stop_cleanup_task()

        # Should complete without errors
        assert True
