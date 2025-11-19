# Advanced Usage

This guide covers advanced features and configuration options for power users.

## Table of Contents

- [Middleware System](#middleware-system)
- [Rotation Strategies](#rotation-strategies)
- [Metrics and Monitoring](#metrics-and-monitoring)
- [Secret Providers](#secret-providers)
- [Custom Callbacks](#custom-callbacks)
- [Anti-Bot Evasion](#anti-bot-evasion)
- [Custom Error Classification](#custom-error-classification)
- [Session Management](#session-management)
- [Configuration Management](#configuration-management)
- [Performance Optimization](#performance-optimization)

---

## Middleware System

APIKeyRotator 0.4.3+ includes a powerful middleware system for intercepting and processing requests/responses.

### Overview

Middleware allows you to:
- Cache responses to reduce API calls
- Log requests and responses
- Track and handle rate limits
- Implement custom retry logic
- Modify headers dynamically
- Collect detailed metrics

**[📖 Complete Middleware Guide →](MIDDLEWARE.md)**

### Quick Example

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import (
    CachingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware
)

# Create middleware instances
cache = CachingMiddleware(ttl=600, max_cache_size=1000)
logger = LoggingMiddleware(verbose=True)
rate_limit = RateLimitMiddleware(pause_on_limit=True)

# Initialize rotator with middleware
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    middlewares=[cache, logger, rate_limit]
)

# Middleware automatically:
# - Caches responses
# - Logs all requests
# - Handles rate limits
response = rotator.get("https://api.example.com/data")
```

### Built-in Middleware

#### CachingMiddleware

Cache responses to reduce API calls:

```python
from apikeyrotator.middleware import CachingMiddleware

cache = CachingMiddleware(
    ttl=300,              # Cache for 5 minutes
    cache_only_get=True,  # Only cache GET requests
    max_cache_size=1000   # Store up to 1000 responses
)

rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[cache]
)

# View cache statistics
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Cache size: {stats['cache_size']}/{stats['max_cache_size']}")

# Clear cache if needed
cache.clear_cache()
```

#### LoggingMiddleware

Detailed request/response logging:

```python
from apikeyrotator.middleware import LoggingMiddleware

logger = LoggingMiddleware(
    verbose=True,           # Include detailed info
    log_response_time=True, # Log request duration
    max_key_chars=4         # Show only first 4 chars of key
)

rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[logger]
)

# Automatically logs:
# 📤 GET https://api.example.com/data (key: key1****, attempt: 1)
# 📥 ✅ 200 from https://api.example.com/data (0.234s)
```

#### RateLimitMiddleware

Automatic rate limit tracking:

```python
from apikeyrotator.middleware import RateLimitMiddleware

rate_limit = RateLimitMiddleware(
    pause_on_limit=True,  # Wait when rate limited
    max_tracked_keys=100
)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[rate_limit]
)

# Middleware automatically:
# - Extracts rate limit info from headers
# - Waits when limits are hit
# - Tracks limits per key
```

#### RetryMiddleware

Additional retry logic:

```python
from apikeyrotator.middleware import RetryMiddleware

retry = RetryMiddleware(
    max_retries=5,
    backoff_factor=2.0
)

rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[retry]
)
```

### Custom Middleware

Create your own middleware:

```python
from apikeyrotator.middleware import RequestInfo, ResponseInfo, ErrorInfo

class CustomHeaderMiddleware:
    """Add custom headers to all requests."""
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        request_info.headers["X-Client-Version"] = "2.0"
        request_info.headers["X-Request-ID"] = generate_id()
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        print(f"Response: {response_info.status_code}")
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        print(f"Error: {error_info.exception}")
        return False  # Don't handle, let rotator retry

# Use custom middleware
custom = CustomHeaderMiddleware()
rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[custom]
)
```

**[📖 Learn More About Middleware →](MIDDLEWARE.md)**

---

## Rotation Strategies

Control how keys are selected for each request.

### Available Strategies

#### Round Robin (Default)

Cycles through keys sequentially:

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    rotation_strategy="round_robin"
)

# Keys used in order: key1 → key2 → key3 → key1 → ...
```

#### Random

Selects keys randomly:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    rotation_strategy="random"
)

# Each request uses a random key
```

#### Weighted

Prioritize certain keys:

```python
from apikeyrotator import APIKeyRotator, create_rotation_strategy

# Create weighted strategy
strategy = create_rotation_strategy('weighted', {
    'key1': 1,  # Low priority (10%)
    'key2': 3,  # Medium priority (30%)
    'key3': 6   # High priority (60%)
})

rotator = APIKeyRotator(
    api_keys=strategy.keys(),
    rotation_strategy=strategy
)
```

#### LRU (Least Recently Used)

Selects the least recently used key:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    rotation_strategy="lru"
)

# Always uses the key that hasn't been used in the longest time
```

#### Health-Based

Only uses healthy keys:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    rotation_strategy="health_based",
    rotation_strategy_kwargs={
        'failure_threshold': 5,       # Mark unhealthy after 5 failures
        'health_check_interval': 300  # Recheck every 5 minutes
    }
)

# Automatically excludes failing keys
# Re-checks unhealthy keys periodically
```

### Custom Strategy

Create your own rotation strategy:

```python
from apikeyrotator.strategies import BaseRotationStrategy, KeyMetrics
from typing import Dict, Optional

class PriorityRotationStrategy(BaseRotationStrategy):
    """Prioritize keys based on success rate."""
    
    def __init__(self, keys):
        super().__init__(keys)
    
    def get_next_key(
        self,
        current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        if not current_key_metrics:
            return self._keys[0]
        
        # Select key with highest success rate
        best_key = max(
            current_key_metrics.items(),
            key=lambda x: x[1].success_rate
        )
        return best_key[0]

# Use custom strategy
strategy = PriorityRotationStrategy(['key1', 'key2', 'key3'])
rotator = APIKeyRotator(
    api_keys=['key1', 'key2', 'key3'],
    rotation_strategy=strategy
)
```

---

## Metrics and Monitoring

Track and monitor rotator performance.

### Enable Metrics

```python
from apikeyrotator import APIKeyRotator

# Metrics enabled by default
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    enable_metrics=True
)

# Make requests...
for i in range(100):
    rotator.get(f"https://api.example.com/data/{i}")

# Get overall metrics
metrics = rotator.get_metrics()
print(f"Total requests: {metrics['total_requests']}")
print(f"Success rate: {metrics['success_rate']:.2%}")
print(f"Uptime: {metrics['uptime_seconds']:.1f}s")
```

### Per-Key Statistics

```python
# Get statistics for each key
key_stats = rotator.get_key_statistics()

for key, stats in key_stats.items():
    print(f"\nKey: {key[:4]}****")
    print(f"  Requests: {stats['total_requests']}")
    print(f"  Success rate: {stats['success_rate']:.2%}")
    print(f"  Avg response time: {stats['avg_response_time']:.3f}s")
    print(f"  Healthy: {'✅' if stats['is_healthy'] else '❌'}")
    print(f"  Rate limit hits: {stats['rate_limit_hits']}")
```

### Per-Endpoint Statistics

```python
metrics = rotator.get_metrics()

for endpoint, stats in metrics['endpoint_stats'].items():
    print(f"\nEndpoint: {endpoint}")
    print(f"  Total requests: {stats['total_requests']}")
    print(f"  Successful: {stats['successful_requests']}")
    print(f"  Failed: {stats['failed_requests']}")
    print(f"  Avg time: {stats['avg_response_time']:.3f}s")
```

### Prometheus Export

Export metrics in Prometheus format:

```python
from apikeyrotator.metrics import PrometheusExporter

# Make requests
rotator = APIKeyRotator(api_keys=["key1", "key2"])
for i in range(100):
    rotator.get(f"https://api.example.com/data/{i}")

# Export to Prometheus format
exporter = PrometheusExporter()
metrics_text = exporter.export(rotator.metrics)

# Save to file for node_exporter
with open('/var/lib/prometheus/node_exporter/rotator.prom', 'w') as f:
    f.write(metrics_text)
```

### Export Configuration

```python
# Export current configuration
config = rotator.export_config()

print(f"Keys: {config['keys_count']}")
print(f"Strategy: {config['rotation_strategy']}")
print(f"Max retries: {config['max_retries']}")
print(f"Metrics enabled: {config['enable_metrics']}")
```

---

## Secret Providers

Load API keys from external secret management systems.

### AWS Secrets Manager

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.providers import AWSSecretsManagerProvider

# Create provider
provider = AWSSecretsManagerProvider(
    secret_name="my-api-keys",
    region_name="us-east-1"
)

# Initialize rotator with provider
rotator = APIKeyRotator(secret_provider=provider)

# Keys are automatically loaded from AWS
response = rotator.get("https://api.example.com/data")

# Refresh keys periodically
import asyncio

async def refresh_keys():
    await rotator.refresh_keys_from_provider()
    print("Keys refreshed from AWS")

asyncio.run(refresh_keys())
```

**Requires:** `pip install boto3`

### Google Cloud Secret Manager

```python
from apikeyrotator.providers import GCPSecretManagerProvider

provider = GCPSecretManagerProvider(
    project_id="my-project",
    secret_id="api-keys",
    version_id="latest"
)

rotator = APIKeyRotator(secret_provider=provider)
```

**Requires:** `pip install google-cloud-secret-manager`

### File Provider

```python
from apikeyrotator.providers import FileSecretProvider

# From JSON file: ["key1", "key2", "key3"]
# From CSV: key1,key2,key3
# From text: one key per line
provider = FileSecretProvider(file_path="keys.json")

rotator = APIKeyRotator(secret_provider=provider)
```

### Environment Provider

```python
from apikeyrotator.providers import EnvironmentSecretProvider

provider = EnvironmentSecretProvider(env_var="MY_API_KEYS")
rotator = APIKeyRotator(secret_provider=provider)
```

### Factory Function

```python
from apikeyrotator.providers import create_secret_provider

# Create any provider via factory
provider = create_secret_provider(
    'aws_secrets_manager',
    secret_name='my-keys',
    region_name='us-east-1'
)

rotator = APIKeyRotator(secret_provider=provider)
```

---

## Custom Callbacks

### Custom Retry Logic

Define your own conditions for retrying requests:

```python
from apikeyrotator import APIKeyRotator
import requests

def should_retry(response: requests.Response) -> bool:
    """
    Custom retry logic based on response content.
    """
    # Retry on rate limit
    if response.status_code == 429:
        return True
    
    # Retry if response contains error indicator
    try:
        data = response.json()
        if data.get('status') == 'error' and data.get('code') == 'temporary':
            return True
    except:
        pass
    
    return False

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    should_retry_callback=should_retry
)
```

### Dynamic Header Generation

Generate headers and cookies dynamically for each request:

```python
from typing import Dict, Tuple, Optional
import time

def generate_headers(
    key: str, 
    existing_headers: Optional[Dict]
) -> Tuple[Dict, Dict]:
    """
    Generate custom headers and cookies.
    
    Returns:
        Tuple of (headers, cookies)
    """
    headers = {
        "X-API-Key": key,
        "X-Client-Version": "2.0",
        "X-Request-ID": generate_request_id(),
        "X-Timestamp": str(int(time.time()))
    }
    
    cookies = {
        "session_token": get_session_token(key),
        "preference": "json"
    }
    
    return headers, cookies

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    header_callback=generate_headers
)
```

**Note:** If your callback returns only headers (not a tuple), cookies will be empty:

```python
def simple_headers(key: str, existing: Optional[Dict]) -> Dict:
    """Return only headers."""
    return {
        "X-API-Key": key,
        "X-Client": "MyApp"
    }

rotator = APIKeyRotator(
    api_keys=["key1"],
    header_callback=simple_headers
)
```

---

## Anti-Bot Evasion

Avoid detection and bypass anti-bot measures.

### User-Agent Rotation

Rotate through different browser user agents:

```python
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    
    # Chrome on Android
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36"
]

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    user_agents=USER_AGENTS
)

# Each request uses a different User-Agent
```

### Random Delays

Add human-like delays between requests:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    random_delay_range=(0.5, 2.5)  # Random delay between 0.5-2.5 seconds
)

# Each request will have a random delay before execution
for i in range(100):
    response = rotator.get(f"https://api.example.com/item/{i}")
```

**Delay calculation:** Random value between min and max, plus 0-10% jitter to avoid patterns.

### Proxy Rotation

Distribute requests across multiple proxy servers:

```python
PROXIES = [
    "http://user:pass@proxy1.example.com:8080",
    "http://user:pass@proxy2.example.com:8080",
    "socks5://user:pass@proxy3.example.com:1080"
]

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    proxy_list=PROXIES
)

# Each request uses a different proxy
response = rotator.get("https://api.example.com/data")
```

### Combined Anti-Bot Strategy

Combine all anti-bot features:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    user_agents=USER_AGENTS,
    random_delay_range=(1.0, 3.0),
    proxy_list=PROXIES,
    max_retries=5,
    base_delay=2.0
)

# Now you have:
# ✓ Multiple API keys
# ✓ Rotating User-Agents
# ✓ Random delays
# ✓ Rotating proxies
# ✓ Smart retry logic
```

---

## Custom Error Classification

Implement custom error classification logic:

```python
from apikeyrotator import ErrorClassifier, ErrorType
import requests

class CustomErrorClassifier(ErrorClassifier):
    """Custom error classifier with domain-specific logic."""
    
    def classify_error(
        self,
        response=None,
        exception=None
    ) -> ErrorType:
        # Handle custom API error responses
        if response:
            # Custom rate limit code
            if response.status_code == 420:
                return ErrorType.RATE_LIMIT
            
            # Check response body
            try:
                data = response.json()
                error_code = data.get('error', {}).get('code')
                
                if error_code == 'quota_exceeded':
                    return ErrorType.RATE_LIMIT
                elif error_code == 'invalid_key':
                    return ErrorType.PERMANENT
                elif error_code == 'temporary_failure':
                    return ErrorType.TEMPORARY
            except:
                pass
        
        # Fall back to default classification
        return super().classify_error(response, exception)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    error_classifier=CustomErrorClassifier()
)
```

### Custom Retryable Codes

Add custom HTTP status codes that should be retried:

```python
classifier = ErrorClassifier(
    custom_retryable_codes=[420, 509]  # Custom codes to retry
)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    error_classifier=classifier
)
```

---

## Session Management

### Custom Session Configuration

Configure connection pooling and timeout:

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    timeout=30.0  # 30 seconds timeout
)

# Connection pooling is automatically configured:
# - 100 connections per pool
# - Efficient connection reuse
```

### Session Cleanup

Always clean up sessions:

```python
# Synchronous
rotator = APIKeyRotator(api_keys=["key1"])
try:
    response = rotator.get(url)
finally:
    rotator.session.close()

# Asynchronous (preferred)
async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
    response = await rotator.get(url)
    # Automatically closed
```

---

## Configuration Management

### Custom Config File Location

Store configuration in a custom location:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    config_file="/path/to/custom/config.json"
)
```

### Disable Config Persistence

Disable automatic config saving:

```python
from apikeyrotator import ConfigLoader

class NoOpConfigLoader(ConfigLoader):
    """Config loader that doesn't save anything."""
    
    def save_config(self, config=None):
        pass  # Do nothing
    
    def load_config(self):
        return {}

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    config_loader=NoOpConfigLoader(config_file="", logger=None)
)
```

### Sensitive Headers

Control whether sensitive headers are saved:

```python
# Don't save sensitive headers (default, more secure)
rotator = APIKeyRotator(
    api_keys=["key1"],
    save_sensitive_headers=False
)

# Save sensitive headers (less secure, but remembers auth)
rotator = APIKeyRotator(
    api_keys=["key1"],
    save_sensitive_headers=True
)
```

When `save_sensitive_headers=False`, the following headers are excluded from saved configuration:
- `Authorization`
- `X-API-Key`
- `Cookie`

---

## Performance Optimization

### For High-Volume Requests

Use async for I/O-bound operations:

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def process_many_urls(urls):
    async with AsyncAPIKeyRotator(
        api_keys=["key1", "key2", "key3"],
        timeout=5.0  # Lower timeout for faster failures
    ) as rotator:
        # Process in large batches
        tasks = [rotator.get(url) for url in urls[:1000]]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        return responses

# Process 1000 URLs concurrently
urls = [f"https://api.example.com/item/{i}" for i in range(1000)]
results = asyncio.run(process_many_urls(urls))
```

### For Low-Latency Requirements

Minimize overhead:

```python
rotator = APIKeyRotator(
    api_keys=["key1"],
    max_retries=2,           # Fewer retries
    base_delay=0.5,          # Shorter delays
    random_delay_range=None, # No random delays
    user_agents=None,        # No UA rotation
    enable_metrics=False     # Disable metrics collection
)
```

### Connection Pooling

Connection pooling is automatically configured for optimal performance:

```python
# Default configuration (already optimized):
# - Pool size: 100 connections
# - Reuses connections efficiently
# - Minimal connection overhead

rotator = APIKeyRotator(api_keys=["key1", "key2"])
# No additional configuration needed
```

### Concurrent Async Requests with Semaphore

Control concurrency to prevent overwhelming the API:

```python
import asyncio
from asyncio import Semaphore
from apikeyrotator import AsyncAPIKeyRotator

async def fetch_with_limit(urls, max_concurrent=50):
    """Fetch URLs with concurrency limit."""
    
    semaphore = Semaphore(max_concurrent)
    
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
        async def fetch_one(url):
            async with semaphore:
                return await rotator.get(url)
        
        tasks = [fetch_one(url) for url in urls]
        return await asyncio.gather(*tasks)

# Fetch 1000 URLs with max 50 concurrent requests
urls = [f"https://api.example.com/item/{i}" for i in range(1000)]
results = asyncio.run(fetch_with_limit(urls, max_concurrent=50))
```

---

## Best Practices

### 1. Key Management

```python
# ✅ Good: Load from environment
rotator = APIKeyRotator()  # Uses .env file

# ✅ Good: Use secret provider
from apikeyrotator.providers import AWSSecretsManagerProvider
provider = AWSSecretsManagerProvider(secret_name="my-keys")
rotator = APIKeyRotator(secret_provider=provider)

# ❌ Bad: Hardcode keys
rotator = APIKeyRotator(api_keys=["hardcoded_key_123"])
```

### 2. Error Handling

```python
# ✅ Good: Specific exception handling
from apikeyrotator import AllKeysExhaustedError

try:
    response = rotator.get(url)
except AllKeysExhaustedError:
    # Handle this specific case
    log_failure_and_alert()
except Exception as e:
    # Handle other errors
    log_error(e)

# ❌ Bad: Catch-all without distinction
try:
    response = rotator.get(url)
except:
    pass
```

### 3. Resource Cleanup

```python
# ✅ Good: Use context manager for async
async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
    response = await rotator.get(url)

# ✅ Good: Explicit cleanup for sync
rotator = APIKeyRotator(api_keys=["key1"])
try:
    response = rotator.get(url)
finally:
    rotator.session.close()
```

### 4. Rate Limit Configuration

```python
# ✅ Good: Conservative settings for strict APIs
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    max_retries=5,
    base_delay=2.0,
    random_delay_range=(1.0, 3.0)
)

# ⚠️ Use with caution: Aggressive settings
rotator = APIKeyRotator(
    api_keys=["key1"],
    max_retries=1,
    base_delay=0.1,
    random_delay_range=None
)
```

### 5. Use Middleware for Cross-Cutting Concerns

```python
# ✅ Good: Use middleware for caching, logging, etc.
from apikeyrotator.middleware import CachingMiddleware, LoggingMiddleware

rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[
        CachingMiddleware(ttl=600),
        LoggingMiddleware(verbose=True)
    ]
)

# ❌ Bad: Implement caching/logging manually in application code
```

---

## Next Steps

- See [Middleware Guide](MIDDLEWARE.md) for detailed middleware documentation
- Check [Examples](EXAMPLES.md) for real-world use cases
- Read [API Reference](API_REFERENCE.md) for complete parameter documentation
- Review [Error Handling](ERROR_HANDLING.md) for comprehensive error management
- See [FAQ](FAQ.md) for common questions