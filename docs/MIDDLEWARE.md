# Middleware Guide

Comprehensive guide to APIKeyRotator's middleware system for request/response interception and processing.

## Table of Contents

- [Overview](#overview)
- [Middleware Architecture](#middleware-architecture)
- [Built-in Middleware](#built-in-middleware)
- [Creating Custom Middleware](#creating-custom-middleware)
- [Middleware Best Practices](#middleware-best-practices)
- [Advanced Patterns](#advanced-patterns)
- [Performance Considerations](#performance-considerations)

---

## Overview

Middleware in APIKeyRotator provides a powerful way to intercept and modify HTTP requests and responses. Middleware runs in a pipeline, allowing you to:

- **Cache responses** to reduce API calls
- **Log requests and responses** for debugging and monitoring
- **Track rate limits** and pause when necessary
- **Implement custom retry logic** beyond the rotator's built-in retries
- **Modify headers** dynamically
- **Validate responses** before they reach your application
- **Collect metrics** and statistics
- **Handle errors** in a centralized way

### Key Concepts

**Middleware Pipeline**: Middleware executes in order:
```
Request → Middleware 1 → Middleware 2 → Middleware 3 → API
API → Middleware 3 → Middleware 2 → Middleware 1 → Response
```

**Three Hooks**:
- `before_request`: Called before sending the request
- `after_request`: Called after receiving a successful response
- `on_error`: Called when an error occurs

---

## Middleware Architecture

### RotatorMiddleware Protocol

All middleware must implement the `RotatorMiddleware` protocol:

```python
from apikeyrotator.middleware import RequestInfo, ResponseInfo, ErrorInfo

class RotatorMiddleware(Protocol):
    """Base protocol for middleware."""
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Called before sending the request.
        
        Args:
            request_info: Information about the request
            
        Returns:
            Modified request_info (or original if no changes)
        """
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Called after receiving a successful response.
        
        Args:
            response_info: Information about the response
            
        Returns:
            Modified response_info (or original if no changes)
        """
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Called when an error occurs.
        
        Args:
            error_info: Information about the error
            
        Returns:
            True if error was handled (prevents propagation)
            False to allow error to propagate
        """
        return False
```

### Data Models

#### RequestInfo

Contains all information about an outgoing request:

```python
@dataclass
class RequestInfo:
    method: str              # HTTP method (GET, POST, etc.)
    url: str                 # Target URL
    headers: Dict[str, str]  # Request headers
    cookies: Dict[str, str]  # Request cookies
    key: str                 # Current API key being used
    attempt: int             # Current attempt number (0-indexed)
    kwargs: Dict[str, Any]   # Additional request parameters
```

#### ResponseInfo

Contains information about a received response:

```python
@dataclass
class ResponseInfo:
    status_code: int         # HTTP status code
    headers: Dict[str, str]  # Response headers
    content: Any             # Response body
    request_info: RequestInfo  # Original request info
```

#### ErrorInfo

Contains information about an error:

```python
@dataclass
class ErrorInfo:
    exception: Exception      # The exception that occurred
    request_info: RequestInfo # Original request info
    response_info: Optional[ResponseInfo]  # Response if available
```

---

## Built-in Middleware

### CachingMiddleware

Caches GET request responses to reduce API calls.

#### Features

- **LRU Eviction**: Automatically evicts least recently used entries when cache is full
- **TTL Support**: Cached entries expire after specified time
- **Configurable Size**: Control maximum cache size
- **Statistics**: Track hit rate and cache effectiveness

#### Usage

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import CachingMiddleware

# Create cache middleware
cache = CachingMiddleware(
    ttl=600,              # Cache for 10 minutes
    cache_only_get=True,  # Only cache GET requests
    max_cache_size=1000   # Store up to 1000 responses
)

# Use with rotator
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[cache]
)

# First request - cache miss
response1 = rotator.get("https://api.example.com/data")

# Second request - cache hit (instant)
response2 = rotator.get("https://api.example.com/data")

# View statistics
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Cache size: {stats['cache_size']}/{stats['max_cache_size']}")

# Clear cache if needed
cache.clear_cache()
```

#### Cache Key Generation

Cache keys are generated based on:
- HTTP method
- URL
- Relevant headers (excluding Authorization, cookies)
- Request body (for POST/PUT/PATCH)

This ensures different requests are cached separately.

#### Methods

```python
cache.clear_cache()          # Clear all cached responses
stats = cache.get_stats()    # Get cache statistics
```

**Statistics returned**:
- `cache_size`: Number of cached responses
- `max_cache_size`: Maximum cache capacity
- `hits`: Number of cache hits
- `misses`: Number of cache misses
- `hit_rate`: Percentage of requests served from cache
- `total_requests`: Total requests processed

---

### LoggingMiddleware

Logs all requests and responses with sensitive data masking.

#### Features

- **Sensitive Data Masking**: Automatically masks Authorization, API keys, cookies
- **Configurable Verbosity**: Control detail level
- **Response Time Logging**: Track request duration
- **Color-Coded Output**: Easy visual parsing (via emojis)
- **Traceback Support**: Full error tracebacks in DEBUG mode

#### Usage

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import LoggingMiddleware
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create logging middleware
log_middleware = LoggingMiddleware(
    verbose=True,              # Include detailed info
    log_response_time=True,    # Log request duration
    max_key_chars=4            # Show only first 4 chars of key
)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[log_middleware]
)

# Make request - automatically logged
response = rotator.get("https://api.example.com/data")

# Example output:
# 📤 GET https://api.example.com/data (key: key1****, attempt: 1)
# 📥 ✅ 200 from https://api.example.com/data (key: key1****) (0.234s)
```

#### Log Levels

The middleware uses different log levels based on response status:

- **200-299**: INFO with ✅
- **400-499**: WARNING with ⚠️
- **500-599**: ERROR with ❌

#### Sensitive Data Protection

The following headers are automatically masked:
- `Authorization`
- `X-API-Key`
- `Cookie`
- `Set-Cookie`

Example:
```python
# Original: {"Authorization": "Bearer secret_token_123"}
# Logged:   {"Authorization": "[REDACTED]"}
```

---

### RateLimitMiddleware

Tracks rate limits and automatically pauses when limits are hit.

#### Features

- **Header Parsing**: Extracts rate limit info from response headers
- **Automatic Pausing**: Waits until rate limit expires
- **Multi-Key Tracking**: Tracks rate limits per API key
- **429 Handling**: Automatically handles 429 Too Many Requests

#### Usage

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import RateLimitMiddleware

# Create rate limit middleware
rate_limit = RateLimitMiddleware(
    pause_on_limit=True,      # Automatically wait when rate limited
    max_tracked_keys=1000     # Track up to 1000 keys
)

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    middlewares=[rate_limit]
)

# Make requests - middleware handles rate limits automatically
for i in range(10000):
    response = rotator.get(f"https://api.example.com/data/{i}")
    # If rate limited, middleware will automatically pause

# View rate limit statistics
stats = rate_limit.get_stats()
print(f"Tracked keys: {stats['tracked_keys']}")
print(f"Active limits: {stats['active_limits']}")

# Clear rate limit records if needed
rate_limit.clear_limits()
```

#### Supported Headers

The middleware recognizes these standard headers:

- `X-RateLimit-Limit`: Total request limit
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Unix timestamp when limit resets
- `Retry-After`: Seconds to wait or HTTP date

#### Behavior on Rate Limit

When a key is rate limited:

1. Extract rate limit reset time from headers
2. Store reset time for the key
3. Before next request with that key, check if reset time has passed
4. If not passed and `pause_on_limit=True`, wait until reset
5. If not passed and `pause_on_limit=False`, proceed (likely to fail again)

---

### RetryMiddleware

Provides additional retry logic on top of the rotator's built-in retries.

#### Features

- **URL-Based Tracking**: Tracks retry attempts per URL
- **Exponential Backoff**: Configurable backoff factor
- **Automatic Cleanup**: Removes successful URLs from tracking
- **LRU Eviction**: Prevents memory bloat with many URLs

#### Usage

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import RetryMiddleware

# Create retry middleware
retry = RetryMiddleware(
    max_retries=5,           # Retry up to 5 times per URL
    backoff_factor=2.0,      # Double delay each retry
    max_tracked_urls=1000    # Track up to 1000 URLs
)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[retry]
)

# Middleware will retry failed requests automatically
response = rotator.get("https://api.example.com/flaky-endpoint")

# View retry statistics
stats = retry.get_stats()
print(f"Active retries: {stats['active_retries']}")
print(f"Tracked URLs: {stats['tracked_urls']}")

# Clear retry counters if needed
retry.clear_retries()
```

#### Retry Logic

The middleware:

1. Tracks retry count per URL
2. On error, checks if max retries reached
3. If not, waits with exponential backoff
4. Returns `True` to signal rotator to retry
5. If max retries reached, returns `False` to fail

**Backoff calculation**: `backoff_factor ^ retry_count`

Example with `backoff_factor=2.0`:
- Retry 0: 1 second
- Retry 1: 2 seconds
- Retry 2: 4 seconds
- Retry 3: 8 seconds
- Retry 4: 16 seconds

---

## Creating Custom Middleware

### Basic Custom Middleware

```python
from apikeyrotator.middleware import RequestInfo, ResponseInfo, ErrorInfo

class CustomHeaderMiddleware:
    """Add custom headers to all requests."""
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        # Modify request before sending
        request_info.headers["X-Custom-Header"] = "MyValue"
        request_info.headers["X-Request-Timestamp"] = str(time.time())
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Process response after receiving
        print(f"Received {response_info.status_code} from {response_info.request_info.url}")
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        # Handle errors
        print(f"Error occurred: {error_info.exception}")
        return False  # Don't handle, let it propagate

# Usage
custom = CustomHeaderMiddleware()
rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[custom]
)
```

### Response Validation Middleware

```python
class ResponseValidationMiddleware:
    """Validate response data structure."""
    
    def __init__(self, required_fields: List[str]):
        self.required_fields = required_fields
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Parse JSON response
        try:
            if response_info.content:
                data = json.loads(response_info.content)
                
                # Validate required fields
                missing = [f for f in self.required_fields if f not in data]
                if missing:
                    raise ValueError(f"Missing required fields: {missing}")
        except json.JSONDecodeError:
            pass  # Not JSON, skip validation
        
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        return False

# Usage
validator = ResponseValidationMiddleware(
    required_fields=["id", "name", "created_at"]
)

rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[validator]
)
```

### Metrics Collection Middleware

```python
from collections import defaultdict
import time

class MetricsMiddleware:
    """Collect detailed request metrics."""
    
    def __init__(self):
        self.metrics = defaultdict(lambda: {
            'count': 0,
            'total_time': 0.0,
            'errors': 0,
            'status_codes': defaultdict(int)
        })
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        # Store start time
        request_info.kwargs['_start_time'] = time.time()
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Calculate duration
        start_time = response_info.request_info.kwargs.get('_start_time', 0)
        duration = time.time() - start_time
        
        # Update metrics
        url = response_info.request_info.url
        self.metrics[url]['count'] += 1
        self.metrics[url]['total_time'] += duration
        self.metrics[url]['status_codes'][response_info.status_code] += 1
        
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        url = error_info.request_info.url
        self.metrics[url]['errors'] += 1
        return False
    
    def get_metrics(self) -> Dict:
        """Get collected metrics."""
        return {
            url: {
                'count': stats['count'],
                'avg_time': stats['total_time'] / stats['count'] if stats['count'] > 0 else 0,
                'errors': stats['errors'],
                'status_codes': dict(stats['status_codes'])
            }
            for url, stats in self.metrics.items()
        }

# Usage
metrics = MetricsMiddleware()
rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[metrics]
)

# Make requests...
for i in range(100):
    rotator.get(f"https://api.example.com/data/{i}")

# View metrics
for url, stats in metrics.get_metrics().items():
    print(f"{url}: {stats['count']} requests, {stats['avg_time']:.3f}s avg")
```

### Authentication Middleware

```python
import jwt
from datetime import datetime, timedelta

class JWTAuthMiddleware:
    """Automatically refresh JWT tokens."""
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.token = None
        self.token_expiry = None
    
    def _generate_token(self) -> str:
        """Generate new JWT token."""
        payload = {
            'api_key': self.api_key,
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        return jwt.encode(payload, self.api_secret, algorithm='HS256')
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        # Check if token is expired or missing
        if not self.token or datetime.utcnow() >= self.token_expiry:
            self.token = self._generate_token()
            self.token_expiry = datetime.utcnow() + timedelta(minutes=55)
            print("Generated new JWT token")
        
        # Add token to request
        request_info.headers["Authorization"] = f"Bearer {self.token}"
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Check if token was rejected
        if response_info.status_code == 401:
            # Force token refresh on next request
            self.token = None
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        return False

# Usage
jwt_auth = JWTAuthMiddleware(
    api_key="my_api_key",
    api_secret="my_secret"
)

rotator = APIKeyRotator(
    api_keys=["dummy"],  # Not used, JWT handles auth
    middlewares=[jwt_auth]
)
```

---

## Middleware Best Practices

### 1. Order Matters

Middleware executes in the order specified. Choose the right order:

```python
# Good: Cache checks first, then logging
middlewares = [cache, logger, rate_limit]

# Bad: Logging before cache means cache hits are logged
middlewares = [logger, cache, rate_limit]

# Good for security: Validate first, then process
middlewares = [validator, processor, logger]
```

### 2. Keep Middleware Focused

Each middleware should have a single responsibility:

```python
# Good: Separate concerns
class CachingMiddleware:
    # Only handles caching

class LoggingMiddleware:
    # Only handles logging

# Bad: Mixed concerns
class CachingAndLoggingMiddleware:
    # Handles both - harder to test and reuse
```

### 3. Handle Errors Gracefully

Always use try-except in middleware:

```python
class SafeMiddleware:
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        try:
            # Risky operation
            request_info.headers["X-Token"] = self.get_token()
        except Exception as e:
            # Log error but don't break the request
            print(f"Middleware error: {e}")
        return request_info
```

### 4. Make Middleware Configurable

Allow customization through constructor parameters:

```python
class ConfigurableMiddleware:
    def __init__(
        self,
        enabled: bool = True,
        timeout: int = 300,
        max_size: int = 1000
    ):
        self.enabled = enabled
        self.timeout = timeout
        self.max_size = max_size
```

### 5. Provide Statistics and Introspection

```python
class WellDesignedMiddleware:
    def get_stats(self) -> Dict:
        """Return current statistics."""
        return {
            'requests_processed': self.count,
            'cache_hits': self.hits
        }
    
    def reset(self):
        """Reset internal state."""
        self.count = 0
        self.hits = 0
```

---

## Advanced Patterns

### Conditional Middleware

Middleware that only runs for certain requests:

```python
class ConditionalMiddleware:
    """Only process requests to specific domains."""
    
    def __init__(self, allowed_domains: List[str]):
        self.allowed_domains = allowed_domains
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        from urllib.parse import urlparse
        domain = urlparse(request_info.url).netloc
        
        if domain in self.allowed_domains:
            # Apply middleware logic
            request_info.headers["X-Special-Header"] = "Value"
        
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        return False

# Usage
conditional = ConditionalMiddleware(
    allowed_domains=["api.example.com", "api.other.com"]
)
```

### Composite Middleware

Combine multiple middleware into one:

```python
class CompositeMiddleware:
    """Combine multiple middleware."""
    
    def __init__(self, middlewares: List):
        self.middlewares = middlewares
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        for middleware in self.middlewares:
            request_info = await middleware.before_request(request_info)
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        for middleware in reversed(self.middlewares):
            response_info = await middleware.after_request(response_info)
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        for middleware in self.middlewares:
            if await middleware.on_error(error_info):
                return True
        return False

# Usage
composite = CompositeMiddleware([
    CachingMiddleware(),
    LoggingMiddleware(),
    RateLimitMiddleware()
])

rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[composite]
)
```

### State Sharing Between Middleware

```python
class SharedStateMiddleware:
    """Share state between middleware instances."""
    
    _shared_state = {}
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        # Store request ID in shared state
        request_id = str(uuid.uuid4())
        self._shared_state[request_id] = {
            'start_time': time.time(),
            'url': request_info.url
        }
        request_info.kwargs['_request_id'] = request_id
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Retrieve and use shared state
        request_id = response_info.request_info.kwargs.get('_request_id')
        if request_id in self._shared_state:
            state = self._shared_state.pop(request_id)
            duration = time.time() - state['start_time']
            print(f"Request {request_id} took {duration:.3f}s")
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        # Cleanup shared state on error
        request_id = error_info.request_info.kwargs.get('_request_id')
        if request_id in self._shared_state:
            del self._shared_state[request_id]
        return False
```

---

## Performance Considerations

### 1. Minimize Overhead

Keep middleware logic lightweight:

```python
# Good: Simple and fast
async def before_request(self, request_info):
    request_info.headers["X-Fast"] = "true"
    return request_info

# Bad: Slow and blocking
async def before_request(self, request_info):
    # Don't do expensive operations here
    result = self.expensive_database_query()
    request_info.headers["X-Data"] = result
    return request_info
```

### 2. Use Async Properly

All middleware methods are async - use `await` for I/O operations:

```python
async def before_request(self, request_info):
    # Good: Non-blocking
    await asyncio.sleep(0.1)
    
    # Bad: Blocks event loop
    time.sleep(0.1)
    
    return request_info
```

### 3. Limit Memory Usage

Implement cleanup for long-running middleware:

```python
class MemoryEfficientMiddleware:
    def __init__(self, max_cache_size: int = 1000):
        self.cache = OrderedDict()
        self.max_cache_size = max_cache_size
    
    async def after_response(self, response_info):
        # Evict old entries
        if len(self.cache) >= self.max_cache_size:
            self.cache.popitem(last=False)
        
        # Add new entry
        self.cache[response_info.request_info.url] = response_info
        return response_info
```

### 4. Profile Middleware Performance

```python
from apikeyrotator.utils import measure_time_async

class ProfiledMiddleware:
    @measure_time_async
    async def before_request(self, request_info):
        # This will log execution time
        # Do middleware work
        return request_info
```

---

## Next Steps

- See [Examples](EXAMPLES.md) for practical middleware usage
- Check [API Reference](API_REFERENCE.md) for complete middleware API
- Read [Advanced Usage](ADVANCED_USAGE.md) for more patterns
- Review [Getting Started](GETTING_STARTED.md) for basics