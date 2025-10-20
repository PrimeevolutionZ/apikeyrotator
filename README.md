# APIKeyRotator

**A powerful, simple, and resilient API key rotator for Python.**

`APIKeyRotator` is a Python library designed to make your API interactions more robust. It seamlessly handles API key rotation, automatically manages rate limits, retries on errors, and can even mimic human-like behavior to avoid bot detection. With both synchronous and asynchronous support, it's a drop-in enhancement for your `requests` or `aiohttp` based projects.

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

## Getting Started: A Simple Example

The library is designed to be incredibly simple to use. Here’s a basic example:

```python
from apikeyrotator import APIKeyRotator

# Your API keys can be loaded from a .env file or passed directly.
# Create a .env file with: API_KEYS="key1,key2,key3"

# Initialize the rotator. It will automatically find your keys.
rotator = APIKeyRotator(
    # You can optionally pass custom instances of ErrorClassifier and ConfigLoader
    # error_classifier=MyCustomErrorClassifier(),
    # config_loader=MyCustomConfigLoader(config_file="my_custom_config.json"),
    # For this simple example, we'll let the rotator use its defaults.
) # This is a comment to indicate that the default behavior is still simple.
)


try:
    # Use it just like the requests library!
    response = rotator.get("https://api.example.com/data")
    response.raise_for_status()
    print("Success!", response.json())

except Exception as e:
    print(f"An error occurred: {e}")
```

## Advanced Usage & Configuration

Unlock the full power of `APIKeyRotator` by customizing its behavior.

### Full Configuration

Here is an example demonstrating all the major configuration options for the synchronous `APIKeyRotator`.

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

# A list of proxies to rotate through (optional).
PROXY_LIST = ["http://user:pass@proxy1.com:8080", "http://user:pass@proxy2.com:8080"]

rotator = APIKeyRotator(
    # Provide keys directly or load from environment variables.
    api_keys=["key_sync_1", "key_sync_2"],

    # --- Retry & Timeout Settings ---
    max_retries=5,          # Max retries per key before giving up.
    base_delay=0.5,         # Base delay in seconds for exponential backoff.
    timeout=15.0,           # Request timeout in seconds.

    # --- Anti-Bot Evasion ---
    user_agents=USER_AGENTS,            # List of User-Agents to rotate.
    random_delay_range=(1.0, 3.0),      # Random delay between 1 and 3 seconds before each request.
    proxy_list=PROXY_LIST,              # List of proxies for IP rotation.

    # --- Advanced Customization ---
    logger=logging.getLogger("MyRotator"), # Provide a custom logger instance.
    config_file="my_config.json",       # Custom path for the config file.
    load_env_file=True,                 # Set to False to disable .env loading.
    # New parameters for modularity:
    # error_classifier=ErrorClassifier(), # Use a custom error classifier
    # config_loader=ConfigLoader(config_file="my_custom_config.json", logger=logging.getLogger("MyRotator")), # Use a custom config loader
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

### Asynchronous Mode (`AsyncAPIKeyRotator`)

The asynchronous version, `AsyncAPIKeyRotator`, works seamlessly with `asyncio` and has a similar API to `aiohttp`.

**Important Note on Usage:** When using `AsyncAPIKeyRotator` methods (like `get`, `post`, etc.) with `async with`, you must `await` the method call itself, as it returns a coroutine that resolves to an `aiohttp.ClientResponse` object, which is the actual asynchronous context manager.

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

### Custom Callbacks for Maximum Flexibility

You can inject your own logic for handling retries and generating headers/cookies.

#### `should_retry_callback`

Define custom conditions for when a request should be retried.

```python
import requests

def custom_retry_logic(response: requests.Response) -> bool:
    # Retry on 429 (Too Many Requests) or if the response body contains 'error'.
    if response.status_code == 429:
        return True
    try:
        return 'error' in response.json().get('status', '')
    except requests.exceptions.JSONDecodeError:
        return False

rotator = APIKeyRotator(api_keys=["my_key"], should_retry_callback=custom_retry_logic)
```

#### `header_callback`

Dynamically generate headers and cookies, perfect for handling complex authentication.

```python
from typing import Tuple, Optional, Dict

def dynamic_header_and_cookie_generator(key: str, existing_headers: Optional[Dict]) -> Tuple[Dict, Dict]:
    headers = {"X-Custom-Auth": f"Token {key}"}
    cookies = {"session_id": "some_session_value_from_a_previous_login"}
    return headers, cookies

rotator = APIKeyRotator(api_keys=["my_key"], header_callback=dynamic_header_and_cookie_generator)
```

## API Reference

### `APIKeyRotator` and `AsyncAPIKeyRotator` Parameters

| Parameter              | Type                                       | Default                  | Description                                                                                             |
| ---------------------- | ------------------------------------------ | ------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `api_keys`             | `Optional[Union[List[str], str]]`          | `None`                   | A list of API keys or a single comma-separated string. If `None`, keys are loaded from `env_var`.                 |
| `env_var`              | `str`                                      | `"API_KEYS"`             | The name of the environment variable to load keys from.                                                                 |
| `max_retries`          | `int`                                      | `3`                      | Maximum number of retries for each key.                                                                                 |
| `base_delay`           | `float`                                    | `1.0`                    | The base delay (in seconds) for exponential backoff. Delay is `base_delay * (2 ** attempt)`.                          |
| `timeout`              | `float`                                    | `10.0`                   | Timeout for each HTTP request in seconds.                                                                               |
| `should_retry_callback`| `Optional[Callable]`                       | `None`                   | A function that takes a response object and returns `True` if the request should be retried.                            |
| `header_callback`      | `Optional[Callable]`                       | `None`                   | A function that takes an API key and returns a dictionary of headers, or a tuple of (headers, cookies).               |
| `user_agents`          | `Optional[List[str]]`                      | `None`                   | A list of User-Agent strings to rotate through.                                                                         |
| `random_delay_range`   | `Optional[Tuple[float, float]]`            | `None`                   | A tuple `(min, max)` specifying the range for a random delay before each request.                                       |
| `proxy_list`           | `Optional[List[str]]`                      | `None`                   | A list of proxy URLs (e.g., `"http://user:pass@host:port"`) to rotate through.                                        |
| `logger`               | `Optional[logging.Logger]`                 | `None`                   | A custom logger instance. If `None`, a default logger is created.                                                       |
| `config_file`          | `str`                                      | `"rotator_config.json"`  | Path to the JSON file for storing learned header configurations.                                                        |
| `load_env_file`        | `bool`                                     | `True`                   | If `True` and `python-dotenv` is installed, automatically loads variables from a `.env` file.                         |
| `error_classifier`     | `Optional[ErrorClassifier]`                | `None`                   | Custom instance of `ErrorClassifier` for advanced error handling.                                                       |
| `config_loader`        | `Optional[ConfigLoader]`                   | `None`                   | Custom instance of `ConfigLoader` for advanced configuration management.                                                |

## Error Handling

The library defines custom exceptions to help you gracefully handle failures:

*   `NoAPIKeysError`: Raised if no API keys are provided or found in the environment.
*   `AllKeysExhaustedError`: Raised when a request has failed with every available API key after all retries.

## Multithreading and Concurrency

This library is designed with concurrency in mind.

*   **Concurrency (`asyncio`):** The `AsyncAPIKeyRotator` is the recommended choice for I/O-bound tasks (like making many network requests). It leverages `asyncio` to handle thousands of concurrent requests efficiently without blocking.

*   **Multithreading:** While you can use the synchronous `APIKeyRotator` in a multithreaded application, be aware of Python's Global Interpreter Lock (GIL). For most API-related tasks, `asyncio` provides superior performance. If you need to use threads, it's safe to create a separate `APIKeyRotator` instance per thread.

## License

This library is distributed under the MIT License. See the `LICENSE` file for more information.

### Enhanced Error Handling with `ErrorClassifier`

One of the most significant improvements is the introduction of `ErrorClassifier`. Instead of relying solely on HTTP status codes, the rotator now uses a dedicated classification system to determine the nature of an error. This allows for more nuanced decision-making:

*   **`RATE_LIMIT`**: Indicates that the request failed due to rate limiting. The rotator will typically switch to the next key immediately.
*   **`TEMPORARY`**: Suggests a transient issue (e.g., 5xx server errors). The rotator will retry the request, potentially with the same key after a backoff period.
*   **`PERMANENT`**: Signifies a persistent problem (e.g., 401 Unauthorized, 403 Forbidden). The key causing this error will be marked as invalid and removed from the rotation pool.
*   **`NETWORK`**: Catches network-related exceptions (e.g., connection errors, timeouts), prompting a retry or key switch.

This intelligent error classification minimizes unnecessary retries on permanently invalid keys and ensures that rate-limited keys are quickly bypassed, improving overall efficiency and resilience.

### Connection Pooling for Synchronous Rotator

The synchronous `APIKeyRotator` now explicitly configures `requests.Session` with connection pooling. This optimizes performance by reusing underlying TCP connections, reducing overhead for multiple requests to the same host. The `HTTPAdapter` is set up with `pool_connections=100` and `pool_maxsize=100`, ensuring efficient management of connections.

### Updated API Reference

Below is the updated API reference table reflecting the new parameters and capabilities.

| Parameter              | Type                                       | Default                  | Description                                                                                             |
| :--------------------- | :----------------------------------------- | :----------------------- | :------------------------------------------------------------------------------------------------------ |
| `api_keys`             | `Optional[Union[List[str], str]]`          | `None`                   | A list of API keys or a single comma-separated string. If `None`, keys are loaded from `env_var`.                 |
| `env_var`              | `str`                                      | `"API_KEYS"`             | The name of the environment variable to load keys from.                                                                 |
| `max_retries`          | `int`                                      | `3`                      | Maximum number of retries for each key.                                                                                 |
| `base_delay`           | `float`                                    | `1.0`                    | The base delay (in seconds) for exponential backoff. Delay is `base_delay * (2 ** attempt)`.                          |
| `timeout`              | `float`                                    | `10.0`                   | Timeout for each HTTP request in seconds.                                                                               |
| `should_retry_callback`| `Optional[Callable]`                       | `None`                   | A function that takes a response object and returns `True` if the request should be retried.                            |
| `header_callback`      | `Optional[Callable]`                       | `None`                   | A function that takes an API key and returns a dictionary of headers, or a tuple of (headers, cookies).               |
| `user_agents`          | `Optional[List[str]]`                      | `None`                   | A list of User-Agent strings to rotate through.                                                                         |
| `random_delay_range`   | `Optional[Tuple[float, float]]`            | `None`                   | A tuple `(min, max)` specifying the range for a random delay before each request.                                       |
| `proxy_list`           | `Optional[List[str]]`                      | `None`                   | A list of proxy URLs (e.g., `"http://user:pass@host:port"`) to rotate through.                                        |
| `logger`               | `Optional[logging.Logger]`                 | `None`                   | A custom logger instance. If `None`, a default logger is created.                                                       |
| `config_file`          | `str`                                      | `"rotator_config.json"`  | Custom path for the config file.                                                                                        |
| `load_env_file`        | `bool`                                     | `True`                   | If `True` and `python-dotenv` is installed, automatically loads variables from a `.env` file.                         |
| `error_classifier`     | `Optional[ErrorClassifier]`                | `None`                   | Custom instance of `ErrorClassifier` for advanced error handling.                                                       |
| `config_loader`        | `Optional[ConfigLoader]`                   | `None`                   | Custom instance of `ConfigLoader` for advanced configuration management.                                                |



