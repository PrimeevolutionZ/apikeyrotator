# APIKeyRotator Documentation

Welcome to the complete documentation for **APIKeyRotator** - a powerful, simple, and resilient API key rotator for Python.

## 📚 Documentation Overview

This documentation will help you get started with APIKeyRotator and master its advanced features.

### Quick Navigation

| Document                              | Description                                  | Best For                               |
|---------------------------------------|----------------------------------------------|----------------------------------------|
| [Getting Started](GETTING_STARTED.md) | Installation, basic usage, and core concepts | New users, quick start                 |
| [API Reference](API_REFERENCE.md)     | Complete API documentation                   | Looking up specific methods/parameters |
| [Middleware Guide](MIDDLEWARE.md)     | Request/response interception system         | Custom processing, caching, logging    |
| [Examples](EXAMPLES.md)               | Real-world code examples                     | Practical implementation patterns      |
| [Advanced Usage](ADVANCED_USAGE.md)   | Power features and customization             | Advanced users, custom implementations |
| [Error Handling](ERROR_HANDLING.md)   | Comprehensive error management guide         | Debugging, production deployment       |
| [Resilience & Scaling](RESILIENCE.md) | Deadlines, circuit breaker, rate limits, Redis, httpx | Production under load, many workers |
| [FAQ](FAQ.md)                         | Frequently asked questions                   | Quick answers to common questions      |
| [Benchmarks](../benchmarks/README.md) | Measured speed, CPU and memory; how to compare versions | Performance work, CI |

---

## 🚀 Getting Started

New to APIKeyRotator? Start here!

### Installation

```bash
pip install apikeyrotator
```

### Your First Request

```python
from apikeyrotator import APIKeyRotator

# Initialize with your API keys
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# Make a request - it's that simple!
response = rotator.get("https://api.example.com/data")
print(response.json())
```

### What's Next?

1. **Read [Getting Started](GETTING_STARTED.md)** for installation and basic concepts
2. **Check [Examples](EXAMPLES.md)** for practical use cases
3. **Review [API Reference](API_REFERENCE.md)** for detailed documentation

---

## 📖 Documentation Sections

### [Getting Started Guide](GETTING_STARTED.md)

Perfect for beginners and those who want to understand the basics.

**Topics covered:**
- Installation and setup
- Basic synchronous and asynchronous usage
- Core concepts: key rotation, retries, authorization header
- Common use cases and a production setup
- Keys from `.env` / environment variables, logging

**Start here if you:**
- Are new to APIKeyRotator
- Want a quick overview
- Need basic setup instructions

---

### [API Reference](API_REFERENCE.md)

Complete technical reference for all classes, methods, and parameters.

**Topics covered:**
- `APIKeyRotator` / `AsyncAPIKeyRotator`: every constructor parameter, method and the retry rules
- Exceptions
- Multi-provider routing (`FallbackRouter`)
- Rotation strategies and `KeyMetrics`
- Shared state backends (Redis, in-memory)
- Middleware, metrics, secret providers
- Error classification, circuit breaker and retry utilities

**Use this when you:**
- Need detailed parameter information
- Want to understand method signatures
- Are looking up specific functionality

---

### [Middleware Guide](MIDDLEWARE.md)

Comprehensive guide to the middleware system for request/response interception.

**Topics covered:**
- Middleware architecture and lifecycle
- Built-in middleware (Caching, Logging, Rate Limit)
- Creating custom middleware
- Middleware best practices
- Advanced middleware patterns
- Performance considerations

**Perfect for:**
- Implementing caching strategies
- Adding custom logging
- Building complex request pipelines
- Intercepting and modifying requests/responses

---

### [Examples](EXAMPLES.md)

Real-world code examples demonstrating various use cases.

**Topics covered:**
- Basic usage patterns
- Middleware usage examples
- Metrics and monitoring
- Secret providers
- Web scraping with anti-bot features
- Data collection from APIs
- REST and GraphQL API integration
- Asynchronous operations
- Production-ready patterns

**Perfect for:**
- Learning by example
- Finding patterns for your use case
- Understanding best practices

---

### [Advanced Usage](ADVANCED_USAGE.md)

Deep dive into advanced features and customization options.

**Topics covered:**
- Middleware system overview
- Rotation strategies (round-robin, random, weighted, LRU, health-based, failover)
- Metrics and monitoring
- Secret providers (AWS, GCP, File, Environment)
- Custom callbacks (retry logic, headers)
- Anti-bot evasion (User-Agent rotation, proxies, delays)
- Custom error classification
- Connections and cleanup
- Configuration file
- Performance and best practices

**Read this to:**
- Unlock advanced features
- Customize behavior
- Optimize performance
- Implement complex patterns

---

### [Error Handling](ERROR_HANDLING.md)

Comprehensive guide to error management and troubleshooting.

**Topics covered:**
- Error classification system
- Built-in exceptions
- Handling specific errors (rate limits, auth, network)
- Custom error handling
- Best practices
- Common issues and solutions

**Essential for:**
- Production deployments
- Debugging issues
- Building resilient applications
- Understanding error flows

---

### [Resilience & Scaling](RESILIENCE.md)

Running under load and across many processes.

**Topics covered:**
- Safe retries of POST/PATCH (idempotency)
- Request deadlines (`total_timeout`)
- Per-host circuit breaker
- Client-side rate limits (token bucket, `X-RateLimit-*` hints)
- Shared state between processes (Redis)
- Background key refresh
- httpx backend and HTTP/2, logging

---

### [FAQ](FAQ.md)

Quick answers to frequently asked questions.

**Topics covered:**
- General questions about the library
- Installation and setup questions
- Usage questions
- Error handling
- Performance considerations
- Advanced topics

**Check this for:**
- Quick answers
- Common problems
- Usage tips
- Troubleshooting

---

## 🎯 Quick Reference

### Common Tasks

| Task                | Go To                                                |
|---------------------|------------------------------------------------------|
| Install the library | [Getting Started](GETTING_STARTED.md#installation)   |
| Make first request  | [Getting Started](GETTING_STARTED.md#quick-start)    |
| Use middleware      | [Middleware Guide](MIDDLEWARE.md)                    |
| Handle rate limits  | [Resilience](RESILIENCE.md#client-side-rate-limits)  |
| Use with async code | [API Reference](API_REFERENCE.md#asyncapikeyrotator) |
| Add custom headers  | [Advanced Usage](ADVANCED_USAGE.md#custom-callbacks) |
| Track metrics       | [Advanced Usage](ADVANCED_USAGE.md#metrics-and-monitoring) |
| Handle errors       | [Error Handling](ERROR_HANDLING.md)                  |
| See examples        | [Examples](EXAMPLES.md)                              |
| Debug issues        | [Error Handling](ERROR_HANDLING.md#troubleshooting)  |
| Many workers / Redis | [Resilience](RESILIENCE.md#shared-state-between-processes-redis) |
| Measure performance | [Benchmarks](../benchmarks/README.md)                |

### Code Snippets

#### Basic Usage

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])
response = rotator.get("https://api.example.com/data")
```

#### With Middleware

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import CachingMiddleware, LoggingMiddleware

cache = CachingMiddleware(ttl=600)
logger = LoggingMiddleware(verbose=True)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[cache, logger]
)
```

#### With Rate Limit Protection

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    key_rate_limit=(60, 60),   # at most 60 requests/minute per key
    total_timeout=30,          # bound the whole request, including waits
    circuit_breaker=True,      # fail fast while the host is down
)
```

#### Async Usage

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

#### With Error Handling and Metrics

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    enable_metrics=True
)

try:
    response = rotator.get("https://api.example.com/data")
except AllKeysExhaustedError as e:
    print("All attempts failed:", e.last_response or e.last_exception)

# View metrics
metrics = rotator.get_metrics()
print(f"Success rate: {metrics['success_rate']:.2%}")
```

---

## 🔑 Key Features

### Effortless Integration
Familiar `requests`-style API; works with `requests`, `aiohttp` or `httpx` (HTTP/2).

[Learn more in Getting Started](GETTING_STARTED.md)

### Automatic Key Rotation
Cycles through API keys to distribute load; parks rate-limited keys and drops rejected ones.

[See rotation strategies](API_REFERENCE.md#rotation-strategies)

### Middleware System
Powerful request/response interception for caching, logging, and custom processing.

[Explore middleware](MIDDLEWARE.md)

### Smart Retry Logic
Exponential backoff, request deadlines, safe handling of non-idempotent requests and a per-host circuit breaker.

[Understand error handling](ERROR_HANDLING.md)

### Metrics & Monitoring
Built-in metrics collection with Prometheus export support.

[Learn about metrics](ADVANCED_USAGE.md#metrics-and-monitoring)

### Anti-Bot Evasion
User-Agent rotation, random delays, and proxy support to avoid detection.

[Configure anti-bot features](ADVANCED_USAGE.md#anti-bot-evasion)

### Secret Providers
Load keys from AWS Secrets Manager, GCP Secret Manager, or files.

[See secret providers](ADVANCED_USAGE.md#secret-providers)

### Smart Headers
Infers the authorization header from the key format; custom schemes via `header_callback`.

[Learn about header management](ADVANCED_USAGE.md#dynamic-headers-and-cookies)

### Shared State & Rate Limits
Token buckets per key and shared limits/rejected keys across processes with Redis.

[Resilience & Scaling](RESILIENCE.md)

---

## 💡 Use Cases

### Web Scraping
Rotate through proxies and User-Agents while respecting rate limits.

[See scraping examples](EXAMPLES.md#web-scraping)

### Data Collection
Efficiently gather data from APIs with automatic retry and failover.

[View data collection patterns](EXAMPLES.md#data-collection)

### API Integration
Build robust API clients with automatic error handling and key management.

[Check integration examples](EXAMPLES.md#api-integration)

### High-Volume Requests
Process thousands of requests concurrently with async support.

[Learn async patterns](EXAMPLES.md#asynchronous-operations)

### Enterprise Systems
Production-grade features with secret providers, metrics, and middleware.

[See production patterns](EXAMPLES.md#production-patterns)

---

## 🛠️ Configuration

### Environment Variables

```bash
# .env file
API_KEYS=key1,key2,key3
```

[Configuration guide](GETTING_STARTED.md#keys-from-the-environment)

### Programmatic Setup

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import CachingMiddleware

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    max_retries=5,
    base_delay=1.0,
    timeout=10.0,
    user_agents=[...],
    random_delay_range=(1.0, 3.0),
    proxy_list=[...],
    middlewares=[CachingMiddleware(ttl=600)],
    rotation_strategy="health_based",
    total_timeout=30,
    circuit_breaker=True,
)
```

[Full configuration reference](API_REFERENCE.md#apikeyrotator)

---

## 📊 Comparison

### vs Manual Key Management

| Feature              | Manual              | APIKeyRotator   |
|----------------------|---------------------|-----------------|
| Key rotation         | ❌ Manual            | ✅ Automatic     |
| Retry logic          | ❌ Custom code       | ✅ Built-in      |
| Rate limit handling  | ❌ Manual tracking   | ✅ Automatic     |
| Error classification | ❌ Status codes only | ✅ Intelligent   |
| Anti-bot features    | ❌ Not included      | ✅ Comprehensive |
| Connection pooling   | ❌ Manual            | ✅ Built-in      |
| Circuit breaker      | ❌ Custom code       | ✅ Per host      |
| Shared limits (Redis)| ❌ Custom code       | ✅ Built-in      |
| Middleware system    | ❌ Not available     | ✅ Full support  |
| Metrics collection   | ❌ Custom code       | ✅ Built-in      |
| Secret providers     | ❌ Manual            | ✅ AWS, GCP, etc |

---

## 🤝 Contributing

APIKeyRotator is open-source! We welcome contributions.

**Repository:** [github.com/PrimeevolutionZ/apikeyrotator](https://github.com/PrimeevolutionZ/apikeyrotator)

**Ways to contribute:**
- Report bugs or issues
- Suggest new features
- Submit pull requests
- Improve documentation

---

## 📝 License

APIKeyRotator is distributed under the MIT License.

See [LICENSE](https://github.com/PrimeevolutionZ/apikeyrotator/blob/master/LICENSE) for details.

---

## 🔗 Links

- **GitHub Repository:** [PrimeevolutionZ/apikeyrotator](https://github.com/PrimeevolutionZ/apikeyrotator)
- **PyPI Package:** [pypi.org/project/apikeyrotator](https://pypi.org/project/apikeyrotator/)
- **Issue Tracker:** [GitHub Issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues)

---

## 📞 Support

Need help? Here's how to get support:

1. **Check the [FAQ](FAQ.md)** - Most common questions are answered here
2. **Search [existing issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues)** - Your problem might be solved
3. **Read the documentation** - Use the navigation above to find relevant sections
4. **Open a new issue** - If you can't find an answer, create a detailed issue

---

## 🗺️ Documentation Roadmap

Recommended reading order:

1. **New Users:**
   - [Getting Started](GETTING_STARTED.md) → [Examples](EXAMPLES.md) → [FAQ](FAQ.md)

2. **Intermediate Users:**
   - [Middleware Guide](MIDDLEWARE.md) → [Advanced Usage](ADVANCED_USAGE.md) → [API Reference](API_REFERENCE.md)

3. **Advanced Users:**
   - [API Reference](API_REFERENCE.md) → [Advanced Usage](ADVANCED_USAGE.md) → [Middleware Guide](MIDDLEWARE.md) → Source code

4. **Troubleshooting:**
   - [FAQ](FAQ.md) → [Error Handling](ERROR_HANDLING.md) → [GitHub Issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues)

---

## 🆕 What's New in 0.8.0

- 🧯 **Resilience**: request deadlines (`total_timeout`), per-host circuit breaker, safe retries of POST/PATCH
- 🚦 **Rate limits**: client-side token bucket per key, `X-RateLimit-Remaining` hints
- 🔗 **Shared state**: `RedisStateBackend` shares limits, rejected keys and token buckets between processes
- 🔄 **Background key refresh** from secret providers
- 🌐 **httpx backend** with HTTP/2, `failover` rotation strategy
- 🪶 **Leaner core**: 69 ms import, ~230 bytes per key; Python 3.12+
- 🔇 The library no longer configures logging output (use `logging.basicConfig`)

[View complete changelog](../CHANGELOG.md)

---

**Happy coding with APIKeyRotator! 🚀**