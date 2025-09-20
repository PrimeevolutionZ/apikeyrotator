# APIKeyRotator

**Ultra simple API key rotation for bypassing rate limits**

`APIKeyRotator` is a Python library designed to simplify API key rotation, automatically handle rate limits, errors, and retries. It provides both synchronous and asynchronous interfaces while maintaining maximum ease of use.

## Features

*   **Simplicity:** Intuitive API, similar to `requests` and `aiohttp`.
*   **Automatic Key Rotation:** Switches to the next key upon errors or rate limit exceedance.
*   **Exponential Backoff:** Automatically applies exponential backoff between retries.
*   **Flexible Configuration:** Customizable maximum retries, base delay, and timeouts.
*   **Synchronous and Asynchronous Support:** Use `APIKeyRotator` for synchronous operations and `AsyncAPIKeyRotator` for asynchronous ones.
*   **User-Agent Rotation:** Automatically rotates User-Agent headers from a provided list to mimic different clients.
*   **Random Delay:** Introduces a random delay between requests to prevent bot detection.
*   **Proxy Rotation:** Supports rotating through a list of proxies for IP rotation.
*   **Enhanced Logging:** Configurable logging for better visibility into the library's operations.
*   **Smart Header Detection & Persistence:** Attempts to infer authorization type (Bearer, X-API-Key, Key) based on key format. Learns and saves successful header configurations to a JSON file for specific domains.
*   **Customizable Logic:** Ability to provide custom functions for determining retry necessity and header/cookie generation.
*   **Smart Key Parsing:** Keys can be provided as a list, a comma-separated string, or from an environment variable.
*   **`.env` File Support:** Automatically loads environment variables from a `.env` file if `python-dotenv` is installed.
*   **Session Management:** Integrates seamlessly with `requests.Session` and `aiohttp.ClientSession` for persistent connections and cookie handling.

## Installation

```bash
pip install apikeyrotator
```

## Usage

### Synchronous Mode (APIKeyRotator)

Use `APIKeyRotator` for performing synchronous HTTP requests. Its API is very similar to the `requests` library.

```python
import os
import requests
import logging
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

# Configure a logger (optional, library uses a default if not provided)
my_logger = logging.getLogger("my_app")
my_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
my_logger.addHandler(handler)

# Example: keys from an environment variable (recommended)
# Create a .env file in your project root with: API_KEYS="your_key_1,your_key_2,your_key_3"
# Or set directly: export API_KEYS="your_key_1,your_key_2,your_key_3"

# Or pass keys directly
rotator = APIKeyRotator(
    api_keys=["key_sync_1", "key_sync_2", "key_sync_3"],
    max_retries=5, # Max retries per key
    base_delay=0.5, # Base delay between retries
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
    ],
    random_delay_range=(1.0, 3.0), # Random delay between 1 and 3 seconds
    proxy_list=["http://user:pass@proxy1.com:8080", "http://user:pass@proxy2.com:8080"], # List of proxies to rotate
    logger=my_logger, # Pass your custom logger
    load_env_file=True, # Automatically load .env file (requires python-dotenv)
)

try:
    # Perform a GET request
    response = rotator.get("https://api.example.com/data", params={"query": "test"})
    response.raise_for_status() # Raise an exception for 4xx/5xx responses
    my_logger.info(f"Successful synchronous GET request: {response.status_code}")
    my_logger.info(response.json())

    # Perform a POST request
    response = rotator.post("https://api.example.com/submit", json={"data": "payload"})
    response.raise_for_status()
    my_logger.info(f"Successful synchronous POST request: {response.status_code}")
    my_logger.info(response.json())

except AllKeysExhaustedError as e:
    my_logger.error(f"All keys exhausted: {e}")
except Exception as e:
    my_logger.error(f"An error occurred: {e}")

# Example with custom retry logic and header/cookie callback
def custom_sync_retry_logic(response: requests.Response) -> bool:
    # Retry if status is 429 (Too Many Requests) or 403 (Forbidden)
    return response.status_code in [429, 403]

def custom_header_callback(key: str, existing_headers: Optional[dict]) -> Tuple[dict, dict]:
    headers = existing_headers.copy() if existing_headers else {}
    headers["X-Custom-Auth"] = f"Token {key}"
    headers["User-Agent"] = "MyAwesomeApp/1.0"
    cookies = {"session_id": "some_session_value"}
    return headers, cookies

rotator_custom = APIKeyRotator(
    api_keys=["key_sync_custom_1"],
    should_retry_callback=custom_sync_retry_logic,
    header_callback=custom_header_callback
)

try:
    response = rotator_custom.get("https://api.example.com/protected")
    my_logger.info(f"Successful synchronous request with custom logic: {response.status_code}")
except AllKeysExhaustedError as e:
    my_logger.error(f"All keys exhausted (custom logic): {e}")
except Exception as e:
    my_logger.error(f"An error occurred: {e}")
```

### Asynchronous Mode (AsyncAPIKeyRotator)

Use `AsyncAPIKeyRotator` for performing asynchronous HTTP requests. Its API is very similar to the `aiohttp` library.

```python
import asyncio
import aiohttp
import logging
from apikeyrotator import AsyncAPIKeyRotator, AllKeysExhaustedError

# Configure a logger (optional)
my_async_logger = logging.getLogger("my_async_app")
my_async_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
my_async_logger.addHandler(handler)

async def main():
    # Example: keys from an environment variable (recommended)
    # Create a .env file in your project root with: API_KEYS="your_async_key_1,your_async_key_2"

    # Or pass keys directly
    async with AsyncAPIKeyRotator(
        api_keys=["key_async_1", "key_async_2"],
        max_retries=5,
        base_delay=0.5,
        user_agents=[
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        ],
        random_delay_range=(0.5, 2.0),
        proxy_list=["http://user:pass@asyncproxy1.com:8080", "http://user:pass@asyncproxy2.com:8080"],
        logger=my_async_logger,
        load_env_file=True,
    ) as rotator:
        try:
            # Perform a GET request
            async with rotator.get("https://api.example.com/async_data", params={"query": "async_test"}) as response:
                response.raise_for_status()
                data = await response.json()
                my_async_logger.info(f"Successful asynchronous GET request: {response.status}")
                my_async_logger.info(data)

            # Perform a POST request
            async with rotator.post("https://api.example.com/async_submit", json={"data": "async_payload"}) as response:
                response.raise_for_status()
                data = await response.json()
                my_async_logger.info(f"Successful asynchronous POST request: {response.status}")
                my_async_logger.info(data)

        except AllKeysExhaustedError as e:
            my_async_logger.error(f"All keys exhausted (asynchronously): {e}")
        except aiohttp.ClientError as e:
            my_async_logger.error(f"An asynchronous client error occurred: {e}")
        except Exception as e:
            my_async_logger.error(f"An unexpected error occurred: {e}")

# Example with custom retry logic and header/cookie callback
def custom_async_retry_logic(status_code: int) -> bool:
    # Retry if status is 429 (Too Many Requests) or 503 (Service Unavailable)
    return status_code in [429, 503]

def custom_async_header_callback(key: str, existing_headers: Optional[dict]) -> Tuple[dict, dict]:
    headers = existing_headers.copy() if existing_headers else {}
    headers["X-Async-Auth"] = f"AsyncToken {key}"
    headers["User-Agent"] = "MyAwesomeAsyncApp/1.0"
    cookies = {"async_session_id": "some_async_session_value"}
    return headers, cookies

async def main_custom_async():
    async with AsyncAPIKeyRotator(
        api_keys=["key_async_custom_1"],
        should_retry_callback=custom_async_retry_logic,
        header_callback=custom_async_header_callback
    ) as rotator:
        try:
            async with rotator.get("https://api.example.com/custom_async_auth") as response:
                response.raise_for_status()
                data = await response.json()
                my_async_logger.info(f"Successful asynchronous request with custom logic: {response.status}")
                my_async_logger.info(data)
        except AllKeysExhaustedError as e:
            my_async_logger.error(f"All keys exhausted (custom asynchronous logic): {e}")
        except Exception as e:
            my_async_logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
    # asyncio.run(main_custom_async()) # Uncomment to run the custom logic example
```

## Error Handling

The library raises the following exceptions:

*   `NoAPIKeysError`: If no API keys were provided or found.
*   `AllKeysExhaustedError`: If all provided API keys were exhausted after all retries.

## Development

To run tests or for development:

```bash
git clone https://github.com/PrimeevolutionZ/apikeyrotator.git
cd apikeyrotator
pip install -e .
# Run tests if available
```

## Multithreading and Concurrency

This library is designed to handle **concurrency** efficiently through its `AsyncAPIKeyRotator` for `asyncio`-based applications. This allows you to make multiple requests seemingly at the same time without blocking the main thread, which is ideal for I/O-bound tasks like network requests.

For **multithreading** (true parallelism for CPU-bound tasks), Python's Global Interpreter Lock (GIL) limits the effectiveness of multiple threads executing Python bytecode simultaneously. If your use case requires true multithreading, you would typically manage threads externally and pass `APIKeyRotator` instances to each thread. However, for most web scraping and API interaction tasks, the asynchronous `AsyncAPIKeyRotator` provides excellent performance benefits.

## License

This library is distributed under the MIT License. See the `LICENSE` file for more information.


