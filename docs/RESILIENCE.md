# Resilience & Scaling (0.8.0)

Features for running the rotator under load and across many processes.
All of them are opt-in or safe by default; the table shows the defaults.

| Feature | Parameter | Default |
|---|---|---|
| Safe retries of non-idempotent requests | `retry_non_idempotent` | `False` (safe) |
| Total time budget per request | `total_timeout` | `None` (no limit) |
| Per-host circuit breaker | `circuit_breaker` | off |
| Client-side key rate limit (token bucket) | `key_rate_limit` | off |
| Skip keys reporting `X-RateLimit-Remaining: 0` | `respect_rate_limit_headers` | `True` |
| Shared state between processes (Redis) | `state_backend` | local only |
| Background key refresh | `auto_refresh_interval` | off |
| HTTP backend / HTTP/2 | `http_backend`, `http2` | `requests` / `aiohttp` |

---

## Safe retries of POST / PATCH

Retrying a request that the server may already have processed can duplicate an
operation (a payment, a message, an LLM call you pay for). The rotator therefore
distinguishes **idempotent** methods (`GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE`,
`TRACE`) from the rest.

For `POST` / `PATCH` it retries only when the server certainly did **not** process
the request:

| Outcome | GET / PUT / DELETE ... | POST / PATCH |
|---|---|---|
| `429`, `503`, `408`, `425` | retry | retry |
| `401` / `403` (key rejected) | switch key | switch key |
| `500`, `502`, `504`, ... | retry | **returned to the caller** |
| connection refused / connect timeout | retry | retry |
| read timeout / connection dropped | retry | **exception re-raised** |

Opt in to retries anyway when your endpoint is idempotent:

```python
# Per request - the standard way for APIs that support it (Stripe, OpenAI, ...)
rotator.post(url, json=payload, headers={"Idempotency-Key": str(uuid.uuid4())})

# Or globally
rotator = APIKeyRotator(api_keys=keys, retry_non_idempotent=True)
```

## Request deadline (`total_timeout`)

`timeout` limits a single attempt; `total_timeout` limits the whole request -
all attempts, backoff and rate-limit waits together:

```python
from apikeyrotator import APIKeyRotator, DeadlineExceededError

rotator = APIKeyRotator(api_keys=keys, timeout=10, total_timeout=15)

try:
    rotator.get(url)                     # default budget: 15s
    rotator.get(url, total_timeout=2)    # per-request override
except DeadlineExceededError as e:       # also a TimeoutError and an AllKeysExhaustedError
    print("gave up:", e.last_response or e.last_exception)
```

- Each attempt's timeout is clipped to the remaining budget.
- The rotator never starts a wait it cannot finish (e.g. `Retry-After: 30` with 2s left
  fails immediately instead of sleeping).
- `FallbackRouter` does **not** try the next provider after a deadline error.

## Circuit breaker

When a host is down, every request would otherwise spend all its retries (and time)
on it. The breaker counts consecutive failures (`5xx` and network errors) **per host**:

```
CLOSED --(N failures)--> OPEN --(recovery_timeout)--> HALF_OPEN --(probe ok)--> CLOSED
                           ^                              |
                           +-------(probe failed)---------+
```

```python
from apikeyrotator import APIKeyRotator, CircuitBreakerConfig, CircuitOpenError

rotator = APIKeyRotator(
    api_keys=keys,
    circuit_breaker=CircuitBreakerConfig(failure_threshold=5, recovery_timeout=30),
    # or simply circuit_breaker=True for these defaults
)

try:
    rotator.get("https://api.example.com/v1/items")
except CircuitOpenError as e:
    print(f"{e.host} is down, retry in {e.retry_after:.0f}s")

print(rotator.get_circuit_states())   # {'api.example.com': 'OPEN'}
```

- `4xx` and `429` mean "the host is alive" and do not trip the breaker.
- In HALF_OPEN only `half_open_max_calls` probes (default 1) are let through.
- `CircuitOpenError` is an `AllKeysExhaustedError`, so `FallbackRouter` switches to the
  next provider immediately.

Benchmark (`resilience_host_down*`): with the host answering 503 to everything, the breaker
cuts upstream calls from **3 per request to 0.01** and waiting from **3154 s to 13 s per
1000 requests**.

## Client-side rate limits

### From response headers (default on)

When a response says `X-RateLimit-Remaining: 0` (or `RateLimit-Remaining`), the key is
parked until `X-RateLimit-Reset` - the next request goes to another key instead of
getting a `429`. Disable with `respect_rate_limit_headers=False`.

### Token bucket per key

If you know each key's quota, enforce it before the server does:

```python
# 60 requests per minute per key; keys over budget are skipped,
# the rotator waits only when every key is out of tokens
rotator = APIKeyRotator(api_keys=keys, key_rate_limit=(60, 60))
```

Benchmark (`resilience_quota_*`, 10 keys x 10 req/min): reacting only to 429 costs 1.09
upstream calls per request; header hints bring it to **1.01**, the token bucket to **1.00 - no 429s at all**.

## Shared state between processes (Redis)

Several workers/containers using the same keys should know when one of them hit a rate
limit or got a key rejected:

```python
from apikeyrotator import APIKeyRotator, RedisStateBackend

backend = RedisStateBackend(url="redis://redis:6379/0", namespace="openai")
rotator = APIKeyRotator(
    api_keys=keys,
    state_backend=backend,
    state_sync_interval=1.0,     # pull shared state at most once per second
    key_rate_limit=(60, 60),     # token buckets are shared too - the limit is global
)
```

Shared: rate-limited keys (until when), keys rejected with 401/403, token buckets
(atomic Lua script using the Redis server clock).

- **Raw keys never reach Redis** - only `sha256(key)` (or HMAC with `salt=b"..."`).
- **Fail-open**: if Redis is unavailable, requests continue with local state; a warning
  is logged at most every 30s.
- Async rotators run Redis calls in a worker thread, so the event loop is never blocked.
- `InMemoryStateBackend()` shares state between rotators in one process.

Install: `pip install "apikeyrotator[redis]"`.

## Background key refresh

```python
from apikeyrotator import APIKeyRotator, AWSSecretsManagerProvider

rotator = APIKeyRotator(
    secret_provider=AWSSecretsManagerProvider(secret_name="prod/api-keys"),
    auto_refresh_interval=300,   # reload every 5 minutes
)
...
rotator.close()                  # stops the refresh thread
```

- Sync rotators use a daemon thread, async rotators an asyncio task (started on first use /
  `async with`). Both stop in `close()`.
- Metrics of keys that stay are preserved; keys rejected with 401/403 are not re-added.
- Manual refresh: `rotator.refresh_keys_from_provider_sync()` / `await rotator.refresh_keys_from_provider()`.

## HTTP backends and HTTP/2

| Rotator | Default | Alternative |
|---|---|---|
| `APIKeyRotator` | `requests` | `http_backend="httpx"` |
| `AsyncAPIKeyRotator` | `aiohttp` | `http_backend="httpx"` |

```python
rotator = AsyncAPIKeyRotator(api_keys=keys, http_backend="httpx", http2=True)
response = await rotator.get(url)      # httpx.Response
data = response.json()
```

- The returned response is the backend's native object (`requests.Response`,
  `aiohttp.ClientResponse` or `httpx.Response`).
- Client-level settings (TLS verification, certificates, custom transports) go into
  `http_client_kwargs={...}`.
- HTTP libraries are imported lazily: `import apikeyrotator` does not load aiohttp,
  requests or httpx until a rotator using them is created.

Install: `pip install "apikeyrotator[httpx]"`.

## Logging

The library logs through the standard `logging` module but, like any library, does
**not** configure output (a `NullHandler` is attached to the `apikeyrotator` logger).
To see messages:

```python
import logging
logging.basicConfig(level=logging.INFO)          # everything
logging.getLogger("apikeyrotator").setLevel(logging.WARNING)  # only problems
```
