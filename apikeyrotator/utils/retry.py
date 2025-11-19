import asyncio
import time
from typing import Callable, Any, Type, Union, Tuple
import requests


def retry_with_backoff(
        func: Callable,
        retries: int = 3,
        backoff_factor: float = 0.5,
        exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
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
        ...     return requests.get('https://api.example.com/data')
        >>> response = retry_with_backoff(flaky_request, retries=5)

        >>> # With specific exceptions
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
            print(f"⚠️  Retry {attempt + 1}/{retries} after {delay:.1f}s delay (error: {type(e).__name__})")
            time.sleep(delay)


async def async_retry_with_backoff(
        func: Callable,
        retries: int = 3,
        backoff_factor: float = 0.5,
        exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
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
            print(f"⚠️  Async Retry {attempt + 1}/{retries} after {delay:.1f}s delay (error: {type(e).__name__})")
            await asyncio.sleep(delay)


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
    return min(delay, max_delay)


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
    import random
    base = exponential_backoff(attempt, base_delay, max_delay)
    jitter = random.uniform(0, base * 0.1)  # Add up to 10% random jitter
    return min(base + jitter, max_delay)


class CircuitBreaker:
    """
    Circuit Breaker pattern for preventing cascading failures.

    Tracks consecutive error count and temporarily
    stops sending requests when threshold is exceeded.

    States:
    - CLOSED: Normal operation, requests pass
    - OPEN: Too many errors, requests blocked
    - HALF_OPEN: Trial period after recovery

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        >>>
        >>> def make_request():
        ...     if breaker.allow_request():
        ...         try:
        ...             response = requests.get('https://api.example.com')
        ...             breaker.record_success()
        ...             return response
        ...         except Exception as e:
        ...             breaker.record_failure()
        ...             raise
        ...     else:
        ...         raise Exception("Circuit breaker is OPEN")
    """

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        """
        Initializes Circuit Breaker.

        Args:
            failure_threshold: Number of errors to open circuit
            timeout: Time in seconds until transition to HALF_OPEN
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def allow_request(self) -> bool:
        """
        Checks if request can be executed.

        Returns:
            bool: True if request allowed, False otherwise
        """
        if self.state == 'CLOSED':
            return True

        if self.state == 'OPEN':
            # Check if enough time has passed to transition to HALF_OPEN
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = 'HALF_OPEN'
                return True
            return False

        # HALF_OPEN state
        return True

    def record_success(self):
        """Records successful request."""
        self.failures = 0
        self.state = 'CLOSED'

    def record_failure(self):
        """Records failed request."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.failure_threshold:
            self.state = 'OPEN'
            print(f"⚠️  Circuit breaker opened after {self.failures} failures")

    def get_state(self) -> str:
        """
        Get current circuit breaker state.

        Returns:
            str: 'CLOSED', 'OPEN' or 'HALF_OPEN'
        """
        return self.state

    def reset(self):
        """Resets circuit breaker to initial state."""
        self.failures = 0
        self.last_failure_time = 0
        self.state = 'CLOSED'


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
        ⏱️  slow_function took 1.00s
    """

    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"⏱️  {func.__name__} took {elapsed:.2f}s")
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
        ⏱️  slow_function took 1.00s
    """

    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"⏱️  {func.__name__} took {elapsed:.2f}s")
        return result

    return wrapper