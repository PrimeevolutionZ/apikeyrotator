# API Reference

Complete reference documentation for all APIKeyRotator classes and methods.

## Classes

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
    config_loader: Optional[ConfigLoader] = None
)
```

**Parameters:**

| Parameter               | Type                              | Default                 | Description                                                                           |
|-------------------------|-----------------------------------|-------------------------|---------------------------------------------------------------------------------------|
| `api_keys`              | `Optional[Union[List[str], str]]` | `None`                  | List of API keys or comma-separated string. If `None`, loaded from environment.       |
| `env_var`               | `str`                             | `"API_KEYS"`            | Environment variable name to load keys from.                                          |
| `max_retries`           | `int`                             | `3`                     | Maximum retry attempts per key before moving to next key.                             |
| `base_delay`            | `float`                           | `1.0`                   | Base delay in seconds for exponential backoff: `base_delay * (2 ** attempt)`.         |
| `timeout`               | `float`                           | `10.0`                  | Request timeout in seconds.                                                           |
| `should_retry_callback` | `Optional[Callable]`              | `None`                  | Custom function `(response) -> bool` to determine retry logic.                        |
| `header_callback`       | `Optional[Callable]`              | `None`                  | Custom function `(key, headers) -> (headers, cookies)` for dynamic header generation. |
| `user_agents`           | `Optional[List[str]]`             | `None`                  | List of User-Agent strings to rotate through.                                         |
| `random_delay_range`    | `Optional[Tuple[float, float]]`   | `None`                  | Tuple of `(min, max)` for random delay before each request.                           |
| `proxy_list`            | `Optional[List[str]]`             | `None`                  | List of proxy URLs to rotate through.                                                 |
| `logger`                | `Optional[logging.Logger]`        | `None`                  | Custom logger instance. Creates default if not provided.                              |
| `config_file`           | `str`                             | `"rotator_config.json"` | Path to configuration file for storing learned settings.                              |
| `load_env_file`         | `bool`                            | `True`                  | Whether to automatically load `.env` file (requires `python-dotenv`).                 |
| `error_classifier`      | `Optional[ErrorClassifier]`       | `None`                  | Custom error classifier instance.                                                     |
| `config_loader`         | `Optional[ConfigLoader]`          | `None`                  | Custom configuration loader instance.                                                 |

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

##### post()

```python
def post(self, url: str, **kwargs) -> requests.Response
```

Perform a POST request with automatic key rotation and retry logic.

**Parameters:**
- `url` (str): Target URL.
- `**kwargs`: Additional arguments (e.g., `json`, `data`) passed to `requests.Session.request()`.

**Returns:**
- `requests.Response`: Response object from successful request.

**Example:**
```python
response = rotator.post(
    "https://api.example.com/create",
    json={"name": "test"}
)
```

##### put()

```python
def put(self, url: str, **kwargs) -> requests.Response
```

Perform a PUT request with automatic key rotation and retry logic.

##### delete()

```python
def delete(self, url: str, **kwargs) -> requests.Response
```

Perform a DELETE request with automatic key rotation and retry logic.

##### patch()

```python
def patch(self, url: str, **kwargs) -> requests.Response
```

Perform a PATCH request with automatic key rotation and retry logic.

##### head()

```python
def head(self, url: str, **kwargs) -> requests.Response
```

Perform a HEAD request with automatic key rotation and retry logic.

##### options()

```python
def options(self, url: str, **kwargs) -> requests.Response
```

Perform an OPTIONS request with automatic key rotation and retry logic.

---

### AsyncAPIKeyRotator

Asynchronous API key rotator for `aiohttp`-based applications.

#### Constructor

```python
AsyncAPIKeyRotator(
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
    config_loader: Optional[ConfigLoader] = None
)
```

Parameters are identical to `APIKeyRotator`.

#### Context Manager

`AsyncAPIKeyRotator` should be used as an async context manager:

```python
async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
    response = await rotator.get("https://api.example.com/data")
```

#### Methods

All methods are coroutines and must be awaited.

##### get()

```python
async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform an async GET request.

**Example:**
```python
async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
    response = await rotator.get("https://api.example.com/data")
    data = await response.json()
```

##### post()

```python
async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform an async POST request.

##### put()

```python
async def put(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform an async PUT request.

##### delete()

```python
async def delete(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform an async DELETE request.

##### patch()

```python
async def patch(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform an async PATCH request.

##### head()

```python
async def head(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform an async HEAD request.

##### options()

```python
async def options(self, url: str, **kwargs) -> aiohttp.ClientResponse
```

Perform an async OPTIONS request.

---

## Error Classification

### ErrorClassifier

Base class for error classification logic.

#### Constructor

```python
ErrorClassifier()
```

#### Methods

##### classify_error()

```python
def classify_error(
    self,
    response=None,
    exception=None
) -> ErrorType
```

Classify an error based on response or exception.

**Parameters:**
- `response`: HTTP response object (if available).
- `exception`: Exception object (if available).

**Returns:**
- `ErrorType`: Classification of the error.

**Example:**
```python
classifier = ErrorClassifier()
error_type = classifier.classify_error(response=response)

if error_type == ErrorType.RATE_LIMIT:
    # Switch to next key
    pass
elif error_type == ErrorType.PERMANENT:
    # Remove invalid key
    pass
```

### ErrorType (Enum)

Enumeration of error types:

```python
class ErrorType(Enum):
    RATE_LIMIT = "rate_limit"    # 429 or rate limit detected
    TEMPORARY = "temporary"       # 5xx server errors, temporary issues
    PERMANENT = "permanent"       # 401, 403, 400 - invalid key/request
    NETWORK = "network"           # Connection errors, timeouts
    UNKNOWN = "unknown"           # Unclassified errors
```

---

## Rotation Strategies

### RoundRobinRotationStrategy

Cycles through keys in sequential order.

```python
strategy = RoundRobinRotationStrategy(['key1', 'key2', 'key3'])
key = strategy.get_next_key()  # Returns 'key1', then 'key2', then 'key3', etc.
```

### RandomRotationStrategy

Selects keys randomly with equal probability.

```python
strategy = RandomRotationStrategy(['key1', 'key2', 'key3'])
key = strategy.get_next_key()  # Returns random key
```

### WeightedRotationStrategy

Selects keys based on assigned weights.

```python
strategy = WeightedRotationStrategy({
    'key1': 1,
    'key2': 2,
    'key3': 3
})
key = strategy.get_next_key()  # key3 selected most often
```

### create_rotation_strategy()

Factory function for creating rotation strategies.

```python
def create_rotation_strategy(
    strategy_type: str,
    keys: Union[List[str], Dict[str, int]]
) -> RotationStrategy
```

**Parameters:**
- `strategy_type`: One of `'round_robin'`, `'random'`, or `'weighted'`.
- `keys`: List of keys (for round_robin/random) or dict of key weights (for weighted).

**Returns:**
- Configured rotation strategy instance.

**Example:**
```python
strategy = create_rotation_strategy('weighted', {
    'key1': 1,
    'key2': 3
})
```

---

## Configuration Management

### ConfigLoader

Manages persistent configuration storage.

#### Constructor

```python
ConfigLoader(
    config_file: str = "rotator_config.json",
    logger: Optional[logging.Logger] = None
)
```

#### Methods

##### load_config()

```python
def load_config(self) -> Dict[str, Any]
```

Load configuration from file.

##### save_config()

```python
def save_config(self)
```

Save current configuration to file.

##### get_header_config()

```python
def get_header_config(self, domain: str) -> Optional[Dict]
```

Get saved header configuration for a domain.

##### save_header_config()

```python
def save_header_config(self, domain: str, config: Dict)
```

Save header configuration for a domain.

---

## Exceptions

### NoAPIKeysError

```python
class NoAPIKeysError(Exception):
    """Raised when no API keys are provided or found."""
```

**Example:**
```python
try:
    rotator = APIKeyRotator(api_keys=[])
except NoAPIKeysError as e:
    print(f"No keys available: {e}")
```

### AllKeysExhaustedError

```python
class AllKeysExhaustedError(Exception):
    """Raised when all API keys have failed after maximum retries."""
```

**Example:**
```python
try:
    response = rotator.get("https://api.example.com/data")
except AllKeysExhaustedError as e:
    print(f"All keys failed: {e}")
    # Notify admin, use backup system, etc.
```

---

## Callback Signatures

### should_retry_callback

```python
def should_retry_callback(response: requests.Response) -> bool:
    """
    Determine if a request should be retried.
    
    Args:
        response: The HTTP response object
        
    Returns:
        True if the request should be retried, False otherwise
    """
    pass
```

### header_callback

```python
def header_callback(
    key: str,
    existing_headers: Optional[Dict[str, str]]
) -> Union[Dict[str, str], Tuple[Dict[str, str], Dict[str, str]]]:
    """
    Generate custom headers and optionally cookies.
    
    Args:
        key: The current API key
        existing_headers: Headers that would be used by default
        
    Returns:
        Either a dict of headers, or a tuple of (headers, cookies)
    """
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

## Configuration File Format

The `rotator_config.json` file stores learned configurations:

```json
{
  "domains": {
    "api.example.com": {
      "auth_header": "Authorization",
      "auth_format": "Bearer {key}",
      "last_success": "2025-11-10T12:00:00Z"
    },
    "api.another.com": {
      "auth_header": "X-API-Key",
      "auth_format": "{key}",
      "last_success": "2025-11-10T11:30:00Z"
    }
  },
  "version": "0.4.0"
}
```

---

## Environment Variables

### API_KEYS

Default environment variable for loading API keys:

```bash
# .env file
API_KEYS=key1,key2,key3
```

### Custom Environment Variable

You can specify a custom environment variable:

```python
rotator = APIKeyRotator(env_var="MY_CUSTOM_KEYS")
```

```bash
# .env file
MY_CUSTOM_KEYS=custom_key1,custom_key2
```

---

## Next Steps

- See [Examples](EXAMPLES.md) for practical usage
- Read [Advanced Usage](ADVANCED_USAGE.md) for power features
- Check [Error Handling](ERROR_HANDLING.md) for error management
- Review [Getting Started](GETTING_STARTED.md) for basics