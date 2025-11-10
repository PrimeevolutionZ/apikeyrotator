# Advanced Usage

This guide covers advanced features and configuration options for power users.

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
        "X-Request-ID": generate_request_id()
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

## Anti-Bot Evasion

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

# Requests will be distributed across proxies
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
    max_retries=5
)
```

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
            if response.status_code == 420:  # Custom rate limit code
                return ErrorType.RATE_LIMIT
            
            try:
                data = response.json()
                if data.get('error_type') == 'quota_exceeded':
                    return ErrorType.RATE_LIMIT
                elif data.get('error_type') == 'invalid_key':
                    return ErrorType.PERMANENT
            except:
                pass
        
        # Fall back to default classification
        return super().classify_error(response, exception)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    error_classifier=CustomErrorClassifier()
)
```

## Rotation Strategies

### Round Robin Strategy

Cycle through keys in order:

```python
from apikeyrotator import create_rotation_strategy

strategy = create_rotation_strategy('round_robin', ['key1', 'key2', 'key3'])

# Keys are used in order: key1 -> key2 -> key3 -> key1 ...
```

### Random Strategy

Select keys randomly:

```python
strategy = create_rotation_strategy('random', ['key1', 'key2', 'key3'])

# Keys are selected randomly with equal probability
```

### Weighted Strategy

Assign different weights to keys:

```python
strategy = create_rotation_strategy('weighted', {
    'key1': 1,   # Low priority
    'key2': 3,   # Medium priority
    'key3': 6    # High priority
})

# key3 will be used ~60% of the time
# key2 will be used ~30% of the time
# key1 will be used ~10% of the time
```

## Asynchronous Advanced Features

### Concurrent Requests

Make multiple concurrent requests efficiently:

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def fetch_multiple(urls):
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
        tasks = [rotator.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return responses

urls = [f"https://api.example.com/item/{i}" for i in range(100)]
results = asyncio.run(fetch_multiple(urls))
```

### Rate Limit Aware Batching

Process items in batches with rate limit awareness:

```python
async def process_in_batches(items, batch_size=10):
    async with AsyncAPIKeyRotator(
        api_keys=["key1", "key2", "key3"],
        max_retries=5
    ) as rotator:
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            tasks = [
                rotator.get(f"https://api.example.com/item/{item}")
                for item in batch
            ]
            
            try:
                responses = await asyncio.gather(*tasks)
                for response in responses:
                    data = await response.json()
                    yield data
            except Exception as e:
                print(f"Batch failed: {e}")
```

## Session Management

### Custom Session Configuration

Configure the underlying HTTP session:

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Create custom session
session = requests.Session()

# Configure connection pooling
adapter = HTTPAdapter(
    pool_connections=100,
    pool_maxsize=100,
    max_retries=Retry(total=0)  # Disable urllib3 retries (use rotator's)
)

session.mount('http://', adapter)
session.mount('https://', adapter)

# Use custom session (note: you'd need to pass this to the rotator's internal session)
# The rotator creates its own session, but you can configure similar settings via timeout
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    timeout=30.0  # Longer timeout for slow APIs
)
```

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
    
    def save_config(self):
        pass  # Do nothing
    
    def load_config(self):
        return {}

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    config_loader=NoOpConfigLoader(config_file="", logger=None)
)
```

## Logging Configuration

### Custom Logger

Use a custom logger with specific formatting:

```python
import logging

# Create custom logger
logger = logging.getLogger("MyAPIRotator")
logger.setLevel(logging.DEBUG)

# Add custom handler
handler = logging.FileHandler("api_rotator.log")
handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
logger.addHandler(handler)

# Use custom logger
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    logger=logger
)
```

### Detailed Debug Logging

Enable detailed logging for debugging:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

rotator = APIKeyRotator(api_keys=["key1", "key2"])

# Now all operations will be logged in detail
response = rotator.get("https://api.example.com/data")
```

## Best Practices

### 1. Key Management

```python
# ✅ Good: Load from environment
rotator = APIKeyRotator()  # Uses .env file

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

## Performance Optimization

### For High-Volume Requests

```python
# Use async for I/O-bound operations
async with AsyncAPIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    timeout=5.0  # Lower timeout for faster failures
) as rotator:
    
    # Process in large batches
    tasks = [rotator.get(url) for url in urls[:1000]]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
```

### For Low-Latency Requirements

```python
# Minimize overhead
rotator = APIKeyRotator(
    api_keys=["key1"],
    max_retries=2,  # Fewer retries
    base_delay=0.5,  # Shorter delays
    random_delay_range=None,  # No random delays
    user_agents=None  # No UA rotation
)
```

## Next Steps

- See [Examples](EXAMPLES.md) for real-world use cases
- Check [API Reference](API_REFERENCE.md) for complete parameter documentation
- Read [Error Handling](ERROR_HANDLING.md) for comprehensive error management
- Review [FAQ](FAQ.md) for common questions