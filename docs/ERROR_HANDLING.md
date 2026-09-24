# Error Handling

How APIKeyRotator reacts to failures, which exceptions reach your code, and how
to customise the behaviour.

## Table of Contents

- [What the Rotator Does Automatically](#what-the-rotator-does-automatically)
- [Exceptions](#exceptions)
- [Handling Specific Situations](#handling-specific-situations)
- [Custom Error Handling](#custom-error-handling)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## What the Rotator Does Automatically

Every response or exception is classified by `ErrorClassifier` into an `ErrorType`:

| `ErrorType` | Typical cause | Rotator action |
|---|---|---|
| `RATE_LIMIT` | `429` | Park the key until `Retry-After` / `X-RateLimit-Reset`, retry **immediately** with another key; wait only if all keys are parked |
| `TEMPORARY` | `5xx`, `408`, `409`, `425`, `511` | Retry with exponential backoff (`Retry-After` honoured) |
| `PERMANENT` | `401`, `403` | Remove the key from rotation, retry with another key (before the first accepted request: keep it, try the others, raise `AuthenticationError` if all are rejected) |
| `PERMANENT` | other `4xx` (`400`, `404`, `422`...) | Return the response - the request itself is wrong, retrying won't help |
| `NETWORK` | connection errors, timeouts | Retry with backoff |
| `UNKNOWN` | `2xx`/`3xx` | Return the response |

```
response / exception
        │
   classify_error()
        │
 ┌──────┼─────────────┬──────────────────┬──────────────┐
429    5xx/network   401/403            other 4xx      2xx
 │      │             │                  │              │
park   backoff       remove key         return         return
key    + retry       + retry            response       response
+ next key
```

**Non-idempotent requests.** `POST` and `PATCH` are not retried after errors
where the server may already have executed them (`500`, `502`, `504`, read
timeouts, dropped connections): the response is returned or the HTTP client's
exception is re-raised. They are still retried after `429`, `503`, `408`, `425`,
connection failures and `401`/`403`. Send an `Idempotency-Key` header or set
`retry_non_idempotent=True` to allow all retries.

**Budget.** At most `max_retries` attempts (default 3) per request; each wait is
capped by `max_delay` (60 s); `total_timeout` limits the whole request.

---

## Exceptions

```
APIKeyError
├── NoAPIKeysError
├── AllKeysExhaustedError          .last_response  .last_exception
│   ├── DeadlineExceededError      (also TimeoutError)
│   ├── CircuitOpenError           .host  .retry_after
│   └── AuthenticationError        .statuses  .auth_header
├── AllProvidersExhaustedError
└── HTTPStatusError                .status_code
```

### NoAPIKeysError

No keys were given and none were found (`api_keys`, `secret_provider`, the
`API_KEYS` environment variable; `.env` only with `load_env_file=True`).

```python
from apikeyrotator import APIKeyRotator, NoAPIKeysError

try:
    rotator = APIKeyRotator()
except NoAPIKeysError as e:
    print(f"No API keys available: {e}")
```

### AllKeysExhaustedError

The request failed: all attempts were used, or every key was rejected.

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(api_keys=["key1", "key2"], max_retries=3)

try:
    response = rotator.get("https://api.example.com/data")
except AllKeysExhaustedError as e:
    if e.last_response is not None:
        print("Last status:", e.last_response.status_code)   # .status for aiohttp
    elif e.last_exception is not None:
        print("Last network error:", repr(e.last_exception))
    print("Keys still in rotation:", rotator.key_count)
```

Typical causes: every key rate-limited for longer than the retries last; all keys
rejected with 401/403 (`rotator.key_count == 0`); the API returning 5xx; the
network failing. For async rotators `last_response` has already been released
(status and headers are available; the body was read only if middlewares are used).

### DeadlineExceededError

Raised when `total_timeout` is spent. It is both an `AllKeysExhaustedError` and a
`TimeoutError`. `FallbackRouter` does **not** try other providers after it.

```python
from apikeyrotator import APIKeyRotator, DeadlineExceededError

rotator = APIKeyRotator(api_keys=["key1", "key2"], total_timeout=10)

try:
    response = rotator.get("https://api.example.com/report", total_timeout=3)
except DeadlineExceededError:
    print("Gave up after 3 seconds")
```

### CircuitOpenError

With `circuit_breaker=True`, raised without a network call while the target host
is considered down.

```python
from apikeyrotator import APIKeyRotator, CircuitOpenError

rotator = APIKeyRotator(api_keys=["key1"], circuit_breaker=True)

try:
    rotator.get("https://api.example.com/data")
except CircuitOpenError as e:
    print(f"{e.host} is down; next probe in {e.retry_after:.0f}s")
```

### AuthenticationError

Every key was rejected with `401`/`403` and no request has succeeded yet. That is
almost always a wrong auth header, so the rotator keeps the keys (and doesn't mark
them invalid in shared state) and tells you what it sent:

```python
from apikeyrotator import APIKeyRotator, AuthenticationError

rotator = APIKeyRotator(api_keys=["key1", "key2"])

try:
    rotator.get("https://api.example.com/data")
except AuthenticationError as e:
    print(e.auth_header)   # 'Authorization: Bearer key1****'
    print(e.statuses)      # {'key1****': 401, 'key2****': 401}
    # fix: APIKeyRotator(..., auth="x-api-key") or auth=("Authorization", "Token {key}")
```

It is an `AllKeysExhaustedError`, so existing handlers keep working.

### Exceptions of the HTTP client

A `POST`/`PATCH` that fails after the request may have been sent (e.g. a read
timeout) re-raises the client's own exception - `requests.exceptions.ReadTimeout`,
`aiohttp.ServerDisconnectedError`, `httpx.ReadTimeout`, ... - because retrying
could execute it twice.

---

## Handling Specific Situations

### All keys rate-limited

The rotator already waits for the earliest key to free up (bounded by `max_delay`)
as long as attempts remain. If that is not enough, prevent the limits instead of
reacting to them:

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    key_rate_limit=(60, 60),   # never exceed 60 requests/minute per key
    max_retries=5,
)
```

Header hints (`X-RateLimit-Remaining: 0`) are honoured by default. With several
processes, share limits via `state_backend=RedisStateBackend(...)` - see
[Resilience](RESILIENCE.md).

### Invalid or expired keys

Once requests have succeeded (so the auth header is known to be right), keys
answering `401`/`403` are removed automatically. When all are gone:

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError, AWSSecretsManagerProvider

rotator = APIKeyRotator(secret_provider=AWSSecretsManagerProvider(secret_name="prod/api-keys"))

try:
    response = rotator.get("https://api.example.com/protected")
except AllKeysExhaustedError:
    if rotator.key_count == 0:
        rotator.refresh_keys_from_provider_sync()   # pulls new keys; rejected ones are not re-added
        response = rotator.get("https://api.example.com/protected")
    else:
        raise
```

Use `auto_refresh_interval=` to refresh keys in the background.

### Server errors (5xx)

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=5,
    base_delay=2.0,          # 2s, 4s, 8s, 16s between attempts (capped by max_delay)
    total_timeout=60,
    circuit_breaker=True,    # stop hammering the host after repeated failures
)

try:
    response = rotator.get("https://api.example.com/data")
except AllKeysExhaustedError as e:
    status = getattr(e.last_response, "status_code", None)
    if status is not None and status >= 500:
        print("API is having problems:", status)
```

### Network problems

Network errors are retried inside the rotator; after the last attempt you get
`AllKeysExhaustedError` with the original error in `last_exception`:

```python
import requests
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(api_keys=["key1", "key2"], timeout=30.0)

try:
    response = rotator.get("https://api.example.com/data")
except AllKeysExhaustedError as e:
    if isinstance(e.last_exception, requests.exceptions.Timeout):
        print("The API is too slow")
    elif isinstance(e.last_exception, requests.exceptions.ConnectionError):
        print("Cannot connect")
```

### Client errors (4xx)

`400`, `404`, `422` and similar are returned as normal responses (no exception, no
retry, the key is kept). Check them as you would with plain requests:

```python
response = rotator.get("https://api.example.com/users/123")
if response.status_code == 404:
    print("No such user")
response.raise_for_status()   # raise for other errors
```

---

## Custom Error Handling

### Custom Error Classifier

```python
from apikeyrotator import APIKeyRotator, ErrorClassifier, ErrorType

class MyApiClassifier(ErrorClassifier):
    """Some APIs signal errors inside a 200 JSON body."""

    def classify_error(self, response=None, exception=None) -> ErrorType:
        # "is not None": error responses of requests are falsy
        if response is not None and response.status_code == 200 and hasattr(response, "json"):
            try:
                code = response.json().get("error", {}).get("code")
            except (ValueError, AttributeError):
                code = None
            if code in ("QUOTA_EXCEEDED", "TOO_MANY_REQUESTS"):
                return ErrorType.RATE_LIMIT
            if code in ("SERVICE_UNAVAILABLE", "MAINTENANCE"):
                return ErrorType.TEMPORARY
        return super().classify_error(response, exception)

    def should_remove_key(self, response=None, exception=None) -> bool:
        # Also drop keys on 402 Payment Required
        return response is not None and response.status_code in (401, 402, 403)

rotator = APIKeyRotator(api_keys=["key1", "key2"], error_classifier=MyApiClassifier())
```

Don't classify a successful response as `RATE_LIMIT` just because it reports
`X-RateLimit-Remaining: 0` - the rotator already parks such keys and returns the
response. Async rotators pass an object with only `status_code` and `headers`, so
body-based rules apply to the sync rotator.

### Retrying on response content

`should_retry_callback` is called for responses the rotator would return
(`2xx`/`3xx`); 429/5xx/401/403 are handled before it:

```python
import requests
from apikeyrotator import APIKeyRotator

def retry_on_soft_error(response: requests.Response) -> bool:
    try:
        return bool(response.json().get("error", {}).get("retryable"))
    except ValueError:
        return False

rotator = APIKeyRotator(api_keys=["key1", "key2"], should_retry_callback=retry_on_soft_error)
```

Async rotators pass the status code (`int`) instead of the response.

### Graceful Degradation

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

class ResilientAPIClient:
    def __init__(self, api_keys: list[str]):
        self.rotator = APIKeyRotator(api_keys=api_keys, total_timeout=10, circuit_breaker=True)
        self.cache: dict[str, dict] = {}

    def get_data(self, endpoint: str) -> dict:
        try:
            data = self.rotator.get(f"https://api.example.com{endpoint}").json()
            self.cache[endpoint] = data
            return data
        except AllKeysExhaustedError:        # includes deadline and open circuit
            if endpoint in self.cache:
                return self.cache[endpoint]  # stale but useful
            return {"status": "unavailable", "data": []}
```

For switching between API providers use `FallbackRouter`
([Advanced Usage](ADVANCED_USAGE.md), [API Reference](API_REFERENCE.md#multi-provider-routing)).

---

## Best Practices

### 1. Handle specific exceptions

```python
from apikeyrotator import APIKeyRotator, NoAPIKeysError, AllKeysExhaustedError, DeadlineExceededError

try:
    rotator = APIKeyRotator()
    response = rotator.get("https://api.example.com/data")
except NoAPIKeysError:
    ...  # configuration problem
except DeadlineExceededError:
    ...  # too slow - maybe retry later
except AllKeysExhaustedError as e:
    ...  # inspect e.last_response / e.last_exception
```

### 2. Log errors - never the keys

```python
import logging
from apikeyrotator import AllKeysExhaustedError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

try:
    response = rotator.get(url)
except AllKeysExhaustedError as e:
    log.error("Request to %s failed: %s", url, e)
    log.error("Key pool: %s", rotator.export_config()["key_statistics"])   # keys are masked
```

Don't log `rotator.keys` - it contains the raw keys.

### 3. Use the built-in circuit breaker

```python
from apikeyrotator import APIKeyRotator, CircuitBreakerConfig

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    circuit_breaker=CircuitBreakerConfig(failure_threshold=5, recovery_timeout=30),
)
```

### 4. Bound latency

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    timeout=10.0,        # per attempt
    total_timeout=30.0,  # whole request, including retries and waits
    max_retries=3,
)
```

---

## Troubleshooting

### Nothing is logged

The library attaches only a `NullHandler`. Configure logging in your application:

```python
import logging
logging.basicConfig(level=logging.DEBUG)   # DEBUG shows selected keys (masked) and headers via LoggingMiddleware
```

### Requests fail immediately

- `AuthenticationError` → every key got `401`/`403` before anything succeeded: the auth
  header is probably wrong - its message shows what was sent; set `auth=`.
- `401`/`403` for every key after earlier successes → the keys were revoked;
  `rotator.key_count` drops to 0 and `AllKeysExhaustedError` is raised.
- A `404`/`400` is returned without retries → check the URL and parameters.
- `CircuitOpenError` → the host failed repeatedly; see `rotator.get_circuit_states()`.
- To see every header sent, add `LoggingMiddleware()` with `logging.DEBUG` (secrets
  redacted).

### Requests take too long

Retries, backoff and rate-limit waits add up. Set `total_timeout`, lower
`max_retries` / `base_delay`, and check `rotator.get_key_statistics()` for keys
that are constantly rate-limited (`rate_limit_hits`).

### Still getting rate limited

- Are the keys from **different accounts**? Many APIs limit per account, not per key.
- Several processes? Share state with `RedisStateBackend`.
- Enforce the quota client-side with `key_rate_limit=(requests, seconds)`.
- Inspect the headers: `response.headers.get("X-RateLimit-Remaining")`.

### Memory keeps growing

The rotator's own memory is bounded (metrics are capped, ~230 bytes per key). Check
that you reuse one rotator instead of creating one per request, and close rotators
you no longer need:

```python
with APIKeyRotator(api_keys=["key1"]) as rotator:
    response = rotator.get(url)

async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
    response = await rotator.get(url)
```

With async rotators, read or release every response you get
(`await response.read()` / `response.release()`) so connections return to the pool.

---

## Next Steps

- [Examples](EXAMPLES.md)
- [Advanced Usage](ADVANCED_USAGE.md)
- [Resilience & Scaling](RESILIENCE.md)
- [API Reference](API_REFERENCE.md#exceptions)
- [FAQ](FAQ.md)
