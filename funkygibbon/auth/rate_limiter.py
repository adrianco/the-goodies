"""
Rate limiting implementation for authentication endpoints.

Provides configurable rate limiting with progressive delays for brute force protection.
"""

import time
from typing import Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio
from functools import wraps


class RateLimiter:
    """
    Rate limiter with progressive delays for authentication endpoints.

    Features:
    - Per-IP rate limiting
    - Progressive delays for repeated failures
    - Configurable limits and time windows
    - Automatic cleanup of old entries
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,  # 5 minutes
        lockout_duration: int = 900,  # 15 minutes
        cleanup_interval: int = 3600  # 1 hour
    ):
        """
        Initialize rate limiter.

        Args:
            max_attempts: Maximum attempts allowed within window
            window_seconds: Time window for counting attempts
            lockout_duration: Lockout duration after max attempts exceeded
            cleanup_interval: Interval for cleaning up old entries
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_duration = lockout_duration
        self.cleanup_interval = cleanup_interval

        # Track attempts by IP
        self._attempts: Dict[str, list] = defaultdict(list)
        # Track lockouts by IP
        self._lockouts: Dict[str, float] = {}
        # Track progressive delays
        self._delays: Dict[str, int] = defaultdict(int)

        # Start cleanup task
        self._cleanup_task = None

    async def start_cleanup_task(self):
        """Start background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self):
        """Background task to clean up old entries."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                self._cleanup_old_entries()
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error in production
                pass

    def _cleanup_old_entries(self):
        """Remove old entries from tracking dictionaries."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        # Clean attempts
        for ip in list(self._attempts.keys()):
            self._attempts[ip] = [
                timestamp for timestamp in self._attempts[ip]
                if timestamp > cutoff_time
            ]
            if not self._attempts[ip]:
                del self._attempts[ip]

        # Clean lockouts
        for ip in list(self._lockouts.keys()):
            if self._lockouts[ip] < current_time:
                del self._lockouts[ip]
                # Reset delay counter when lockout expires
                if ip in self._delays:
                    del self._delays[ip]

    def check_rate_limit(self, identifier: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is rate limited.

        Args:
            identifier: Unique identifier (e.g., IP address)

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        current_time = time.time()

        # Check if locked out
        if identifier in self._lockouts:
            lockout_end = self._lockouts[identifier]
            if current_time < lockout_end:
                retry_after = int(lockout_end - current_time)
                return False, retry_after
            else:
                # Lockout expired
                del self._lockouts[identifier]

        # Clean old attempts
        cutoff_time = current_time - self.window_seconds
        self._attempts[identifier] = [
            timestamp for timestamp in self._attempts[identifier]
            if timestamp > cutoff_time
        ]

        # Check attempt count
        attempt_count = len(self._attempts[identifier])

        if attempt_count >= self.max_attempts:
            # Apply lockout with progressive delay
            delay_multiplier = self._delays[identifier] + 1
            lockout_duration = self.lockout_duration * delay_multiplier

            self._lockouts[identifier] = current_time + lockout_duration
            self._delays[identifier] = min(delay_multiplier, 5)  # Cap at 5x

            return False, lockout_duration

        return True, None

    def record_attempt(self, identifier: str):
        """Record an attempt for rate limiting."""
        self._attempts[identifier].append(time.time())

    def record_success(self, identifier: str):
        """
        Record successful authentication.

        Clears rate limit counters for the identifier.
        """
        if identifier in self._attempts:
            del self._attempts[identifier]
        if identifier in self._lockouts:
            del self._lockouts[identifier]
        if identifier in self._delays:
            del self._delays[identifier]

    def get_status(self, identifier: str) -> Dict[str, any]:
        """
        Get rate limit status for identifier.

        Returns:
            Dictionary with current status information
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        # Count recent attempts
        recent_attempts = [
            t for t in self._attempts.get(identifier, [])
            if t > cutoff_time
        ]

        # Check lockout
        locked_out = False
        lockout_remaining = 0
        if identifier in self._lockouts:
            lockout_end = self._lockouts[identifier]
            if current_time < lockout_end:
                locked_out = True
                lockout_remaining = int(lockout_end - current_time)

        return {
            "attempts": len(recent_attempts),
            "max_attempts": self.max_attempts,
            "window_seconds": self.window_seconds,
            "locked_out": locked_out,
            "lockout_remaining": lockout_remaining,
            "delay_multiplier": self._delays.get(identifier, 0)
        }


# Global rate limiter instance
auth_rate_limiter = RateLimiter(
    max_attempts=5,
    window_seconds=300,  # 5 minutes
    lockout_duration=900  # 15 minutes
)


def rate_limit_decorator(get_identifier):
    """
    Decorator for rate limiting endpoints.

    Args:
        get_identifier: Function to extract identifier from request
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract identifier
            identifier = await get_identifier(*args, **kwargs)

            # Check rate limit
            allowed, retry_after = auth_rate_limiter.check_rate_limit(identifier)

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many attempts. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)}
                )

            # Record attempt
            auth_rate_limiter.record_attempt(identifier)

            try:
                # Call original function
                result = await func(*args, **kwargs)

                # Record success if no exception
                auth_rate_limiter.record_success(identifier)

                return result
            except HTTPException as e:
                # Don't record success for HTTP errors
                if e.status_code < 500:
                    # Client error - keep the attempt recorded
                    pass
                else:
                    # Server error - don't count against rate limit
                    auth_rate_limiter.record_success(identifier)
                raise
            except Exception:
                # Server error - don't count against rate limit
                auth_rate_limiter.record_success(identifier)
                raise

        return wrapper
    return decorator
