# Changelog

All notable changes to APIKeyRotator will be documented in this file.

## [0.9.1] - 2026-09-24

Checks of thread safety, binary bodies, partial failures and Redis consistency in real
code, a new guide with the results, and the fixes they led to.

### Fixed
- **LRU strategy on coarse clocks**: selections were ordered by `time.time()`; where the clock moves in steps (~15 ms on Windows) every selection within a step got the same timestamp and one key received almost all requests (2395 of 2400 in a test). It also let the completion time of a request reorder keys, so concurrent use was not strictly least-recently-used. Selections are now ordered by a counter: exact rotation under any clock and concurrency.
- **Redis outage**: while the state backend was unreachable, `key_rate_limit` was not enforced at all (every token request "succeeded"), and every request paid the connection timeout again - with an unreachable host, possibly minutes, since clients created from `url=` had no timeout. Now Redis is not contacted for 5 s after an error, token buckets are kept per process meanwhile, and `RedisStateBackend(url=...)` uses `socket_timeout=1.0`.

### Changed
- `PrometheusExporter.export(rotator)` accepts the rotator itself (the `metrics, key_metrics=` form still works).
- `UnifiedResponse.json()` raises `json.JSONDecodeError` for bodies that are not JSON in any encoding (it raised `UnicodeDecodeError` for non-UTF-8 bodies).

### Tests
- Concurrency: every strategy under 8 threads (request, per-key and global counters must match exactly), concurrent key removal / parking / replacement, per-host circuit breakers, byte-exact binary bodies for all four backends.
- Shared state against a real Redis with several processes (global token bucket, revoked key propagation); CI runs it with a Redis service.

### Documentation
- New guide [Behavior Under Load and Edge Cases](docs/BEHAVIOR.md): threads, asyncio and processes, strategies under concurrency, binary / large / non-UTF-8 / non-JSON bodies, one host down, revoked keys, fallback providers, several processes with Redis (global limits, revoked keys, outages), keys with commas, auth header choice, metrics calls. Every example shows its real output.
- Consistency model of the shared state (token buckets strong, rate-limited / revoked keys eventual within `state_sync_interval`), breaker scope per host, keys containing commas.

## [0.9.0] - 2026-09-24

Safety for requests with side effects (payments, orders, messages), one response type for
all HTTP clients, and fixes found by running the usage examples against a live API.

### Added
- **`unified_response=True`**: every rotator and HTTP backend (requests, httpx, aiohttp; sync and async) returns the same `UnifiedResponse` - `status_code`, case-insensitive `headers` (with `get_list()` for repeated headers), `content` / `text` / `json()` without `await`, `ok`, `reason`, `url`, `elapsed`, `raise_for_status()` and the client's own object as `native`. The body is read and the connection returned to the pool; `AllKeysExhaustedError.last_response`, cache hits and `should_retry_callback` use the same object. About 2-3 µs per request; off by default.
- `HTTPStatusError.response`.
- **`auto_idempotency_key=True`** (or a header name): adds an `Idempotency-Key` to every POST/PATCH without one - one value per request, reused on its retries.
- `AllKeysExhaustedError.possibly_processed`: `True` when a POST/PATCH attempt may have been executed (5xx / read timeout while retrying with an idempotency key).
- Benchmark scenarios `overhead_sync_unified` and `overhead_async_unified`.

### Fixed
- After an `AuthenticationError`, fixing the header (`rotator.auth = ...`) and making a successful request removed **all** keys: the keys rejected because of the wrong header were treated as invalid once a request succeeded. Rejections that explain an `AuthenticationError` are now forgotten, and changing `auth` / `header_callback` requires the new header to be confirmed again.
- Key masks: keys of 16+ characters show their first and last 4 characters (`sk-p...wxyz`), so keys with a common prefix (`sk-proj-...`) are distinguishable in logs, metrics and errors; `AuthenticationError.statuses` no longer merges keys with the same mask.
- Log messages use one format (`status 503, key sk-p...wxyz`); per-attempt timeouts clipped to the deadline are rounded to milliseconds.

### Fixed (side effects)
- A POST/PATCH retried because of an `Idempotency-Key` now keeps **the same API key** after a failure where it may have been executed. It switched keys before, and idempotency keys are usually scoped to the key's account, so the retry could execute the operation a second time.
- `FallbackRouter` no longer sends such a request to the next provider (which doesn't know the idempotency key) - it re-raises the error with `possibly_processed=True`.
- `should_retry_callback` can no longer repeat a POST/PATCH the server has answered (and therefore executed) unless the request is idempotent.

### CI
- GitHub Actions updated to their Node 24 versions (`checkout@v5`, `setup-python@v6`, `upload-artifact@v5`, `download-artifact@v5`).
- The release workflow takes `ref` and `latest` inputs (release any commit, optionally not as the latest release). The tag for 0.8.0 could not be created retroactively: GitHub does not let the workflow token create a tag on a commit whose workflow files differ from the current ones. The 0.8.0 changes are listed below and shipped in 0.8.1+.

## [0.8.2] - 2026-09-24

Developer-experience release: fewer surprises, clearer errors.

### Breaking changes
- **No implicit file reads.** `load_env_file` now defaults to `False` and `config_file` to `None`: the rotator no longer loads `./.env` into `os.environ` or reads `./rotator_config.json` unless asked. Pass `load_env_file=True` / `config_file="..."` to keep the old behaviour. `NoAPIKeysError` says so when a `.env` file is present.
- **Default auth header**: keys that are not 32 characters long are sent as `Authorization: Bearer <key>` (was the non-standard `Authorization: Key <key>`). Use `auth=` to choose the scheme explicitly.
- `should_retry_callback` receives the response object in `AsyncAPIKeyRotator` too (it received the status code) - the same callback now works with both rotators.

### Added
- **`auth=`**: `"bearer"`, `"x-api-key"`, `(header, template)` such as `("Authorization", "Token {key}")` or `("x-goog-api-key", "{key}")`, or `False` for no auth header. Writable later (`rotator.auth = ...`).
- **`AuthenticationError`** (an `AllKeysExhaustedError`): raised when every key is rejected with 401/403 before any request succeeded, with the header that was sent (key masked) and the status per key.

### Fixed
- **A wrong auth header no longer destroys the key pool.** Previously every key answering 401/403 was removed immediately (and, with a shared state backend, marked invalid for all instances), so a misconfigured header left an empty pool and the message "All keys are invalid". Until a request has been accepted, rejected keys are now kept, the other keys are tried, and `AuthenticationError` explains the likely cause; once any request succeeds, the keys rejected earlier are removed as before.
- `load_env_file=True` searched for `.env` from the library's own directory, so it never found the application's `.env` once the package was installed; it now searches from the working directory.
- The default auth header is not added when `header_callback` already sends the key in some other header (it was sent twice).
- `AsyncAPIKeyRotator` runs the `*_sync` hooks of middlewares that don't inherit from `RotatorMiddleware` and have no async hooks (they were silently skipped).

### Changed
- `APIKeyRotator` warns (`UserWarning`) when a middleware implements only async hooks, which a sync rotator never calls.
- No emoji in log messages, error messages or documentation.
- The benchmark history job uses the same size as `benchmarks/RESULTS.md` (`-n 5000 -r 3`), so the charts and the reference table are comparable.

## [0.8.1] - 2026-09-24

### Changed
- **Core split into components** (`apikeyrotator/core/`): `KeyPool` (keys, metrics, strategy), `RetryPolicy`, `RateLimiter`, `BreakerRegistry`, `StateSync`, `RequestBuilder`, `MiddlewareChain`. The retry loop exists **once**, in the sans-IO `RequestEngine` (a generator yielding I/O effects); `APIKeyRotator` and `AsyncAPIKeyRotator` only perform the effects. `rotator.py` shrank from 1674 to ~790 lines, and the two copies of the retry loop became one. The public API is unchanged: constructor arguments, attributes (still writable, e.g. `rotator.max_retries = 5`), methods, and `key_manager` (now a `KeyPool`, old method names kept). Behaviour is identical in all resilience benchmarks (upstream calls, waiting, success rate).
- **`AsyncAPIKeyRotator` + `secret_provider` inside a running event loop** no longer calls the provider in the constructor. That call blocked the loop and ran the provider on a helper thread's loop, which broke providers holding loop-bound resources (`RuntimeError: ... attached to a different loop`). Keys are now loaded on first use (`async with`, the first request or the new `await rotator.load_keys()`) in the rotator's loop. Outside a loop, keys are still loaded in the constructor.
- Sync rotator with middlewares: a network error while reading the response body is now handled like any network error of the attempt (retried according to the idempotency rules) instead of escaping the retry loop.
- The inferred auth header is cached per key.

### Benchmark
- Published results: `benchmarks/RESULTS.md` (reference run), history charts on GitHub Pages updated by `.github/workflows/benchmark.yml` on every change on `master`, Markdown tables in CI job summaries (PRs also get the comparison with the base branch).
- `--markdown FILE` (Markdown report) and `--export-github PREFIX` (github-action-benchmark data).
- The virtual clock now starts at a fixed, minute-aligned epoch: quota scenarios depended on the wall clock and varied by up to ~10% between runs (enough to trip the CI gate); all resilience metrics are now identical on every run.
- Transient allocations per request: +0.5 KB, because the shared request loop's generator frame lives on the heap during a request (freed afterwards; memory growth stays 0). Throughput is unchanged within noise.

### Release process
- CI also runs on tags. After lint/docs/tests pass on `master` or a tag, the new `Release` workflow creates the tag for the `pyproject.toml` version (if missing) and a GitHub release with the wheel, the sdist and the notes from this changelog. PyPI publishing is opt-in (`PYPI_PUBLISH` variable + trusted publisher).
- Benchmark history is deployed to GitHub Pages with GitHub Actions.
- `.idea/` removed from the repository (IDE folders are git-ignored); `aioresponses` removed from the test extras (it does not support aiohttp 3.14+).

## [0.8.0] - 2026-09-24

### Breaking changes
- **Python 3.12+ is required** (was 3.8+). The code base uses modern syntax (`X | None`, `list[...]`, slots dataclasses).
- **Logging**: the library no longer attaches a `StreamHandler` or sets log levels. A `NullHandler` is attached to the `apikeyrotator` logger; call `logging.basicConfig(level=logging.INFO)` in your application to see messages.
- **POST/PATCH are no longer retried after errors where the request may already have been processed** (`500`, `502`, `504`, read timeouts, dropped connections) - the response is returned / the exception re-raised. They are still retried on `429`, `503`, `408`, `425`, connection failures and key rejections (`401`/`403`). Restore the old behaviour with `retry_non_idempotent=True` or per request with an `Idempotency-Key` header.

### Added
- **Request deadline** `total_timeout` (rotator default and per request): budget for all attempts and waits; `DeadlineExceededError` (a `TimeoutError` and `AllKeysExhaustedError`). Per-attempt timeouts are clipped to the remaining budget; waits that cannot finish in time are not started.
- **Per-host circuit breaker** `circuit_breaker=True | CircuitBreakerConfig(...)`: after repeated 5xx/network failures requests fail fast with `CircuitOpenError` (FallbackRouter moves to the next provider); half-open probing; `get_circuit_states()`.
- **Client-side key rate limits**: token bucket `key_rate_limit=(requests, per_seconds)`; keys reporting `X-RateLimit-Remaining: 0` are parked until reset (`respect_rate_limit_headers`, on by default). 429 without `Retry-After` now also honours `X-RateLimit-Reset`.
- **Shared state between processes**: `state_backend=RedisStateBackend(...)` shares rate-limited keys, keys rejected with 401/403 and token buckets (atomic Lua, Redis server clock). Only key hashes (optionally HMAC-salted) are stored; Redis outages fail open. `InMemoryStateBackend` shares state between rotators in one process. Extra: `pip install apikeyrotator[redis]`.
- **Background key refresh** `auto_refresh_interval=` (daemon thread / asyncio task, stopped by `close()`); `start_auto_refresh()` / `stop_auto_refresh()`. Refreshes never re-add keys rejected with 401/403.
- **httpx backend** `http_backend="httpx"` for both rotators, optional `http2=True`, `http_client_kwargs=` for client settings. Extra: `pip install apikeyrotator[httpx]`.
- `CircuitBreaker` utility rewritten: thread-safe, limited half-open probes, `retry_after()`.
- Benchmark: CPU time per operation for every scenario, `resources` group (memory per key, leak check, allocations per request, import cost), scenarios for the new features, `--gate deterministic`, `--scenario-timeout`, best-of-N reporting.
- **CI** (GitHub Actions): ruff, tests on Python 3.12/3.13, and a benchmark of every PR against its base branch (gated on machine-independent metrics).

- **`failover` rotation strategy** (`FailoverRotationStrategy`): always the first available key, the rest are backups. The never-implemented `RotationStrategy.RATE_LIMIT_AWARE` enum member was removed (it always raised `ValueError`).
- `py.typed` marker - type hints are now visible to type checkers (the package already declared `Typing :: Typed`).

### Changed
- The default auth header is no longer added when the request or `header_callback` already sets `X-API-Key` (previously the key was sent twice: `X-API-Key` and `Authorization: Key ...`).

### Documentation
- All guides rewritten against the actual API and checked automatically: `scripts/check_docs.py` verifies that every example's imports, parameters and methods exist and that links/anchors resolve (runs in CI); every example was also executed with a mocked network.
- Fixed many wrong or broken examples: async-only middleware used with the sync rotator (hooks never ran), middlewares putting private keys into `request_info.kwargs` (crashed the HTTP call), non-existent methods (`clear_cache()`, `clear_limits()`, `strategy.keys()`, `CircuitBreaker.call()`), wrong `export_config()`/cache stats keys, the `if response:` truthiness bug in classifier examples, logging raw keys, a broken code fence that swallowed half of the README.
- Corrected behaviour descriptions: `max_retries` is per request (not per key), 4xx responses are returned (not "remove key"), the config file is read-only (nothing is "learned and saved"), `after_request` runs in list order, the rotator is thread-safe (share one instance), `requests`/`aiohttp` are required dependencies.
- New `docs/RESILIENCE.md`; `API_REFERENCE.md` regenerated from the code (router, state backends, all parameters and methods); `SECURITY.md` gained guidance on redirects leaking custom auth headers and Redis hardening.

### Performance & resources
- `import apikeyrotator` no longer loads aiohttp/requests/yaml: **245 ms → 69 ms, 33.5 MB → 13.8 MB RSS**. HTTP libraries load when a rotator using them is created.
- Memory per key **374 B → 230 B** (round-robin) and **730 B → 230 B** (LRU / health-based): `KeyMetrics` uses `__slots__` and a striped lock pool; strategies no longer keep a second copy of per-key metrics.
- Key selection and the plain request path are 2-17% faster despite the new features (see `benchmarks/README.md`); single-pass rate-limit header parsing shared with `RateLimitMiddleware`; one lock instead of three in `RotatorMetrics`; `__slots__` for `RequestInfo`/`ResponseInfo`/`ErrorInfo`; no `urlsplit` per request.
- Test suite: 12.4 s → ~2 s (no real backoff sleeps), 268 tests.

## [0.7.0] - 2026-09-24

### Fixed
- **Key pool destruction on client errors**: any 4xx (e.g. `404`, `400`, `422`) removed the key from rotation, so a wrong URL burned through the whole pool. Now only `401`/`403` remove a key; other client errors are returned to the caller without retries.
- **`ErrorClassifier.should_remove_key()` / `get_retry_delay()`** relied on the truthiness of `requests.Response`, which is `False` for error codes — they never worked with real responses.
- **Async `FallbackRouter.request_async()`** called a non-existent `rotator.request_async()` and always failed.
- **`rotation_strategy="weighted"`** always raised `ValueError`; weights can now be passed via `rotation_strategy_kwargs={"weights": {...}}` (default: equal weights).
- **Async caching**: responses were cached with `content=None`, so cache hits returned an empty body. The body is now read when middlewares are active.
- **Caching key collisions**: `params=` were not part of the cache key (`?q=a` and `?q=b` shared one entry).
- **`RateLimitMiddleware`** paused every request until the window reset even with quota remaining; `RateLimit-Reset` (delta seconds) was treated as a UNIX timestamp; fractional / HTTP-date `Retry-After` was ignored.
- **Middleware `on_error` hooks** were never invoked by the rotators.
- **Response time metrics** included all previous retries and backoff sleeps.
- **Unhealthy keys were excluded forever**: after 3 failures a key was never selected again (unless all keys failed). Keys are now probed again after `recovery_timeout` (60s). An active rate limit no longer flips `is_healthy`.
- **`HealthBasedStrategy`** ignored its own `failure_threshold` when used from the rotator.
- **Thread safety**: LRU could hand the same key to concurrent callers; user-agent/proxy cycling was not synchronised; `LoggingMiddleware` rate limiter counters were racy.
- **Prometheus exporter** emitted duplicate `# HELP`/`# TYPE` lines (invalid format), did not escape label values and exposed 8 key characters (now 4, masked).
- **Secret providers**: `secret_provider=` was accepted but never used. AWS/GCP providers swallowed errors so retries never happened. File provider used `print()` and mis-parsed mixed CSV/newline files.
- **Tests**: `test_middleware.py` / `test_providers.py` were truncated and the suite failed to import (`RetryMiddleware`); the concurrency test leaked real HTTP requests.

### Changed (load resilience & performance)
- On `429` the rotator marks the key as rate-limited (using `Retry-After`) and switches to the next available key **immediately**; it waits only when all keys are limited — until the earliest one frees up.
- Backoff and rate-limit waits are capped by the new `max_delay` (60s).
- Failed responses are closed/released so connections return to the pool; streaming responses (`stream=True`) are no longer consumed.
- Key selection is O(1) in the common case for round-robin / random / weighted (1000 keys: ~7.9k → ~1.1M selections/s). Metrics dict is copy-on-write instead of being copied per request.
- Endpoint metrics drop query strings and are bounded (`RotatorMetrics(max_endpoints=1000)`) — no unbounded memory growth.
- `CachingMiddleware` tracks its size incrementally (was O(n) per insert).
- Per-request log messages moved from INFO to DEBUG.
- Duplicate API keys are removed on load.

### Added
- `max_delay`, `pool_size`, `recovery_timeout` rotator parameters.
- `refresh_keys_from_provider()` / `refresh_keys_from_provider_sync()`; keys are loaded from `secret_provider` when `api_keys` is not given. Changing keys preserves metrics of kept keys.
- `AllKeysExhaustedError.last_response` / `.last_exception`; new `HTTPStatusError`.
- `patch()` / `head()` methods, `close()` and context-manager support for the sync rotator, `close()` for the async one.
- `ResponseInfo.response_time`, `CachingMiddleware.clear()`, `hit_rate` in cache stats, `RateLimitMiddleware(max_wait=...)`.
- **Benchmark suite** `benchmarks/bench_core.py` with baseline save/compare (see `benchmarks/README.md`).
- Regression tests (`tests/test_regressions.py`) and full middleware/provider test suites.

## [0.6.1] - 2026-06-19

### Added
- **Multi-Provider Routing**: Introduced `FallbackRouter` and `ProviderRoute` to seamlessly fall back between multiple service providers (e.g., OpenAI to Anthropic) with custom payload transformers.
- **Dynamic Imports**: GCP and AWS secret providers are now imported dynamically to prevent `ImportError` when optional dependencies are missing.

### Fixed
- **Caching Middleware**: Fixed a bug where `CachingMiddleware` logged cache hits but didn't actually return the cached response. It now properly short-circuits the network request.
- **Thread Safety**: Fixed thread-safety issues in tests (`test_integration.py`).
- **Language Consistency**: Translated all core Russian logging messages to English to ensure a globally consistent, professional codebase.

### Removed
- **RetryMiddleware**: Completely removed because it duplicated the core `BaseKeyRotator`'s exponential backoff, causing $N^2$ redundant requests.
- **Ghost CLI**: Removed unimplemented `apikeyrotator-cli` from `pyproject.toml`.

## [0.6.0] - 2026-06-19

### Fixed
- **Code Quality**: Replaced `print()` with standard `logging` module in `utils/retry.py`.
- **Thread Safety**: Added proper locks (`self._lock`) for key updates in `WeightedRotationStrategy` and `LRURotationStrategy`.
- **Key Selection Logic**: Updated strategies to correctly filter out unhealthy keys using `_get_healthy_keys()` instead of selecting from the entire pool.
- **Function Metadata**: Added `@functools.wraps` to decorators to preserve original function signatures and documentation.

### Changed
- Removed public support email to focus on internal issue tracking.
- Added `.gitignore` for Python build artifacts.

## [0.5.1] - Previous Release

*(Includes all features and improvements up to 0.5.1)*

## [0.4.3] - Legacy Release
### Added
- **Middleware System**: Comprehensive middleware support for request/response interception
  - `CachingMiddleware`: Response caching with LRU eviction
  - `LoggingMiddleware`: Detailed request/response logging with sensitive data masking
  - `RateLimitMiddleware`: Rate limit tracking and automatic pause
  - `RetryMiddleware`: Advanced retry logic with exponential backoff
- **Metrics Collection**: Built-in metrics tracking system
  - `RotatorMetrics`: Centralized metrics collector
  - Per-endpoint statistics
  - Success rate tracking
  - Response time monitoring
  - `PrometheusExporter`: Export metrics in Prometheus format
- **Secret Providers**: External secret management integration
  - `EnvironmentSecretProvider`: Load keys from environment variables
  - `FileSecretProvider`: Load keys from JSON/CSV files
  - `AWSSecretsManagerProvider`: AWS Secrets Manager integration
  - `GCPSecretManagerProvider`: Google Cloud Secret Manager integration
  - `create_secret_provider()`: Factory function for provider creation
- **Rotation Strategies**: Advanced key selection strategies
  - `RoundRobinRotationStrategy`: Sequential key rotation
  - `RandomRotationStrategy`: Random key selection
  - `WeightedRotationStrategy`: Weighted key distribution
  - `LRURotationStrategy`: Least Recently Used selection
  - `HealthBasedStrategy`: Health-aware key selection
- **KeyMetrics Class**: Comprehensive per-key metrics tracking
  - EWMA (Exponential Weighted Moving Average) for success rate
  - Response time tracking
  - Rate limit detection
  - Automatic health status calculation
- **Enhanced Error Classification**: More granular error handling
  - Support for status codes: 408, 409, 425 as temporary errors
  - Better distinction between client and server errors
  - Custom retryable codes support
- **Thread Safety**: Full thread-safe implementation
  - RLock usage for critical sections
  - Separate locks for different resources
  - Safe concurrent access to shared state

### Changed
- **Improved Error Classifier**: More intelligent error categorization
  - HTTP 408 (Request Timeout) now classified as TEMPORARY
  - HTTP 409 (Conflict) now classified as TEMPORARY
  - HTTP 425 (Too Early) now classified as TEMPORARY
  - Better handling of 4xx vs 5xx errors
- **Enhanced BaseKeyRotator**: Better core functionality
  - Thread-safe key rotation
  - Improved metrics tracking
  - Better proxy and User-Agent rotation
  - Configurable sensitive header saving
- **Optimized Connection Pooling**: Better performance
  - Pool size increased to 100 connections
  - More efficient resource usage
  - Reduced connection overhead
- **Better Configuration Management**: Enhanced config system
  - Thread-safe configuration access
  - Improved config file handling
  - Better error handling in config operations
- **Improved Async Support**: Enhanced async operations
  - Better session management
  - Proper resource cleanup
  - More efficient concurrent requests

### Fixed
- **Critical Thread Safety Issues**: Fixed race conditions
  - Proper locking around key rotation
  - Thread-safe metrics updates
  - Safe concurrent configuration access
- **Memory Leaks**: Fixed resource cleanup issues
  - Proper session closure in async mode
  - Better cache eviction in middleware
  - Cleanup of expired rate limit entries
- **LRU Eviction**: Fixed cache middleware eviction
  - Now uses OrderedDict for proper LRU behavior
  - Automatic eviction when cache is full
  - Better memory management
- **EWMA Calculation**: Corrected Exponential Weighted Moving Average formula
  - Proper implementation of EWMA for success rate
  - Configurable alpha parameter
  - More accurate success rate tracking
- **Exponential Backoff**: Fixed jitter calculation
  - Proper jitter implementation (0-10% of delay)
  - Prevents thundering herd problem
  - More distributed retry timing

### Security
- **Sensitive Data Protection**: Enhanced security measures
  - Authorization headers masked in logs
  - API keys truncated in output
  - Cookie values redacted in logs
  - Optional sensitive header persistence (`save_sensitive_headers=False` by default)
- **Safe Header Handling**: Better header security
  - Sensitive headers excluded from saved configurations
  - Automatic removal of auth data from persistent storage
  - Configurable sensitive header persistence

### Performance
- **Connection Pooling**: Optimized for high throughput
  - 100 connections per pool (up from default)
  - Reduced connection establishment overhead
  - Better resource reuse
- **Efficient Caching**: Improved middleware caching
  - LRU eviction prevents memory bloat
  - Configurable cache size
  - Periodic cleanup of expired entries
- **Better Concurrency**: Enhanced async performance
  - More efficient task scheduling
  - Better resource utilization
  - Reduced contention in thread-safe operations

### Documentation
- Complete API reference for all classes and methods
- Comprehensive middleware documentation
- Examples for all new features
- Security best practices guide
- Advanced usage patterns

### Dependencies
- `requests` - For synchronous HTTP requests
- `aiohttp` - For asynchronous HTTP requests
- `python-dotenv` - Optional, for .env file support
- `pyyaml` - For YAML configuration support
- `boto3` - Optional, for AWS Secrets Manager
- `google-cloud-secret-manager` - Optional, for GCP Secret Manager
---

## Types of Changes

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for vulnerability fixes
- **Performance** for performance improvements
- **Documentation** for documentation updates

## Links

- [GitHub Releases](https://github.com/PrimeevolutionZ/apikeyrotator/releases)
- [PyPI Releases](https://pypi.org/project/apikeyrotator/#history)
- [Documentation](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/INDEX.md)