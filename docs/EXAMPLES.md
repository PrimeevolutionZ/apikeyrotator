# Examples

Real-world examples demonstrating various use cases for APIKeyRotator.

## Table of Contents

- [Basic Usage](#basic-usage)
- [Middleware Examples](#middleware-examples)
- [Metrics & Monitoring](#metrics--monitoring)
- [Secret Providers](#secret-providers)
- [Web Scraping](#web-scraping)
- [Data Collection](#data-collection)
- [API Integration](#api-integration)
- [Asynchronous Operations](#asynchronous-operations)
- [Production Patterns](#production-patterns)

---

## Basic Usage

### Simple GET Request

```python
from apikeyrotator import APIKeyRotator

# Initialize rotator
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])

# Make a simple request
response = rotator.get("https://api.example.com/users")
users = response.json()

for user in users:
    print(f"User: {user['name']}")
```

### POST Request with Data

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2"])

# Create a new resource
response = rotator.post(
    "https://api.example.com/users",
    json={
        "name": "John Doe",
        "email": "john@example.com"
    }
)

if response.status_code == 201:
    user = response.json()
    print(f"Created user: {user['id']}")
```

---

## Middleware Examples

### Using Cache Middleware

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import CachingMiddleware

# Create cache middleware
cache = CachingMiddleware(
    ttl=600,  # Cache for 10 minutes
    max_cache_size=500  # Store up to 500 responses
)

# Initialize rotator with middleware
rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[cache]
)

# First request - cache miss
response1 = rotator.get("https://api.example.com/data")
print("First request completed")

# Second request - cache hit (instant)
response2 = rotator.get("https://api.example.com/data")
print("Second request completed (from cache)")

# View cache statistics
stats = cache.get_stats()
print(f"Cache hits: {stats['hits']}")
print(f"Cache misses: {stats['misses']}")
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Cache size: {stats['cache_size']}/{stats['max_cache_size']}")
```

### Logging Middleware

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import LoggingMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create logging middleware
log_middleware = LoggingMiddleware(
    verbose=True,
    log_response_time=True,
    max_key_chars=4  # Show only first 4 chars of key
)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[log_middleware]
)

# Requests will be logged automatically
response = rotator.get("https://api.example.com/data")

# Output:
# 📤 GET https://api.example.com/data (key: key1****, attempt: 1)
# 📥 ✅ 200 from https://api.example.com/data (key: key1****) (0.234s)
```

### Rate Limit Middleware

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import RateLimitMiddleware

# Create rate limit middleware
rate_limit = RateLimitMiddleware(
    pause_on_limit=True,  # Automatically wait when rate limited
    max_tracked_keys=100
)

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    middlewares=[rate_limit]
)

# Make many requests - middleware tracks rate limits
for i in range(1000):
    response = rotator.get(f"https://api.example.com/item/{i}")
    print(f"Processed item {i}")

# View rate limit stats
stats = rate_limit.get_stats()
print(f"Tracked keys: {stats['tracked_keys']}")
print(f"Active limits: {stats['active_limits']}")
```

### Combining Multiple Middleware

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import (
    CachingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware
)

# Create middleware stack
cache = CachingMiddleware(ttl=300)
logger = LoggingMiddleware(verbose=True)
rate_limit = RateLimitMiddleware(pause_on_limit=True)

# Initialize with all middleware
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    middlewares=[cache, logger, rate_limit]  # Order matters!
)

# Middleware execution order:
# before_request: cache → logger → rate_limit
# after_request: rate_limit → logger → cache

# Make requests with full middleware stack
for i in range(100):
    response = rotator.get(f"https://api.example.com/data/{i}")
```

### Custom Middleware

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import RequestInfo, ResponseInfo, ErrorInfo

class CustomHeaderMiddleware:
    """Add custom headers to all requests."""
    
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        # Add custom headers
        request_info.headers["X-Client-Version"] = "2.0"
        request_info.headers["X-Request-ID"] = self._generate_request_id()
        return request_info
    
    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Log response status
        print(f"Response: {response_info.status_code}")
        return response_info
    
    async def on_error(self, error_info: ErrorInfo) -> bool:
        # Handle errors
        print(f"Error: {error_info.exception}")
        return False  # Don't handle, let rotator retry
    
    def _generate_request_id(self) -> str:
        import uuid
        return str(uuid.uuid4())

# Use custom middleware
custom = CustomHeaderMiddleware()
rotator = APIKeyRotator(
    api_keys=["key1"],
    middlewares=[custom]
)
```

---

## Metrics & Monitoring

### Basic Metrics Collection

```python
from apikeyrotator import APIKeyRotator

# Enable metrics (enabled by default)
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    enable_metrics=True
)

# Make requests
for i in range(100):
    try:
        response = rotator.get(f"https://api.example.com/item/{i}")
    except Exception:
        pass

# Get overall metrics
metrics = rotator.get_metrics()
print(f"Total requests: {metrics['total_requests']}")
print(f"Successful: {metrics['successful_requests']}")
print(f"Failed: {metrics['failed_requests']}")
print(f"Success rate: {metrics['success_rate']:.2%}")
print(f"Uptime: {metrics['uptime_seconds']:.1f}s")

# Get per-key statistics
key_stats = rotator.get_key_statistics()
for key, stats in key_stats.items():
    print(f"\nKey: {key[:4]}****")
    print(f"  Total: {stats['total_requests']}")
    print(f"  Success rate: {stats['success_rate']:.2%}")
    print(f"  Avg response time: {stats['avg_response_time']:.3f}s")
    print(f"  Health: {'✅' if stats['is_healthy'] else '❌'}")
```

### Per-Endpoint Metrics

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2"])

# Make requests to different endpoints
endpoints = [
    "/users",
    "/posts",
    "/comments",
    "/analytics"
]

for endpoint in endpoints:
    for i in range(25):
        rotator.get(f"https://api.example.com{endpoint}")

# Get metrics
metrics = rotator.get_metrics()

# View per-endpoint stats
for endpoint, stats in metrics['endpoint_stats'].items():
    print(f"\nEndpoint: {endpoint}")
    print(f"  Requests: {stats['total_requests']}")
    print(f"  Success: {stats['successful_requests']}")
    print(f"  Failed: {stats['failed_requests']}")
    print(f"  Avg time: {stats['avg_response_time']:.3f}s")
```

### Prometheus Export

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.metrics import PrometheusExporter

# Make requests
rotator = APIKeyRotator(api_keys=["key1", "key2"])
for i in range(100):
    rotator.get(f"https://api.example.com/data/{i}")

# Export to Prometheus format
exporter = PrometheusExporter()
metrics_text = exporter.export(rotator.metrics)

# Save to file for node_exporter
with open('/var/lib/prometheus/node_exporter/rotator.prom', 'w') as f:
    f.write(metrics_text)

# Or serve via HTTP endpoint
from flask import Flask, Response

app = Flask(__name__)

@app.route('/metrics')
def metrics():
    return Response(metrics_text, mimetype='text/plain')

if __name__ == '__main__':
    app.run(port=9090)
```

### Real-Time Monitoring Dashboard

```python
from apikeyrotator import APIKeyRotator
import time
import os

class MonitoringDashboard:
    """Real-time monitoring dashboard."""
    
    def __init__(self, rotator: APIKeyRotator):
        self.rotator = rotator
    
    def display(self):
        """Display current stats."""
        os.system('clear' if os.name == 'posix' else 'cls')
        
        metrics = self.rotator.get_metrics()
        key_stats = self.rotator.get_key_statistics()
        
        print("=" * 60)
        print("APIKeyRotator Monitoring Dashboard")
        print("=" * 60)
        
        print(f"\n📊 Overall Stats:")
        print(f"  Total Requests: {metrics['total_requests']}")
        print(f"  Success Rate: {metrics['success_rate']:.2%}")
        print(f"  Uptime: {metrics['uptime_seconds']:.1f}s")
        
        print(f"\n🔑 Key Health:")
        for key, stats in key_stats.items():
            health = "✅" if stats['is_healthy'] else "❌"
            print(f"  {health} {key[:4]}**** - "
                  f"{stats['successful_requests']}/{stats['total_requests']} "
                  f"({stats['success_rate']:.1%})")
        
        print(f"\n🌐 Top Endpoints:")
        if hasattr(self.rotator.metrics, 'get_top_endpoints'):
            for endpoint, count in self.rotator.metrics.get_top_endpoints(5):
                print(f"  {count:>4} requests - {endpoint}")
    
    def run(self, interval: int = 5):
        """Run dashboard with auto-refresh."""
        try:
            while True:
                self.display()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nDashboard stopped")

# Usage
rotator = APIKeyRotator(api_keys=["key1", "key2"])
dashboard = MonitoringDashboard(rotator)

# Start making requests in background thread
import threading

def make_requests():
    for i in range(1000):
        try:
            rotator.get(f"https://api.example.com/item/{i}")
            time.sleep(0.1)
        except Exception:
            pass

thread = threading.Thread(target=make_requests)
thread.daemon = True
thread.start()

# Display dashboard
dashboard.run(interval=2)
```

---

## Secret Providers

### Loading from AWS Secrets Manager

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.providers import AWSSecretsManagerProvider

# Create AWS provider
provider = AWSSecretsManagerProvider(
    secret_name="my-api-keys",
    region_name="us-east-1"
)

# Initialize rotator with provider
rotator = APIKeyRotator(secret_provider=provider)

# Keys are automatically loaded from AWS
response = rotator.get("https://api.example.com/data")

# Refresh keys periodically
import asyncio

async def refresh_keys_periodically():
    while True:
        await asyncio.sleep(3600)  # Every hour
        await rotator.refresh_keys_from_provider()
        print("Keys refreshed from AWS")

# Run in background
asyncio.create_task(refresh_keys_periodically())
```

### Loading from Google Cloud

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.providers import GCPSecretManagerProvider

provider = GCPSecretManagerProvider(
    project_id="my-project",
    secret_id="api-keys",
    version_id="latest"
)

rotator = APIKeyRotator(secret_provider=provider)
```

### Loading from File

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.providers import FileSecretProvider

# From JSON file
provider = FileSecretProvider(file_path="keys.json")
# File content: ["key1", "key2", "key3"]

rotator = APIKeyRotator(secret_provider=provider)
```

### Using Factory Function

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.providers import create_secret_provider

# Create provider via factory
provider = create_secret_provider(
    'aws_secrets_manager',
    secret_name='my-keys',
    region_name='us-east-1'
)

rotator = APIKeyRotator(secret_provider=provider)
```

---

## Web Scraping

### Scraping with Rate Limit Protection

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import CachingMiddleware, LoggingMiddleware
from bs4 import BeautifulSoup
import time

# Configure for web scraping
cache = CachingMiddleware(ttl=3600)  # Cache for 1 hour
logger = LoggingMiddleware(verbose=False)

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    ],
    random_delay_range=(1.0, 3.0),
    max_retries=5,
    middlewares=[cache, logger]
)

# Scrape multiple pages
base_url = "https://example.com/products"
products = []

for page in range(1, 11):
    try:
        response = rotator.get(f"{base_url}?page={page}")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract product information
        for item in soup.find_all('div', class_='product'):
            products.append({
                'name': item.find('h2').text,
                'price': item.find('span', class_='price').text,
                'url': item.find('a')['href']
            })
        
        print(f"Scraped page {page}, total products: {len(products)}")
        
    except Exception as e:
        print(f"Error scraping page {page}: {e}")

print(f"Successfully scraped {len(products)} products")

# View cache effectiveness
cache_stats = cache.get_stats()
print(f"Cache saved {cache_stats['hits']} requests")
```

### Rotating Proxies for Scraping

```python
from apikeyrotator import APIKeyRotator

PROXIES = [
    "http://user:pass@proxy1.example.com:8080",
    "http://user:pass@proxy2.example.com:8080",
    "http://user:pass@proxy3.example.com:8080"
]

rotator = APIKeyRotator(
    api_keys=["scraping_key_1", "scraping_key_2"],
    proxy_list=PROXIES,
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        "Mozilla/5.0 (X11; Linux x86_64)..."
    ],
    random_delay_range=(2.0, 5.0)
)

urls = [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3"
]

for url in urls:
    try:
        response = rotator.get(url)
        print(f"Scraped {url}: {response.status_code}")
    except Exception as e:
        print(f"Failed {url}: {e}")
```

---

## Data Collection

### Collecting Data from Multiple Endpoints

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError
from apikeyrotator.middleware import CachingMiddleware
import json

cache = CachingMiddleware(ttl=300)

rotator = APIKeyRotator(
    api_keys=["analytics_key_1", "analytics_key_2", "analytics_key_3"],
    max_retries=5,
    base_delay=2.0,
    middlewares=[cache]
)

def collect_analytics_data(start_date, end_date):
    """Collect analytics data for a date range."""
    
    endpoints = [
        "/api/v1/analytics/pageviews",
        "/api/v1/analytics/visitors",
        "/api/v1/analytics/conversions",
        "/api/v1/analytics/revenue"
    ]
    
    results = {}
    
    for endpoint in endpoints:
        try:
            response = rotator.get(
                f"https://analytics.example.com{endpoint}",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "format": "json"
                }
            )
            
            data = response.json()
            metric_name = endpoint.split('/')[-1]
            results[metric_name] = data
            
            print(f"✓ Collected {metric_name}")
            
        except AllKeysExhaustedError:
            print(f"✗ Failed to collect {metric_name} - all keys exhausted")
        except Exception as e:
            print(f"✗ Error collecting {metric_name}: {e}")
    
    return results

# Collect data
data = collect_analytics_data("2025-01-01", "2025-01-31")

# Save to file
with open("analytics_data.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"Collected data for {len(data)} metrics")

# View cache performance
cache_stats = cache.get_stats()
print(f"Cache hit rate: {cache_stats['hit_rate']:.2%}")
```

### Batch Processing with Progress Tracking

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import LoggingMiddleware
from tqdm import tqdm
from datetime import datetime

logger = LoggingMiddleware(verbose=False)

rotator = APIKeyRotator(
    api_keys=["batch_key_1", "batch_key_2"],
    max_retries=3,
    middlewares=[logger]
)

def process_batch(item_ids):
    """Process a batch of items with progress tracking."""
    
    results = []
    failed = []
    
    for item_id in tqdm(item_ids, desc="Processing items"):
        try:
            response = rotator.get(
                f"https://api.example.com/items/{item_id}"
            )
            
            item_data = response.json()
            
            # Transform data
            processed = {
                'id': item_data['id'],
                'name': item_data['name'],
                'category': item_data['category'],
                'processed_at': datetime.now().isoformat()
            }
            
            results.append(processed)
            
        except Exception as e:
            failed.append({'id': item_id, 'error': str(e)})
    
    return results, failed

# Process items
item_ids = range(1, 1001)  # 1000 items
successful, failed = process_batch(item_ids)

print(f"Processed: {len(successful)}, Failed: {len(failed)}")

# View metrics
metrics = rotator.get_metrics()
print(f"Success rate: {metrics['success_rate']:.2%}")
```

---

## API Integration

### REST API Client with Middleware

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import CachingMiddleware, LoggingMiddleware
from typing import Dict, List, Optional

class APIClient:
    """Wrapper around APIKeyRotator for a specific API."""
    
    def __init__(self, api_keys: List[str], base_url: str):
        self.base_url = base_url.rstrip('/')
        
        # Setup middleware
        cache = CachingMiddleware(ttl=300)
        logger = LoggingMiddleware(verbose=True)
        
        self.rotator = APIKeyRotator(
            api_keys=api_keys,
            max_retries=5,
            base_delay=1.0,
            middlewares=[cache, logger]
        )
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make a request to the API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = getattr(self.rotator, method)(url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def get_user(self, user_id: int) -> Dict:
        """Get user by ID."""
        return self._request('get', f'/users/{user_id}')
    
    def list_users(self, page: int = 1, per_page: int = 20) -> List[Dict]:
        """List users with pagination."""
        return self._request('get', '/users', params={
            'page': page,
            'per_page': per_page
        })
    
    def create_user(self, data: Dict) -> Dict:
        """Create a new user."""
        return self._request('post', '/users', json=data)
    
    def update_user(self, user_id: int, data: Dict) -> Dict:
        """Update an existing user."""
        return self._request('put', f'/users/{user_id}', json=data)
    
    def delete_user(self, user_id: int) -> None:
        """Delete a user."""
        self._request('delete', f'/users/{user_id}')
    
    def get_metrics(self) -> Dict:
        """Get API client metrics."""
        return self.rotator.get_metrics()

# Usage
client = APIClient(
    api_keys=["key1", "key2", "key3"],
    base_url="https://api.example.com/v1"
)

# Get user
user = client.get_user(123)
print(f"User: {user['name']}")

# Create user
new_user = client.create_user({
    'name': 'Jane Doe',
    'email': 'jane@example.com'
})

# List all users
all_users = []
page = 1
while True:
    users = client.list_users(page=page, per_page=50)
    if not users:
        break
    all_users.extend(users)
    page += 1

print(f"Total users: {len(all_users)}")

# View metrics
metrics = client.get_metrics()
print(f"API calls made: {metrics['total_requests']}")
print(f"Success rate: {metrics['success_rate']:.2%}")
```

### GraphQL API Client

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.middleware import CachingMiddleware
import json

class GraphQLClient:
    """GraphQL client using APIKeyRotator."""
    
    def __init__(self, api_keys: List[str], endpoint: str):
        self.endpoint = endpoint
        
        cache = CachingMiddleware(ttl=600)
        self.rotator = APIKeyRotator(
            api_keys=api_keys,
            middlewares=[cache]
        )
    
    def query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a GraphQL query."""
        response = self.rotator.post(
            self.endpoint,
            json={
                'query': query,
                'variables': variables or {}
            }
        )
        
        data = response.json()
        
        if 'errors' in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        
        return data['data']

# Usage
client = GraphQLClient(
    api_keys=["graphql_key_1", "graphql_key_2"],
    endpoint="https://api.example.com/graphql"
)

# Query
query = """
query GetUser($id: ID!) {
    user(id: $id) {
        id
        name
        email
        posts {
            title
            createdAt
        }
    }
}
"""

result = client.query(query, variables={'id': '123'})
user = result['user']
print(f"User {user['name']} has {len(user['posts'])} posts")
```

---

## Asynchronous Operations

### Concurrent Data Fetching with Middleware

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator
from apikeyrotator.middleware import CachingMiddleware, LoggingMiddleware
from typing import List, Dict

async def fetch_all_items(item_ids: List[int]) -> List[Dict]:
    """Fetch multiple items concurrently."""
    
    cache = CachingMiddleware(ttl=300)
    logger = LoggingMiddleware(verbose=False)
    
    async with AsyncAPIKeyRotator(
        api_keys=["async_key_1", "async_key_2", "async_key_3"],
        max_retries=3,
        middlewares=[cache, logger]
    ) as rotator:
        
        async def fetch_item(item_id: int) -> Dict:
            """Fetch a single item."""
            response = await rotator.get(
                f"https://api.example.com/items/{item_id}"
            )
            return await response.json()
        
        # Create tasks for all items
        tasks = [fetch_item(item_id) for item_id in item_ids]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        items = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]
        
        print(f"Success: {len(items)}, Errors: {len(errors)}")
        
        # View cache performance
        cache_stats = cache.get_stats()
        print(f"Cache hit rate: {cache_stats['hit_rate']:.2%}")
        
        return items

# Run
item_ids = list(range(1, 101))  # Fetch 100 items
items = asyncio.run(fetch_all_items(item_ids))
```

### Rate-Limited Async Processing

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator
from apikeyrotator.middleware import RateLimitMiddleware
from asyncio import Semaphore

async def process_with_rate_limit(urls: List[str], max_concurrent: int = 10):
    """Process URLs with concurrent request limiting."""
    
    semaphore = Semaphore(max_concurrent)
    rate_limit = RateLimitMiddleware(pause_on_limit=True)
    
    async with AsyncAPIKeyRotator(
        api_keys=["key1", "key2"],
        random_delay_range=(0.5, 1.5),
        middlewares=[rate_limit]
    ) as rotator:
        
        async def fetch_url(url: str) -> Dict:
            """Fetch single URL with semaphore."""
            async with semaphore:
                response = await rotator.get(url)
                return {
                    'url': url,
                    'status': response.status,
                    'data': await response.json()
                }
        
        tasks = [fetch_url(url) for url in urls]
        results = await asyncio.gather(*tasks)
        
        # View rate limit stats
        stats = rate_limit.get_stats()
        print(f"Rate limits encountered: {stats['active_limits']}")
        
        return results

# Process 100 URLs with max 10 concurrent requests
urls = [f"https://api.example.com/resource/{i}" for i in range(100)]
results = asyncio.run(process_with_rate_limit(urls, max_concurrent=10))
```

---

## Production Patterns

### Resilient API Client with Full Monitoring

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError
from apikeyrotator.middleware import (
    CachingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware
)
import logging
from typing import Optional, Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProductionAPIClient:
    """Production-ready API client with full monitoring."""
    
    def __init__(
        self,
        primary_keys: List[str],
        fallback_keys: Optional[List[str]] = None
    ):
        # Setup middleware
        cache = CachingMiddleware(ttl=600, max_cache_size=1000)
        log_middleware = LoggingMiddleware(verbose=True)
        rate_limit = RateLimitMiddleware(pause_on_limit=True)
        
        self.primary = APIKeyRotator(
            api_keys=primary_keys,
            max_retries=3,
            logger=logger,
            middlewares=[cache, log_middleware, rate_limit],
            enable_metrics=True
        )
        
        self.fallback = None
        if fallback_keys:
            self.fallback = APIKeyRotator(
                api_keys=fallback_keys,
                max_retries=2,
                logger=logger,
                middlewares=[log_middleware]
            )
        
        self.cache = cache
        self.rate_limit = rate_limit
    
    def get(self, url: str, use_cache: bool = True, **kwargs) -> Dict:
        """
        Make a GET request with fallback support.
        """
        # Try primary rotator
        try:
            response = self.primary.get(url, **kwargs)
            data = response.json()
            return data
            
        except AllKeysExhaustedError:
            logger.warning("Primary keys exhausted, trying fallback")
            
            # Try fallback if available
            if self.fallback:
                try:
                    response = self.fallback.get(url, **kwargs)
                    data = response.json()
                    return data
                    
                except AllKeysExhaustedError:
                    logger.error("Fallback keys also exhausted")
                    raise
            else:
                raise
    
    def get_health_report(self) -> Dict:
        """Get comprehensive health report."""
        metrics = self.primary.get_metrics()
        key_stats = self.primary.get_key_statistics()
        cache_stats = self.cache.get_stats()
        rate_limit_stats = self.rate_limit.get_stats()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'overall': {
                'total_requests': metrics['total_requests'],
                'success_rate': metrics['success_rate'],
                'uptime': metrics['uptime_seconds']
            },
            'keys': {
                'healthy': sum(1 for s in key_stats.values() if s['is_healthy']),
                'total': len(key_stats)
            },
            'cache': {
                'hit_rate': cache_stats['hit_rate'],
                'size': cache_stats['cache_size']
            },
            'rate_limits': {
                'active': rate_limit_stats['active_limits']
            }
        }

# Usage
client = ProductionAPIClient(
    primary_keys=["primary_key_1", "primary_key_2"],
    fallback_keys=["fallback_key_1"]
)

try:
    data = client.get("https://api.example.com/critical/data")
    print("Success:", data)
except AllKeysExhaustedError:
    print("All keys exhausted, cannot proceed")

# Regular health checks
health = client.get_health_report()
print(f"System health: {health['overall']['success_rate']:.2%} success rate")
print(f"Healthy keys: {health['keys']['healthy']}/{health['keys']['total']}")
print(f"Cache hit rate: {health['cache']['hit_rate']:.2%}")
```

### Enterprise-Grade API Client

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError
from apikeyrotator.middleware import (
    CachingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    RetryMiddleware
)
from apikeyrotator.providers import AWSSecretsManagerProvider
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import json

@dataclass
class APIMetrics:
    """Metrics for monitoring."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cache_hits: int = 0
    rate_limit_hits: int = 0
    start_time: datetime = None

class EnterpriseAPIClient:
    """
    Enterprise-grade API client with:
    - AWS Secrets Manager integration
    - Comprehensive middleware stack
    - Health monitoring
    - Automatic alerting
    """
    
    def __init__(
        self,
        secret_name: str,
        region_name: str = "us-east-1",
        alert_callback: Optional[callable] = None
    ):
        # Load keys from AWS
        provider = AWSSecretsManagerProvider(
            secret_name=secret_name,
            region_name=region_name
        )
        
        # Setup comprehensive middleware stack
        self.cache = CachingMiddleware(ttl=900, max_cache_size=5000)
        self.logger = LoggingMiddleware(verbose=True)
        self.rate_limit = RateLimitMiddleware(pause_on_limit=True)
        self.retry = RetryMiddleware(max_retries=5, backoff_factor=2.0)
        
        self.rotator = APIKeyRotator(
            secret_provider=provider,
            max_retries=3,
            base_delay=2.0,
            middlewares=[
                self.cache,
                self.logger,
                self.rate_limit,
                self.retry
            ],
            enable_metrics=True
        )
        
        self.alert_callback = alert_callback
        self.metrics = APIMetrics(start_time=datetime.now())
    
    def request(self, method: str, url: str, **kwargs) -> Dict:
        """Make HTTP request with full monitoring."""
        self.metrics.total_requests += 1
        
        try:
            response = getattr(self.rotator, method)(url, **kwargs)
            self.metrics.successful_requests += 1
            
            # Check if from cache
            cache_stats = self.cache.get_stats()
            self.metrics.cache_hits = cache_stats['hits']
            
            return response.json()
            
        except AllKeysExhaustedError as e:
            self.metrics.failed_requests += 1
            self._send_alert("All keys exhausted", str(e))
            raise
        except Exception as e:
            self.metrics.failed_requests += 1
            raise
    
    def get(self, url: str, **kwargs) -> Dict:
        """GET request."""
        return self.request('get', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> Dict:
        """POST request."""
        return self.request('post', url, **kwargs)
    
    def _send_alert(self, title: str, message: str):
        """Send alert via callback."""
        if self.alert_callback:
            self.alert_callback(title, message)
    
    def get_comprehensive_report(self) -> Dict:
        """Get comprehensive system report."""
        rotator_metrics = self.rotator.get_metrics()
        key_stats = self.rotator.get_key_statistics()
        cache_stats = self.cache.get_stats()
        rate_limit_stats = self.rate_limit.get_stats()
        retry_stats = self.retry.get_stats()
        
        uptime = (datetime.now() - self.metrics.start_time).total_seconds()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': uptime,
            'requests': {
                'total': self.metrics.total_requests,
                'successful': self.metrics.successful_requests,
                'failed': self.metrics.failed_requests,
                'success_rate': (
                    self.metrics.successful_requests / self.metrics.total_requests
                    if self.metrics.total_requests > 0 else 0
                )
            },
            'keys': {
                'total': len(key_stats),
                'healthy': sum(1 for s in key_stats.values() if s['is_healthy']),
                'details': {
                    k[:4] + '****': {
                        'requests': v['total_requests'],
                        'success_rate': v['success_rate'],
                        'healthy': v['is_healthy']
                    }
                    for k, v in key_stats.items()
                }
            },
            'cache': {
                'hit_rate': cache_stats['hit_rate'],
                'hits': cache_stats['hits'],
                'misses': cache_stats['misses'],
                'size': cache_stats['cache_size'],
                'max_size': cache_stats['max_cache_size']
            },
            'rate_limits': {
                'tracked_keys': rate_limit_stats['tracked_keys'],
                'active_limits': rate_limit_stats['active_limits']
            },
            'retries': {
                'active_retries': retry_stats['active_retries'],
                'tracked_urls': retry_stats['tracked_urls']
            },
            'endpoints': rotator_metrics.get('endpoint_stats', {})
        }
    
    def export_report(self, filename: str = "api_report.json"):
        """Export report to file."""
        report = self.get_comprehensive_report()
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Report exported to {filename}")

# Usage with alerting
def send_slack_alert(title: str, message: str):
    """Send alert to Slack."""
    # Implementation for Slack webhook
    print(f"ALERT: {title} - {message}")

client = EnterpriseAPIClient(
    secret_name="production-api-keys",
    region_name="us-east-1",
    alert_callback=send_slack_alert
)

# Make requests
for i in range(1000):
    try:
        data = client.get(f"https://api.example.com/data/{i}")
    except Exception as e:
        print(f"Error: {e}")

# Get and export comprehensive report
report = client.get_comprehensive_report()
print(f"Success rate: {report['requests']['success_rate']:.2%}")
print(f"Cache hit rate: {report['cache']['hit_rate']:.2%}")
print(f"Healthy keys: {report['keys']['healthy']}/{report['keys']['total']}")

client.export_report("production_api_report.json")
```

---

## Advanced Patterns

### Circuit Breaker Pattern

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.utils import CircuitBreaker

# Create circuit breaker
breaker = CircuitBreaker(
    failure_threshold=5,  # Open after 5 failures
    timeout=60  # Try again after 60 seconds
)

rotator = APIKeyRotator(api_keys=["key1", "key2"])

def safe_api_call(url: str):
    """API call with circuit breaker protection."""
    if not breaker.allow_request():
        print(f"Circuit breaker is {breaker.get_state()}, skipping request")
        return None
    
    try:
        response = rotator.get(url)
        breaker.record_success()
        return response.json()
    except Exception as e:
        breaker.record_failure()
        print(f"Request failed: {e}")
        return None

# Make requests
for i in range(20):
    result = safe_api_call(f"https://api.example.com/data/{i}")
    if result:
        print(f"Success: {result}")
    print(f"Circuit breaker state: {breaker.get_state()}")
```

### Retry with Custom Exponential Backoff

```python
from apikeyrotator import APIKeyRotator
from apikeyrotator.utils import jittered_backoff
import time

rotator = APIKeyRotator(api_keys=["key1", "key2"])

def retry_with_jitter(url: str, max_attempts: int = 5):
    """Retry with jittered exponential backoff."""
    for attempt in range(max_attempts):
        try:
            response = rotator.get(url)
            return response.json()
        except Exception as e:
            if attempt < max_attempts - 1:
                delay = jittered_backoff(attempt, base_delay=1.0, max_delay=30.0)
                print(f"Attempt {attempt + 1} failed, waiting {delay:.2f}s")
                time.sleep(delay)
            else:
                print(f"All {max_attempts} attempts failed")
                raise

# Usage
data = retry_with_jitter("https://api.example.com/data")
```

### Performance Benchmarking

```python
from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator
from apikeyrotator.utils import measure_time, measure_time_async
import asyncio
import time

# Synchronous benchmark
@measure_time
def sync_benchmark(count: int = 100):
    """Benchmark synchronous requests."""
    rotator = APIKeyRotator(api_keys=["key1", "key2"])
    for i in range(count):
        rotator.get(f"https://api.example.com/data/{i}")

# Asynchronous benchmark
@measure_time_async
async def async_benchmark(count: int = 100):
    """Benchmark asynchronous requests."""
    async with AsyncAPIKeyRotator(api_keys=["key1", "key2"]) as rotator:
        tasks = [
            rotator.get(f"https://api.example.com/data/{i}")
            for i in range(count)
        ]
        await asyncio.gather(*tasks)

# Run benchmarks
print("Synchronous benchmark:")
sync_benchmark(100)

print("\nAsynchronous benchmark:")
asyncio.run(async_benchmark(100))
```

---

## Next Steps

- Read [Middleware Guide](MIDDLEWARE.md) for detailed middleware documentation
- Check [API Reference](API_REFERENCE.md) for complete API documentation
- Review [Advanced Usage](ADVANCED_USAGE.md) for more features
- See [FAQ](FAQ.md) for common questions