"""Token bucket rate limiter for API calls."""

import threading
import time

import structlog

logger = structlog.get_logger()


class TokenBucketRateLimiter:
    """Rate limiter using the token bucket algorithm.

    Supports both per-second and per-day limits (for Etsy: 10/sec, 10k/day).
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        requests_per_day: int = 10_000,
    ):
        self.rate = requests_per_second
        self.daily_limit = requests_per_day

        # Per-second bucket
        self.tokens = requests_per_second
        self.max_tokens = requests_per_second
        self.last_refill = time.monotonic()

        # Daily counter
        self.daily_count = 0
        self.daily_reset_time = time.monotonic() + 86400

        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        """Block until a token is available or timeout."""
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            with self._lock:
                self._refill()
                self._check_daily_reset()

                if self.daily_count >= self.daily_limit:
                    logger.warning("rate_limit_daily_exhausted", count=self.daily_count)
                    return False

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    self.daily_count += 1
                    return True

            # Wait for token refill
            time.sleep(1.0 / self.rate)

        logger.warning("rate_limit_timeout", timeout=timeout)
        return False

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def _check_daily_reset(self):
        now = time.monotonic()
        if now >= self.daily_reset_time:
            self.daily_count = 0
            self.daily_reset_time = now + 86400
            logger.info("rate_limit_daily_reset")

    @property
    def remaining_daily(self) -> int:
        with self._lock:
            self._check_daily_reset()
            return max(0, self.daily_limit - self.daily_count)
