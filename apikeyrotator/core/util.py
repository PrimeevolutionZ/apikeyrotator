"""Small helpers shared by the rotator components."""

from __future__ import annotations
import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any


KEY_LOG_LENGTH = 4
KEY_LOG_SUFFIX = '****'


def mask_key(key: str) -> str:
    return f"{key[:KEY_LOG_LENGTH]}{KEY_LOG_SUFFIX}"


def endpoint_label(url: str) -> str:
    """URL without query string/fragment - keeps endpoint metrics bounded (no urlsplit allocations)."""
    cut = len(url)
    for ch in ('?', '#'):
        i = url.find(ch)
        if i != -1 and i < cut:
            cut = i
    return url[:cut] if cut != len(url) else url


def host_of(url: str) -> str:
    """Host[:port] of a URL (lower-cased), used as circuit breaker scope."""
    start = url.find('://')
    rest = url[start + 3:] if start != -1 else url
    end = len(rest)
    for ch in ('/', '?', '#'):
        i = rest.find(ch, 0, end)
        if i != -1:
            end = i
    host = rest[:end]
    if '@' in host:
        host = host.rsplit('@', 1)[1]
    return host.lower()


def run_coroutine_sync(factory: Callable[[], Awaitable[Any]]) -> Any:
    """
    Runs a coroutine to completion from synchronous code.

    Works both when no event loop is running (uses asyncio.run) and when called
    from inside a running loop (runs the coroutine on a helper thread with its
    own loop, so the caller's loop is not re-entered). The second case blocks
    the caller's loop until the coroutine finishes - it is only used by
    synchronous APIs; async code should call the async variants instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    result: dict[str, Any] = {}

    def runner():
        try:
            result['value'] = asyncio.run(factory())
        except BaseException as e:  # propagate to caller thread
            result['error'] = e

    thread = threading.Thread(target=runner, name="apikeyrotator-provider", daemon=True)
    thread.start()
    thread.join()
    if 'error' in result:
        raise result['error']
    return result.get('value')


def in_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True
