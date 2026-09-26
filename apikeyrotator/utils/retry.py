"""Retry helpers for code outside the rotator (used by the secret providers)."""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


def retry_with_backoff(
        func: Callable,
        retries: int = 3,
        backoff_factor: float = 0.5,
        exceptions: type[Exception] | tuple[type[Exception], ...] = Exception
) -> Any:
    """
    Universal function for retries with exponential backoff.

    Executes a function with automatic retries on exceptions.
    Delay between attempts increases exponentially.

    Args:
        func: Function to execute
        retries: Maximum number of attempts (default 3)
        backoff_factor: Base delay for exponential growth (default 0.5)
        exceptions: Exception type(s) to catch (default Exception)

    Returns:
        Any: Function execution result

    Raises:
        Exception: Re-raises last exception if all attempts are exhausted

    Examples:
        >>> # Simple example
        >>> def flaky_request():
        ...     import requests
        ...     return requests.get('https://api.example.com/data')
        >>> response = retry_with_backoff(flaky_request, retries=5)

        >>> # With specific exceptions
        >>> import requests
        >>> response = retry_with_backoff(
        ...     lambda: requests.get('https://api.example.com'),
        ...     retries=3,
        ...     exceptions=requests.RequestException
        ... )

        >>> # With custom parameters
        >>> response = retry_with_backoff(
        ...     func=my_api_call,
        ...     retries=5,
        ...     backoff_factor=1.0,  # Start with 1 second
        ...     exceptions=(ConnectionError, TimeoutError)
        ... )

    Note:
        Delay is calculated as: backoff_factor * (2 ** attempt)
        For example, with backoff_factor=0.5:
        - Attempt 0: no delay
        - Attempt 1: 0.5 sec
        - Attempt 2: 1.0 sec
        - Attempt 3: 2.0 sec
        - Attempt 4: 4.0 sec
    """
    for attempt in range(retries):
        try:
            return func()
        except exceptions as e:
            if attempt == retries - 1:
                # Last attempt - re-raise exception
                raise e

            delay = backoff_factor * (2 ** attempt)
            logger.warning(f"Retry {attempt + 1}/{retries} after {delay:.1f}s delay (error: {type(e).__name__})")
            time.sleep(delay)


async def async_retry_with_backoff(
        func: Callable,
        retries: int = 3,
        backoff_factor: float = 0.5,
        exceptions: type[Exception] | tuple[type[Exception], ...] = Exception
) -> Any:
    """
    Asynchronous universal function for retries with exponential backoff.

    Executes an async function with automatic retries.
    Delay between attempts increases exponentially.

    Args:
        func: Async function to execute (coroutine)
        retries: Maximum number of attempts (default 3)
        backoff_factor: Base delay for exponential growth (default 0.5)
        exceptions: Exception type(s) to catch (default Exception)

    Returns:
        Any: Function execution result

    Raises:
        Exception: Re-raises last exception if all attempts are exhausted

    Examples:
        >>> # Simple example
        >>> async def flaky_request():
        ...     async with aiohttp.ClientSession() as session:
        ...         async with session.get('https://api.example.com') as resp:
        ...             return await resp.json()
        >>> response = await async_retry_with_backoff(flaky_request, retries=5)

        >>> # With specific exceptions
        >>> response = await async_retry_with_backoff(
        ...     lambda: session.get('https://api.example.com'),
        ...     retries=3,
        ...     exceptions=aiohttp.ClientError
        ... )

        >>> # In async/await context
        >>> async def main():
        ...     result = await async_retry_with_backoff(
        ...         my_async_api_call,
        ...         retries=5,
        ...         backoff_factor=1.0
        ...     )
        ...     return result

    Note:
        Uses asyncio.sleep() for non-blocking delay between attempts.
    """
    for attempt in range(retries):
        try:
            return await func()
        except exceptions as e:
            if attempt == retries - 1:
                # Last attempt - re-raise exception
                raise e

            delay = backoff_factor * (2 ** attempt)
            logger.warning(f"Async retry {attempt + 1}/{retries} after {delay:.1f}s delay (error: {type(e).__name__})")
            await asyncio.sleep(delay)


def __getattr__(name: str) -> Any:
    from . import _deprecated

    if name in _deprecated.REPLACEMENTS:
        return _deprecated.warn(name, __name__)
    if name == "CircuitBreaker":   # was re-exported here before 0.9.2
        from .circuit_breaker import CircuitBreaker
        return CircuitBreaker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
