# Getting Started with APIKeyRotator

Welcome to APIKeyRotator! This guide will help you get up and running quickly.

## Installation

Install APIKeyRotator using pip:

```bash
pip install apikeyrotator
```

### Optional Dependencies

For full functionality, you may want to install additional dependencies:

```bash
# For synchronous HTTP requests
pip install requests

# For asynchronous HTTP requests
pip install aiohttp

# For environment variable management
pip install python-dotenv

# Install all optional dependencies
pip install apikeyrotator[all]
```

## Quick Start

### Basic Synchronous Usage

The simplest way to use APIKeyRotator:

```python
from apikeyrotator import APIKeyRotator

# Initialize with API keys
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# Make a request
response = rotator.get("https://api.example.com/data")
print(response.json())
```

### Using Environment Variables

Create a `.env` file in your project root:

```bash
API_KEYS=key1,key2,key3
```

Then use the rotator without explicitly passing keys:

```python
from apikeyrotator import APIKeyRotator

# Keys are automatically loaded from .env
rotator = APIKeyRotator()

response = rotator.get("https://api.example.com/data")
```

### Basic Asynchronous Usage

For async applications:

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def main():
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
        response = await rotator.get("https://api.example.com/data")
        data = await response.json()
        print(data)

asyncio.run(main())
```

## Core Concepts

### 1. Automatic Key Rotation

APIKeyRotator automatically cycles through your keys when:
- A rate limit is encountered (429 status)
- A key becomes invalid (401/403 status)
- Network errors occur

```python
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# The rotator will automatically switch keys if needed
for i in range(100):
    response = rotator.get(f"https://api.example.com/data/{i}")
```

### 2. Smart Retry Logic

Failed requests are automatically retried with exponential backoff:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=5,        # Retry up to 5 times per key
    base_delay=1.0        # Start with 1 second delay
)
```

The delay between retries follows the formula: `base_delay * (2 ** attempt)`

### 3. Intelligent Header Detection

APIKeyRotator automatically detects the correct authorization header format:

```python
# Bearer token format (JWT-like keys)
rotator = APIKeyRotator(api_keys=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."])
# Uses: Authorization: Bearer <key>

# API key format
rotator = APIKeyRotator(api_keys=["sk-1234567890abcdef"])
# Uses: Authorization: <key>

# Custom header detection is learned and saved
```

## Common Use Cases

### Rate Limit Management

Handle APIs with strict rate limits:

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    max_retries=3,
    base_delay=2.0
)

# Make many requests without worrying about rate limits
for item_id in range(1000):
    try:
        response = rotator.get(f"https://api.example.com/items/{item_id}")
        data = response.json()
        print(f"Processed item {item_id}")
    except Exception as e:
        print(f"Failed to process item {item_id}: {e}")
```

### Multi-Key API Access

Distribute load across multiple API keys:

```python
rotator = APIKeyRotator(api_keys=[
    "key_account_1",
    "key_account_2",
    "key_account_3"
])

# Requests are distributed across all keys
results = []
for i in range(300):  # 100 requests per key
    response = rotator.get("https://api.example.com/data")
    results.append(response.json())
```

### Anti-Bot Protection

Add human-like behavior to avoid detection:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
    ],
    random_delay_range=(1.0, 3.0)  # Random delay between requests
)
```

## Error Handling

APIKeyRotator provides specific exceptions for different failure scenarios:

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
    print("No API keys were provided or found in environment")
    
except AllKeysExhaustedError:
    print("All keys failed after maximum retries")
    
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Configuration Files

APIKeyRotator learns successful header configurations and saves them:

```python
rotator = APIKeyRotator(
    api_keys=["key1"],
    config_file="my_config.json"  # Custom config file location
)
```

The config file stores:
- Successful authorization header formats per domain
- Header detection patterns
- Domain-specific configurations
## DOCS:
- See [INDEX](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/INDEX.md)
## Next Steps

- Learn about [Advanced Configuration](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/ADVANCED_USAGE.md)
- Explore [Error Handling](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/ERROR_HANDLING.md)
- Understand [Rotation Strategies](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/ROTATION_STRATEGIES.md)
- See [API Reference](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/API_REFERENCE.md)
- Check out [Examples](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/EXAMPLES.md)

## Need Help?

- Check the [FAQ](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/FAQ.md)
- Report issues on [GitHub](https://github.com/PrimeevolutionZ/apikeyrotator/issues)
- Read the full [API Reference](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/apikeyrotator/docs/API_REFERENCE.md)