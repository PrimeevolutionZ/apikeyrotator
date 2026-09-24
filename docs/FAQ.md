# Frequently Asked Questions (FAQ)

## Table of Contents

- [General Questions](#general-questions)
- [Installation & Setup](#installation--setup)
- [Usage Questions](#usage-questions)
- [Error Handling](#error-handling)
- [Performance](#performance)
- [Advanced Topics](#advanced-topics)

---

## General Questions

### What is APIKeyRotator?

A Python library that spreads requests over several API keys and handles the
failure modes of real APIs for you: rate limits, invalid keys, server errors,
network problems and dead hosts. It works with `requests`, `aiohttp` or `httpx`.

### Why do I need it?

- You have several API keys and want to use them all without hand-written rotation.
- You want 429s, 5xx and timeouts handled consistently (backoff, key switching, deadlines).
- Several processes share the same keys and must respect the same limits (Redis).
- You want a resilient client without boilerplate: circuit breaker, provider fallback,
  caching, metrics.

### Is it free?

Yes, it is open source under the MIT License.

### What Python versions are supported?

Python 3.12 and newer (since 0.8.0). Use apikeyrotator 0.7.x for older Pythons.

---

## Installation & Setup

### How do I install it?

```bash
pip install apikeyrotator
```

### Do I need to install requests or aiohttp separately?

No. `requests`, `aiohttp`, `python-dotenv` and `PyYAML` are regular dependencies.
Optional extras:

```bash
pip install "apikeyrotator[httpx]"   # httpx backend, HTTP/2
pip install "apikeyrotator[redis]"   # shared state between processes
pip install "apikeyrotator[aws]"     # AWS Secrets Manager
pip install "apikeyrotator[gcp]"     # GCP Secret Manager
```

HTTP libraries are imported lazily, so a sync-only application never loads aiohttp.

### How do I set up my API keys?

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])   # directly
rotator = APIKeyRotator(api_keys="key1,key2,key3")           # comma-separated string
rotator = APIKeyRotator()                                    # API_KEYS env variable
rotator = APIKeyRotator(load_env_file=True)                  # ...after loading ./.env
rotator = APIKeyRotator(env_var="MY_CUSTOM_KEYS")            # another variable
```

Or load them from a secret store with `secret_provider=` (AWS, GCP, file, env) and
keep them fresh with `auto_refresh_interval=`. Duplicates and blank entries are
removed automatically.

---

## Usage Questions

### How does key rotation work?

Every attempt asks the rotation strategy for a key. With the default round-robin
strategy consecutive requests use `key1 → key2 → key3 → key1 ...`. Keys that are
not usable are skipped:

- **429** - the key is parked until `Retry-After` / `X-RateLimit-Reset`;
- **`X-RateLimit-Remaining: 0`** - parked until the reset, before a 429 even happens;
- **401 / 403** - the key is removed from the rotation;
- **repeated failures** - the key becomes unhealthy and gets a probe request after
  `recovery_timeout` (60 s).

### Can I control which key is used?

Choose a strategy:

```python
from apikeyrotator import APIKeyRotator

# Primary key first, others only as backups
APIKeyRotator(api_keys=["primary", "backup"], rotation_strategy="failover")

# key2 gets 5x more traffic than key1
APIKeyRotator(api_keys=["key1", "key2"], rotation_strategy="weighted",
              rotation_strategy_kwargs={"weights": {"key1": 1, "key2": 5}})
```

Also available: `"random"`, `"lru"`, `"health_based"` or your own subclass of
`BaseRotationStrategy`. See [Advanced Usage](ADVANCED_USAGE.md#rotation-strategies).

### How many retries does it attempt?

`max_retries` (default 3) is the number of **attempts per request**, across all
keys. Switching away from a key rejected with 401/403 does not use up an attempt.
Waits between attempts grow exponentially from `base_delay` (1 s) and are capped
by `max_delay` (60 s). To bound the total time, set `total_timeout`:

```python
rotator = APIKeyRotator(api_keys=["key1", "key2"], max_retries=5, total_timeout=30)
```

### What happens when all attempts fail?

`AllKeysExhaustedError` is raised; `e.last_response` / `e.last_exception` tell you why:

```python
from apikeyrotator import AllKeysExhaustedError

try:
    response = rotator.get(url)
except AllKeysExhaustedError as e:
    print("Failed:", e.last_response or e.last_exception)
```

Its subclasses `DeadlineExceededError` (time budget spent) and `CircuitOpenError`
(host considered down) are caught by the same `except`.

### Are POST requests retried?

Only when retrying is safe: after `429`, `503`, `408`, `425`, connection failures
or a rejected key. After `500`/`502`/`504` or a read timeout the server may already
have executed the request, so the response is returned (or the exception
re-raised). Send an `Idempotency-Key` header (or set `auto_idempotency_key=True`) if
the API de-duplicates requests; such retries reuse the same API key. `GET`, `PUT`,
`DELETE` are always retried.

### Is it safe for payments, orders and webhooks?

Yes - it is built for any API, not only LLMs. A `POST`/`PATCH` is never repeated after
a failure where it may have been executed, not by retries, not by
`should_retry_callback`, not by `FallbackRouter`. With idempotency keys the retries
become safe, keep the same API key, and a final error tells you whether the operation
may have happened (`AllKeysExhaustedError.possibly_processed`). Details:
[Payments, orders and other side effects](RESILIENCE.md#payments-orders-and-other-side-effects).

### Can I get the same response object from requests, httpx and aiohttp?

Yes: `unified_response=True`. Every rotator and backend then returns a
`UnifiedResponse` (`status_code`, case-insensitive `headers`, `content`, `text`,
`json()`, `ok`, `raise_for_status()`, the client's own object as `native`), with the
body already read - so async code calls `response.json()` without `await`:

```python
from apikeyrotator import AsyncAPIKeyRotator

async def fetch():
    async with AsyncAPIKeyRotator(api_keys=["key1"], http_backend="httpx", unified_response=True) as r:
        return (await r.get("https://api.example.com/data")).json()
```

### Can I use it with any API?

Yes. Say how the API expects the key with `auth=` - `"bearer"`, `"x-api-key"` or
any `(header, template)`:

```python
rotator = APIKeyRotator(api_keys=["key1"], auth=("Authorization", "Token {key}"))
```

Without `auth=`, 32-character keys go in `X-API-Key` and everything else in
`Authorization: Bearer <key>`. Headers that need more than the key (several headers,
signatures) come from `header_callback`.

### How do I make POST/PUT/PATCH/DELETE requests?

Same interface as `requests`: `rotator.post(url, json=...)`, `put`, `patch`,
`delete`, `head`, or `rotator.request("OPTIONS", url)`. All keyword arguments
(`params`, `json`, `data`, `headers`, `timeout`, `stream`...) are passed to the
HTTP client.

### Can I pass custom headers?

```python
response = rotator.get(url, headers={"X-Custom-Header": "value"})
```

For headers that depend on the key, use `header_callback` (it may return
`headers` or `(headers, cookies)`).

---

## Error Handling

### What does the rotator handle automatically?

| Situation | Behaviour |
|---|---|
| 429 | next key immediately; waits only if every key is limited |
| 5xx, network errors | exponential backoff |
| 401 / 403 | key removed, next key |
| other 4xx (404, 400, 422...) | response returned to you, no retry |
| host keeps failing (with `circuit_breaker=True`) | fail fast with `CircuitOpenError` |

### Why do I get a 404 response instead of an exception?

Because retrying a wrong URL or a malformed request can't succeed. Client errors
are returned like with plain `requests`; call `response.raise_for_status()` if you
want an exception.

### Why are my requests failing immediately?

1. **Wrong auth header** - every key gets 401/403 before anything succeeded: you get an
   `AuthenticationError` showing the header that was sent; set `auth=`. The keys are kept.
2. **Invalid keys** - after requests have succeeded, keys answering 401/403 are removed
   (`rotator.key_count`); when none are left you get `AllKeysExhaustedError`.
3. **Wrong URL / parameters** - 4xx responses are returned without retries.
4. **Open circuit** - the host failed repeatedly (`rotator.get_circuit_states()`).

Turn on logging to see what happens:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### How do I customise retry logic?

- Treat more statuses as temporary: `ErrorClassifier(custom_retryable_codes=[420])`.
- Retry "successful" responses with an error in the body: `should_retry_callback`.
- Change the rules completely: subclass `ErrorClassifier` ([Error Handling](ERROR_HANDLING.md#custom-error-handling)).

```python
def retry_on_soft_error(response) -> bool:
    try:
        return response.json().get("status") == "try_again"
    except ValueError:
        return False

rotator = APIKeyRotator(api_keys=["key1"], should_retry_callback=retry_on_soft_error)
```

---

## Performance

### Is it fast?

The rotator adds about **10 µs of CPU per request** and ~1 µs to select a key
(even with 1000 keys); it uses ~230 bytes of memory per key and doesn't grow under
sustained load. Importing the library takes ~70 ms. Numbers and methodology:
[benchmarks](../benchmarks/README.md). Your throughput is limited by the API and the
network, not by the rotator.

### Should I use sync or async?

- **`APIKeyRotator`** (sync): scripts, sequential work, sync web frameworks. It is
  thread-safe - share one instance between threads.
- **`AsyncAPIKeyRotator`**: many concurrent requests, asyncio applications.

```python
# Sequential: total time ≈ sum of latencies
for i in range(100):
    rotator.get(url)

# Concurrent: total time ≈ a few latencies
responses = await asyncio.gather(*(async_rotator.get(url) for _ in range(100)))
```

### How many requests per second can I make?

As many as your keys' rate limits allow. To use them fully:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    key_rate_limit=(60, 60),   # match the provider's per-key quota - no 429s
    random_delay_range=None,
    timeout=5.0,
)
```

### Does it cache responses?

Not by default. Add `CachingMiddleware`:

```python
from apikeyrotator import APIKeyRotator, CachingMiddleware

rotator = APIKeyRotator(api_keys=["key1"], middlewares=[CachingMiddleware(ttl=300)])
```

---

## Advanced Topics

### Can I use proxies?

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    proxy_list=["http://user:pass@proxy1.com:8080", "http://user:pass@proxy2.com:8080"],
)
```

Each attempt uses the next proxy.

### How do I rotate User-Agents?

`user_agents=[...]` - each request gets the next one unless it sets `User-Agent` itself.

### Can I add delays between requests?

`random_delay_range=(1.0, 3.0)` waits a random 1-3 s (+ up to 10% jitter) before
each attempt.

### How do I use custom error classification?

```python
from apikeyrotator import APIKeyRotator, ErrorClassifier, ErrorType

class MyErrorClassifier(ErrorClassifier):
    def classify_error(self, response=None, exception=None):
        # "is not None": error responses of requests are falsy
        if response is not None and response.status_code == 418:
            return ErrorType.TEMPORARY
        return super().classify_error(response, exception)

rotator = APIKeyRotator(api_keys=["key1"], error_classifier=MyErrorClassifier())
```

### Can I use it in a multithreaded application?

Yes - **share one rotator** between threads. It is thread-safe, and sharing means
all threads see the same key health, rate limits and connection pool:

```python
from concurrent.futures import ThreadPoolExecutor
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"], pool_size=32)

def fetch(i: int) -> dict:
    return rotator.get(f"https://api.example.com/items/{i}").json()

with ThreadPoolExecutor(max_workers=16) as executor:
    results = list(executor.map(fetch, range(100)))
```

For several **processes** or machines, add `state_backend=RedisStateBackend(...)`
so they share limits and rejected keys ([Resilience](RESILIENCE.md)).

### Can I switch to another API provider when one fails?

Yes, with `FallbackRouter`:

```python
from apikeyrotator import APIKeyRotator, FallbackRouter, ProviderRoute

router = FallbackRouter([
    ProviderRoute(APIKeyRotator(api_keys=["a1", "a2"]), name="provider-a"),
    ProviderRoute(APIKeyRotator(api_keys=["b1"]), name="provider-b",
                  request_transformer=lambda m, u, kw: (m, u.replace("api.a.com", "api.b.com"), kw)),
])
response = router.get("https://api.a.com/v1/data")
```

### Does the rotator read .env files?

Only with `load_env_file=True` (needs `python-dotenv`): then the `.env` of the working
directory is loaded into `os.environ` before keys are read. By default the library
reads no files and doesn't change the environment.

### What is the configuration file for?

`config_file` is only **read** (never written), and only when you pass one. With
`save_sensitive_headers=True` its `successful_headers` section adds extra headers
per domain (auth headers in it are ignored).

### How do I enable debug logging?

```python
import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")
```

Keys are masked in logs (`key1****`). The library itself never prints anything
until logging is configured.

### Can I use it with GraphQL APIs?

Yes - GraphQL queries are POSTs. Since queries are read-only, allow retrying them:

```python
rotator = APIKeyRotator(api_keys=["key1"], retry_non_idempotent=True)
response = rotator.post(
    "https://api.example.com/graphql",
    json={"query": "query($id: ID!) { user(id: $id) { name } }", "variables": {"id": "123"}},
)
data = response.json()["data"]
```

### Is it compatible with requests-mock / respx for testing?

Yes. `requests-mock` works with the default sync backend; for the httpx backend
pass a mock transport: `http_client_kwargs={"transport": httpx.MockTransport(handler)}`.

```python
import requests_mock
from apikeyrotator import APIKeyRotator

def test_api_call():
    with requests_mock.Mocker() as m:
        m.get("https://api.example.com/data", json={"result": "success"})
        rotator = APIKeyRotator(api_keys=["test_key"])
        assert rotator.get("https://api.example.com/data").json() == {"result": "success"}
```

### How do I contribute?

See [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Still have questions?

- [Documentation Index](INDEX.md)
- [API Reference](API_REFERENCE.md)
- [Examples](EXAMPLES.md)
- [GitHub Issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues)
