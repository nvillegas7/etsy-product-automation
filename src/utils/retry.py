"""Exponential backoff with jitter for API calls."""

import random
import time
from functools import wraps
from typing import Any, Callable

import structlog

logger = structlog.get_logger()


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator for exponential backoff with jitter."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempts=max_retries + 1,
                            error=str(e),
                        )
                        raise
                    delay = min(base_delay * (2**attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.5)
                    total_delay = delay + jitter
                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        delay=round(total_delay, 2),
                        error=str(e),
                    )
                    time.sleep(total_delay)
            return None  # unreachable

        return wrapper

    return decorator
