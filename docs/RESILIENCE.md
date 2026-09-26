# Resilience & Scaling (0.8.0)

Features for running the rotator under load and across many processes.
All of them are opt-in or safe by default; the table shows the defaults.

| Feature | Parameter | Default |
|---|---|---|
| Safe retries of non-idempotent requests | `retry_non_idempotent`, `auto_idempotency_key` | `False` (safe) |
| Total time budget per request | `total_timeout` | `None` (no limit) |
| Per-host circuit breaker | `circuit_breaker` | off |
| Client-side key rate limit (token bucket) | `key_rate_limit` | off |
| Skip keys reporting `X-RateLimit-Remaining: 0` | `respect_rate_limit_headers` | `True` |
| Shared state between processes (Redis) | `state_backend` | local only |
| Background key refresh | `auto_refresh_interval` | off |
| HTTP backend / HTTP/2 | `http_backend`, `http2` | `requests` / `aiohttp` |

---

## Payments, orders and other side effects

The rotator is used for any HTTP API with keys - LLMs, but also payments, orders,
messaging, user management, webhooks. Retrying a request the server may already have
executed would repeat the operation (charge twice, send twice), so the rotator
distinguishes **idempotent** methods (`GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE`,
`TRACE`) from the rest (`POST`, `PATCH`).

**Guarantee: a `POST`/`PATCH` is repeated only when the server certainly did not
execute it** - unless you explicitly mark the request as idempotent.

| Outcome of a `POST` / `PATCH` | Default | With an `Idempotency-Key` |
|---|---|---|
| `429`, `503`, `408`, `425` (not processed) | retried, any key | retried, any key |
| `401` / `403` (key rejected) | retried with another key | retried with another key |
| connection refused / connect timeout (never sent) | retried | retried |
| `500`, `502`, `504`, other 5xx (maybe executed) | **returned to you** | retried **with the same key** |
| read timeout / connection dropped (maybe executed) | **exception re-raised** | retried **with the same key** |
| `should_retry_callback` returns `True` (executed) | **not retried**, response returned | retried with the same key |
| `FallbackRouter`, provider failed | next provider only if nothing was executed | same - **never** sent to another provider after a maybe-executed attempt |

Why the same key: idempotency keys are usually scoped to the account behind the API
key (Stripe works this way). A retry with a key of another account would not be
recognised as a repeat and could execute the operation again.

Make retries safe for APIs that support idempotency keys (Stripe, Adyen and most
payment APIs):

```python
import uuid
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2"])

# Per request: one key for the logical operation (store it with your order to retry later)
rotator.post("https://api.example.com/v1/charges", json={"amount": 1000},
             headers={"Idempotency-Key": f"order-{uuid.uuid4()}"})

# Or automatically: an Idempotency-Key is generated for every POST/PATCH without one,
# identical on all retries of that request
rotator = APIKeyRotator(api_keys=["key1", "key2"], auto_idempotency_key=True)
rotator = APIKeyRotator(api_keys=["key1", "key2"], auto_idempotency_key="X-Request-Id")  # other header
```

Only use `auto_idempotency_key` / `retry_non_idempotent=True` if the API really
de-duplicates requests - sending the header to an API that ignores it does not make
retries safe.

When a maybe-executed request finally fails, the exception says so:

```python
from apikeyrotator import AllKeysExhaustedError

try:
    rotator.post("https://api.example.com/v1/charges", json={"amount": 1000},
                 headers={"Idempotency-Key": "order-42"})
except AllKeysExhaustedError as e:
    if e.possibly_processed:
        ...   # check the charge's status before trying again
    else:
        ...   # nothing was executed - safe to retry later
```

Also keep in mind:

- `retry_non_idempotent=True` treats every POST as idempotent - prefer idempotency keys.
- Set `total_timeout` for user-facing payments, so a request doesn't keep retrying.
- Keys used for payments should belong to the same account (see "Why the same key").

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
- Breakers are per `host[:port]` of the URL: a dead host doesn't affect requests to other
  hosts (note that `localhost` and `127.0.0.1` are different hosts).
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

**Consistency model:**

| State | Consistency | Delay until other processes see it |
|---|---|---|
| Token buckets (`key_rate_limit`) | strong - every token is taken in Redis atomically, so the limit is global across all processes | none |
| Rate-limited keys (429, `X-RateLimit-Remaining: 0`) | eventual | up to `state_sync_interval` (default 1 s) + one Redis round trip |
| Rejected keys (401/403) | eventual; the ban expires after `invalid_ttl` (default 1 day) | same |

All deadlines (parked-until times, bans, token buckets) are computed on the Redis server
clock, so machines with different clocks park a key for the same time. The process
that got a 401/403 itself never uses that key again until restarted; other processes
follow the ban while it is in Redis.

During that delay another process may still send a request with a key that was just
limited or revoked; it gets the same 429/401 and handles it locally. Lower
`state_sync_interval` for faster propagation (each sync is one Redis call per request at
most once per interval). Verified with 4 processes against a real Redis: a shared
`key_rate_limit=(20, 60)` on 2 keys let exactly 40 requests through.

- **Raw keys never reach Redis** - only `sha256(key)` (or HMAC with `salt=b"..."`).
- **Fail-open**: if Redis is unavailable, requests continue with local state; a warning
  is logged at most every 30s. Redis is then left alone for 5 s (one timeout per 5 s, not
  per request; clients created from `url=` use a 1 s `socket_timeout`), and `key_rate_limit`
  is enforced per process by local token buckets meanwhile. Real output of an outage and of
  4 processes sharing a limit: [Behavior Under Load](BEHAVIOR.md#5-several-processes-sharing-keys-redis).
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
