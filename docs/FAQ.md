# Frequently Asked Questions (FAQ)

Common questions and answers about APIKeyRotator.

## Table of Contents

- [General Questions](#general-questions)
- [Installation & Setup](#installation--setup)
- [Usage Questions](#usage-questions)
- [Error Handling](#error-handling)
- [Performance](#performance)
- [Advanced Topics](#advanced-topics)

---

## General Questions

### What is APIKeyRotator?

APIKeyRotator is a Python library that automatically manages multiple API keys for your applications. It handles key rotation, retries failed requests, manages rate limits, and provides anti-bot evasion features.

### Why do I need APIKeyRotator?

You need APIKeyRotator if you:
- Have multiple API keys and want to distribute load
- Need to handle rate limits automatically
- Want automatic retry logic for failed requests
- Need to rotate User-Agents or proxies
- Want resilient API clients without boilerplate code

### Is APIKeyRotator free?

Yes! APIKeyRotator is open-source and distributed under the MIT License. You can use it freely in commercial and non-commercial projects.

### What Python versions are supported?

APIKeyRotator supports Python 3.9 and higher.

---

## Installation & Setup

### How do I install APIKeyRotator?

```bash
pip install apikeyrotator
```

### Do I need to install requests or aiohttp separately?

Yes, these are optional dependencies. Install based on your needs:

```bash
# For synchronous use
pip install requests

# For asynchronous use
pip install aiohttp

# For environment file support
pip install python-dotenv

# Install everything
pip install apikeyrotator[all]
```

### How do I set up my API keys?

**Option 1: Using .env file**
```bash
# .env
API_KEYS=key1,key2,key3
```

```python
from apikeyrotator import APIKeyRotator
rotator = APIKeyRotator()  # Automatically loads from .env
```

**Option 2: Direct passing**
```python
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])
```

**Option 3: Environment variable**
```bash
export API_KEYS="key1,key2,key3"
```

```python
rotator = APIKeyRotator()  # Loads from environment
```

### Can I use different environment variable names?

Yes:

```bash
# .env
MY_CUSTOM_KEYS=key1,key2,key3
```

```python
rotator = APIKeyRotator(env_var="MY_CUSTOM_KEYS")
```

---

## Usage Questions

### How does key rotation work?

APIKeyRotator automatically rotates keys when:
1. A rate limit is encountered (HTTP 429)
2. An authentication error occurs (HTTP 401/403)
3. Network errors happen
4. After maximum retries on a key

Example:
```python
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])
# Request 1 uses key1
# If key1 is rate-limited, request 2 uses key2
# If key2 works, it continues with key2
# Pattern: Use current key until it fails, then rotate
```

### Can I control which key is used?

Not directly - the rotator manages keys automatically for resilience. However, you can influence behavior:

```python
# Use rotation strategies
from apikeyrotator import create_rotation_strategy

# Round-robin: cycles through all keys equally
strategy = create_rotation_strategy('round_robin', ['key1', 'key2', 'key3'])

# Weighted: prioritizes certain keys
strategy = create_rotation_strategy('weighted', {
    'key1': 1,  # Used less
    'key2': 5   # Used more
})
```

### How many retries does it attempt?

By default, 3 retries per key. You can configure this:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=5  # Try each key up to 5 times
)
```

With 2 keys and 5 retries each, that's up to 10 total attempts before failing.

### What happens when all keys fail?

An `AllKeysExhaustedError` exception is raised:

```python
from apikeyrotator import AllKeysExhaustedError

try:
    response = rotator.get(url)
except AllKeysExhaustedError:
    print("All API keys failed after retries")
    # Handle accordingly - use cache, alert admin, etc.
```

### Can I use it with any API?

Yes! APIKeyRotator works with any REST API. It automatically detects common authorization patterns:

- Bearer tokens (OAuth, JWT)
- API keys in headers
- Basic authentication
- Custom header formats

The library learns and saves successful configurations per domain.

### How do I make POST/PUT/DELETE requests?

Use the same interface as the `requests` library:

```python
# POST
response = rotator.post(url, json={"key": "value"})

# PUT
response = rotator.put(url, json={"key": "value"})

# DELETE
response = rotator.delete(url)

# PATCH
response = rotator.patch(url, json={"key": "value"})
```

### Can I pass custom headers?

Yes, pass them as keyword arguments:

```python
response = rotator.get(
    url,
    headers={"X-Custom-Header": "value"}
)
```

Or use the `header_callback` for dynamic headers:

```python
def custom_headers(key, existing_headers):
    return {
        "Authorization": f"Bearer {key}",
        "X-Client-ID": "my-app"
    }, {}

rotator = APIKeyRotator(
    api_keys=["key1"],
    header_callback=custom_headers
)
```

---

## Error Handling

### What errors can APIKeyRotator handle automatically?

- **Rate limits (429)**: Automatically switches to next key
- **Server errors (5xx)**: Retries with exponential backoff
- **Network errors**: Retries or switches key
- **Authentication errors (401/403)**: Removes invalid key and tries next

### How do I handle errors in my code?

Use try-except blocks:

```python
from apikeyrotator import AllKeysExhaustedError, NoAPIKeysError

try:
    rotator = APIKeyRotator()
    response = rotator.get(url)
    data = response.json()
    
except NoAPIKeysError:
    print("No API keys configured")
    
except AllKeysExhaustedError:
    print("All keys failed")
    
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Why are my requests failing immediately?

Common causes:

1. **Invalid API keys**: Check your keys are correct
2. **Wrong URL**: Verify the endpoint URL
3. **Incorrect headers**: API might require specific headers
4. **IP restrictions**: Your IP might be blocked

Debug by checking:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

rotator = APIKeyRotator(api_keys=["test_key"])
response = rotator.get(url)
# Check logs for detailed information
```

### How do I customize retry logic?

Use the `should_retry_callback`:

```python
def my_retry_logic(response):
    # Don't retry on client errors except 429
    if 400 <= response.status_code < 500 and response.status_code != 429:
        return False
    
    # Retry on server errors
    return response.status_code >= 500

rotator = APIKeyRotator(
    api_keys=["key1"],
    should_retry_callback=my_retry_logic
)
```

---

## Performance

### Is APIKeyRotator fast?

Yes! The overhead is minimal:
- Connection pooling for reusing TCP connections
- Efficient key rotation algorithms
- No unnecessary delays (unless configured)

For best performance:
- Use async version for I/O-bound tasks
- Enable connection pooling (enabled by default)
- Minimize `random_delay_range` if not needed

### Should I use sync or async?

**Use Synchronous (`APIKeyRotator`)** when:
- Making sequential requests
- Simple scripts or applications
- Working with synchronous code

**Use Asynchronous (`AsyncAPIKeyRotator`)** when:
- Making many concurrent requests
- Building async applications
- Need maximum throughput

Example performance comparison:
```python
# Sync: 100 requests = ~100 seconds (sequential)
for i in range(100):
    response = rotator.get(url)

# Async: 100 requests = ~5 seconds (concurrent)
tasks = [rotator.get(url) for _ in range(100)]
responses = await asyncio.gather(*tasks)
```

### How many requests can I make per second?

This depends on:
1. Your API's rate limits
2. Number of keys you have
3. Network latency
4. `random_delay_range` setting

To maximize throughput:
```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],  # More keys
    max_retries=2,  # Fewer retries
    base_delay=0.5,  # Shorter delays
    random_delay_range=None,  # No artificial delays
    timeout=5.0  # Quick timeout
)
```

### Does it cache responses?

No, APIKeyRotator does not cache responses by default. You can implement caching yourself:

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_get(url):
    return rotator.get(url).json()
```

Or use a caching library like `requests-cache`.

---

## Advanced Topics

### Can I use it with proxies?

Yes! Pass a list of proxies:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    proxy_list=[
        "http://user:pass@proxy1.com:8080",
        "http://user:pass@proxy2.com:8080"
    ]
)
```

Each request will use a different proxy from the list.

### How do I rotate User-Agents?

Pass a list of User-Agent strings:

```python
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
]

rotator = APIKeyRotator(
    api_keys=["key1"],
    user_agents=USER_AGENTS
)
```

### Can I add delays between requests?

Yes, use `random_delay_range`:

```python
rotator = APIKeyRotator(
    api_keys=["key1"],
    random_delay_range=(1.0, 3.0)  # 1-3 seconds delay
)
```

Each request will wait a random time in this range before executing.

### How do I use custom error classification?

Create a custom `ErrorClassifier`:

```python
from apikeyrotator import ErrorClassifier, ErrorType

class MyErrorClassifier(ErrorClassifier):
    def classify_error(self, response=None, exception=None):
        if response and response.status_code == 418:  # I'm a teapot
            return ErrorType.TEMPORARY
        return super().classify_error(response, exception)

rotator = APIKeyRotator(
    api_keys=["key1"],
    error_classifier=MyErrorClassifier()
)
```

### Can I use it in a multithreaded application?

Yes, but create separate instances per thread:

```python
from concurrent.futures import ThreadPoolExecutor

def worker(thread_id, keys):
    rotator = APIKeyRotator(api_keys=keys)
    return rotator.get(url).json()

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [
        executor.submit(worker, i, get_keys_for_thread(i))
        for i in range(4)
    ]
    results = [f.result() for f in futures]
```

For I/O-bound tasks, async is usually better than threads.

### How do I disable .env file loading?

Set `load_env_file=False`:

```python
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    load_env_file=False  # Don't load .env
)
```

### Where is the configuration file stored?

By default, `rotator_config.json` in the current directory. Customize:

```python
rotator = APIKeyRotator(
    api_keys=["key1"],
    config_file="/path/to/my/config.json"
)
```

### Can I disable configuration persistence?

Yes, provide a no-op config loader:

```python
from apikeyrotator import ConfigLoader

class NoOpConfigLoader(ConfigLoader):
    def save_config(self):
        pass
    def load_config(self):
        return {}

rotator = APIKeyRotator(
    api_keys=["key1"],
    config_loader=NoOpConfigLoader(config_file="", logger=None)
)
```

### How do I enable debug logging?

Configure Python's logging:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

rotator = APIKeyRotator(api_keys=["key1"])
# Now you'll see detailed logs
```

### Can I use it with GraphQL APIs?

Yes! GraphQL uses POST requests:

```python
rotator = APIKeyRotator(api_keys=["key1"])

query = """
query GetUser($id: ID!) {
    user(id: $id) { name email }
}
"""

response = rotator.post(
    "https://api.example.com/graphql",
    json={
        "query": query,
        "variables": {"id": "123"}
    }
)

data = response.json()
```

### Is it compatible with requests-mock for testing?

Yes:

```python
import requests_mock
from apikeyrotator import APIKeyRotator

def test_api_call():
    with requests_mock.Mocker() as m:
        m.get('https://api.example.com/data', json={'result': 'success'})
        
        rotator = APIKeyRotator(api_keys=["test_key"])
        response = rotator.get('https://api.example.com/data')
        
        assert response.json() == {'result': 'success'}
```

### How do I contribute to the project?

1. Fork the repository on GitHub
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

See the [GitHub repository](https://github.com/PrimeevolutionZ/apikeyrotator) for more details.

---

## Still have questions?

- Check the [Documentation Index](INDEX.md)
- Read the [API Reference](API_REFERENCE.md)
- See [Examples](EXAMPLES.md)
- Open an issue on [GitHub](https://github.com/PrimeevolutionZ/apikeyrotator/issues)