# Changelog

All notable changes to APIKeyRotator will be documented in this file.
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