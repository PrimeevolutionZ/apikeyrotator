# API Reference

Complete reference for the public API of **apikeyrotator 0.8** (Python 3.12+).
Everything listed here is importable from the top-level package unless another
module is shown:

```python
from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator, FallbackRouter, RedisStateBackend
```

## Table of Contents

- [Rotators](#rotators)
  - [Constructor parameters](#constructor-parameters)
  - [Grouped settings (config objects)](#grouped-settings-config-objects)
  - [Retry behaviour](#retry-behaviour)
  - [APIKeyRotator](#apikeyrotator)
  - [AsyncAPIKeyRotator](#asyncapikeyrotator)
- [Exceptions](#exceptions)
- [Multi-Provider Routing](#multi-provider-routing)
- [Rotation Strategies](#rotation-strategies)
- [Shared State Backends](#shared-state-backends)
- [Middleware](#middleware)
- [Metrics & Monitoring](#metrics--monitoring)
- [Secret Providers](#secret-providers)
- [Error Classification](#error-classification)
- [Utilities](#utilities)
- [Configuration Loader](#configuration-loader)
- [Key Parsing](#key-parsing)

---

## Rotators

`APIKeyRotator` (sync) and `AsyncAPIKeyRotator` (async) share all constructor
parameters and behaviour; they differ only in the HTTP client and in which
methods are coroutines.

### Constructor parameters

```python signature
APIKeyRotator(
    api_keys=None, env_var="API_KEYS", max_retries=3, base_delay=1.0, timeout=10.0,
    should_retry_callback=None, header_callback=None, user_agents=None,
    random_delay_range=None, proxy_list=None, logger=None,
    config_file=None, error_classifier=None,
    config_loader=None, rotation_strategy="round_robin", rotation_strategy_kwargs=None,
    middlewares=None, secret_provider=None, enable_metrics=True,
    save_sensitive_headers=False, max_delay=60.0, pool_size=100, recovery_timeout=None,
    total_timeout=None, retry_non_idempotent=False, circuit_breaker=None,
    key_rate_limit=None, respect_rate_limit_headers=True, state_backend=None,
    state_sync_interval=1.0, auto_refresh_interval=None, auth=None, unified_response=False,
    auto_idempotency_key=False,
    *, retry=None, rate_limits=None, shared_state=None, request=None,
    http_backend="requests", http2=False, http_client_kwargs=None, http=None,
)
```

**Keys & basics**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_keys` | `list[str] \| str \| None` | `None` | Keys as a list or a comma-separated string (pass a list if a key itself contains a comma). If `None`, keys come from `secret_provider`, else from the `env_var` environment variable. Duplicates and blanks are removed. |
| `env_var` | `str` | `"API_KEYS"` | Environment variable with comma-separated keys. |
| `load_env_file` | `bool` | `False` | Load the `.env` file of the working directory (or its parents) into `os.environ` first. Needs `python-dotenv`. Off by default: the library does not change the process environment unless asked. |
| `secret_provider` | `SecretProvider \| None` | `None` | Source of keys (env, file, AWS, GCP...). See [Secret Providers](#secret-providers). |
| `auto_refresh_interval` | `float \| None` | `None` | Reload keys from `secret_provider` every N seconds in the background. Requires `secret_provider`. |
| `rotation_strategy` | `str \| RotationStrategy \| BaseRotationStrategy` | `"round_robin"` | `"round_robin"`, `"random"`, `"weighted"`, `"lru"`, `"health_based"`, `"failover"`, or a strategy instance. |
| `rotation_strategy_kwargs` | `dict \| None` | `None` | Extra strategy arguments. For `"weighted"`: `{"weights": {"key1": 3, "key2": 1}}` (missing keys get `1.0`). For `"health_based"`: `failure_threshold`, `health_check_interval`. |
| `recovery_timeout` | `float \| None` | `None` (strategy default `60`) | Seconds after its last failure when an unhealthy key gets a probe request again. |

**Retries & timeouts** (or `retry=RetryConfig(...)`, except `error_classifier`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_retries` | `int` | `3` | Maximum attempts per request (>= 1). Switching away from a key rejected with 401/403 does not consume an attempt. |
| `base_delay` | `float` | `1.0` | Exponential backoff base: `base_delay * 2 ** attempt` (+ up to 10% jitter). |
| `max_delay` | `float` | `60.0` | Upper bound for any single backoff or rate-limit wait. |
| `timeout` | `float` | `10.0` | Timeout of one attempt, seconds. Overridable per request (`timeout=`). |
| `total_timeout` | `float \| None` | `None` | Time budget of the whole request (all attempts and waits). Overridable per request (`total_timeout=`). Raises `DeadlineExceededError`. |
| `retry_non_idempotent` | `bool` | `False` | Also retry `POST`/`PATCH` after errors where the request may already have been processed. See [Retry behaviour](#retry-behaviour). |
| `auto_idempotency_key` | `bool \| str` | `False` | Add an `Idempotency-Key` (or the given header) to every `POST`/`PATCH` that has none - one value per request, reused on its retries - which makes those retries allowed. Only for APIs that de-duplicate by that header. |
| `should_retry_callback` | `Callable \| None` | `None` | `callback(response) -> bool`, called with the backend's response object (`requests`/`aiohttp`/`httpx`) in both rotators. Return `True` to retry an otherwise successful response. |
| `error_classifier` | `ErrorClassifier \| None` | `None` | Custom classification of statuses/exceptions. |

**Resilience & rate limits** (`key_rate_limit`, `respect_rate_limit_headers` or
`rate_limits=RateLimitConfig(...)`; `state_backend`, `state_sync_interval` or
`shared_state=SharedStateConfig(backend=..., sync_interval=...)`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `circuit_breaker` | `bool \| CircuitBreakerConfig \| None` | `None` | Per-host circuit breaker. `True` = `CircuitBreakerConfig()` defaults. |
| `key_rate_limit` | `tuple[int, float] \| None` | `None` | Client-side token bucket per key: `(requests, per_seconds)`, e.g. `(60, 60)`. |
| `respect_rate_limit_headers` | `bool` | `True` | Park a key whose response says `X-RateLimit-Remaining: 0` until `X-RateLimit-Reset`. |
| `state_backend` | `StateBackend \| None` | `None` | Share rate limits, rejected keys and token buckets between rotators/processes (e.g. `RedisStateBackend`). |
| `state_sync_interval` | `float` | `1.0` | How often (seconds) shared state is pulled from `state_backend`. |

**Requests, headers & HTTP client** (`auth`, `header_callback`, `user_agents`,
`random_delay_range`, `proxy_list` or `request=RequestConfig(...)`; `pool_size`,
`http_backend`, `http2`, `http_client_kwargs` or `http=HTTPConfig(pool_size=..., backend=...,
http2=..., client_kwargs=...)`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `auth` | `str \| tuple[str, str] \| bool \| None` | `None` | How the key is sent. `"bearer"` = `Authorization: Bearer <key>`, `"x-api-key"` = `X-API-Key: <key>`, `(header, template)` e.g. `("Authorization", "Token {key}")` or `("x-goog-api-key", "{key}")`, `False` = no auth header. `None` infers it: `X-API-Key` for 32-character keys, `Bearer` otherwise. |
| `header_callback` | `Callable \| None` | `None` | `callback(key, headers) -> dict` or `-> (headers, cookies)`; its headers are merged into every request. If they contain the key, no auth header is added. |
| `user_agents` | `list[str] \| None` | `None` | User-Agent strings rotated per request (only if the request sets none). |
| `random_delay_range` | `tuple[float, float] \| None` | `None` | Random pause `(min, max)` seconds before each attempt. |
| `proxy_list` | `list[str] \| None` | `None` | Proxy URLs rotated per attempt. |
| `pool_size` | `int` | `100` | Connection pool size. |
| `middlewares` | `list[RotatorMiddleware] \| None` | `None` | Request/response hooks. See [Middleware](#middleware). |
| `enable_metrics` | `bool` | `True` | Collect `RotatorMetrics` (`get_metrics()`). |
| `logger` | `logging.Logger \| None` | `None` | Logger to use (default: `logging.getLogger("apikeyrotator.core.rotator")`, no handler attached). |
| `config_file` / `config_loader` | `str \| None` / `ConfigLoader \| None` | `None` / `None` | JSON/YAML config read at start (used with `save_sensitive_headers`). Nothing is read unless one is given. |
| `save_sensitive_headers` | `bool` | `False` | Apply headers saved in the config (`successful_headers`, auth headers excluded) to requests for the same domain. |
| `http_backend` *(keyword-only)* | `str` | `"requests"` (sync) / `"aiohttp"` (async) | `"httpx"` for either rotator (`pip install apikeyrotator[httpx]`). |
| `http2` *(keyword-only)* | `bool` | `False` | HTTP/2 - httpx backend only. |
| `unified_response` | `bool` | `False` | Return a [`UnifiedResponse`](#unified-responses) - the same object for requests, aiohttp and httpx, sync and async. Writable later. |
| `http_client_kwargs` *(keyword-only)* | `dict \| None` | `None` | Client-level settings: for requests they are set on the `Session` (e.g. `verify`, `cert`); for aiohttp/httpx they are passed to the `ClientSession` / `httpx.Client` constructor (e.g. httpx `transport=`, `verify=`; aiohttp `connector_owner=`, `trust_env=`). |

**Raises** at construction: `NoAPIKeysError` (no keys found), `ValueError` (invalid
parameters, e.g. `max_retries < 1`, `auto_refresh_interval` without `secret_provider`).

**Authorization header.** Set it with `auth=` (see the table). Without it, the rotator
sends `X-API-Key: <key>` for 32-character keys and `Authorization: Bearer <key>` for all
others. Nothing is added when the request or `header_callback` already sets
`Authorization` / `X-API-Key` or a header containing the key.

**A wrong auth header does not destroy the key pool.** Until one request has been
accepted by the API, a `401`/`403` may mean "wrong header format" rather than "bad key":
the rotator then tries the other keys, and if all of them are rejected it raises
`AuthenticationError` with the header it sent - the keys are kept and not reported to a
shared state backend. Once any request succeeds, keys rejected earlier are removed.

### Grouped settings (config objects)

Instead of many flat arguments, each group can be passed as one frozen object - handy
to keep settings in one place and share them between rotators:

```python
from apikeyrotator import (
    APIKeyRotator, HTTPConfig, RateLimitConfig, RedisStateBackend, RequestConfig, RetryConfig,
    SharedStateConfig,
)

retry = RetryConfig(max_retries=5, base_delay=0.5, timeout=10, total_timeout=30)
shared = SharedStateConfig(backend=RedisStateBackend(url="redis://redis:6379/0"), sync_interval=1.0)

openai = APIKeyRotator(
    api_keys=["sk-a", "sk-b"],
    retry=retry,
    rate_limits=RateLimitConfig(key_rate_limit=(60, 60)),
    shared_state=shared,
    request=RequestConfig(auth="bearer"),
    http=HTTPConfig(pool_size=50),
)
maps = APIKeyRotator(api_keys=["m-1"], retry=retry, request=RequestConfig(auth=("X-Goog-Api-Key", "{key}")))
```

| Object | Argument | Fields (same meaning and defaults as the flat arguments) |
|---|---|---|
| `RetryConfig` | `retry=` | `max_retries`, `base_delay`, `max_delay`, `timeout`, `total_timeout`, `retry_non_idempotent`, `auto_idempotency_key`, `should_retry_callback` |
| `RateLimitConfig` | `rate_limits=` | `key_rate_limit`, `respect_rate_limit_headers` |
| `SharedStateConfig` | `shared_state=` | `backend` (= `state_backend`), `sync_interval` (= `state_sync_interval`) |
| `RequestConfig` | `request=` | `auth`, `header_callback`, `user_agents`, `proxy_list`, `random_delay_range` |
| `HTTPConfig` | `http=` | `backend` (= `http_backend`, `None` = the rotator's default), `http2`, `pool_size`, `client_kwargs` (= `http_client_kwargs`) |
| `CircuitBreakerConfig` | `circuit_breaker=` | see [Utilities](#circuitbreakerconfig--circuitbreaker) |

- Flat arguments keep working. Giving one value both ways (`max_retries=5` and
  `retry=RetryConfig(...)`) raises `TypeError` - there is no silent winner.
- The rotator copies the values: `rotator.max_retries = 2` later changes that rotator
  only, never the shared config object.

### Retry behaviour

| Outcome | What the rotator does |
|---|---|
| `2xx` / `3xx` | Returns the response. If it reports `X-RateLimit-Remaining: 0`, the key is parked until the reset. |
| `429` | Parks the key (until `Retry-After` / `X-RateLimit-Reset`, else a backoff interval) and retries **immediately** with another key; waits only if every key is parked (until the earliest frees up, capped by `max_delay`). |
| `401`, `403` | Removes the key from rotation (and from shared state) and retries with another key. Before the first accepted request: keeps the key, tries the others, raises `AuthenticationError` if all are rejected. |
| other `4xx` (`400`, `404`, `422`...) | Returns the response - no retry, the key is kept. |
| `5xx` | Retries with backoff (`Retry-After` honoured). |
| Network error | Retries with backoff. |
| `POST`/`PATCH` + `500`/`502`/`504`, read timeout, dropped connection | **Not retried**: the response is returned / the exception re-raised (the operation may have been executed). Retried if `retry_non_idempotent=True` or an `Idempotency-Key` header is sent. `429`, `503`, `408`, `425` and connection failures are always retried. |
| `POST`/`PATCH` retried after a maybe-executed failure (idempotency key) | Retries use the **same key** (idempotency keys are scoped to the key's account); a final error has `possibly_processed=True` and `FallbackRouter` doesn't send it elsewhere. |
| `should_retry_callback` returns `True` for a `POST`/`PATCH` | Not retried unless the request is idempotent (the server has executed it). |
| All attempts used | Raises `AllKeysExhaustedError` (`last_response` / `last_exception` attached). |
| `total_timeout` spent | Raises `DeadlineExceededError`. |
| Circuit open for the host | Raises `CircuitOpenError` without a network call. |

### APIKeyRotator

Synchronous rotator (default HTTP client: `requests`).

```python
from apikeyrotator import APIKeyRotator

with APIKeyRotator(api_keys=["key1", "key2"], total_timeout=30) as rotator:
    response = rotator.get("https://api.example.com/data", params={"q": "x"})
    print(response.json())
```

| Method / property | Description |
|---|---|
| `request(method, url, **kwargs)` | Sends a request with rotation and retries. `kwargs` are passed to the HTTP client (`params`, `json`, `data`, `headers`, `cookies`, `timeout`, `stream`...) plus `total_timeout`. Returns the client's response (`requests.Response` or `httpx.Response`). |
| `get / post / put / patch / delete / head(url, **kwargs)` | Shortcuts for `request()`. |
| `close()` | Stops background refresh and closes the connection pool. The rotator is also a context manager (`with ... as rotator`). |
| `session` *(property)* | Underlying client (`requests.Session` / `httpx.Client`). |
| `keys` *(property, settable)* | Current key list (copy). Assigning replaces the keys; metrics of kept keys are preserved. |
| `key_count` *(property)* | Number of keys in rotation. |
| `get_next_key()` | Key the strategy would use next (advances the strategy). |
| `get_key_statistics()` | `{key: KeyMetrics.to_dict()}` for every key. |
| `get_metrics()` | Global metrics (see [RotatorMetrics](#rotatormetrics)); `{}` if metrics are disabled. |
| `get_circuit_states()` | `{host: "CLOSED" \| "OPEN" \| "HALF_OPEN"}`. |
| `reset_key_health(key=None)` | Marks one key (or all) healthy again and clears its rate-limit parking. |
| `export_config()` | Settings plus per-key statistics with masked keys (safe to log). |
| `refresh_keys_from_provider_sync()` | Reloads keys from `secret_provider` now. Keys rejected with 401/403 are not re-added; an empty result keeps the current keys. |
| `await refresh_keys_from_provider()` | Async version of the above. |
| `start_auto_refresh(interval)` / `stop_auto_refresh()` | Start/stop background refresh (daemon thread). |
| `get_next_user_agent()` / `get_next_proxy()` | Next value of the rotation lists (`None` if not configured). |

### AsyncAPIKeyRotator

Asynchronous rotator (default HTTP client: `aiohttp`). Same constructor.

```python
from apikeyrotator import AsyncAPIKeyRotator

async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
    response = await rotator.get("https://api.example.com/data")
    data = await response.json()          # aiohttp
```

| Method / property | Description |
|---|---|
| `await request(method, url, **kwargs)` | Like the sync version. Returns `aiohttp.ClientResponse` (or `httpx.Response` with `http_backend="httpx"`). With middlewares the body is read before returning (still available via `read()`/`json()`). A cache hit returns a small response object with `status`, `status_code`, `headers`, `read()`, `text()`, `json()`. |
| `await get / post / put / patch / delete / head(url, **kwargs)` | Shortcuts. |
| `await close()` | Closes the client session and stops background refresh. Use `async with` or call it explicitly. |
| `start_auto_refresh(interval)` / `await stop_auto_refresh()` | Background refresh as an asyncio task (needs a running loop; started automatically on first use when `auto_refresh_interval` is set). |
| `await load_keys()` | Loads keys from `secret_provider` if that is still pending (see below) and returns the active keys. Called automatically by `async with` and the first request; safe to call concurrently. |
| `keys`, `key_count`, `get_next_key()`, `get_key_statistics()`, `get_metrics()`, `get_circuit_states()`, `reset_key_health()`, `export_config()`, `refresh_keys_from_provider()`, `refresh_keys_from_provider_sync()` | Same as the sync rotator. |

State backends that do network I/O (Redis) are called in a worker thread, so the
event loop is never blocked.

### Unified responses

With `unified_response=True` every rotator and backend returns the same
`UnifiedResponse`, with the body already read - so the code is identical for
requests, httpx and aiohttp, and `json()` is never awaited:

```python
from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator

rotator = APIKeyRotator(api_keys=["key1"], unified_response=True)   # or http_backend="httpx"
response = rotator.get("https://api.example.com/data")
data = response.json()

async def main():
    async with AsyncAPIKeyRotator(api_keys=["key1"], unified_response=True) as rotator:
        response = await rotator.get("https://api.example.com/data")
        data = response.json()             # same API - no await
```

| Attribute / method | Description |
|---|---|
| `status_code` (`status`) | HTTP status. |
| `ok` | `status_code < 400`. The object itself is always truthy - test `ok`, not `if response:`. |
| `reason` (`reason_phrase`) | Status text, e.g. `"OK"`. |
| `headers` | Case-insensitive `Headers` mapping; repeated headers are joined with `", "`, `headers.get_list("Set-Cookie")` returns them separately. |
| `content`, `text`, `json(**kwargs)` | Body as bytes / str (charset from `Content-Type`, default utf-8; `encoding` can be set) / parsed JSON. |
| `url`, `elapsed` | Final URL; time to the response as `timedelta`. |
| `raise_for_status()` | Raises `HTTPStatusError` (with `.status_code` and `.response`) for 4xx/5xx, returns the response otherwise. |
| `native` | The client's own response (`requests.Response`, `aiohttp.ClientResponse`, `httpx.Response`), already released; `None` for cache hits. |
| `close()`, `release()`, `await aclose()`, `with` / `async with` | No-ops (the connection is already back in the pool), so existing code keeps working. |

The same object is used for `AllKeysExhaustedError.last_response` (its body stays
readable in async too), cache hits and `should_retry_callback`. Not available with
`stream=True` (raises `ValueError`) - streaming needs the client's own response.
Cost: about 2-3 µs per request (`overhead_*_unified` in the benchmark).

**Keys from a secret provider.** Created inside a running event loop with
`secret_provider=` and no `api_keys`, the async rotator does not call the provider in the
constructor (that would block the loop and run the provider on a different loop). Keys are
loaded on first use - `async with`, the first request or `await rotator.load_keys()` - in
the rotator's loop; until then `keys` is empty. A provider error is raised from that call
and loading is retried on the next one. Created outside a loop, the rotator loads keys in
the constructor, as the sync rotator does.

```python
from apikeyrotator import AsyncAPIKeyRotator, AWSSecretsManagerProvider

async def main():
    async with AsyncAPIKeyRotator(secret_provider=AWSSecretsManagerProvider(secret_name="prod/keys")) as rotator:
        print(rotator.key_count)          # keys are loaded here
        await rotator.get("https://api.example.com/data")
```

---

## Exceptions

```
APIKeyError
├── NoAPIKeysError
├── AllKeysExhaustedError          (.last_response, .last_exception, .possibly_processed)
│   ├── DeadlineExceededError      (also a TimeoutError)
│   ├── CircuitOpenError           (.host, .retry_after)
│   └── AuthenticationError        (.statuses, .auth_header)
├── AllProvidersExhaustedError
└── HTTPStatusError                (.status_code)
```

| Exception | Raised when |
|---|---|
| `NoAPIKeysError` | No keys were given or found (`parse_keys`, rotator constructor). |
| `AllKeysExhaustedError(message, last_response=None, last_exception=None)` | All attempts failed or no keys are left. `last_response` is the last HTTP response (released for async), `last_exception` the last network error. `possibly_processed` is `True` if a `POST`/`PATCH` attempt may have been executed - check the operation before retrying it. |
| `DeadlineExceededError` | The request's `total_timeout` was spent. `FallbackRouter` re-raises it instead of trying other providers. |
| `AuthenticationError` | Every key was rejected (`401`/`403`) before any request succeeded - usually a wrong auth header. The message shows the header that was sent (key masked); `statuses` maps masked keys to status codes. Keys are kept. |
| `CircuitOpenError(host, retry_after)` | The circuit breaker for `host` is open; `retry_after` = seconds until a probe is allowed. `FallbackRouter` moves to the next provider. |
| `AllProvidersExhaustedError` | `FallbackRouter`: every route failed and no `on_all_exhausted` callback is set. |
| `HTTPStatusError(status_code)` | Passed to middleware `on_error` hooks for error responses; raised by `raise_for_status()` of cached async responses. |

Network errors of non-idempotent requests that are not retried are re-raised as
the HTTP client's own exception (`requests.ReadTimeout`, `httpx.ReadTimeout`...).

---

## Multi-Provider Routing

### ProviderRoute

```python
ProviderRoute(rotator, name="default", request_transformer=None, condition=None, on_exhausted=None)
```

| Parameter | Description |
|---|---|
| `rotator` | `APIKeyRotator` or `AsyncAPIKeyRotator` of this provider. |
| `name` | Name used in logs. |
| `request_transformer` | `f(method, url, kwargs) -> (method, url, kwargs)` adapting the request to this provider (receives a copy of `kwargs`). |
| `condition` | `f(method, url, kwargs) -> bool`; the route is skipped when it returns `False`. |
| `on_exhausted` | Callback (sync or async) run when this provider gives up. |

### FallbackRouter

```python
FallbackRouter(routes, on_all_exhausted=None, logger=None)
```

Tries routes in order and moves to the next one when a provider raises
`AllKeysExhaustedError` (including `CircuitOpenError`). `DeadlineExceededError`
is re-raised immediately. If all routes fail, `on_all_exhausted(method, url, kwargs)`
is called (its return value is returned) or `AllProvidersExhaustedError` is raised.

| Method | Description |
|---|---|
| `request(method, url, **kwargs)`, `get/post/put/delete(url, **kwargs)` | Sync; routes with async rotators are skipped. |
| `await request_async(method, url, **kwargs)`, `get_async/post_async/put_async/delete_async(...)` | Async; routes with sync rotators are skipped. |

```python
from apikeyrotator import APIKeyRotator, FallbackRouter, ProviderRoute

def to_backup(method, url, kwargs):
    return method, url.replace("api.primary.com", "api.backup.com"), kwargs

router = FallbackRouter([
    ProviderRoute(APIKeyRotator(api_keys=["p1", "p2"]), name="primary"),
    ProviderRoute(APIKeyRotator(api_keys=["b1"]), name="backup", request_transformer=to_backup),
])
response = router.get("https://api.primary.com/v1/items")
```

---

## Rotation Strategies

| Name | Class | Behaviour |
|---|---|---|
| `"round_robin"` | `RoundRobinRotationStrategy(keys)` | Cycles through keys in order, skipping unavailable ones. |
| `"random"` | `RandomRotationStrategy(keys)` | Random available key. |
| `"weighted"` | `WeightedRotationStrategy({key: weight})` | Random, proportional to weights (non-negative, at least one positive). |
| `"lru"` | `LRURotationStrategy(keys)` | Least recently used available key (atomic under concurrency). |
| `"health_based"` | `HealthBasedStrategy(keys, failure_threshold=3, health_check_interval=300)` | Random healthy key; a key with `failure_threshold` consecutive failures is excluded and rechecked after `health_check_interval` seconds. |
| `"failover"` | `FailoverRotationStrategy(keys)` | Priority order: always the first available key; later keys are backups. |

"Available" means not rate-limited and healthy (or unhealthy but past
`recovery_timeout` since its last failure). If no key is available, strategies
fall back to all keys.

### create_rotation_strategy()

```python signature
create_rotation_strategy(strategy_type: str | RotationStrategy, keys: list[str] | dict[str, float], **kwargs) -> BaseRotationStrategy
```

```python
from apikeyrotator import create_rotation_strategy, RotationStrategy

create_rotation_strategy("weighted", {"key1": 3, "key2": 1})
create_rotation_strategy(RotationStrategy.HEALTH_BASED, ["k1", "k2"], failure_threshold=5)
```

`RotationStrategy` enum: `ROUND_ROBIN`, `RANDOM`, `WEIGHTED`, `LRU`, `HEALTH_BASED`, `FAILOVER`.

### BaseRotationStrategy

Subclass it for a custom strategy:

```python
from apikeyrotator import BaseRotationStrategy, KeyMetrics

class FirstHealthyStrategy(BaseRotationStrategy):
    def get_next_key(self, current_key_metrics: dict[str, KeyMetrics] | None = None) -> str:
        keys = self._get_healthy_keys(current_key_metrics)   # honours rate limits / recovery
        return keys[0]
```

| Member | Description |
|---|---|
| `get_next_key(current_key_metrics=None) -> str` | **Abstract.** The rotator passes its live `{key: KeyMetrics}`. |
| `update_keys(new_keys)` | Called when keys are added/removed. |
| `recovery_timeout` | Class attribute (default `60.0`); `None` disables probing of unhealthy keys. |
| `_get_healthy_keys(metrics)` | Helper: available keys (all keys if none is available). |

### KeyMetrics

Per-key statistics kept by the rotator (`get_key_statistics()` returns `to_dict()` of each).

| Field | Meaning |
|---|---|
| `total_requests`, `successful_requests`, `failed_requests` | Counters. |
| `success_rate` | EWMA of successes (`ewma_alpha=0.1`). |
| `avg_response_time` | Average response time, seconds. |
| `consecutive_failures`, `last_used`, `last_success`, `last_failure` | Recent history (UNIX timestamps). |
| `rate_limit_hits`, `rate_limit_reset` | 429 count; time until which the key is parked. |
| `is_healthy` | `False` after 3 consecutive failures or a success rate below 0.3 (after 10+ requests). |

Methods: `update_from_request(success, response_time=0.0, is_rate_limited=False)`,
`mark_rate_limited(until)`, `is_available(now=None, recovery_timeout=None)`,
`get_score()` (0..1 from success rate, speed and recency), `to_dict()`,
`KeyMetrics.from_dict(data)`.

---

## Shared State Backends

Used via `state_backend=`. Keys are identified by `sha256(key)` (HMAC-SHA256 with
`salt`) - raw keys are never stored.

### RedisStateBackend

```python
RedisStateBackend(client=None, url=None, namespace="apikeyrotator", salt=None, bucket_ttl=3600,
                  socket_timeout=1.0, invalid_ttl=86400)
```

| Parameter | Description |
|---|---|
| `client` | A sync `redis.Redis` client. Created from `url` if omitted. |
| `url` | Default `redis://localhost:6379/0`. |
| `namespace` | Prefix of all Redis keys - use one per upstream provider. |
| `salt` | HMAC salt for key ids; must be the same on all instances. |
| `bucket_ttl` | Seconds after which idle token buckets expire. |
| `socket_timeout` | Connect/read timeout of the client created from `url` (default 1 s), so an unreachable Redis cannot stall requests. Ignored when `client` is given - set timeouts on your client. |
| `invalid_ttl` | Seconds a key rejected with 401/403 stays banned for other instances (default one day). `None` = until `clear_invalid()`. The process that got the rejection itself does not use the key again until restarted. |

Stores `{namespace}:rl` (sorted set: key id → parked until), `{namespace}:revoked`
(sorted set: rejected key id → ban expiry) and `{namespace}:tb:{id}` (token buckets).
All times are computed by Lua scripts on the Redis server clock - clients only send
durations - so clock differences between machines do not change how long a key is
parked. Requires Redis 6.2+ (`ZADD GT`).
Upgrading from 0.9.1: bans in the old `{namespace}:invalid` set are no longer read
(it had no expiry); `clear_invalid()` also deletes it.
Errors never fail requests: the rotator continues with local state and logs a
warning at most every 30 s. After an error Redis is not contacted for 5 s; token
buckets are kept per process during that time. Requires `pip install apikeyrotator[redis]`.

### InMemoryStateBackend

```python
InMemoryStateBackend(shared=True, salt=None, invalid_ttl=86400)
```

Same interface, in-process. Pass one instance to several rotators to share state
between them.

### StateBackend interface

For custom backends: `shared` / `blocking` class attributes and
`report_rate_limited(key_id, until)`, `report_invalid(key_id)`,
`clear_invalid(key_id=None)`, `snapshot() -> SharedState`,
`acquire_token(key_id, capacity, refill_per_sec) -> float` (0 = acquired, else
seconds to wait), `key_id(key)`, `close()`. `SharedState` and `TokenBucket` live in
`apikeyrotator.state`.

---

## Middleware

### RotatorMiddleware

Base class with optional hooks. Sync rotators call the `*_sync` hooks, async
rotators the coroutine hooks (which delegate to the sync ones by default), so a
middleware that only implements `*_sync` works with both.

| Hook | Called | Return |
|---|---|---|
| `before_request(_sync)(request_info)` | Before each attempt | `RequestInfo` (possibly modified) or a `ResponseInfo` to short-circuit (e.g. cache hit) |
| `after_request(_sync)(response_info)` | After each response | `ResponseInfo` |
| `on_error(_sync)(error_info)` | After a network error or an error response (429/5xx/401/403) | `bool` (informational) |

Exceptions in `on_error` hooks are logged and ignored.

```python
from apikeyrotator import RotatorMiddleware

class TraceMiddleware(RotatorMiddleware):
    def before_request_sync(self, request_info):
        request_info.headers["X-Request-ID"] = new_request_id()
        return request_info
```

### Data models

| Class | Attributes |
|---|---|
| `RequestInfo` | `method`, `url`, `headers`, `cookies`, `key`, `attempt` (0-based), `kwargs` |
| `ResponseInfo` | `status_code`, `headers` (dict), `content` (bytes, `None` for `stream=True`), `request_info`, `response_time` (seconds or `None`) |
| `ErrorInfo` | `exception`, `request_info`, `response_info` (for error responses) |

### CachingMiddleware

```python
CachingMiddleware(ttl=300, cache_only_get=True, max_cache_size=1000,
                  max_cache_size_bytes=100 * 1024 * 1024, max_cacheable_size=10 * 1024 * 1024, logger=None)
```

LRU cache of `2xx` responses. The cache key includes method, URL, `params`,
non-auth headers and (for POST/PUT/PATCH with `cache_only_get=False`) the body.
Responses with `Set-Cookie`, `Cache-Control: no-store/private` or streaming
content types are not cached.

Methods: `get_stats()` → `{"cache_size", "hits", "misses", "total", "hit_rate", "size_bytes"}`, `clear()`.

### LoggingMiddleware

```python
LoggingMiddleware(verbose=True, logger=None, log_level=logging.INFO,
                  log_response_time=True, max_key_chars=4, max_logs_per_second=1000)
```

Logs requests, responses (with response time) and errors; masks keys and
`Authorization`/`X-API-Key`/`Cookie` headers; drops messages above
`max_logs_per_second`. `log_level` is applied only to its own default logger.

### RateLimitMiddleware

*Deprecated in 0.9.2, removed in 1.0* (emits `DeprecationWarning`). The rotator already
parks keys that got a `429` or report `X-RateLimit-Remaining: 0`, skips them and waits
only when every key is parked; use `key_rate_limit=(n, seconds)` for known quotas.

```python
RateLimitMiddleware(pause_on_limit=True, max_tracked_keys=1000, logger=None, max_wait=300.0)
```

Tracks `X-RateLimit-*` / `RateLimit-*` headers and 429 `Retry-After` per key and,
with `pause_on_limit=True`, waits before using a key whose quota is used up
(`remaining == 0`), for at most `max_wait` seconds. `get_stats()` →
`{"tracked_keys", "active_limits", "max_tracked_keys"}`.

The rotator itself already skips parked keys; this middleware is useful when you
want to *wait* for a specific key instead of switching.

---

## Metrics & Monitoring

### RotatorMetrics

Available as `rotator.metrics` (when `enable_metrics=True`).

```python
RotatorMetrics(max_endpoints=1000)
```

| Method | Description |
|---|---|
| `get_metrics()` | `{"total_requests", "successful_requests", "failed_requests", "success_rate", "uptime_seconds", "endpoint_stats": {endpoint: {...}}}` |
| `get_endpoint_stats(endpoint)` | `{"total_requests", "successful_requests", "failed_requests", "avg_response_time"}` |
| `get_top_endpoints(limit=10)` | `[(endpoint, total_requests), ...]` |
| `record_request(key, endpoint, success, response_time, is_rate_limited=False)` | Called by the rotator for every attempt. |
| `reset()` | Clears all counters. |

Endpoints are URLs without query string; beyond `max_endpoints` distinct
endpoints, stats are aggregated under `"__other__"`, so memory stays bounded.

### PrometheusExporter

```python
from apikeyrotator import PrometheusExporter

text = PrometheusExporter.export(rotator)
# or with the parts: PrometheusExporter.export(rotator.metrics, key_metrics=rotator.get_key_statistics())
```

Returns the Prometheus text format: `rotator_total_requests`,
`rotator_successful_requests`, `rotator_failed_requests`, `rotator_uptime_seconds`,
per-key `rotator_key_*{key="sk-p...wxyz"}` (masked) and per-endpoint
`rotator_endpoint_*{endpoint="..."}` series.

---

## Secret Providers

All providers implement `async get_keys() -> list[str]` and
`async refresh_keys() -> list[str]` (the `SecretProvider` protocol). Rotators call
them from sync code transparently.

| Provider | Constructor | Notes |
|---|---|---|
| `EnvironmentSecretProvider` | `(env_var="API_KEYS")` | Comma-separated value. |
| `FileSecretProvider` | `(file_path, logger=None)` | JSON array, CSV and/or one key per line (`#` comments). |
| `AWSSecretsManagerProvider` | `(secret_name, region_name="us-east-1", logger=None)` | `pip install apikeyrotator[aws]`. Secret: JSON array, `{"keys": [...]}` / `{"api_keys": [...]}`, JSON object values, or CSV. Retries transient errors 3 times. |
| `GCPSecretManagerProvider` | `(project_id, secret_id, version_id="latest", logger=None)` | `pip install apikeyrotator[gcp]`. Same payload formats. |

```python
from apikeyrotator import create_secret_provider

create_secret_provider("env", env_var="MY_KEYS")                  # also "environment"
create_secret_provider("file", file_path="keys.txt")
create_secret_provider("aws", secret_name="prod/keys")           # also "aws_secrets_manager"
create_secret_provider("gcp", project_id="p", secret_id="keys")  # also "gcp_secret_manager"
```

Custom providers only need the two async methods.

---

## Error Classification

### ErrorClassifier

```python signature
ErrorClassifier(custom_retryable_codes: list[int] | None = None)
```

| Method | Returns |
|---|---|
| `classify_error(response=None, exception=None)` | `ErrorType` |
| `is_retryable(response=None, exception=None)` | `True` for `RATE_LIMIT`, `TEMPORARY`, `NETWORK` |
| `should_switch_key(response=None, exception=None)` | `True` for `RATE_LIMIT`, `PERMANENT` |
| `should_remove_key(response=None, exception=None)` | `True` for 401 / 403 |
| `get_retry_delay(response=None, default_delay=1.0)` | `Retry-After` (seconds or HTTP date), else `5 * default_delay` for 429, else `default_delay` |

| `ErrorType` | Statuses / exceptions |
|---|---|
| `RATE_LIMIT` | 429 |
| `TEMPORARY` | 5xx, 408, 409, 425, 511, `custom_retryable_codes` |
| `PERMANENT` | other 4xx (401/403 remove the key; the rest are returned to the caller) |
| `NETWORK` | connection errors and timeouts of requests / aiohttp / httpx |
| `UNKNOWN` | success statuses and unrecognised exceptions |

Subclass it to change the rules, e.g. treat 402 as a key problem:

```python
from apikeyrotator import ErrorClassifier

class MyClassifier(ErrorClassifier):
    def should_remove_key(self, response=None, exception=None):
        return response is not None and response.status_code in (401, 402, 403)
```

Header helpers (in `apikeyrotator.utils`): `parse_retry_after(headers)`,
`parse_rate_limit_headers(headers) -> (remaining, reset_timestamp)`,
`get_header(headers, name)` (case-insensitive).

---

## Utilities

### CircuitBreakerConfig / CircuitBreaker

```python
CircuitBreakerConfig(failure_threshold=5, recovery_timeout=30.0, half_open_max_calls=1)
CircuitBreaker(failure_threshold=5, timeout=60, half_open_max_calls=1, name="")
```

`CircuitBreaker` is the thread-safe breaker the rotator uses per host; you can use
it standalone: `allow_request()`, `record_success()`, `record_failure()`,
`retry_after()`, `get_state()` (`"CLOSED"`, `"OPEN"`, `"HALF_OPEN"`), `reset()`,
`release_probe()`, `CircuitBreaker.from_config(config, name="")`.

```python
from apikeyrotator import CircuitBreaker

breaker = CircuitBreaker(failure_threshold=5, timeout=60)
if breaker.allow_request():
    try:
        do_call()
        breaker.record_success()
    except Exception:
        breaker.record_failure()
        raise
```

### Retry helpers

```python
retry_with_backoff(func, retries=3, backoff_factor=0.5, exceptions=Exception)
await async_retry_with_backoff(func, retries=3, backoff_factor=0.5, exceptions=Exception)
```

Call `func()` (or `await func()`) up to `retries` times, sleeping
`backoff_factor * 2 ** attempt` between attempts; the last exception is re-raised.

*Deprecated in 0.9.2, removed in 1.0* (emit `DeprecationWarning` on import):
`apikeyrotator.utils.exponential_backoff`, `jittered_backoff`, `measure_time`,
`measure_time_async`. The rotator does not use them; time calls with
`time.perf_counter()` or read `rotator.get_metrics()["endpoint_stats"]`.

---

## Configuration Loader

```python signature
ConfigLoader(config_file: str, logger=None)
```

JSON / YAML (`.json`, `.yaml`, `.yml`) configuration file: `load_config()`,
`save_config(config=None)`, `get(key, default=None)`, `update_config(new_data)`,
`clear()`, `delete_config_file()`. A missing or broken file loads as `{}`.

## Key Parsing

```python signature
parse_keys(api_keys=None, env_var="API_KEYS", logger=None) -> list[str]
```

Accepts a list/tuple or a comma-separated string; falls back to the environment
variable; strips blanks and removes duplicates. Raises `NoAPIKeysError`.

---

## See also

- [Resilience & Scaling](RESILIENCE.md) - deadlines, circuit breaker, rate limits, Redis, httpx
- [Middleware Guide](MIDDLEWARE.md)
- [Error Handling](ERROR_HANDLING.md)
- [Examples](EXAMPLES.md)
