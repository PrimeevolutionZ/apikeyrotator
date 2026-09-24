# Getting Started with APIKeyRotator

This guide gets you from installation to a production-ready setup.

## Installation

APIKeyRotator requires **Python 3.12+**.

```bash
pip install apikeyrotator
```

`requests`, `aiohttp`, `python-dotenv` and `PyYAML` are installed automatically.
Optional extras:

```bash
pip install "apikeyrotator[httpx]"   # httpx backend (sync + async, HTTP/2)
pip install "apikeyrotator[redis]"   # shared state between processes
pip install "apikeyrotator[aws]"     # AWS Secrets Manager provider
pip install "apikeyrotator[gcp]"     # GCP Secret Manager provider
```

## Quick Start

### Synchronous

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

response = rotator.get("https://api.example.com/data", params={"page": 1})
print(response.json())      # a regular requests.Response

rotator.close()             # or use: with APIKeyRotator(...) as rotator:
```

### Keys from the environment

Export the variable (or put it in a `.env` file):

```bash
export API_KEYS=key1,key2,key3
```

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator()                        # reads API_KEYS
rotator = APIKeyRotator(env_var="OPENAI_KEYS")   # another variable
rotator = APIKeyRotator(load_env_file=True)      # load ./.env into the environment first
```

### Asynchronous

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def main():
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
        response = await rotator.get("https://api.example.com/data")
        print(await response.json())   # aiohttp.ClientResponse

asyncio.run(main())
```

### One response type for every client

With `unified_response=True` the sync and async rotators return the same object for
requests, httpx and aiohttp - and `json()` is never awaited:

```python
import asyncio
from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator

print(APIKeyRotator(api_keys=["key1"], unified_response=True).get("https://api.example.com/data").json())

async def main():
    async with AsyncAPIKeyRotator(api_keys=["key1"], unified_response=True) as rotator:
        response = await rotator.get("https://api.example.com/data")
        print(response.status_code, response.json())

asyncio.run(main())
```

### Seeing what happens

The library logs through the standard `logging` module but does not print
anything unless your application configures logging:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Core Concepts

### 1. Key rotation

Every attempt takes the next key from the rotation strategy (round-robin by
default). A key is taken out of the rotation when:

- the server answers **429** - the key is parked until `Retry-After` expires and the
  request continues immediately with another key;
- the server answers **401/403** - the key is removed for good;
- the key keeps failing - it becomes unhealthy and is retried later (after
  `recovery_timeout`, 60 s by default).

```python
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

for i in range(100):
    response = rotator.get(f"https://api.example.com/data/{i}")
```

Other strategies: `"random"`, `"weighted"`, `"lru"`, `"health_based"`, `"failover"` -
see [Advanced Usage](ADVANCED_USAGE.md#rotation-strategies).

### 2. Retries

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=5,       # up to 5 attempts per request (across keys)
    base_delay=1.0,      # backoff: 1s, 2s, 4s, ... (+ jitter), capped by max_delay=60
    timeout=10.0,        # per attempt
    total_timeout=30.0,  # optional budget for the whole request
)
```

| Response | Behaviour |
|---|---|
| 2xx / 3xx | returned |
| 429 | next key immediately (waits only if all keys are limited) |
| 5xx, network errors | retried with exponential backoff |
| 401 / 403 | key removed, retried with another key |
| other 4xx (404, 400...) | returned to you - retrying would not help |

`POST`/`PATCH` are not retried after errors where the server may already have
processed them (500/502/504, read timeouts); send an `Idempotency-Key` header or set
`retry_non_idempotent=True` if retrying is safe. When all attempts fail,
`AllKeysExhaustedError` is raised.

### 3. Authorization header

Tell the rotator how your API expects the key with `auth=`:

```python
from apikeyrotator import APIKeyRotator

APIKeyRotator(api_keys=["key1"], auth="bearer")                          # Authorization: Bearer key1
APIKeyRotator(api_keys=["key1"], auth="x-api-key")                       # X-API-Key: key1
APIKeyRotator(api_keys=["key1"], auth=("Authorization", "Token {key}"))  # any header / scheme
APIKeyRotator(api_keys=["key1"], auth=("x-goog-api-key", "{key}"))
```

Without `auth=`, 32-character keys are sent as `X-API-Key` and everything else as
`Authorization: Bearer <key>`. If you get the header wrong, you get an
`AuthenticationError` that shows the header that was sent - your keys are not
thrown away. For headers that need more than the key, use `header_callback`.

The callback's headers are added to every request. The default header is added
only when neither `Authorization` nor `X-API-Key` is set by the request or the callback.

## Common Use Cases

### Rate limit management

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    key_rate_limit=(60, 60),   # optional: never exceed 60 requests/minute per key
)

for item_id in range(1000):
    try:
        data = rotator.get(f"https://api.example.com/items/{item_id}").json()
    except AllKeysExhaustedError as e:
        print(f"Item {item_id} failed: {e}")
```

### Anti-bot measures

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
    ],
    random_delay_range=(1.0, 3.0),   # random pause before each attempt
    proxy_list=["http://proxy1:8080", "http://proxy2:8080"],
)
```

### Production setup

```python
from apikeyrotator import APIKeyRotator, RedisStateBackend

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    total_timeout=30,
    circuit_breaker=True,
    key_rate_limit=(60, 60),
    state_backend=RedisStateBackend(url="redis://localhost:6379/0"),
)
```

See [Resilience & Scaling](RESILIENCE.md).

## Error Handling

```python
from apikeyrotator import APIKeyRotator, NoAPIKeysError, AllKeysExhaustedError

try:
    rotator = APIKeyRotator(api_keys=["key1", "key2"])
    response = rotator.get("https://api.example.com/data")
except NoAPIKeysError:
    print("No API keys were provided or found in the environment")
except AllKeysExhaustedError as e:
    print("All attempts failed; last response:", e.last_response)
```

More in [Error Handling](ERROR_HANDLING.md).

## Next Steps

- [Advanced Usage](ADVANCED_USAGE.md) - strategies, middleware, providers, metrics
- [Resilience & Scaling](RESILIENCE.md) - deadlines, circuit breaker, rate limits, Redis, httpx
- [Error Handling](ERROR_HANDLING.md)
- [API Reference](API_REFERENCE.md)
- [Examples](EXAMPLES.md)
- [FAQ](FAQ.md)
