# Examples

Real-world examples demonstrating various use cases for APIKeyRotator.

## Table of Contents

- [Basic Usage](#basic-usage)
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

## Web Scraping

### Scraping with Rate Limit Protection

```python
from apikeyrotator import APIKeyRotator
from bs4 import BeautifulSoup
import time

# Configure rotator for web scraping
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    ],
    random_delay_range=(1.0, 3.0),
    max_retries=5
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
import json

rotator = APIKeyRotator(
    api_keys=["analytics_key_1", "analytics_key_2", "analytics_key_3"],
    max_retries=5,
    base_delay=2.0
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
```

### Batch Processing with Progress Tracking

```python
from apikeyrotator import APIKeyRotator
from tqdm import tqdm

rotator = APIKeyRotator(
    api_keys=["batch_key_1", "batch_key_2"],
    max_retries=3
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
```

---

## API Integration

### REST API Client

```python
from apikeyrotator import APIKeyRotator
from typing import Dict, List, Optional

class APIClient:
    """Wrapper around APIKeyRotator for a specific API."""
    
    def __init__(self, api_keys: List[str], base_url: str):
        self.base_url = base_url.rstrip('/')
        self.rotator = APIKeyRotator(
            api_keys=api_keys,
            max_retries=5,
            base_delay=1.0
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
```

### GraphQL API Client

```python
from apikeyrotator import APIKeyRotator
import json

class GraphQLClient:
    """GraphQL client using APIKeyRotator."""
    
    def __init__(self, api_keys: List[str], endpoint: str):
        self.endpoint = endpoint
        self.rotator = APIKeyRotator(api_keys=api_keys)
    
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

### Concurrent Data Fetching

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator
from typing import List, Dict

async def fetch_all_items(item_ids: List[int]) -> List[Dict]:
    """Fetch multiple items concurrently."""
    
    async with AsyncAPIKeyRotator(
        api_keys=["async_key_1", "async_key_2", "async_key_3"],
        max_retries=3
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
        
        return items

# Run
item_ids = list(range(1, 101))  # Fetch 100 items
items = asyncio.run(fetch_all_items(item_ids))
```

### Rate-Limited Async Processing

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator
from asyncio import Semaphore

async def process_with_rate_limit(urls: List[str], max_concurrent: int = 10):
    """Process URLs with concurrent request limiting."""
    
    semaphore = Semaphore(max_concurrent)
    
    async with AsyncAPIKeyRotator(
        api_keys=["key1", "key2"],
        random_delay_range=(0.5, 1.5)
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
        
        return results

# Process 100 URLs with max 10 concurrent requests
urls = [f"https://api.example.com/resource/{i}" for i in range(100)]
results = asyncio.run(process_with_rate_limit(urls, max_concurrent=10))
```

---

## Production Patterns

### Resilient API Client with Fallback

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError
import logging
from typing import Optional, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResilientAPIClient:
    """Production-ready API client with fallback mechanisms."""
    
    def __init__(
        self,
        primary_keys: List[str],
        fallback_keys: Optional[List[str]] = None,
        cache_results: bool = True
    ):
        self.primary = APIKeyRotator(
            api_keys=primary_keys,
            max_retries=3,
            logger=logger
        )
        
        self.fallback = None
        if fallback_keys:
            self.fallback = APIKeyRotator(
                api_keys=fallback_keys,
                max_retries=2,
                logger=logger
            )
        
        self.cache = {} if cache_results else None
    
    def get(self, url: str, use_cache: bool = True, **kwargs) -> Dict:
        """
        Make a GET request with fallback support.
        """
        # Check cache
        if use_cache and self.cache and url in self.cache:
            logger.info(f"Cache hit for {url}")
            return self.cache[url]
        
        # Try primary rotator
        try:
            response = self.primary.get(url, **kwargs)
            data = response.json()
            
            if self.cache:
                self.cache[url] = data
            
            return data
            
        except AllKeysExhaustedError:
            logger.warning("Primary keys exhausted, trying fallback")
            
            # Try fallback if available
            if self.fallback:
                try:
                    response = self.fallback.get(url, **kwargs)
                    data = response.json()
                    
                    if self.cache:
                        self.cache[url] = data
                    
                    return data
                    
                except AllKeysExhaustedError:
                    logger.error("Fallback keys also exhausted")
                    raise
            else:
                raise

# Usage
client = ResilientAPIClient(
    primary_keys=["primary_key_1", "primary_key_2"],
    fallback_keys=["fallback_key_1"],
    cache_results=True
)

try:
    data = client.get("https://api.example.com/critical/data")
    print("Success:", data)
except AllKeysExhaustedError:
    print("All keys exhausted, cannot proceed")
```

### Monitoring and Metrics

```python
from apikeyrotator import APIKeyRotator
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime
import json

@dataclass
class RequestMetrics:
    """Track request metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    key_switches: int = 0
    retries: int = 0
    errors: Dict[str, int] = field(default_factory=dict)
    response_times: List[float] = field(default_factory=list)

class MonitoredRotator:
    """APIKeyRotator with metrics tracking."""
    
    def __init__(self, api_keys: List[str]):
        self.rotator = APIKeyRotator(api_keys=api_keys)
        self.metrics = RequestMetrics()
    
    def get(self, url: str, **kwargs):
        """Make GET request and track metrics."""
        start_time = datetime.now()
        self.metrics.total_requests += 1
        
        try:
            response = self.rotator.get(url, **kwargs)
            
            # Track timing
            elapsed = (datetime.now() - start_time).total_seconds()
            self.metrics.response_times.append(elapsed)
            
            # Track success
            self.metrics.successful_requests += 1
            
            return response
            
        except Exception as e:
            # Track failure
            self.metrics.failed_requests += 1
            error_type = type(e).__name__
            self.metrics.errors[error_type] = \
                self.metrics.errors.get(error_type, 0) + 1
            raise
    
    def get_metrics(self) -> Dict:
        """Get current metrics."""
        avg_response_time = (
            sum(self.metrics.response_times) / len(self.metrics.response_times)
            if self.metrics.response_times else 0
        )
        
        return {
            'total_requests': self.metrics.total_requests,
            'successful_requests': self.metrics.successful_requests,
            'failed_requests': self.metrics.failed_requests,
            'success_rate': (
                self.metrics.successful_requests / self.metrics.total_requests
                if self.metrics.total_requests > 0 else 0
            ),
            'average_response_time': avg_response_time,
            'errors': self.metrics.errors
        }
    
    def export_metrics(self, filename: str):
        """Export metrics to JSON file."""
        with open(filename, 'w') as f:
            json.dump(self.get_metrics(), f, indent=2)

# Usage
rotator = MonitoredRotator(api_keys=["key1", "key2", "key3"])

# Make requests
for i in range(100):
    try:
        rotator.get(f"https://api.example.com/item/{i}")
    except:
        pass

# View metrics
metrics = rotator.get_metrics()
print(f"Success rate: {metrics['success_rate']:.2%}")
print(f"Average response time: {metrics['average_response_time']:.3f}s")

# Export to file
rotator.export_metrics("api_metrics.json")
```

---

## Next Steps

- Read [Advanced Usage](ADVANCED_USAGE.md) for power features
- Check [API Reference](API_REFERENCE.md) for complete documentation
- Review [Error Handling](ERROR_HANDLING.md) for robust error management
- See [FAQ](FAQ.md) for common questions