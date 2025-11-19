# API Reference

Complete reference documentation for all APIKeyRotator classes and methods.

## Table of Contents

- [Core Classes](#core-classes)
  - [APIKeyRotator](#apikeyrotator)
  - [AsyncAPIKeyRotator](#asyncapikeyrotator)
- [Error Classification](#error-classification)
- [Rotation Strategies](#rotation-strategies)
- [Middleware System](#middleware-system)
- [Metrics & Monitoring](#metrics--monitoring)
- [Secret Providers](#secret-providers)
- [Configuration Management](#configuration-management)
- [Exceptions](#exceptions)
- [Utilities](#utilities)

---

## Core Classes

### APIKeyRotator

Synchronous API key rotator for `requests`-based applications.

#### Constructor

```python
APIKeyRotator(
    api_keys: Optional[Union[List[str], str]] = None,
    env_var: str = "API_KEYS",
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: float = 10.0,
    should_retry_callback: Optional[Callable] = None,
    header_callback: Optional[Callable] = None,
    user_agents: Optional[List[str]] = None,
    random_delay_range: Optional[Tuple[float, float]] = None,
    proxy_list: Optional[List[str]] = None,
    logger: Optional[logging.Logger] = None,
    config_file: str = "rotator_config.json",
    load_env_file: bool = True,
    error_classifier: Optional[ErrorClassifier] = None,
    config_loader: Optional[ConfigLoader] = None,
    rotation_strategy: Union[str, RotationStrategy, BaseRotationStrategy] = "round_robin",
    rotation_strategy_kwargs: Optional[Dict] = None,
    middlewares: Optional[List[RotatorMiddleware]] = None,
    secret_provider: Optional[SecretProvider] = None,
    enable_metrics: bool = True,
    save_sensitive_headers: bool = False
)
```

**Parameters:**

| Parameter                | Type                                             | Default                 | Description                                                                           |
|--------------------------|--------------------------------------------------|-------------------------|---------------------------------------------------------------------------------------|
| `api_keys`               | `Optional[Union[List[str], str]]`                | `None`                  | List of API keys or comma-separated string. If `None`, loaded from environment.       |
| `env_var`                | `str`                                            | `"API_KEYS"`            | Environment variable name to load keys from.                                          |
| `max_retries`            | `int`                                            | `3`                     | Maximum retry attempts per key before moving to next key.                             |
| `base_delay`             | `float`                                          | `1.0`                   | Base delay in seconds for exponential backoff: `base_delay * (2 ** attempt)`.         |
| `timeout`                | `float`                                          | `10.0`                  | Request timeout in seconds.                                                           |
| `should_retry_callback`  | `Optional[Callable]`                             | `None`                  | Custom function `(response) -> bool` to determine retry logic.                        |
| `header_callback`        | `Optional[Callable]`                             | `None`                  | Custom function `(key, headers) -> (headers, cookies)` for dynamic header generation. |
| `user_agents`            | `Optional[List[str]]`                            | `None`                  | List of User-Agent strings to rotate through.                                         |
| `random_delay_range`     | `Optional[Tuple[float, float]]`                  | `None`                  | Tuple of `(min, max)` for random delay before each request.                           |
| `proxy_list`             | `Optional[List[str]]`                            | `None`                  | List of proxy URLs to rotate through.                                                 |
| `logger`                 | `Optional[logging.Logger]`                       | `None`                  | Custom logger instance. Creates default if not provided.                              |
| `config_file`            | `str`                                            | `"rotator_config.json"` | Path to configuration file for storing learned settings.                              |
| `load_env_file`          | `bool`                                           | `True`                  | Whether to automatically load `.env` file (requires `python-dotenv`).                 |
| `error_classifier`       | `Optional[ErrorClassifier]`                      | `None`                  | Custom error classifier instance.                                                     |
| `config_loader`          | `Optional[ConfigLoader]`                         | `None`                  | Custom configuration loader instance.                                                 |
| `rotation_strategy`      | `Union[str, RotationStrategy, BaseRotationStrategy]` | `"round_robin"`     | Key rotation strategy ('round_robin', 'random', 'weighted', 'lru', 'health_based').  |
| `rotation_strategy_kwargs` | `Optional[Dict]`                               | `None`                  | Additional kwargs for rotation strategy initialization.                               |
| `middlewares`            | `Optional[List[RotatorMiddleware]]`              | `None`                  | List of middleware instances for request/response interception.                       |
| `secret_provider`        | `Optional[SecretProvider]`                       | `None`                  | Secret provider for loading keys from external sources.                               |
| `enable_metrics`         | `bool`                                           | `True`                  | Enable built-in metrics collection.                                                   |
| `save_sensitive_headers` | `bool`                                           | `False`                 | Whether to save sensitive headers (Authorization, X-API-Key) to config.               |

**Raises:**
- `NoAPIKeysError`: If no API keys are provided or found in environment.

#### Methods

##### get()

```python
def get(self, url: str, **kwargs) -> requests.Response
```

Perform a GET request with automatic key rotation and retry logic.

**Parameters:**
- `url` (str): Target URL.
- `**kwargs`: Additional arguments passed to `requests.Session.request()`.

**Returns:**
- `requests.Response`: Response object from successful request.

**Raises:**
- `AllKeysExhaustedError`: If all keys fail after maximum retries.

**Example:**
```python
response = rotator.get("https://api.example.com/data")
print(response.json())
```

##### post(), put(), delete(), patch()

Similar to `get()`, but for different HTTP methods.

##### get_key_statistics()

```python
def get_key_statistics(self) -> Dict[str, Dict]
```

Get detailed statistics for all keys.

**Returns:**
- Dictionary mapping keys to their metrics (total_requests, success_rate, etc.)

##### get_metrics()

```python
def get_metrics(self) -> Optional[Dict]
```

Get general rotator metrics (if metrics enabled).

**Returns:**
- Dictionary with total requests, success rate, uptime, endpoint stats

##### reset_key_health()

```python
def reset_key_health(self, key: Optional[str] = None)
```

Reset health status for one or all keys.

##### export_config()

```python
def export_config(self) -> Dict
```

Export current rotator configuration.

##### refresh_keys_from_provider()

```python
async def refresh_keys_from_provider()
```

Refresh keys from the configured secret provider.

---

### AsyncAPIKeyRotator

Asynchronous API key rotator for `aiohttp`-based applications.

#### Constructor

Same parameters as `APIKeyRotator`.

#### Context Manager

`AsyncAPIKeyRotator` should be used as an async context manager:

```python
async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
    response = await rotator.get("https://api.example.com/data")
```

#### Methods

All methods are coroutines and must be awaited.

##### get(), post(), put(), delete(), etc.

```python
async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform async HTTP requests.

---

## Error Classification

### ErrorClassifier

Intelligent error classification for determining retry behavior.

#### Constructor

```python
ErrorClassifier(custom_retryable_codes: Optional[List[int]] = None)
```

**Parameters:**
- `custom_retryable_codes`: Additional HTTP status codes to treat as retryable

#### Methods

##### classify_error()

```python
def classify_error(
    self,
    response: Optional[requests.Response] = None,
    exception: Optional[Exception] = None
) -> ErrorType
```

Classify an error based on response or exception.

**Error Classification:**
- **RATE_LIMIT**: HTTP 429 → Switch to next key
- **TEMPORARY**: 5xx, 408, 409, 425, 503 → Retry with backoff
- **PERMANENT**: 401, 403, 404, 410, other 4xx → Remove key or fail
- **NETWORK**: Connection errors, timeouts → Retry or switch key
- **UNKNOWN**: Unclassified errors

**Example:**
```python
classifier = ErrorClassifier(custom_retryable_codes=[420])
error_type = classifier.classify_error(response=response)

if error_type == ErrorType.RATE_LIMIT:
    # Handle rate limit
    pass
```

##### is_retryable()

```python
def is_retryable(
    self,
    response: Optional[requests.Response] = None,
    exception: Optional[Exception] = None
) -> bool
```

Determine if request can be retried.

##### should_switch_key()

```python
def should_switch_key(
    self,
    response: Optional[requests.Response] = None,
    exception: Optional[Exception] = None
) -> bool
```

Determine if API key should be switched.

##### get_retry_delay()

```python
def get_retry_delay(
    self,
    response: Optional[requests.Response] = None,
    default_delay: float = 1.0
) -> float
```

Get recommended retry delay based on response headers.

### ErrorType (Enum)

```python
class ErrorType(Enum):
    RATE_LIMIT = "rate_limit"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    NETWORK = "network"
    UNKNOWN = "unknown"
```

---

## Rotation Strategies

### Base Strategy Classes

#### BaseRotationStrategy

Abstract base class for all rotation strategies.

```python
class BaseRotationStrategy(ABC):
    def __init__(self, keys: Union[List[str], Dict[str, float]])
    
    @abstractmethod
    def get_next_key(
        self,
        current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str
```

#### KeyMetrics

Per-key metrics tracking.

```python
class KeyMetrics:
    key: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    last_used: float
    last_success: float
    last_failure: float
    consecutive_failures: int
    rate_limit_hits: int
    is_healthy: bool
    success_rate: float
    rate_limit_reset: float
    requests_remaining: float
```

**Methods:**
- `update_from_request(success, response_time, is_rate_limited, **kwargs)`: Update metrics
- `get_score() -> float`: Calculate key quality score (0.0-1.0)
- `to_dict() -> Dict`: Serialize to dictionary

### Strategy Implementations

#### RoundRobinRotationStrategy

Cycles through keys sequentially.

```python
strategy = RoundRobinRotationStrategy(['key1', 'key2', 'key3'])
key = strategy.get_next_key()  # Returns 'key1', then 'key2', etc.
```

#### RandomRotationStrategy

Selects keys randomly.

```python
strategy = RandomRotationStrategy(['key1', 'key2', 'key3'])
key = strategy.get_next_key()  # Random key
```

#### WeightedRotationStrategy

Weighted selection based on assigned weights.

```python
strategy = WeightedRotationStrategy({
    'key1': 0.2,  # 20%
    'key2': 0.3,  # 30%
    'key3': 0.5   # 50%
})
```

#### LRURotationStrategy

Least Recently Used - selects least recently used key.

```python
strategy = LRURotationStrategy(['key1', 'key2', 'key3'])
key = strategy.get_next_key()  # Returns oldest unused key
```

#### HealthBasedStrategy

Selects only healthy keys, automatically excludes failing keys.

```python
strategy = HealthBasedStrategy(
    ['key1', 'key2', 'key3'],
    failure_threshold=5,
    health_check_interval=300  # Re-check after 5 minutes
)
```

### Factory Function

#### create_rotation_strategy()

```python
def create_rotation_strategy(
    strategy_type: Union[str, RotationStrategy],
    keys: Union[List[str], Dict[str, float]],
    **kwargs
) -> BaseRotationStrategy
```

**Example:**
```python
# Round robin
strategy = create_rotation_strategy('round_robin', ['key1', 'key2'])

# Weighted
strategy = create_rotation_strategy('weighted', {
    'key1': 1,
    'key2': 3
})

# Health-based with custom parameters
strategy = create_rotation_strategy(
    'health_based',
    ['key1', 'key2'],
    failure_threshold=10
)
```

---

## Middleware System

### RotatorMiddleware Protocol

Base protocol for all middleware.

```python
class RotatorMiddleware(Protocol):
    async def before_request(self, request_info: RequestInfo) -> RequestInfo
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo
    async def on_error(self, error_info: ErrorInfo) -> bool
```

### Middleware Classes

#### CachingMiddleware

Response caching with LRU eviction.

```python
CachingMiddleware(
    ttl: int = 300,
    cache_only_get: bool = True,
    max_cache_size: int = 1000,
    logger: Optional[logging.Logger] = None
)
```

**Methods:**
- `clear_cache()`: Clear all cached responses
- `get_stats() -> Dict`: Get cache statistics (hits, misses, hit_rate)

**Example:**
```python
cache_middleware = CachingMiddleware(ttl=600, max_cache_size=500)
rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[cache_middleware]
)

# View stats
stats = cache_middleware.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
```

#### LoggingMiddleware

Request/response logging with sensitive data masking.

```python
LoggingMiddleware(
    verbose: bool = True,
    logger: Optional[logging.Logger] = None,
    log_level: int = logging.INFO,
    log_response_time: bool = True,
    max_key_chars: int = 4
)
```

**Features:**
- Masks sensitive headers (Authorization, X-API-Key, Cookie)
- Logs request method, URL, status code
- Optional response time logging
- Configurable key masking

#### RateLimitMiddleware

Rate limit tracking and automatic pause.

```python
RateLimitMiddleware(
    pause_on_limit: bool = True,
    max_tracked_keys: int = 1000,
    logger: Optional[logging.Logger] = None
)
```

**Methods:**
- `get_stats() -> Dict`: Get rate limit statistics
- `clear_limits()`: Clear all rate limit records

**Features:**
- Extracts rate limit info from headers (X-RateLimit-*, Retry-After)
- Automatic waiting when rate limited
- Per-key rate limit tracking

#### RetryMiddleware

Advanced retry logic beyond the rotator's built-in retries.

```python
RetryMiddleware(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    max_tracked_urls: int = 1000,
    logger: Optional[logging.Logger] = None
)
```

**Methods:**
- `get_stats() -> Dict`: Get retry statistics
- `clear_retries()`: Clear retry counters

### Middleware Data Models

#### RequestInfo

```python
@dataclass
class RequestInfo:
    method: str
    url: str
    headers: Dict[str, str]
    cookies: Dict[str, str]
    key: str
    attempt: int
    kwargs: Dict[str, Any]
```

#### ResponseInfo

```python
@dataclass
class ResponseInfo:
    status_code: int
    headers: Dict[str, str]
    content: Any
    request_info: RequestInfo
```

#### ErrorInfo

```python
@dataclass
class ErrorInfo:
    exception: Exception
    request_info: RequestInfo
    response_info: Optional[ResponseInfo] = None
```

---

## Metrics & Monitoring

### RotatorMetrics

Central metrics collector.

```python
class RotatorMetrics:
    def record_request(
        self,
        key: str,
        endpoint: str,
        success: bool,
        response_time: float,
        is_rate_limited: bool = False
    )
    
    def get_metrics(self) -> Dict[str, Any]
    def get_endpoint_stats(self, endpoint: str) -> Dict[str, Any]
    def get_top_endpoints(self, limit: int = 10) -> List[Tuple[str, int]]
    def reset()
```

**Metrics Provided:**
- Total requests
- Successful/failed requests
- Success rate
- Uptime
- Per-endpoint statistics
- Average response times

**Example:**
```python
rotator = APIKeyRotator(api_keys=["key1"], enable_metrics=True)

# Make requests...
for i in range(100):
    rotator.get(f"https://api.example.com/item/{i}")

# Get metrics
metrics = rotator.get_metrics()
print(f"Success rate: {metrics['success_rate']:.2%}")
print(f"Total requests: {metrics['total_requests']}")

# Get key statistics
key_stats = rotator.get_key_statistics()
for key, stats in key_stats.items():
    print(f"Key {key[:4]}****: {stats['successful_requests']} successful")
```

### PrometheusExporter

Export metrics in Prometheus format.

```python
from apikeyrotator.metrics import PrometheusExporter

exporter = PrometheusExporter()
metrics_text = exporter.export(rotator.metrics)

# Write to file or serve via HTTP
with open('/var/lib/prometheus/node_exporter/rotator.prom', 'w') as f:
    f.write(metrics_text)
```

---

## Secret Providers

### SecretProvider Protocol

Base protocol for loading keys from external sources.

```python
class SecretProvider(Protocol):
    async def get_keys(self) -> List[str]
    async def refresh_keys(self) -> List[str]
```

### Provider Implementations

#### EnvironmentSecretProvider

Load from environment variable.

```python
from apikeyrotator.providers import EnvironmentSecretProvider

provider = EnvironmentSecretProvider(env_var="MY_API_KEYS")
rotator = APIKeyRotator(secret_provider=provider)
```

#### FileSecretProvider

Load from file (JSON, CSV, or line-by-line).

```python
from apikeyrotator.providers import FileSecretProvider

provider = FileSecretProvider(file_path="keys.json")
# Supports: ["key1", "key2"] or key1,key2,key3 or one-per-line
```

#### AWSSecretsManagerProvider

Load from AWS Secrets Manager.

```python
from apikeyrotator.providers import AWSSecretsManagerProvider

provider = AWSSecretsManagerProvider(
    secret_name="my-api-keys",
    region_name="us-east-1"
)

rotator = APIKeyRotator(secret_provider=provider)
```

**Requires:** `pip install boto3`

#### GCPSecretManagerProvider

Load from Google Cloud Secret Manager.

```python
from apikeyrotator.providers import GCPSecretManagerProvider

provider = GCPSecretManagerProvider(
    project_id="my-project",
    secret_id="api-keys",
    version_id="latest"
)
```

**Requires:** `pip install google-cloud-secret-manager`

### Factory Function

```python
from apikeyrotator.providers import create_secret_provider

# Environment
provider = create_secret_provider('env', env_var='API_KEYS')

# File
provider = create_secret_provider('file', file_path='keys.txt')

# AWS
provider = create_secret_provider(
    'aws_secrets_manager',
    secret_name='my-keys',
    region_name='us-east-1'
)

# GCP
provider = create_secret_provider(
    'gcp_secret_manager',
    project_id='my-project',
    secret_id='api-keys'
)
```

---

## Configuration Management

### ConfigLoader

Manages persistent configuration storage.

```python
ConfigLoader(
    config_file: str = "rotator_config.json",
    logger: Optional[logging.Logger] = None
)
```

**Methods:**
- `load_config() -> Dict[str, Any]`: Load configuration
- `save_config(config: Optional[Dict] = None)`: Save configuration
- `get(key: str, default: Any = None) -> Any`: Get config value
- `update_config(new_data: Dict)`: Update and save
- `clear()`: Clear configuration
- `delete_config_file()`: Remove config file

**Configuration Format:**
```json
{
  "successful_headers": {
    "api.example.com": {
      "User-Agent": "...",
      "Accept": "application/json"
    }
  }
}
```

---

## Exceptions

### NoAPIKeysError

Raised when no API keys are provided or found.

```python
class NoAPIKeysError(APIKeyError):
    """No API keys found"""
```

### AllKeysExhaustedError

Raised when all API keys fail after maximum retries.

```python
class AllKeysExhaustedError(APIKeyError):
    """All keys are exhausted"""
```

---

## Utilities

### Retry Utilities

#### retry_with_backoff()

```python
def retry_with_backoff(
    func: Callable,
    retries: int = 3,
    backoff_factor: float = 0.5,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
) -> Any
```

Synchronous retry with exponential backoff.

#### async_retry_with_backoff()

```python
async def async_retry_with_backoff(
    func: Callable,
    retries: int = 3,
    backoff_factor: float = 0.5,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
) -> Any
```

Asynchronous retry with exponential backoff.

#### exponential_backoff()

```python
def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0
) -> float
```

Calculate delay for exponential backoff.

#### jittered_backoff()

```python
def jittered_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0
) -> float
```

Calculate delay with random jitter (prevents thundering herd).

### Circuit Breaker

```python
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60
    )
    
    def allow_request(self) -> bool
    def record_success()
    def record_failure()
    def get_state(self) -> str  # 'CLOSED', 'OPEN', 'HALF_OPEN'
    def reset()
```

**Example:**
```python
breaker = CircuitBreaker(failure_threshold=5, timeout=60)

if breaker.allow_request():
    try:
        response = rotator.get(url)
        breaker.record_success()
    except Exception:
        breaker.record_failure()
```

### Decorators

#### measure_time()

```python
@measure_time
def my_function():
    # Function execution time will be logged
    pass
```

#### measure_time_async()

```python
@measure_time_async
async def my_async_function():
    # Async function execution time will be logged
    pass
```

---

## Type Hints

Common type hints used throughout the library:

```python
from typing import Optional, Union, List, Dict, Tuple, Callable, Any
import requests
import aiohttp

# Key types
KeyType = Union[List[str], str]

# Callback types
RetryCallback = Callable[[requests.Response], bool]
HeaderCallback = Callable[
    [str, Optional[Dict[str, str]]],
    Union[Dict[str, str], Tuple[Dict[str, str], Dict[str, str]]]
]

# Response types
SyncResponse = requests.Response
AsyncResponse = aiohttp.ClientResponse
```

---

## Next Steps

- See [Middleware Guide](MIDDLEWARE.md) for detailed middleware usage
- Check [Examples](EXAMPLES.md) for practical usage
- Read [Advanced Usage](ADVANCED_USAGE.md) for power features
- Review [Getting Started](GETTING_STARTED.md) for basics