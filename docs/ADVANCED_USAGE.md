# Advanced Usage

Advanced features and configuration for power users. For production resilience
(deadlines, circuit breaker, client-side rate limits, Redis, httpx) see
[Resilience & Scaling](RESILIENCE.md).

## Table of Contents

- [Middleware System](#middleware-system)
- [Rotation Strategies](#rotation-strategies)
- [Metrics and Monitoring](#metrics-and-monitoring)
- [Secret Providers](#secret-providers)
- [Custom Callbacks](#custom-callbacks)
- [Anti-Bot Evasion](#anti-bot-evasion)
- [Custom Error Classification](#custom-error-classification)
- [Connections and Cleanup](#connections-and-cleanup)
- [Configuration File](#configuration-file)
- [Performance](#performance)
- [Best Practices](#best-practices)

---

## Middleware System

Middleware intercepts every attempt: before the request, after the response and
on errors. Use it to cache responses, log traffic, track rate limits or modify
headers.

**[📖 Complete Middleware Guide →](MIDDLEWARE.md)**

### Quick Example

```python
import logging
from apikeyrotator import APIKeyRotator, CachingMiddleware, LoggingMiddleware, RateLimitMiddleware

logging.basicConfig(level=logging.INFO)   # needed to see LoggingMiddleware output

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    middlewares=[
        CachingMiddleware(ttl=600, max_cache_size=1000),
        LoggingMiddleware(verbose=True),
        RateLimitMiddleware(pause_on_limit=True),
    ],
)

response = rotator.get("https://api.example.com/data")   # logged, cached for 10 minutes
```

Middlewares run in list order. A `before_request` hook that returns a response
(like a cache hit) stops the chain and no HTTP request is made.

### Built-in Middleware

#### CachingMiddleware

```python
from apikeyrotator import APIKeyRotator, CachingMiddleware

cache = CachingMiddleware(
    ttl=300,               # seconds
    cache_only_get=True,   # only GET requests
    max_cache_size=1000,   # entries (LRU eviction)
)
rotator = APIKeyRotator(api_keys=["key1"], middlewares=[cache])

stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}, entries: {stats['cache_size']}, bytes: {stats['size_bytes']}")

cache.clear()
```

Only `2xx` responses are cached; responses with `Set-Cookie` or
`Cache-Control: no-store/private` are not. Query `params` are part of the cache key.

#### LoggingMiddleware

```python
from apikeyrotator import APIKeyRotator, LoggingMiddleware

rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[LoggingMiddleware(verbose=True, log_response_time=True, max_key_chars=4)],
)

# 📤 GET https://api.example.com/data (key: key1****, attempt: 1)
# 📥 ✅ 200 from https://api.example.com/data (key: key1****) (0.234s)
```

Sensitive headers (`Authorization`, `X-API-Key`, `Cookie`) are redacted.

#### RateLimitMiddleware

```python
from apikeyrotator import APIKeyRotator, RateLimitMiddleware

rate_limit = RateLimitMiddleware(pause_on_limit=True, max_wait=60)
rotator = APIKeyRotator(api_keys=["key1", "key2"], middlewares=[rate_limit])

print(rate_limit.get_stats())   # {'tracked_keys': ..., 'active_limits': ..., 'max_tracked_keys': ...}
```

The rotator already parks keys that return `429` or `X-RateLimit-Remaining: 0`
and switches to other keys. This middleware additionally *waits* (up to
`max_wait` seconds) when the selected key's quota is used up - useful with a
single key.

> `RetryMiddleware` was removed in 0.6.1 - retries are built into the rotator
> (`max_retries`, `base_delay`, `max_delay`, `total_timeout`).

### Custom Middleware

Subclass `RotatorMiddleware` and implement the hooks you need. Sync rotators call
the `*_sync` hooks; async rotators call the coroutine versions, which by default
delegate to the sync ones - so implementing `*_sync` covers both.

```python
import uuid
from apikeyrotator import APIKeyRotator, RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo

class RequestIdMiddleware(RotatorMiddleware):
    """Adds a request id and reports failures."""

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo:
        request_info.headers["X-Request-ID"] = str(uuid.uuid4())
        return request_info

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        print(f"{response_info.status_code} in {response_info.response_time:.3f}s")
        return response_info

    def on_error_sync(self, error_info: ErrorInfo) -> bool:
        print(f"Attempt {error_info.request_info.attempt + 1} failed: {error_info.exception}")
        return False

rotator = APIKeyRotator(api_keys=["key1"], middlewares=[RequestIdMiddleware()])
```

Override the `async def before_request / after_request / on_error` methods only
if the async version needs to `await` something.

---

## Rotation Strategies

The strategy decides which key each attempt uses. All strategies skip keys that
are rate-limited or unhealthy (an unhealthy key gets a probe request again
`recovery_timeout` seconds after its last failure, 60 s by default).

| Strategy | Use when |
|---|---|
| `"round_robin"` (default) | Keys are equal - spread load evenly. |
| `"random"` | Avoid predictable patterns. |
| `"weighted"` | Keys have different quotas. |
| `"lru"` | Keep all keys "warm"; least recently used goes next. |
| `"health_based"` | Keys fail independently; exclude failing ones with your own threshold. |
| `"failover"` | One primary key, others only as backups. |

```python
from apikeyrotator import APIKeyRotator

# Round robin: key1 -> key2 -> key3 -> key1 ...
APIKeyRotator(api_keys=["key1", "key2", "key3"], rotation_strategy="round_robin")

# Weighted: key3 gets 60% of requests, key2 30%, key1 10%
APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    rotation_strategy="weighted",
    rotation_strategy_kwargs={"weights": {"key1": 1, "key2": 3, "key3": 6}},
)

# Health-based: exclude a key after 5 consecutive failures, recheck after 5 minutes
APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    rotation_strategy="health_based",
    rotation_strategy_kwargs={"failure_threshold": 5, "health_check_interval": 300},
)

# Failover: always "primary" while it works
APIKeyRotator(api_keys=["primary", "backup1", "backup2"], rotation_strategy="failover")

# Probe unhealthy keys sooner / never
APIKeyRotator(api_keys=["key1", "key2"], recovery_timeout=10)
```

### Custom Strategy

```python
from apikeyrotator import APIKeyRotator, BaseRotationStrategy, KeyMetrics

class BestSuccessRateStrategy(BaseRotationStrategy):
    """Use the available key with the highest success rate."""

    def get_next_key(self, current_key_metrics: dict[str, KeyMetrics] | None = None) -> str:
        candidates = self._get_healthy_keys(current_key_metrics)  # skips limited/unhealthy keys
        if not current_key_metrics:
            return candidates[0]
        return max(candidates, key=lambda k: current_key_metrics[k].success_rate)

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    rotation_strategy=BestSuccessRateStrategy(["key1", "key2", "key3"]),
)
```

The rotator passes its live metrics (`{key: KeyMetrics}`) on every call and calls
`update_keys()` when keys are added or removed.

---

## Metrics and Monitoring

Metrics are enabled by default (`enable_metrics=True`).

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])
for i in range(100):
    rotator.get(f"https://api.example.com/data/{i}")

metrics = rotator.get_metrics()
print(f"Total requests: {metrics['total_requests']}")      # every attempt counts
print(f"Success rate: {metrics['success_rate']:.2%}")
print(f"Uptime: {metrics['uptime_seconds']:.1f}s")

# Endpoints are URLs without the query string (bounded memory)
for endpoint, stats in metrics["endpoint_stats"].items():
    print(endpoint, stats["total_requests"], f"{stats['avg_response_time']:.3f}s")
```

### Per-Key Statistics

```python
for key, stats in rotator.get_key_statistics().items():
    print(f"{key[:4]}****: {stats['total_requests']} requests, "
          f"success {stats['success_rate']:.0%}, "
          f"avg {stats['avg_response_time']:.3f}s, "
          f"{'healthy' if stats['is_healthy'] else 'UNHEALTHY'}, "
          f"429s: {stats['rate_limit_hits']}")
```

### Prometheus Export

```python
from apikeyrotator import PrometheusExporter

text = PrometheusExporter.export(rotator.metrics, key_metrics=rotator.get_key_statistics())

with open("/var/lib/node_exporter/textfile/rotator.prom", "w") as f:   # textfile collector
    f.write(text)
```

Keys are masked in labels (`key="sk-1****"`).

### Export Configuration

`export_config()` returns settings and per-key statistics with masked keys - safe to log:

```python
config = rotator.export_config()
print(config["keys_count"], config["strategy"], config["max_retries"], config["metrics_enabled"])
```

### Circuit breaker state

```python
rotator = APIKeyRotator(api_keys=["key1"], circuit_breaker=True)
print(rotator.get_circuit_states())   # {'api.example.com': 'CLOSED'}
```

---

## Secret Providers

Load keys from a secret store instead of code or environment variables.

```python
from apikeyrotator import APIKeyRotator, AWSSecretsManagerProvider

provider = AWSSecretsManagerProvider(secret_name="prod/api-keys", region_name="us-east-1")

rotator = APIKeyRotator(
    secret_provider=provider,
    auto_refresh_interval=300,   # reload every 5 minutes in the background
)
response = rotator.get("https://api.example.com/data")

# Manual refresh
rotator.refresh_keys_from_provider_sync()        # or: await rotator.refresh_keys_from_provider()
```

Requires `pip install "apikeyrotator[aws]"`. The secret may be a JSON array, a JSON
object (`{"keys": [...]}`, `{"api_keys": [...]}` or `{"name": "key", ...}`) or a
comma-separated string.

```python
from apikeyrotator import (
    GCPSecretManagerProvider, FileSecretProvider, EnvironmentSecretProvider, create_secret_provider,
)

GCPSecretManagerProvider(project_id="my-project", secret_id="api-keys")   # pip install "apikeyrotator[gcp]"
FileSecretProvider(file_path="keys.txt")      # JSON array, CSV and/or one key per line, '#' comments
EnvironmentSecretProvider(env_var="MY_API_KEYS")
create_secret_provider("aws", secret_name="prod/api-keys")
```

Keys that were rejected with 401/403 are not re-added by a refresh; metrics of keys
that stay are preserved. A custom provider is any object with
`async get_keys()` and `async refresh_keys()` returning `list[str]`.

In async code, `AsyncAPIKeyRotator(secret_provider=...)` loads the keys on first use
(`async with`, the first request or `await rotator.load_keys()`) in your event loop, so a
provider may use loop-bound clients such as an `aiohttp.ClientSession`. See
[API Reference](API_REFERENCE.md#asyncapikeyrotator).

---

## Custom Callbacks

### Custom Retry Logic

`should_retry_callback` is consulted for responses the rotator would otherwise
return (2xx/3xx). Sync rotators pass the response, async rotators the status code.

```python
import requests
from apikeyrotator import APIKeyRotator

def should_retry(response: requests.Response) -> bool:
    """Retry when the API reports a temporary error in a 200 response."""
    try:
        data = response.json()
    except ValueError:
        return False
    return data.get("status") == "error" and data.get("code") == "temporary"

rotator = APIKeyRotator(api_keys=["key1", "key2"], should_retry_callback=should_retry)
```

429/5xx/401/403 are already handled by the rotator; the callback does not need to
cover them.

### Dynamic Headers and Cookies

```python
import time
from apikeyrotator import APIKeyRotator

def generate_headers(key: str, existing_headers: dict | None) -> tuple[dict, dict]:
    headers = {
        "X-API-Key": key,                   # replaces the default Authorization header
        "X-Timestamp": str(int(time.time())),
    }
    cookies = {"preference": "json"}
    return headers, cookies

rotator = APIKeyRotator(api_keys=["key1", "key2"], header_callback=generate_headers)
```

The callback may also return just a headers `dict`. When it sets `Authorization`
or `X-API-Key`, the rotator does not add its default auth header.

---

## Anti-Bot Evasion

```python
from apikeyrotator import APIKeyRotator

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]
PROXIES = [
    "http://user:pass@proxy1.example.com:8080",
    "http://user:pass@proxy2.example.com:8080",
]

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    user_agents=USER_AGENTS,        # next UA per request (unless the request sets one)
    random_delay_range=(1.0, 3.0),  # random pause before each attempt (+ up to 10% jitter)
    proxy_list=PROXIES,             # next proxy per attempt
)
```

SOCKS proxies (`socks5://...`) need `pip install "requests[socks]"` with the
requests backend; aiohttp does not support SOCKS natively (use the httpx backend
with `pip install "httpx[socks]"`). The random delay counts towards `total_timeout`.

---

## Custom Error Classification

Subclass `ErrorClassifier` to adapt to an API's conventions:

```python
from apikeyrotator import APIKeyRotator, ErrorClassifier, ErrorType

class MyApiClassifier(ErrorClassifier):
    def classify_error(self, response=None, exception=None) -> ErrorType:
        # NOTE: use "is not None" - error responses of requests are falsy
        if response is not None:
            if response.status_code == 420:          # custom "enhance your calm"
                return ErrorType.RATE_LIMIT
            if response.status_code == 200:
                try:
                    code = response.json().get("error", {}).get("code")
                except (ValueError, AttributeError):
                    code = None
                if code == "quota_exceeded":
                    return ErrorType.RATE_LIMIT
                if code == "temporary_failure":
                    return ErrorType.TEMPORARY
        return super().classify_error(response, exception)

    def should_remove_key(self, response=None, exception=None) -> bool:
        # Also drop keys on 402 Payment Required
        return response is not None and response.status_code in (401, 402, 403)

rotator = APIKeyRotator(api_keys=["key1", "key2"], error_classifier=MyApiClassifier())
```

- `RATE_LIMIT` parks the key and switches keys, `TEMPORARY` retries with backoff.
- `PERMANENT` removes the key if `should_remove_key()` is true, otherwise returns the response.
- Async rotators pass a lightweight object with only `status_code` and `headers`
  (no body), so body-based rules apply to the sync rotator only.

Extra retryable statuses without subclassing:

```python
from apikeyrotator import APIKeyRotator, ErrorClassifier

rotator = APIKeyRotator(api_keys=["key1"], error_classifier=ErrorClassifier(custom_retryable_codes=[420, 509]))
```

---

## Connections and Cleanup

Each rotator keeps a connection pool (`pool_size=100` by default). Close it when done:

```python
from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator

# Sync
with APIKeyRotator(api_keys=["key1"]) as rotator:
    response = rotator.get("https://api.example.com/data")

# Async
async def main():
    async with AsyncAPIKeyRotator(api_keys=["key1"], pool_size=200) as rotator:
        response = await rotator.get("https://api.example.com/data")
```

`close()` also stops the background key refresh. Reuse one rotator for the whole
application instead of creating one per request.

Client-level options go to `http_client_kwargs`, e.g. a custom CA bundle with the
requests backend:

```python
rotator = APIKeyRotator(api_keys=["key1"], http_client_kwargs={"verify": "/etc/ssl/company-ca.pem"})
```

---

## Configuration File

The rotator reads `config_file` (default `rotator_config.json`, JSON or YAML) at
start-up; it never writes it. The only setting it uses is `successful_headers` -
extra headers per domain - and only when `save_sensitive_headers=True`:

```json
{
  "successful_headers": {
    "api.example.com": {"Accept": "application/json", "X-Client": "my-app"}
  }
}
```

```python
rotator = APIKeyRotator(
    api_keys=["key1"],
    config_file="/etc/myapp/rotator.json",
    save_sensitive_headers=True,   # apply successful_headers for matching domains
)
```

`Authorization` and `X-API-Key` entries in the file are always ignored - the key
comes from the rotator. `ConfigLoader` can be used directly to read/write such files.

---

## Performance

- Per-request overhead is ~10 µs of CPU; key selection ~1 µs even with 1000 keys;
  ~230 bytes of memory per key (see [benchmarks](../benchmarks/README.md)).
- Use the async rotator (or threads with the sync one) for many concurrent requests,
  and limit concurrency yourself:

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def fetch_all(urls, max_concurrent=50):
    semaphore = asyncio.Semaphore(max_concurrent)
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2"], total_timeout=30) as rotator:
        async def fetch_one(url):
            async with semaphore:
                response = await rotator.get(url)
                return await response.json()
        return await asyncio.gather(*(fetch_one(u) for u in urls), return_exceptions=True)

results = asyncio.run(fetch_all([f"https://api.example.com/item/{i}" for i in range(1000)]))
```

- For the lowest latency: `max_retries=2`, a small `base_delay`, no
  `random_delay_range`, and `enable_metrics=False` if you don't read metrics.
- HTTP/2 multiplexing: `AsyncAPIKeyRotator(..., http_backend="httpx", http2=True)`.

---

## Best Practices

1. **Keep keys out of code** - use `API_KEYS` / `.env` or a secret provider with
   `auto_refresh_interval`.
2. **Set a deadline** - `total_timeout` bounds the worst-case latency of a request.
3. **Catch `AllKeysExhaustedError`** (it includes `DeadlineExceededError` and
   `CircuitOpenError`) and inspect `last_response` / `last_exception`.
4. **Use `Idempotency-Key`** for POST requests that are safe to retry.
5. **Reuse and close rotators** (`with` / `async with`).
6. **Share state between workers** with `RedisStateBackend` when several processes use the same keys.
7. **Configure logging** in your application (`logging.basicConfig(...)`); the library prints nothing by itself.

---

## Next Steps

- [Resilience & Scaling](RESILIENCE.md)
- [Middleware Guide](MIDDLEWARE.md)
- [Examples](EXAMPLES.md)
- [API Reference](API_REFERENCE.md)
- [Error Handling](ERROR_HANDLING.md)
- [FAQ](FAQ.md)
