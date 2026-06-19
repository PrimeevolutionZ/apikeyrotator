<div align="center">

# 🔄 APIKeyRotator
### <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=600&size=24&pause=1000&color=4F46E5&center=true&vCenter=true&width=700&lines=Powerful+API+Key+Management+for+Python;Automatic+Rotation+%2B+Smart+Retries;Handle+Rate+Limits+Like+a+Pro;" alt="Typing SVG" />

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.6.0-blue.svg)](https://pypi.org/project/apikeyrotator/)

[![Downloads](https://pepy.tech/badge/apikeyrotator)](https://pepy.tech/project/apikeyrotator)
[![Tests](https://github.com/PrimeevolutionZ/apikeyrotator/actions/workflows/python-app.yml/badge.svg)](https://github.com/PrimeevolutionZ/apikeyrotator/actions)
[![Stars](https://img.shields.io/github/stars/PrimeevolutionZ/apikeyrotator?style=social)](https://github.com/PrimeevolutionZ/apikeyrotator)


[🚀 Quick Start](#-quick-start) • [📚 Documentation](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/INDEX.md) • [💡 Examples](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/EXAMPLES.md) • [🔒 Security](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/SECURITY.md) • [📝 Changelog](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/CHANGELOG.md)

---

</div>

## ✨ Features

<table>
<tr>
<td>

🔄 **Automatic Key Rotation**
- Seamlessly cycles through API keys
- Bypasses rate limits effortlessly
- Removes invalid keys automatically

</td>
<td>

🔁 **Smart Retry Logic**
- Exponential backoff strategy
- Intelligent error classification
- Configurable retry attempts

</td>
<td>

🛡️ **Anti-Bot Evasion**
- User-Agent rotation
- Random delays between requests
- Proxy support

</td>
</tr>
<tr>
<td>

⚡ **Dual Mode Support**
- Synchronous (`requests`)
- Asynchronous (`aiohttp`)
- Drop-in replacement

</td>
<td>

🧠 **Intelligent Headers**
- Auto-detects auth patterns
- Learns successful configs
- Persistent configuration

</td>
<td>

🛣️ **Multi-Provider Routing**
- Fallback across different APIs
- Payload transformers
- Conditional routing

</td>


</table>

## 🚀 Quick Start

### 📦 Installation

```bash
pip install apikeyrotator
```

### ⚡ Basic Usage

```python
from apikeyrotator import APIKeyRotator

# Initialize with API keys
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# Make requests - it's that simple!
response = rotator.get("https://api.example.com/data")
print(response.json())

# The rotator automatically:
# ✅ Rotates keys on rate limits
# ✅ Retries on failures
# ✅ Manages headers intelligently

### 🛣️ Multi-Provider Fallback Routing

```python
from apikeyrotator import FallbackRouter, ProviderRoute, APIKeyRotator

router = FallbackRouter(routes=[
    ProviderRoute(name="Primary", rotator=APIKeyRotator(api_keys=["key1"])),
    ProviderRoute(
        name="Fallback",
        rotator=APIKeyRotator(api_keys=["key2"]),
        request_transformer=lambda m, u, k: (m, "https://api.fallback.com/data", k)
    )
])

# Automatically falls back to the second API if the first is exhausted!
response = router.get("https://api.primary.com/data")
```
```

### 🌟 Using Environment Variables

Create a `.env` file:

```bash
API_KEYS=key1,key2,key3
```

Then use without explicit keys:

```python
from apikeyrotator import APIKeyRotator

# Automatically loads from .env
rotator = APIKeyRotator()

response = rotator.get("https://api.example.com/data")
```

### 🔥 Advanced Configuration

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    
    # Retry & Timeout
    max_retries=5,              # Retry up to 5 times per key
    base_delay=1.0,             # Start with 1s delay
    timeout=15.0,               # 15s request timeout
    
    # Anti-Bot Features
    user_agents=[               # Rotate User-Agents
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
    ],
    random_delay_range=(1.0, 3.0),  # Random 1-3s delays
    proxy_list=[                # Rotate proxies
        "http://proxy1.com:8080",
        "http://proxy2.com:8080"
    ]
)

# Now make requests with all these features active!
response = rotator.get("https://api.example.com/data")
```

### 🌐 Asynchronous Usage

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def main():
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
        # Make async requests
        response = await rotator.get("https://api.example.com/data")
        data = await response.json()
        print(data)

asyncio.run(main())
```

## 🎯 Why APIKeyRotator?

```
┌────────────────────────────────────────────────────────────────┐
│  ✓ Effortless API key management                              │
│  ✓ Automatic rate limit handling                              │
│  ✓ Smart retry logic with exponential backoff                 │
│  ✓ Anti-bot evasion (User-Agents, delays, proxies)            │
│  ✓ Both sync and async support                                │
│  ✓ Intelligent header detection and persistence               │
│  ✓ Clean, modern Python with full type hints                  │
└────────────────────────────────────────────────────────────────┘
```

## 📊 Comparison

| Feature              | Manual Management | APIKeyRotator |
|----------------------|-------------------|---------------|
| Key rotation         | ❌ Manual          | ✅ Automatic   |
| Retry logic          | ❌ Custom code     | ✅ Built-in    |
| Rate limit handling  | ❌ Manual          | ✅ Automatic   |
| Error classification | ❌ Status codes    | ✅ Intelligent |
| Anti-bot features    | ❌ Not included    | ✅ Complete    |
| Session management   | ❌ Manual          | ✅ Optimized   |
| Code complexity      | ❌ High            | ✅ Minimal     |

## 🎨 Use Cases

<details>
<summary><b>🕷️ Web Scraping</b></summary>

```python
from apikeyrotator import APIKeyRotator
from bs4 import BeautifulSoup

# Configure for web scraping
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
    ],
    random_delay_range=(1.0, 3.0),
    max_retries=5
)

# Scrape multiple pages
for page in range(1, 11):
    response = rotator.get(f"https://example.com/products?page={page}")
    soup = BeautifulSoup(response.content, 'html.parser')
    # Process data...
```

</details>

<details>
<summary><b>📊 Data Collection</b></summary>

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# Collect data from multiple endpoints
endpoints = ["/users", "/posts", "/comments", "/analytics"]

data = {}
for endpoint in endpoints:
    response = rotator.get(f"https://api.example.com{endpoint}")
    data[endpoint] = response.json()
    print(f"✓ Collected {endpoint}")
```

</details>

<details>
<summary><b>🔄 High-Volume Requests</b></summary>

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def fetch_all_items(item_ids):
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2", "key3"]) as rotator:
        tasks = [
            rotator.get(f"https://api.example.com/items/{id}")
            for id in item_ids
        ]
        responses = await asyncio.gather(*tasks)
        return [await r.json() for r in responses]

# Fetch 1000 items concurrently
items = asyncio.run(fetch_all_items(range(1000)))
```

</details>

<details>
<summary><b>🛠️ Production API Client</b></summary>

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError
from typing import Dict, List

class APIClient:
    def __init__(self, api_keys: List[str]):
        self.rotator = APIKeyRotator(
            api_keys=api_keys,
            max_retries=5,
            base_delay=2.0
        )
    
    def get_user(self, user_id: int) -> Dict:
        try:
            response = self.rotator.get(f"https://api.example.com/users/{user_id}")
            return response.json()
        except AllKeysExhaustedError:
            # Fallback to cache or alternative source
            return self._get_cached_user(user_id)

client = APIClient(api_keys=["key1", "key2", "key3"])
user = client.get_user(123)
```

</details>

## 🔧 Configuration Options

| Parameter            | Type                  | Default      | Description                           |
|----------------------|-----------------------|--------------|---------------------------------------|
| `api_keys`           | `List[str]` or `str`  | `None`       | API keys to rotate                    |
| `env_var`            | `str`                 | `"API_KEYS"` | Environment variable name             |
| `max_retries`        | `int`                 | `3`          | Max retry attempts per key            |
| `base_delay`         | `float`               | `1.0`        | Base delay for exponential backoff    |
| `timeout`            | `float`               | `10.0`       | Request timeout in seconds            |
| `user_agents`        | `List[str]`           | `None`       | User-Agent strings to rotate          |
| `random_delay_range` | `Tuple[float, float]` | `None`       | Random delay range (min, max)         |
| `proxy_list`         | `List[str]`           | `None`       | Proxy URLs to rotate                  |
| `error_classifier`   | `ErrorClassifier`     | `None`       | Custom error classifier               |

**[📚 View Complete API Reference →](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/API_REFERENCE.md)**

## 🛡️ Error Handling

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
    print("❌ No API keys provided or found")
    
except AllKeysExhaustedError:
    print("❌ All keys failed after maximum retries")
    # Implement fallback strategy
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
```

**Error Classification System:**

- **RATE_LIMIT** (429): Switches to next key immediately
- **TEMPORARY** (5xx): Retries with exponential backoff
- **PERMANENT** (401, 403): Removes invalid key from pool
- **NETWORK**: Connection errors, retries or switches key

**[📖 Learn More About Error Handling →](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/ERROR_HANDLING.md)**

## 🎯 Advanced Features

<table>
<tr>
<td>

### 🎭 Custom Retry Logic

```python
def custom_retry(response):
    if response.status_code == 429:
        return True
    try:
        return 'error' in response.json()
    except:
        return False

rotator = APIKeyRotator(
    api_keys=["key1"],
    should_retry_callback=custom_retry
)
```

</td>
<td>

### 🔑 Dynamic Headers

```python
def header_callback(key, headers):
    return {
        "Authorization": f"Bearer {key}",
        "X-Client-Version": "2.0"
    }, {}

rotator = APIKeyRotator(
    api_keys=["key1"],
    header_callback=header_callback
)
```

</td>
</tr>
</table>

**[🚀 Explore Advanced Features →](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/ADVANCED_USAGE.md)**

## 📚 Documentation

<div align="center">

| Resource                                                                                                   | Description                    |
|------------------------------------------------------------------------------------------------------------|--------------------------------|
| [📖 Documentation Index](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/INDEX.md)       | Complete documentation hub     |
| [🚀 Getting Started](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/GETTING_STARTED.md) | Quick start guide              |
| [📋 API Reference](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/API_REFERENCE.md)     | Complete API documentation     |
| [💡 Examples](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/EXAMPLES.md)               | Real-world code examples       |
| [🔧 Advanced Usage](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/ADVANCED_USAGE.md)   | Power features & customization |
| [🚨 Error Handling](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/ERROR_HANDLING.md)   | Comprehensive error management |
| [❓ FAQ](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/FAQ.md)                          | Frequently asked questions     |
| [🔒 Security](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/SECURITY.md)                    | Security best practices        |

</div>

## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio requests-mock aioresponses

# Run all tests
pytest

# Run with coverage
pytest --cov=apikeyrotator --cov-report=html

# Run specific test file
pytest tests/test_rotator.py -v
```

## 🤝 Contributing

Contributions are what make the open-source community amazing! We welcome:

- 🐛 Bug reports
- 💡 Feature suggestions
- 📝 Documentation improvements
- 🔧 Code contributions

**[📖 Read Contributing Guidelines →](CONTRIBUTING.md)**

### Quick Contribution Steps

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📈 Performance

APIKeyRotator is optimized for production use:

- ⚡ **Connection Pooling**: Reuses TCP connections
- 🧠 **Smart Caching**: Caches successful header configurations
- 🔄 **Async Support**: Handle thousands of concurrent requests
- 📊 **Memory Efficient**: Minimal memory footprint

### Benchmarks

```python
# Synchronous: ~100 requests/second
# Asynchronous: ~1000 requests/second (10x faster)
```

## 🔒 Security

Security is a top priority. Please review our [Security Policy](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/SECURITY.md) for:

- 🔐 Best practices for API key management
- 🛡️ Reporting vulnerabilities
- 📜 Security features
- ✅ Security audit checklist

**Found a security issue?** Please report it privately via the internal issue tracker.

## 📜 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=PrimeevolutionZ/apikeyrotator&type=Date)](https://star-history.com/#PrimeevolutionZ/apikeyrotator&Date)

## 💖 Support

If you find this project helpful, please consider:

- ⭐ Starring the repository
- 🐛 Reporting bugs
- 💡 Suggesting new features
- 📢 Sharing with others

## 📞 Contact & Support

- **GitHub Issues**: [Report bugs](https://github.com/PrimeevolutionZ/apikeyrotator/issues)
- **GitHub Discussions**: [Ask questions](https://github.com/PrimeevolutionZ/apikeyrotator/discussions)

## 🔗 Links

- **PyPI**: [pypi.org/project/apikeyrotator](https://pypi.org/project/apikeyrotator/)
- **GitHub**: [github.com/PrimeevolutionZ/apikeyrotator](https://github.com/PrimeevolutionZ/apikeyrotator)
- **Documentation**: [Full Documentation](https://github.com/PrimeevolutionZ/apikeyrotator/tree/master/docs/INDEX.md)
- **Changelog**: [What's New](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/CHANGELOG.md)

---

<div align="center">

**Made with 🔄 and ❤️ by [Eclips Team](https://github.com/PrimeevolutionZ)**

[![Made with Python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)
[![Powered by requests](https://img.shields.io/badge/Powered%20by-requests-blue.svg)](https://requests.readthedocs.io/)
[![Async with aiohttp](https://img.shields.io/badge/Async%20with-aiohttp-brightgreen.svg)](https://docs.aiohttp.org/)

[⬆️ Back to top](#-apikeyrotator)

</div>