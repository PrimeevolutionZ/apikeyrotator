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
| [FAQ](FAQ.md)                         | Frequently asked questions                   | Quick answers to common questions      |

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
- Core concepts: key rotation, retry logic, header detection
- Common use cases
- Configuration with `.env` files

**Start here if you:**
- Are new to APIKeyRotator
- Want a quick overview
- Need basic setup instructions

---

### [API Reference](API_REFERENCE.md)

Complete technical reference for all classes, methods, and parameters.

**Topics covered:**
- `APIKeyRotator` class (synchronous)
- `AsyncAPIKeyRotator` class (asynchronous)
- Error classification system
- Rotation strategies
- Middleware system
- Metrics and monitoring
- Secret providers
- Configuration management
- Custom callbacks
- Exception types

**Use this when you:**
- Need detailed parameter information
- Want to understand method signatures
- Are looking up specific functionality

---

### [Middleware Guide](MIDDLEWARE.md)

Comprehensive guide to the middleware system for request/response interception.

**Topics covered:**
- Middleware architecture and lifecycle
- Built-in middleware (Caching, Logging, Rate Limit, Retry)
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
- Rotation strategies (round-robin, random, weighted, LRU, health-based)
- Metrics and monitoring
- Secret providers (AWS, GCP, File, Environment)
- Custom callbacks (retry logic, headers)
- Anti-bot evasion (User-Agent rotation, proxies, delays)
- Custom error classification
- Session management
- Configuration management
- Performance optimization

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
| Handle rate limits  | [Advanced Usage](ADVANCED_USAGE.md#anti-bot-evasion) |
| Use with async code | [API Reference](API_REFERENCE.md#asyncapikeyrotator) |
| Add custom headers  | [Advanced Usage](ADVANCED_USAGE.md#custom-callbacks) |
| Track metrics       | [Advanced Usage](ADVANCED_USAGE.md#metrics-and-monitoring) |
| Handle errors       | [Error Handling](ERROR_HANDLING.md)                  |
| See examples        | [Examples](EXAMPLES.md)                              |
| Debug issues        | [FAQ](FAQ.md#error-handling)                         |

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
from apikeyrotator.middleware import RateLimitMiddleware

rate_limit = RateLimitMiddleware(pause_on_limit=True)

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    max_retries=5,
    base_delay=2.0,
    random_delay_range=(1.0, 3.0),
    middlewares=[rate_limit]
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
except AllKeysExhaustedError:
    print("All keys failed")

# View metrics
metrics = rotator.get_metrics()
print(f"Success rate: {metrics['success_rate']:.2%}")
```

---

## 🔑 Key Features

### Effortless Integration
Drop-in replacement for `requests` and `aiohttp` with familiar API.

[Learn more in Getting Started](GETTING_STARTED.md)

### Automatic Key Rotation
Seamlessly cycles through API keys to distribute load and bypass rate limits.

[See rotation strategies](API_REFERENCE.md#rotation-strategies)

### Middleware System
Powerful request/response interception for caching, logging, and custom processing.

[Explore middleware](MIDDLEWARE.md)

### Smart Retry Logic
Exponential backoff and intelligent error classification for resilient requests.

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

### Intelligent Headers
Auto-detects authorization patterns and persists successful configurations.

[Learn about header management](ADVANCED_USAGE.md#dynamic-header-generation)

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

[Configuration guide](GETTING_STARTED.md#using-environment-variables)

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
    enable_metrics=True
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
| Session management   | ❌ Manual            | ✅ Optimized     |
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

## 🆕 What's New in 0.4.3

**Major Features:**
- 🎯 **Middleware System**: Caching, Logging, Rate Limit, Retry middleware
- 📊 **Metrics Collection**: Built-in metrics with Prometheus export
- 🔐 **Secret Providers**: AWS, GCP, File, Environment providers
- 🔄 **Rotation Strategies**: Round-robin, Random, Weighted, LRU, Health-based
- 🧵 **Thread Safety**: Full thread-safe implementation
- 🔧 **Enhanced Error Classification**: More granular error handling

[View complete changelog](../CHANGELOG.md)

---

**Happy coding with APIKeyRotator! 🚀**