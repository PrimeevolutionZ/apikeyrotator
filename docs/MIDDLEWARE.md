# Middleware Guide

Middleware intercepts every attempt the rotator makes: before the request is
sent, after a response arrives, and when an attempt fails.

## Table of Contents

- [Overview](#overview)
- [How Middleware Runs](#how-middleware-runs)
- [Built-in Middleware](#built-in-middleware)
- [Creating Custom Middleware](#creating-custom-middleware)
- [Best Practices](#best-practices)
- [Advanced Patterns](#advanced-patterns)
- [Performance Considerations](#performance-considerations)

---

## Overview

Typical uses:

- **Cache** responses to avoid repeated calls
- **Log** requests and responses (with secrets redacted)
- **Track rate limits** and wait for a key's quota
- **Modify headers** (request ids, signatures, tracing)
- **Validate** responses before they reach your code
- **Collect** custom metrics

Retries are built into the rotator (`max_retries`, `total_timeout`); middleware
is not needed for them.

---

## How Middleware Runs

### Hooks

Subclass `RotatorMiddleware` and implement any of these hooks:

| Hook | Called | Must return |
|---|---|---|
| `before_request_sync(request_info)` / `async before_request(...)` | before each attempt | the `RequestInfo` (possibly modified), **or** a `ResponseInfo` to answer without calling the API |
| `after_request_sync(response_info)` / `async after_request(...)` | after each response (any status) | the `ResponseInfo` |
| `on_error_sync(error_info)` / `async on_error(...)` | after a network error, or an error response the rotator retries (429, 5xx, 401/403) | `bool` (informational; exceptions raised here are logged and ignored) |

`APIKeyRotator` calls the `*_sync` hooks, `AsyncAPIKeyRotator` calls the
coroutine hooks. The base class's coroutine hooks delegate to the sync ones, so
**implementing `*_sync` makes a middleware work with both rotators** (this also holds
for classes that don't inherit from `RotatorMiddleware`). Override the `async`
versions only when they need to `await` something. A middleware with only async hooks
never runs in `APIKeyRotator` - the rotator emits a `UserWarning` when it is created.

### Order

Middlewares run in list order for every hook:

```
attempt:   before_request: M1 → M2 → M3 → HTTP request
response:  after_request:  M1 → M2 → M3 → rotator decides (return / retry)
failure:   on_error:       M1 → M2 → M3 → rotator retries or gives up
```

If a `before_request` hook returns a `ResponseInfo` (e.g. a cache hit), the
remaining `before_request` hooks are skipped and that response is returned to the
caller - no HTTP request, no retry logic.

Hooks run once **per attempt**: a request retried 3 times produces 3
`before_request` calls with `request_info.attempt` = 0, 1, 2.

### Data Models

`RequestInfo`:

| Attribute | Description |
|---|---|
| `method`, `url` | HTTP method and URL |
| `headers`, `cookies` | Headers/cookies that will be sent (mutable) |
| `key` | API key used for this attempt |
| `attempt` | Attempt number, 0-based |
| `kwargs` | Arguments passed to the HTTP client (`params`, `json`, ...). **Do not add your own entries** - they are passed to the client. |

`ResponseInfo`:

| Attribute | Description |
|---|---|
| `status_code`, `headers` | Status and response headers (dict) |
| `content` | Body as bytes (`None` for `stream=True`) |
| `request_info` | The `RequestInfo` of this attempt (same object) |
| `response_time` | Seconds the attempt took |

`ErrorInfo`: `exception`, `request_info`, `response_info` (set for error
responses; the exception is then an `HTTPStatusError` with `.status_code`).
Responses returned to the caller (2xx, most 4xx, non-retried POST errors) go
through `after_request` only.

---

## Built-in Middleware

### CachingMiddleware

Caches `2xx` responses (GET only by default) with TTL and LRU eviction.

```python
from apikeyrotator import APIKeyRotator, CachingMiddleware

cache = CachingMiddleware(
    ttl=600,                               # seconds
    cache_only_get=True,                   # set False to also cache POST/PUT/PATCH (body is part of the key)
    max_cache_size=1000,                   # entries
    max_cache_size_bytes=100 * 1024 ** 2,  # total size
    max_cacheable_size=10 * 1024 ** 2,     # larger responses are not cached
)
rotator = APIKeyRotator(api_keys=["key1", "key2"], middlewares=[cache])

response1 = rotator.get("https://api.example.com/data")   # miss - calls the API
response2 = rotator.get("https://api.example.com/data")   # hit - no network call

stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%} ({stats['hits']} hits / {stats['total']})")
print(f"Entries: {stats['cache_size']}, bytes: {stats['size_bytes']}")

cache.clear()
```

**Cache key**: method + URL + query `params` + request headers except
`Authorization`, `X-API-Key`, `User-Agent`, `Cookie` (so all API keys share the
cache) + body for POST/PUT/PATCH.

**Not cached**: non-2xx responses, responses with `Set-Cookie`,
`Cache-Control: no-store` / `private`, `text/event-stream` and
`multipart/x-mixed-replace` content.

A cache hit returns a regular `requests.Response` / `httpx.Response` (sync) or a
small object with `status`, `status_code`, `headers`, `read()`, `text()`,
`json()` (async).

### LoggingMiddleware

```python
import logging
from apikeyrotator import APIKeyRotator, LoggingMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[LoggingMiddleware(
        verbose=True,              # include key (masked) and attempt number
        log_response_time=True,
        max_key_chars=4,           # characters of the key shown in logs
        max_logs_per_second=1000,  # drop messages above this rate
    )],
)
rotator.get("https://api.example.com/data")

# GET https://api.example.com/data (key: key1****, attempt: 1)
# 200 from https://api.example.com/data (key: key1****) (0.234s)
```

Log levels: `2xx` INFO, `4xx` WARNING, `5xx` ERROR; errors are logged at
ERROR with a traceback at DEBUG level. Headers `Authorization`, `X-API-Key`,
`Cookie`, `Set-Cookie` are logged as `[REDACTED]` (headers are logged at DEBUG).

The middleware logs to the `apikeyrotator.middleware.logging` logger (or the
`logger=` you pass); configure logging in your application to see the output.

### RateLimitMiddleware

```python
from apikeyrotator import APIKeyRotator, RateLimitMiddleware

rate_limit = RateLimitMiddleware(
    pause_on_limit=True,    # wait before using a key whose quota is used up
    max_tracked_keys=1000,
    max_wait=60,            # never wait longer than this per request
)
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"], middlewares=[rate_limit])

stats = rate_limit.get_stats()
print(stats["tracked_keys"], stats["active_limits"])
```

It reads `X-RateLimit-Limit/Remaining/Reset` and the IETF `RateLimit-*` headers
(reset as UNIX timestamp or seconds) from every response, and `Retry-After`
(seconds or HTTP date) from `429` responses. Before an attempt, if the selected
key has `remaining == 0` and its reset time is in the future, it waits until the
reset (at most `max_wait`).

**Do you need it?** The rotator already parks keys that answer `429` or report
`X-RateLimit-Remaining: 0` and continues with other keys, and `key_rate_limit=`
enforces a quota client-side ([Resilience](RESILIENCE.md)). The middleware is
useful when you prefer *waiting* for a key - e.g. with a single key.

---

## Creating Custom Middleware

### Adding Headers

```python
import time
import uuid
from apikeyrotator import APIKeyRotator, RotatorMiddleware, RequestInfo

class RequestIdMiddleware(RotatorMiddleware):
    """Adds a request id and a timestamp to every attempt."""

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo:
        request_info.headers["X-Request-ID"] = str(uuid.uuid4())
        request_info.headers["X-Request-Timestamp"] = str(int(time.time()))
        return request_info

rotator = APIKeyRotator(api_keys=["key1"], middlewares=[RequestIdMiddleware()])
```

### Response Validation

An exception raised in `after_request` propagates to the caller of
`rotator.get()` - a convenient way to reject malformed responses:

```python
import json
from apikeyrotator import APIKeyRotator, RotatorMiddleware, ResponseInfo

class InvalidResponseError(Exception):
    pass

class RequiredFieldsMiddleware(RotatorMiddleware):
    def __init__(self, required_fields: list[str]):
        self.required_fields = required_fields

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        if response_info.status_code == 200 and response_info.content:
            try:
                data = json.loads(response_info.content)
            except ValueError:
                return response_info   # not JSON
            missing = [f for f in self.required_fields if f not in data]
            if missing:
                raise InvalidResponseError(f"Missing fields: {missing}")
        return response_info

rotator = APIKeyRotator(api_keys=["key1"], middlewares=[RequiredFieldsMiddleware(["id", "name"])])
```

### Metrics Collection

`ResponseInfo.response_time` already holds the duration of the attempt:

```python
from collections import defaultdict
from apikeyrotator import APIKeyRotator, RotatorMiddleware, ResponseInfo, ErrorInfo

class StatusCodeMetrics(RotatorMiddleware):
    def __init__(self):
        self.status_codes = defaultdict(int)
        self.total_time = 0.0
        self.responses = 0
        self.errors = 0

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        self.status_codes[response_info.status_code] += 1
        self.total_time += response_info.response_time or 0.0
        self.responses += 1
        return response_info

    def on_error_sync(self, error_info: ErrorInfo) -> bool:
        self.errors += 1
        return False

    def summary(self) -> dict:
        avg = self.total_time / self.responses if self.responses else 0.0
        return {"status_codes": dict(self.status_codes), "avg_time": avg, "errors": self.errors}

metrics = StatusCodeMetrics()
rotator = APIKeyRotator(api_keys=["key1"], middlewares=[metrics])
for i in range(100):
    rotator.get(f"https://api.example.com/data/{i}")
print(metrics.summary())
```

The rotator also has built-in metrics: `rotator.get_metrics()` and
`rotator.get_key_statistics()`.

### Request Signing / JWT per Key

Per-key authentication is best done with `header_callback` - it receives the key
chosen for the attempt:

```python
import time
import jwt   # pip install pyjwt
from apikeyrotator import APIKeyRotator

_tokens: dict[str, tuple[str, float]] = {}

def jwt_headers(key: str, headers: dict | None) -> dict:
    """Sign a short-lived JWT with the rotated secret; cache it per key."""
    token, expires = _tokens.get(key, ("", 0.0))
    if time.time() > expires - 60:
        expires = time.time() + 3600
        token = jwt.encode({"exp": int(expires)}, key, algorithm="HS256")
        _tokens[key] = (token, expires)
    return {"Authorization": f"Bearer {token}"}

rotator = APIKeyRotator(api_keys=["secret1", "secret2"], header_callback=jwt_headers)
```

Remember that a `401`/`403` removes the key from rotation; for tokens that can
simply expire, refresh them before they do (as above).

### Async-only Work

Override the coroutine hooks when the middleware must `await`:

```python
from apikeyrotator import AsyncAPIKeyRotator, RotatorMiddleware, RequestInfo

class AsyncTokenMiddleware(RotatorMiddleware):
    def __init__(self, token_source):
        self.token_source = token_source   # object with: async def get_token() -> str

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        request_info.headers["X-Session-Token"] = await self.token_source.get_token()
        return request_info
```

Such a middleware only works with `AsyncAPIKeyRotator`.

---

## Best Practices

1. **Order matters.** Put `CachingMiddleware` first so a cache hit skips the others;
   put logging after it if cache hits should not be logged as requests.
2. **One responsibility per middleware** - easier to test and reuse.
3. **Don't let optional work break requests.** Wrap non-essential logic in
   `try/except` inside `before_request` / `after_request` (exceptions there reach
   the caller; exceptions in `on_error` are ignored).
4. **Don't put your own keys into `request_info.kwargs`** - they are passed to the
   HTTP client. Keep per-attempt state keyed by the `RequestInfo` object instead
   (see below).
5. **Bound your memory** - any per-URL or per-key storage needs a size limit.
6. **Provide `get_stats()`** for introspection, like the built-ins.

---

## Advanced Patterns

### Conditional Middleware

```python
from urllib.parse import urlsplit
from apikeyrotator import RotatorMiddleware, RequestInfo

class DomainHeaderMiddleware(RotatorMiddleware):
    """Adds a header only for selected domains."""

    def __init__(self, domains: set[str], header: str, value: str):
        self.domains, self.header, self.value = domains, header, value

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo:
        if urlsplit(request_info.url).hostname in self.domains:
            request_info.headers[self.header] = self.value
        return request_info
```

### Composite Middleware

```python
from apikeyrotator import RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo

class CompositeMiddleware(RotatorMiddleware):
    """Groups several middlewares into one (same order semantics as the rotator)."""

    def __init__(self, middlewares: list[RotatorMiddleware]):
        self.middlewares = middlewares

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo | ResponseInfo:
        for middleware in self.middlewares:
            result = middleware.before_request_sync(request_info)
            if isinstance(result, ResponseInfo):
                return result          # short-circuit (e.g. cache hit)
            request_info = result
        return request_info

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        for middleware in self.middlewares:
            response_info = middleware.after_request_sync(response_info)
        return response_info

    def on_error_sync(self, error_info: ErrorInfo) -> bool:
        return any([m.on_error_sync(error_info) for m in self.middlewares])
```

### Per-Attempt State

`after_request` and `on_error` receive the same `RequestInfo` object that
`before_request` saw, so it can key per-attempt state:

```python
import threading
import time
from apikeyrotator import RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo

class SlowRequestMiddleware(RotatorMiddleware):
    """Reports attempts slower than a threshold (wall clock incl. other middlewares)."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self._started: dict[int, float] = {}
        self._lock = threading.Lock()

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo:
        with self._lock:
            self._started[id(request_info)] = time.monotonic()
        return request_info

    def _finish(self, request_info: RequestInfo) -> None:
        with self._lock:
            started = self._started.pop(id(request_info), None)
        if started is not None and time.monotonic() - started > self.threshold:
            print(f"Slow: {request_info.method} {request_info.url}")

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        self._finish(response_info.request_info)
        return response_info

    def on_error_sync(self, error_info: ErrorInfo) -> bool:
        self._finish(error_info.request_info)
        return False
```

---

## Performance Considerations

1. **Keep hooks cheap** - they run for every attempt. The built-in stack
   (logging + rate limit) adds roughly 17 µs per request; see
   [benchmarks](../benchmarks/README.md).
2. **Avoid blocking in async hooks** - use `await asyncio.sleep()`, not
   `time.sleep()`, and async clients for I/O.
3. **With any middleware installed, async responses are read into memory** so that
   `ResponseInfo.content` is available. For large downloads without middleware
   needs, use a rotator without middlewares (or `stream=True` with the sync rotator,
   where `content` is `None`).
4. **Profile** with `apikeyrotator.utils.measure_time` / `measure_time_async`
   (log durations at DEBUG level).

---

## Next Steps

- [Examples](EXAMPLES.md) - practical middleware usage
- [API Reference](API_REFERENCE.md#middleware) - complete middleware API
- [Advanced Usage](ADVANCED_USAGE.md) - strategies, providers, metrics
