# Changelog

All notable changes to APIKeyRotator will be documented in this file.
## [0.4.3] - Lastes

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