# Error Handling

Comprehensive guide to error handling in APIKeyRotator.

## Table of Contents

- [Error Classification](#error-classification)
- [Built-in Exceptions](#built-in-exceptions)
- [Handling Specific Errors](#handling-specific-errors)
- [Custom Error Handling](#custom-error-handling)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Error Classification

APIKeyRotator uses an intelligent error classification system to determine how to handle different types of errors.

### ErrorType Enum

```python
from apikeyrotator import ErrorType

class ErrorType(Enum):
    RATE_LIMIT = "rate_limit"    # HTTP 429 or rate limit detected
    TEMPORARY = "temporary"       # 5xx errors, temporary server issues
    PERMANENT = "permanent"       # 401, 403, 400 - invalid credentials
    NETWORK = "network"           # Connection errors, timeouts
    UNKNOWN = "unknown"           # Unclassified errors
```

### How Errors Are Classified

```python
from apikeyrotator import ErrorClassifier

classifier = ErrorClassifier()

# Rate limit errors (429)
# → RATE_LIMIT: Switch to next key immediately

# Server errors (500-599)
# → TEMPORARY: Retry with exponential backoff

# Authentication errors (401, 403)
# → PERMANENT: Remove key from rotation

# Connection errors
# → NETWORK: Retry or switch key

# Other errors
# → UNKNOWN: Apply default retry logic
```

### Error Classification Flow

```
Request Fails
    ↓
Classify Error
    ↓
┌───────────────┬───────────────┬───────────────┬─────────────┐
│  RATE_LIMIT   │   TEMPORARY   │   PERMANENT   │   NETWORK   │
└───────────────┴───────────────┴───────────────┴─────────────┘
        ↓               ↓               ↓              ↓
   Switch Key      Retry with      Remove Key     Retry or
                   Backoff                        Switch Key
```

---

## Built-in Exceptions

### NoAPIKeysError

Raised when no API keys are provided or found.

```python
from apikeyrotator import APIKeyRotator, NoAPIKeysError

try:
    # No keys provided and none in environment
    rotator = APIKeyRotator(api_keys=[], load_env_file=False)
except NoAPIKeysError as e:
    print(f"No API keys available: {e}")
    # Load keys from alternative source
    # or exit gracefully
```

**When it occurs:**
- Empty key list provided
- Environment variable not set
- .env file missing or empty

**How to handle:**
```python
import os
from apikeyrotator import NoAPIKeysError

try:
    rotator = APIKeyRotator()
except NoAPIKeysError:
    # Fallback to manual key input
    keys = input("Enter API keys (comma-separated): ")
    rotator = APIKeyRotator(api_keys=keys)
```

### AllKeysExhaustedError

Raised when all API keys fail after maximum retries.

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(api_keys=["key1", "key2"], max_retries=3)

try:
    response = rotator.get("https://api.example.com/data")
except AllKeysExhaustedError as e:
    print(f"All keys failed: {e}")
    # Send alert to admin
    # Use backup system
    # Log to monitoring system
```

**When it occurs:**
- All keys are rate-limited
- All keys are invalid (401/403)
- API is completely down
- Network issues persist

**How to handle:**
```python
from apikeyrotator import AllKeysExhaustedError
import time

def fetch_with_backoff(url, max_attempts=3):
    """Retry entire operation if all keys fail."""
    
    for attempt in range(max_attempts):
        try:
            rotator = APIKeyRotator(api_keys=get_fresh_keys())
            return rotator.get(url)
            
        except AllKeysExhaustedError:
            if attempt < max_attempts - 1:
                wait_time = 60 * (2 ** attempt)  # 60s, 120s, 240s
                print(f"All keys failed, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
```

---

## Handling Specific Errors

### Rate Limit Errors

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError
import time

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    max_retries=5,
    base_delay=2.0  # Longer delays for rate limits
)

try:
    response = rotator.get("https://api.example.com/data")
    
except AllKeysExhaustedError as e:
    # All keys are rate-limited
    print("Rate limit exceeded on all keys")
    
    # Option 1: Wait and retry
    print("Waiting 5 minutes before retry...")
    time.sleep(300)
    response = rotator.get("https://api.example.com/data")
    
    # Option 2: Use alternative data source
    response = fetch_from_backup_api()
    
    # Option 3: Return cached data
    response = get_cached_data()
```

### Authentication Errors

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

def handle_auth_errors():
    """Handle authentication failures gracefully."""
    
    try:
        rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])
        response = rotator.get("https://api.example.com/protected")
        
    except AllKeysExhaustedError as e:
        error_message = str(e)
        
        if "401" in error_message or "403" in error_message:
            # Authentication issue
            print("Authentication failed for all keys")
            
            # Notify admin
            send_alert("API keys are invalid or expired")
            
            # Try to refresh keys
            new_keys = refresh_api_keys()
            if new_keys:
                rotator = APIKeyRotator(api_keys=new_keys)
                return rotator.get("https://api.example.com/protected")
        
        raise  # Re-raise if can't handle
```

### Network Errors

```python
from apikeyrotator import APIKeyRotator
import requests

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=5,
    timeout=30.0  # Longer timeout for slow networks
)

try:
    response = rotator.get("https://api.example.com/data")
    
except requests.exceptions.ConnectionError:
    print("Network connection failed")
    # Check internet connectivity
    # Try different network
    
except requests.exceptions.Timeout:
    print("Request timed out")
    # Increase timeout
    # Try with smaller data request
    
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
    # General request error handling
```

### Server Errors (5xx)

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=10,  # More retries for server issues
    base_delay=5.0   # Longer delays
)

try:
    response = rotator.get("https://api.example.com/data")
    
except AllKeysExhaustedError as e:
    if "500" in str(e) or "503" in str(e):
        print("API server is experiencing issues")
        
        # Check API status page
        status = check_api_status()
        
        if status == "maintenance":
            print("API is under maintenance")
            # Schedule retry later
            
        elif status == "outage":
            print("API is down")
            # Use cached data or alternative source
```

---

## Custom Error Handling

### Custom Error Classifier

```python
from apikeyrotator import ErrorClassifier, ErrorType, APIKeyRotator
import requests

class CustomErrorClassifier(ErrorClassifier):
    """Custom error classification for specific API."""
    
    def classify_error(self, response=None, exception=None) -> ErrorType:
        # Custom rate limit detection
        if response:
            # Check custom rate limit header
            if response.headers.get('X-RateLimit-Remaining') == '0':
                return ErrorType.RATE_LIMIT
            
            # Check custom error codes in response body
            try:
                data = response.json()
                error_code = data.get('error', {}).get('code')
                
                if error_code in ['QUOTA_EXCEEDED', 'TOO_MANY_REQUESTS']:
                    return ErrorType.RATE_LIMIT
                elif error_code in ['INVALID_TOKEN', 'EXPIRED_TOKEN']:
                    return ErrorType.PERMANENT
                elif error_code in ['SERVICE_UNAVAILABLE', 'MAINTENANCE']:
                    return ErrorType.TEMPORARY
            except:
                pass
        
        # Fall back to default classification
        return super().classify_error(response, exception)

# Use custom classifier
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    error_classifier=CustomErrorClassifier()
)
```

### Custom Retry Logic

```python
from apikeyrotator import APIKeyRotator
import requests

def custom_should_retry(response: requests.Response) -> bool:
    """
    Custom logic to determine if request should be retried.
    """
    # Don't retry client errors (4xx) except 429
    if 400 <= response.status_code < 500 and response.status_code != 429:
        return False
    
    # Check custom retry header
    if response.headers.get('X-Retry-After'):
        return True
    
    # Check response content
    try:
        data = response.json()
        # Retry on specific error messages
        if data.get('error', {}).get('retryable'):
            return True
    except:
        pass
    
    # Default: retry on 5xx and 429
    return response.status_code >= 500 or response.status_code == 429

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    should_retry_callback=custom_should_retry
)
```

### Graceful Degradation

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError
from typing import Optional, Dict

class ResilientAPIClient:
    """API client with graceful degradation."""
    
    def __init__(self, api_keys):
        self.rotator = APIKeyRotator(api_keys=api_keys)
        self.cache = {}
        self.fallback_enabled = True
    
    def get_data(self, endpoint: str) -> Optional[Dict]:
        """Get data with multiple fallback strategies."""
        
        # Strategy 1: Try with rotator
        try:
            response = self.rotator.get(f"https://api.example.com{endpoint}")
            data = response.json()
            self.cache[endpoint] = data  # Cache successful response
            return data
            
        except AllKeysExhaustedError:
            print("Primary API failed, trying fallbacks...")
        
        # Strategy 2: Return cached data
        if endpoint in self.cache:
            print("Returning cached data")
            return self.cache[endpoint]
        
        # Strategy 3: Try alternative API
        if self.fallback_enabled:
            try:
                return self._try_fallback_api(endpoint)
            except:
                pass
        
        # Strategy 4: Return default/empty data
        print("All strategies failed, returning default")
        return self._get_default_data(endpoint)
    
    def _try_fallback_api(self, endpoint: str) -> Dict:
        """Try alternative API endpoint."""
        # Implementation depends on your fallback API
        pass
    
    def _get_default_data(self, endpoint: str) -> Dict:
        """Return sensible defaults."""
        return {"status": "unavailable", "data": []}
```

---

## Best Practices

### 1. Always Handle Specific Exceptions

```python
# ✅ Good: Handle specific exceptions
from apikeyrotator import NoAPIKeysError, AllKeysExhaustedError

try:
    rotator = APIKeyRotator()
    response = rotator.get(url)
except NoAPIKeysError:
    handle_missing_keys()
except AllKeysExhaustedError:
    handle_exhausted_keys()
except Exception as e:
    handle_unexpected_error(e)

# ❌ Bad: Catch-all without specifics
try:
    response = rotator.get(url)
except:
    pass  # What went wrong?
```

### 2. Log Errors Appropriately

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    response = rotator.get(url)
except AllKeysExhaustedError as e:
    logger.error(f"All keys exhausted for {url}: {e}")
    logger.error(f"Keys used: {rotator.keys}")
    # Send to monitoring system
except Exception as e:
    logger.exception(f"Unexpected error: {e}")
```

### 3. Implement Circuit Breaker Pattern

```python
from datetime import datetime, timedelta
from typing import Optional

class CircuitBreaker:
    """Prevent repeated failures."""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time: Optional[datetime] = None
        self.is_open = False
    
    def call(self, func, *args, **kwargs):
        # Check if circuit is open
        if self.is_open:
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout):
                # Try to close circuit
                self.is_open = False
                self.failure_count = 0
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = func(*args, **kwargs)
            self.failure_count = 0  # Reset on success
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.is_open = True
            
            raise

# Usage
breaker = CircuitBreaker(failure_threshold=5, timeout=60)
rotator = APIKeyRotator(api_keys=["key1", "key2"])

try:
    response = breaker.call(rotator.get, "https://api.example.com/data")
except Exception as e:
    print(f"Request failed: {e}")
```

### 4. Set Appropriate Timeouts

```python
# ✅ Good: Set reasonable timeouts
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    timeout=30.0,  # 30 seconds for slow APIs
    max_retries=3
)

# ⚠️ Be cautious with very long timeouts
rotator = APIKeyRotator(
    api_keys=["key1"],
    timeout=300.0,  # 5 minutes might be too long
    max_retries=1
)
```

---

## Troubleshooting

### Problem: Requests Failing Immediately

**Symptoms:**
- All requests fail on first attempt
- No retries happening

**Possible Causes:**
```python
# Check 1: Are keys valid?
rotator = APIKeyRotator(api_keys=["test_key"])
try:
    response = rotator.get(url)
except Exception as e:
    print(f"Error: {e}")
    # Check if it's 401/403 (invalid key)

# Check 2: Is URL correct?
print(f"Requesting: {url}")

# Check 3: Are headers correct?
print(f"Headers: {rotator._generate_headers('test_key')}")
```

### Problem: Infinite Retries

**Symptoms:**
- Requests hang for very long time
- Many retry attempts

**Solution:**
```python
# Set lower max_retries and base_delay
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=3,  # Lower from default
    base_delay=1.0  # Reasonable delay
)
```

### Problem: Rate Limits Not Working

**Symptoms:**
- Getting rate limited despite multiple keys
- Keys not rotating

**Solution:**
```python
# Check 1: Are keys different accounts?
print(f"Keys: {rotator.keys}")

# Check 2: Add delays between requests
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    random_delay_range=(1.0, 3.0)  # Add delays
)

# Check 3: Check rate limit headers
response = rotator.get(url)
print(f"Rate limit remaining: {response.headers.get('X-RateLimit-Remaining')}")
```

### Problem: Memory Leaks

**Symptoms:**
- Memory usage grows over time
- Application slows down

**Solution:**
```python
# Close sessions properly
rotator = APIKeyRotator(api_keys=["key1"])
try:
    # Make requests
    response = rotator.get(url)
finally:
    rotator.session.close()  # Clean up

# Or use context manager for async
async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
    response = await rotator.get(url)
    # Automatically closed
```

---

## Next Steps

- See [Examples](EXAMPLES.md) for practical error handling patterns
- Read [Advanced Usage](ADVANCED_USAGE.md) for custom error classification
- Check [API Reference](API_REFERENCE.md) for exception documentation
- Review [FAQ](FAQ.md) for common issues