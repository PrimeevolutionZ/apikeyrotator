"""
Helpers that are not used by the rotator any more; kept for backwards compatibility.

Accessing them through ``apikeyrotator.utils`` (or ``apikeyrotator.utils.retry``) emits a
DeprecationWarning; they will be removed in 1.0.
"""

from __future__ import annotations
import functools
import logging
import random
import time
import warnings
from collections.abc import Callable
from typing import Any


logger = logging.getLogger("apikeyrotator.utils")

#: name -> what to use instead
REPLACEMENTS = {
    "exponential_backoff": "min(base_delay * 2 ** attempt, max_delay)",
    "jittered_backoff": "the rotator's own backoff (base_delay / max_delay)",
    "measure_time": "rotator.get_metrics()['endpoint_stats'] or time.perf_counter()",
    "measure_time_async": "rotator.get_metrics()['endpoint_stats'] or time.perf_counter()",
}


def warn(name: str, module: str) -> Any:
    """Returns the deprecated helper `name`, warning the caller."""
    warnings.warn(
        f"{module}.{name} is deprecated and will be removed in 1.0; use {REPLACEMENTS[name]}",
        DeprecationWarning, stacklevel=3,
    )
    return globals()[name]


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Calculates delay for exponential backoff.

    Args:
        attempt: Attempt number (starting from 0)
        base_delay: Base delay in seconds (default 1.0)
        max_delay: Maximum delay in seconds (default 60.0)

    Returns:
        float: Delay in seconds

    Examples:
        >>> for i in range(5):
        ...     delay = exponential_backoff(i)
        ...     print(f"Attempt {i}: {delay}s")
        Attempt 0: 1.0s
        Attempt 1: 2.0s
        Attempt 2: 4.0s
        Attempt 3: 8.0s
        Attempt 4: 16.0s
    """
    delay = base_delay * (2 ** attempt)
    return float(min(delay, max_delay))


def jittered_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Calculates delay with added random jitter.

    Adding jitter helps avoid the "thundering herd problem"
    when many clients retry requests simultaneously.

    Args:
        attempt: Attempt number (starting from 0)
        base_delay: Base delay in seconds (default 1.0)
        max_delay: Maximum delay in seconds (default 60.0)

    Returns:
        float: Delay in seconds with jitter

    Examples:
        >>> import random
        >>> random.seed(42)
        >>> for i in range(3):
        ...     delay = jittered_backoff(i)
        ...     print(f"Attempt {i}: {delay:.2f}s")
    """
    base = exponential_backoff(attempt, base_delay, max_delay)
    jitter = random.uniform(0, base * 0.1)  # Add up to 10% random jitter
    return min(base + jitter, max_delay)


def measure_time(func: Callable) -> Callable:
    """
    Decorator for measuring function execution time.

    Args:
        func: Function to measure

    Returns:
        Callable: Wrapped function

    Examples:
        >>> @measure_time
        ... def slow_function():
        ...     time.sleep(1)
        ...     return "done"
        >>> result = slow_function()
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.debug(f"{func.__name__} took {elapsed:.2f}s")
        return result

    return wrapper


def measure_time_async(func: Callable) -> Callable:
    """
    Decorator for measuring async function execution time.

    Args:
        func: Async function to measure

    Returns:
        Callable: Wrapped function

    Examples:
        >>> @measure_time_async
        ... async def slow_function():
        ...     await asyncio.sleep(1)
        ...     return "done"
        >>> result = await slow_function()
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start
        logger.debug(f"{func.__name__} took {elapsed:.2f}s")
        return result

    return wrapper
