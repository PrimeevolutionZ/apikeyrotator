# APIKeyRotator

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.4.0-blue.svg)](https://pypi.org/project/apikeyrotator/)

**A powerful, simple, and resilient API key rotator for Python.**

`APIKeyRotator` is a Python library designed to make your API interactions more robust. It seamlessly handles API key rotation, automatically manages rate limits, retries on errors, and can even mimic human-like behavior to avoid bot detection. With both synchronous and asynchronous support, it's a drop-in enhancement for your `requests` or `aiohttp` based projects.

## 📚 Documentation

**[→ Full Documentation](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/INDEX.md)**

- [Getting Started Guide](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/GETTING_STARTED.md) - Installation and basic usage
- [API Reference](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/API_REFERENCE.md) - Complete API documentation
- [Examples](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/EXAMPLES.md) - Real-world code examples
- [Advanced Usage](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/ADVANCED_USAGE.md) - Power features and customization
- [Error Handling](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/ERROR_HANDLING.md) - Comprehensive error management
- [FAQ](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/FAQ.md) - Frequently asked questions

## Key Features

*   **Effortless Integration:** An intuitive API that mirrors popular libraries like `requests` and `aiohttp`.
*   **Automatic Key Rotation:** Cycles through your API keys to distribute load and bypass rate limits.
*   **Smart Retries with Exponential Backoff:** Automatically retries failed requests with increasing delays to handle temporary server issues.
*   **Advanced Anti-Bot Evasion:**
    *   **User-Agent Rotation:** Rotates `User-Agent` headers to simulate requests from different browsers.
    *   **Random Delays:** Injects random delays between requests to avoid predictable, bot-like patterns.
    *   **Proxy Rotation:** Distributes requests across a list of proxies for IP address rotation.
*   **Intelligent Header Management:**
    *   **Auto-Detection:** Infers the correct authorization header (`Bearer`, `X-API-Key`, etc.) based on key format.
    *   **Configuration Persistence:** Learns and saves successful header configurations for specific domains to a `rotator_config.json` file, making future requests more efficient.
*   **Enhanced Logging:** Provides detailed, configurable logging for full visibility into the rotator's operations.
*   **Flexible Configuration:**
    *   **`.env` Support:** Automatically loads API keys and other settings from a `.env` file.
    *   **Custom Logic:** Allows you to provide your own functions for retry conditions and dynamic header/cookie generation.
*   **Session Management:** Utilizes `requests.Session` and `aiohttp.ClientSession` for connection pooling and persistent cookie handling.

## Installation

```bash
pip install apikeyrotator
```

### Optional Dependencies

```bash
# For synchronous requests (recommended)
pip install requests

# For asynchronous requests
pip install aiohttp

# For environment variable management
pip install python-dotenv

# Install all optional dependencies
pip install apikeyrotator[all]
```

## Quick Start

### Simple Example

```python
from apikeyrotator import APIKeyRotator

# Your API keys can be loaded from a .env file or passed directly.
# Create a .env file with: API_KEYS="key1,key2,key3"

# Initialize the rotator. It will automatically find your keys.
rotator = APIKeyRotator()

try:
    # Use it just like the requests library!
    response = rotator.get("https://api.example.com/data")
    response.raise_for_status()
    print("Success!", response.json())

except Exception as e:
    print(f"An error occurred: {e}")
```

### With Configuration

```python
import logging
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

# For detailed output, configure a logger.
logging.basicConfig(level=logging.INFO)

# A list of common user agents to rotate through.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
]

rotator = APIKeyRotator(
    # Provide keys directly or load from environment variables.
    api_keys=["key_1", "key_2", "key_3"],
    
    # Retry & Timeout Settings
    max_retries=5,
    base_delay=1.0,
    timeout=15.0,
    
    # Anti-Bot Evasion
    user_agents=USER_AGENTS,
    random_delay_range=(1.0, 3.0),
)

try:
    response = rotator.get("https://api.example.com/data")
    response.raise_for_status()
    print(f"Success: {response.status_code}")

except AllKeysExhaustedError as e:
    print(f"All keys and retries failed: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
```

### Asynchronous Usage

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def main():
    async with AsyncAPIKeyRotator(
        api_keys=["key_async_1", "key_async_2"],
        max_retries=3
    ) as rotator:
        try:
            response = await rotator.get("https://api.example.com/async_data")
            data = await response.json()
            print(f"Async Success: {response.status}", data)

        except Exception as e:
            print(f"An async error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Core Concepts

### Automatic Key Rotation

APIKeyRotator automatically switches between your API keys when:
- A rate limit is encountered (HTTP 429)
- An authentication error occurs (HTTP 401/403)
- Network errors happen
- After maximum retries on the current key

### Smart Retry Logic

Failed requests are automatically retried with exponential backoff:
- Delay formula: `base_delay * (2 ** attempt)`
- Configurable maximum retries per key
- Intelligent error classification

### Intelligent Header Detection

The library automatically detects and uses the correct authorization header format:
- Bearer tokens (for JWT-like keys)
- API keys in various header formats
- Custom headers via callbacks
- Learned configurations are persisted

## Use Cases

### Rate Limit Management
```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    max_retries=5,
    base_delay=2.0
)

# Make many requests without worrying about rate limits
for item_id in range(1000):
    response = rotator.get(f"https://api.example.com/items/{item_id}")
```

### Web Scraping
```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    user_agents=[...],
    random_delay_range=(1.0, 3.0),
    proxy_list=["http://proxy1.com:8080", "http://proxy2.com:8080"]
)
```

### High-Volume Data Collection
```python
async with AsyncAPIKeyRotator(api_keys=["key1", "key2", "key3"]) as rotator:
    tasks = [rotator.get(url) for url in urls]
    responses = await asyncio.gather(*tasks)
```

## Configuration Options

| Parameter               | Type                  | Default      | Description                               |
|-------------------------|-----------------------|--------------|-------------------------------------------|
| `api_keys`              | `List[str]` or `str`  | `None`       | API keys (comma-separated string or list) |
| `env_var`               | `str`                 | `"API_KEYS"` | Environment variable name for keys        |
| `max_retries`           | `int`                 | `3`          | Maximum retry attempts per key            |
| `base_delay`            | `float`               | `1.0`        | Base delay for exponential backoff        |
| `timeout`               | `float`               | `10.0`       | Request timeout in seconds                |
| `user_agents`           | `List[str]`           | `None`       | List of User-Agent strings to rotate      |
| `random_delay_range`    | `Tuple[float, float]` | `None`       | Random delay range (min, max)             |
| `proxy_list`            | `List[str]`           | `None`       | List of proxy URLs                        |
| `should_retry_callback` | `Callable`            | `None`       | Custom retry logic function               |
| `header_callback`       | `Callable`            | `None`       | Custom header generation function         |
| `error_classifier`      | `ErrorClassifier`     | `None`       | Custom error classifier                   |

[→ See full API reference](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/API_REFERENCE.md)

## Error Handling

```python
from apikeyrotator import (
    APIKeyRotator,
    NoAPIKeysError,
    AllKeysExhaustedError
)

try:
    rotator = APIKeyRotator(api_keys=["key1", "key2"])
    response = rotator.get("https://api.example.com/data")
    
except NoAPIKeysError:
    print("No API keys were provided or found")
    
except AllKeysExhaustedError:
    print("All keys failed after maximum retries")
    
except Exception as e:
    print(f"Unexpected error: {e}")
```

[→ Learn more about error handling](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/ERROR_HANDLING.md)

## Advanced Features

### Custom Error Classification

```python
from apikeyrotator import ErrorClassifier, ErrorType

class CustomErrorClassifier(ErrorClassifier):
    def classify_error(self, response=None, exception=None) -> ErrorType:
        if response and response.status_code == 420:
            return ErrorType.RATE_LIMIT
        return super().classify_error(response, exception)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    error_classifier=CustomErrorClassifier()
)
```

### Custom Retry Logic

```python
def custom_retry(response):
    if response.status_code == 429:
        return True
    try:
        return 'error' in response.json().get('status', '')
    except:
        return False

rotator = APIKeyRotator(
    api_keys=["key1"],
    should_retry_callback=custom_retry
)
```

### Dynamic Headers

```python
def header_callback(key, existing_headers):
    return {
        "Authorization": f"Bearer {key}",
        "X-Client-Version": "2.0"
    }, {"session": "token"}

rotator = APIKeyRotator(
    api_keys=["key1"],
    header_callback=header_callback
)
```

[→ Explore advanced usage](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/ADVANCED_USAGE.md)

## Enhanced Error Handling with `ErrorClassifier`

One of the most significant improvements is the introduction of `ErrorClassifier`. Instead of relying solely on HTTP status codes, the rotator now uses a dedicated classification system to determine the nature of an error. This allows for more nuanced decision-making:

*   **`RATE_LIMIT`**: Indicates that the request failed due to rate limiting. The rotator will typically switch to the next key immediately.
*   **`TEMPORARY`**: Suggests a transient issue (e.g., 5xx server errors). The rotator will retry the request, potentially with the same key after a backoff period.
*   **`PERMANENT`**: Signifies a persistent problem (e.g., 401 Unauthorized, 403 Forbidden). The key causing this error will be marked as invalid and removed from the rotation pool.
*   **`NETWORK`**: Catches network-related exceptions (e.g., connection errors, timeouts), prompting a retry or key switch.

This intelligent error classification minimizes unnecessary retries on permanently invalid keys and ensures that rate-limited keys are quickly bypassed, improving overall efficiency and resilience.

## Performance

### Connection Pooling

The synchronous `APIKeyRotator` uses connection pooling for optimal performance:
- Reuses TCP connections
- Configured with `pool_connections=100` and `pool_maxsize=100`
- Reduces overhead for multiple requests

### Concurrency

For maximum performance with many requests:

```python
# Async for I/O-bound tasks
async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
    tasks = [rotator.get(url) for url in urls]
    responses = await asyncio.gather(*tasks)

# Result: 100x faster for 100 concurrent requests
```

## Multithreading and Concurrency

*   **Concurrency (`asyncio`):** The `AsyncAPIKeyRotator` is the recommended choice for I/O-bound tasks (like making many network requests). It leverages `asyncio` to handle thousands of concurrent requests efficiently without blocking.

*   **Multithreading:** While you can use the synchronous `APIKeyRotator` in a multithreaded application, be aware of Python's Global Interpreter Lock (GIL). For most API-related tasks, `asyncio` provides superior performance. If you need to use threads, it's safe to create a separate `APIKeyRotator` instance per thread.

## Examples

Check out the [examples directory](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/EXAMPLES.md) for more use cases:

- Web scraping with anti-bot features
- Data collection from multiple endpoints
- REST and GraphQL API integration
- Production-ready patterns with monitoring
- Batch processing with progress tracking

## Testing

Run the test suite:

```bash
# Install test dependencies
pip install pytest pytest-asyncio requests-mock aioresponses

# Run tests
pytest test_all.py -v
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This library is distributed under the MIT License. See the `LICENSE` file for more information.

## Links

- **GitHub:** [github.com/PrimeevolutionZ/apikeyrotator](https://github.com/PrimeevolutionZ/apikeyrotator)
- **PyPI:** [pypi.org/project/apikeyrotator](https://pypi.org/project/apikeyrotator/)
- **Documentation:** [Full Documentation](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/INDEX.md)
- **Issues:** [GitHub Issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues)

## Support

If you encounter any issues or have questions:

1. Check the [FAQ](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/FAQ.md)
2. Search [existing issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues)
3. Read the [documentation](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/apikeyrotator/docs/INDEX.md)
4. Open a [new issue](https://github.com/PrimeevolutionZ/apikeyrotator/issues/new) with details

---

**Made with ❤️ by [Eclips Team](https://github.com/PrimeevolutionZ)**