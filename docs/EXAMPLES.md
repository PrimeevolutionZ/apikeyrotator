# Examples

Real-world examples for APIKeyRotator. All examples assume Python 3.12+ and
`pip install apikeyrotator` (extras are mentioned where needed).

## Table of Contents

- [Basic Usage](#basic-usage)
- [Middleware Examples](#middleware-examples)
- [Metrics & Monitoring](#metrics--monitoring)
- [Secret Providers](#secret-providers)
- [Web Scraping](#web-scraping)
- [Data Collection](#data-collection)
- [API Integration](#api-integration)
- [Payments and Orders](#payments-and-orders)
- [Asynchronous Operations](#asynchronous-operations)
- [Production Patterns](#production-patterns)
- [Advanced Patterns](#advanced-patterns)

---

## Basic Usage

### Simple GET Request

```python
from apikeyrotator import APIKeyRotator

with APIKeyRotator(api_keys=["key1", "key2", "key3"]) as rotator:
    response = rotator.get("https://api.example.com/users", params={"limit": 50})
    for user in response.json():
        print(f"User: {user['name']}")
```

### POST Request with Data

```python
import uuid
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2"])

response = rotator.post(
    "https://api.example.com/users",
    json={"name": "John Doe", "email": "john@example.com"},
    # Makes retries after 5xx/timeouts safe (if the API supports idempotency keys)
    headers={"Idempotency-Key": str(uuid.uuid4())},
)

if response.status_code == 201:
    print(f"Created user: {response.json()['id']}")
```

Without an `Idempotency-Key`, a POST that gets a `500`/`502`/`504` or a read
timeout is **not** retried (it may already have been executed). With
`auto_idempotency_key=True` the rotator adds one to every POST/PATCH itself - see
[Payments and Orders](#payments-and-orders).

### Choosing the Auth Header

```python
from apikeyrotator import APIKeyRotator

APIKeyRotator(api_keys=["key1"], auth="bearer")                          # Authorization: Bearer key1
APIKeyRotator(api_keys=["key1"], auth="x-api-key")                       # X-API-Key: key1
APIKeyRotator(api_keys=["key1"], auth=("Authorization", "Token {key}"))  # Authorization: Token key1
APIKeyRotator(api_keys=["key1"], auth=("x-goog-api-key", "{key}"))       # x-goog-api-key: key1
```

Without `auth=`: `X-API-Key` for 32-character keys, `Authorization: Bearer` for the rest.

### Wrong Auth Header? The Keys Are Kept

```python
from apikeyrotator import APIKeyRotator, AuthenticationError

rotator = APIKeyRotator(api_keys=["key1", "key2"])
try:
    rotator.get("https://api.example.com/data")
except AuthenticationError as e:
    # "All 2 key(s) were rejected (401) and no request has succeeded yet. ...
    #  Sent: 'Authorization: Bearer key1****'. Set auth='bearer', auth='x-api-key', ..."
    print(e.auth_header, e.statuses)
    rotator.auth = "x-api-key"          # fix it - both keys are still in rotation
    response = rotator.get("https://api.example.com/data")
```

Keys are removed for `401`/`403` only once the API has accepted a request, i.e. when
the header format is known to be right.

### Custom Authorization Header

```python
from apikeyrotator import APIKeyRotator

# Anthropic-style header
rotator = APIKeyRotator(
    api_keys=["sk-ant-...1", "sk-ant-...2"],
    header_callback=lambda key, headers: {"x-api-key": key, "anthropic-version": "2023-06-01"},
)
```

When the callback sets `Authorization` / `X-API-Key` (case-insensitive) or any
header containing the key, the rotator does not add its own auth header.

### httpx backend and HTTP/2

```python
# pip install "apikeyrotator[httpx]"
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2"], http_backend="httpx", http2=True)
response = rotator.get("https://api.example.com/data")   # httpx.Response
print(response.http_version, response.json())
```

### Same Response Object for Every HTTP Client

```python
from apikeyrotator import APIKeyRotator

for backend in ["requests", "httpx"]:
    rotator = APIKeyRotator(api_keys=["key1"], http_backend=backend, unified_response=True)
    r = rotator.get("https://api.example.com/users")
    print(type(r).__name__, r.status_code, r.ok, r.headers["content-type"], r.json())
    # UnifiedResponse 200 True application/json [...]   - identical for both backends

    r.raise_for_status()                  # HTTPStatusError (.response) for 4xx/5xx
    print(r.headers.get_list("Set-Cookie"), r.elapsed.total_seconds(), type(r.native))
```

The async rotator returns the same `UnifiedResponse` (see
[Asynchronous Operations](#asynchronous-operations)). Not usable with `stream=True`.

---

## Middleware Examples

### Using Cache Middleware

```python
from apikeyrotator import APIKeyRotator, CachingMiddleware

cache = CachingMiddleware(ttl=600, max_cache_size=500)
rotator = APIKeyRotator(api_keys=["key1", "key2"], middlewares=[cache])

rotator.get("https://api.example.com/data")   # miss - calls the API
rotator.get("https://api.example.com/data")   # hit - served from memory

stats = cache.get_stats()
print(f"Hits: {stats['hits']}, misses: {stats['misses']}, hit rate: {stats['hit_rate']:.2%}")
print(f"Entries: {stats['cache_size']}, bytes: {stats['size_bytes']}")
```

### Logging Middleware

```python
import logging
from apikeyrotator import APIKeyRotator, LoggingMiddleware

logging.basicConfig(level=logging.INFO)

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    middlewares=[LoggingMiddleware(verbose=True, log_response_time=True, max_key_chars=4)],
)
rotator.get("https://api.example.com/data")

# GET https://api.example.com/data (key: key1****, attempt: 1)
# 200 from https://api.example.com/data (key: key1****) (0.234s)
```

### Rate Limit Middleware

```python
from apikeyrotator import APIKeyRotator, RateLimitMiddleware

rate_limit = RateLimitMiddleware(pause_on_limit=True, max_wait=60)
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"], middlewares=[rate_limit])

for i in range(1000):
    rotator.get(f"https://api.example.com/item/{i}")

stats = rate_limit.get_stats()
print(f"Tracked keys: {stats['tracked_keys']}, currently limited: {stats['active_limits']}")
```

### Combining Multiple Middleware

```python
from apikeyrotator import APIKeyRotator, CachingMiddleware, LoggingMiddleware, RateLimitMiddleware

rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    # Every hook runs in list order: cache -> logging -> rate limit.
    # A cache hit returns before the other before_request hooks run.
    middlewares=[CachingMiddleware(ttl=300), LoggingMiddleware(), RateLimitMiddleware()],
)

for i in range(100):
    rotator.get(f"https://api.example.com/data/{i}")
```

### Custom Middleware

```python
import uuid
from apikeyrotator import APIKeyRotator, RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo

class RequestIdMiddleware(RotatorMiddleware):
    """Adds X-Request-ID and prints outcomes. *_sync hooks work for sync and async rotators."""

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo:
        request_info.headers["X-Client-Version"] = "2.0"
        request_info.headers["X-Request-ID"] = str(uuid.uuid4())
        return request_info

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        print(f"Response: {response_info.status_code} in {response_info.response_time:.3f}s")
        return response_info

    def on_error_sync(self, error_info: ErrorInfo) -> bool:
        print(f"Attempt failed: {error_info.exception}")
        return False

rotator = APIKeyRotator(api_keys=["key1"], middlewares=[RequestIdMiddleware()])
```

---

## Metrics & Monitoring

### Basic Metrics Collection

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])   # metrics are on by default

for i in range(100):
    try:
        rotator.get(f"https://api.example.com/item/{i}")
    except AllKeysExhaustedError:
        pass

metrics = rotator.get_metrics()   # counts every attempt, including retries
print(f"Attempts: {metrics['total_requests']}, "
      f"ok: {metrics['successful_requests']}, failed: {metrics['failed_requests']}, "
      f"success rate: {metrics['success_rate']:.2%}, uptime: {metrics['uptime_seconds']:.1f}s")

for key, stats in rotator.get_key_statistics().items():
    print(f"{key[:4]}****: {stats['total_requests']} requests, "
          f"{stats['success_rate']:.2%} success, "
          f"{stats['avg_response_time']:.3f}s avg, "
          f"{'healthy' if stats['is_healthy'] else 'unhealthy'}")
```

### Per-Endpoint Metrics

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1", "key2"])

for endpoint in ["/users", "/posts", "/comments", "/analytics"]:
    for page in range(25):
        rotator.get(f"https://api.example.com{endpoint}", params={"page": page})

# Query strings are not part of the endpoint name, so memory stays bounded
for endpoint, stats in rotator.get_metrics()["endpoint_stats"].items():
    print(f"{endpoint}: {stats['total_requests']} requests, "
          f"{stats['failed_requests']} failed, {stats['avg_response_time']:.3f}s avg")
```

### Prometheus Endpoint

```python
# pip install flask
from flask import Flask, Response
from apikeyrotator import APIKeyRotator, PrometheusExporter

rotator = APIKeyRotator(api_keys=["key1", "key2"])
app = Flask(__name__)

@app.route("/metrics")
def metrics():
    # Render on every scrape so the numbers are current
    text = PrometheusExporter.export(rotator.metrics, key_metrics=rotator.get_key_statistics())
    return Response(text, mimetype="text/plain; version=0.0.4")

if __name__ == "__main__":
    app.run(port=9090)
```

Keys are masked in the labels (`key="key1****"`).

### Real-Time Monitoring Dashboard

```python
import os
import threading
import time
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(api_keys=["key1", "key2"], circuit_breaker=True)

def display():
    os.system("clear" if os.name == "posix" else "cls")
    metrics = rotator.get_metrics()
    print("=" * 60)
    print(f"Attempts: {metrics['total_requests']}  success: {metrics['success_rate']:.2%}  "
          f"uptime: {metrics['uptime_seconds']:.0f}s")
    print("Keys:")
    for key, s in rotator.get_key_statistics().items():
        parked = s["rate_limit_reset"] > time.time()
        print(f"  {'healthy  ' if s['is_healthy'] else 'unhealthy'} {key[:4]}****  "
              f"{s['successful_requests']}/{s['total_requests']}  {'(rate limited)' if parked else ''}")
    print("Top endpoints:")
    for endpoint, count in rotator.metrics.get_top_endpoints(5):
        print(f"  {count:>5}  {endpoint}")
    print("Circuits:", rotator.get_circuit_states())

def make_requests():
    for i in range(1000):
        try:
            rotator.get(f"https://api.example.com/item/{i}")
        except AllKeysExhaustedError:
            pass
        time.sleep(0.1)

threading.Thread(target=make_requests, daemon=True).start()
try:
    while True:
        display()
        time.sleep(2)
except KeyboardInterrupt:
    print("\nDashboard stopped")
```

---

## Secret Providers

### AWS Secrets Manager with Background Refresh

```python
# pip install "apikeyrotator[aws]"
from apikeyrotator import APIKeyRotator, AWSSecretsManagerProvider

provider = AWSSecretsManagerProvider(secret_name="my-api-keys", region_name="us-east-1")

rotator = APIKeyRotator(
    secret_provider=provider,
    auto_refresh_interval=3600,   # reload every hour (daemon thread; stopped by close())
)
response = rotator.get("https://api.example.com/data")
```

The secret can be a JSON array (`["k1", "k2"]`), `{"keys": [...]}`,
`{"api_keys": [...]}` or a comma-separated string.

### Google Cloud Secret Manager

```python
# pip install "apikeyrotator[gcp]"
from apikeyrotator import APIKeyRotator, GCPSecretManagerProvider

provider = GCPSecretManagerProvider(project_id="my-project", secret_id="api-keys", version_id="latest")
rotator = APIKeyRotator(secret_provider=provider)
```

### Loading from a File

```python
from apikeyrotator import APIKeyRotator, FileSecretProvider

# keys.txt - JSON array, comma-separated values, or one key per line ('#' = comment)
rotator = APIKeyRotator(secret_provider=FileSecretProvider(file_path="keys.txt"),
                        auto_refresh_interval=60)   # pick up edits every minute
```

### Using the Factory Function

```python
from apikeyrotator import APIKeyRotator, create_secret_provider

provider = create_secret_provider("aws", secret_name="my-keys", region_name="us-east-1")
rotator = APIKeyRotator(secret_provider=provider)
```

---

## Web Scraping

> The rotator adds an auth header with a key to every request. Only send
> requests to the API that issued the keys - for third-party sites, use a rotator
> whose `header_callback` returns the headers that site expects.

### Scraping an API-backed Catalogue

```python
# pip install beautifulsoup4
from bs4 import BeautifulSoup
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError, CachingMiddleware

cache = CachingMiddleware(ttl=3600)
rotator = APIKeyRotator(
    api_keys=["key1", "key2", "key3"],
    user_agents=[
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    ],
    random_delay_range=(1.0, 3.0),
    max_retries=5,
    total_timeout=60,
    middlewares=[cache],
)

products = []
for page in range(1, 11):
    try:
        response = rotator.get("https://catalog.example.com/products", params={"page": page})
    except AllKeysExhaustedError as e:
        print(f"Page {page} failed: {e}")
        continue
    soup = BeautifulSoup(response.content, "html.parser")
    for item in soup.find_all("div", class_="product"):
        products.append({
            "name": item.find("h2").text,
            "price": item.find("span", class_="price").text,
            "url": item.find("a")["href"],
        })
    print(f"Page {page}: {len(products)} products so far")

print(f"Scraped {len(products)} products, cache hits: {cache.get_stats()['hits']}")
```

### Rotating Proxies

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(
    api_keys=["scraping_key_1", "scraping_key_2"],
    proxy_list=[
        "http://user:pass@proxy1.example.com:8080",
        "http://user:pass@proxy2.example.com:8080",
        "http://user:pass@proxy3.example.com:8080",
    ],
    random_delay_range=(2.0, 5.0),
)

for url in ["https://api.example.com/page1", "https://api.example.com/page2"]:
    try:
        print(url, rotator.get(url).status_code)
    except AllKeysExhaustedError as e:
        print(f"Failed {url}: {e}")
```

A proxy is chosen per attempt, so a retry also switches the proxy.

---

## Data Collection

### Collecting Data from Multiple Endpoints

```python
import json
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError, CachingMiddleware

cache = CachingMiddleware(ttl=300)
rotator = APIKeyRotator(
    api_keys=["analytics_key_1", "analytics_key_2", "analytics_key_3"],
    max_retries=5,
    base_delay=2.0,
    middlewares=[cache],
)

def collect_analytics_data(start_date: str, end_date: str) -> dict:
    results = {}
    for endpoint in ["pageviews", "visitors", "conversions", "revenue"]:
        try:
            response = rotator.get(
                f"https://analytics.example.com/api/v1/analytics/{endpoint}",
                params={"start_date": start_date, "end_date": end_date, "format": "json"},
            )
            response.raise_for_status()
            results[endpoint] = response.json()
            print(f"OK {endpoint}")
        except AllKeysExhaustedError as e:
            print(f"FAILED {endpoint}: {e}")
    return results

data = collect_analytics_data("2026-01-01", "2026-01-31")
with open("analytics_data.json", "w") as f:
    json.dump(data, f, indent=2)
print(f"Collected {len(data)} metrics, cache hit rate {cache.get_stats()['hit_rate']:.2%}")
```

### Batch Processing with Progress Tracking

```python
# pip install tqdm
from datetime import datetime
from tqdm import tqdm
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

rotator = APIKeyRotator(api_keys=["batch_key_1", "batch_key_2"], key_rate_limit=(100, 60))

def process_batch(item_ids):
    results, failed = [], []
    for item_id in tqdm(item_ids, desc="Processing items"):
        try:
            response = rotator.get(f"https://api.example.com/items/{item_id}")
            response.raise_for_status()
        except Exception as e:   # AllKeysExhaustedError or an HTTP error status
            failed.append({"id": item_id, "error": str(e)})
            continue
        item = response.json()
        results.append({"id": item["id"], "name": item["name"],
                        "processed_at": datetime.now().isoformat()})
    return results, failed

successful, failed = process_batch(range(1, 1001))
print(f"Processed: {len(successful)}, failed: {len(failed)}")
```

With `key_rate_limit=(100, 60)` each key sends at most 100 requests per minute;
the rotator waits when both keys have used their budget.

---

## API Integration

### REST API Client

```python
from apikeyrotator import APIKeyRotator, CachingMiddleware

class APIClient:
    """Thin client for one API."""

    def __init__(self, api_keys: list[str], base_url: str):
        self.base_url = base_url.rstrip("/")
        self.rotator = APIKeyRotator(
            api_keys=api_keys,
            max_retries=5,
            total_timeout=30,
            middlewares=[CachingMiddleware(ttl=300)],
        )

    def _request(self, method: str, endpoint: str, **kwargs):
        response = self.rotator.request(method, f"{self.base_url}/{endpoint.lstrip('/')}", **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    def get_user(self, user_id: int) -> dict:
        return self._request("GET", f"/users/{user_id}")

    def list_users(self, page: int = 1, per_page: int = 20) -> list[dict]:
        return self._request("GET", "/users", params={"page": page, "per_page": per_page})

    def create_user(self, data: dict) -> dict:
        return self._request("POST", "/users", json=data)

    def update_user(self, user_id: int, data: dict) -> dict:
        return self._request("PUT", f"/users/{user_id}", json=data)   # PUT is idempotent - retried

    def delete_user(self, user_id: int) -> None:
        self._request("DELETE", f"/users/{user_id}")

    def close(self) -> None:
        self.rotator.close()

client = APIClient(api_keys=["key1", "key2", "key3"], base_url="https://api.example.com/v1")

all_users, page = [], 1
while users := client.list_users(page=page, per_page=50):
    all_users.extend(users)
    page += 1
print(f"Total users: {len(all_users)}; attempts made: {client.rotator.get_metrics()['total_requests']}")
client.close()
```

### GraphQL API Client

```python
from apikeyrotator import APIKeyRotator, CachingMiddleware

class GraphQLError(Exception):
    pass

class GraphQLClient:
    def __init__(self, api_keys: list[str], endpoint: str):
        self.endpoint = endpoint
        self.rotator = APIKeyRotator(
            api_keys=api_keys,
            # GraphQL queries are POSTs: cache them by body (don't use for mutations)
            middlewares=[CachingMiddleware(ttl=600, cache_only_get=False)],
            # Queries are safe to repeat after 5xx/timeouts
            retry_non_idempotent=True,
        )

    def query(self, query: str, variables: dict | None = None) -> dict:
        response = self.rotator.post(self.endpoint, json={"query": query, "variables": variables or {}})
        data = response.json()
        if data.get("errors"):
            raise GraphQLError(data["errors"])
        return data["data"]

client = GraphQLClient(api_keys=["graphql_key_1", "graphql_key_2"], endpoint="https://api.example.com/graphql")
result = client.query(
    "query GetUser($id: ID!) { user(id: $id) { id name posts { title } } }",
    variables={"id": "123"},
)
print(f"{result['user']['name']} has {len(result['user']['posts'])} posts")
```

---

## Payments and Orders

A client for an API with side effects (charges, orders, messages). The rotator never
repeats a request that may have been executed; with idempotency keys the retries become
safe and reuse the same API key.

```python
import logging
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

log = logging.getLogger("billing")

payments = APIKeyRotator(
    api_keys=["sk_live_1", "sk_live_2"],   # keys of the same account
    auto_idempotency_key=True,             # Idempotency-Key on every POST/PATCH
    total_timeout=20,                      # a user is waiting - bound the whole request
    unified_response=True,
)


def charge(order_id: str, amount: int) -> dict | None:
    try:
        response = payments.post(
            "https://api.example.com/v1/charges",
            json={"amount": amount, "order": order_id},
            # a stable key per order lets you retry this call later without charging twice
            headers={"Idempotency-Key": f"charge-{order_id}"},
        )
    except AllKeysExhaustedError as e:
        if e.possibly_processed:
            log.error("Charge %s may have happened - check it before retrying", order_id)
        else:
            log.warning("Charge %s was not executed - safe to retry later", order_id)
        return None

    if not response.ok:          # a 500 without idempotency, a 4xx...: returned, never retried
        log.error("Charge %s failed: %s %s", order_id, response.status_code, response.text)
        return None
    return response.json()
```

What happens on failures:

| Server answer | What the rotator does |
|---|---|
| `429`, `503` | retries (the charge was not executed), possibly with another key |
| `500`, read timeout | retries **with the same key** (the idempotency key makes it safe); without an idempotency key the response / exception is returned to you |
| `401` on one key | switches to another key |
| still failing | `AllKeysExhaustedError(possibly_processed=True)` |

With `FallbackRouter`, a charge that may have been executed by the first provider is
**not** sent to the second one - the error is raised instead:

```python
from apikeyrotator import APIKeyRotator, FallbackRouter, ProviderRoute

router = FallbackRouter([
    ProviderRoute(name="stripe", rotator=APIKeyRotator(api_keys=["sk_1"], auto_idempotency_key=True)),
    ProviderRoute(name="backup-psp", rotator=APIKeyRotator(api_keys=["bk_1"], auto_idempotency_key=True)),
])
router.post("https://api.example.com/v1/charges", json={"amount": 1000})
```

---

## Asynchronous Operations

### Same Code for aiohttp and httpx

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def main():
    for backend in ["aiohttp", "httpx"]:
        async with AsyncAPIKeyRotator(api_keys=["key1", "key2"], http_backend=backend,
                                      unified_response=True) as rotator:
            r = await rotator.get("https://api.example.com/users")
            print(r.status_code, r.json())    # json() is not awaited - the body is already read

asyncio.run(main())
```

### Keys From a Secret Store, Loaded in Your Event Loop

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator, AWSSecretsManagerProvider

async def main():
    rotator = AsyncAPIKeyRotator(secret_provider=AWSSecretsManagerProvider(secret_name="prod/keys"))
    print(rotator.keys)               # [] - nothing loaded yet, the loop is not blocked
    async with rotator:               # keys are loaded here (or on the first request)
        print(rotator.key_count)
        await rotator.get("https://api.example.com/data")

asyncio.run(main())
```

### Concurrent Data Fetching

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator, CachingMiddleware

async def fetch_all_items(item_ids: list[int]) -> list[dict]:
    cache = CachingMiddleware(ttl=300)
    async with AsyncAPIKeyRotator(
        api_keys=["async_key_1", "async_key_2", "async_key_3"],
        max_retries=3,
        total_timeout=30,
        middlewares=[cache],
    ) as rotator:

        async def fetch_item(item_id: int) -> dict:
            response = await rotator.get(f"https://api.example.com/items/{item_id}")
            return await response.json()

        results = await asyncio.gather(*(fetch_item(i) for i in item_ids), return_exceptions=True)

    items = [r for r in results if not isinstance(r, BaseException)]
    print(f"Success: {len(items)}, errors: {len(results) - len(items)}, "
          f"cache hit rate: {cache.get_stats()['hit_rate']:.2%}")
    return items

items = asyncio.run(fetch_all_items(list(range(1, 101))))
```

### Bounded Concurrency with Client-Side Rate Limits

```python
import asyncio
from apikeyrotator import AsyncAPIKeyRotator

async def process(urls: list[str], max_concurrent: int = 10) -> list[dict]:
    semaphore = asyncio.Semaphore(max_concurrent)
    async with AsyncAPIKeyRotator(
        api_keys=["key1", "key2"],
        key_rate_limit=(30, 60),    # each key: at most 30 requests per minute
        total_timeout=120,
    ) as rotator:

        async def fetch(url: str) -> dict:
            async with semaphore:
                response = await rotator.get(url)
                return {"url": url, "status": response.status, "data": await response.json()}

        return await asyncio.gather(*(fetch(u) for u in urls))

results = asyncio.run(process([f"https://api.example.com/resource/{i}" for i in range(100)]))
```

---

## Production Patterns

### Resilient Client with Provider Fallback

```python
import logging
from apikeyrotator import (
    APIKeyRotator, AllProvidersExhaustedError, CachingMiddleware, FallbackRouter, ProviderRoute,
)

logging.basicConfig(level=logging.INFO)

cache = CachingMiddleware(ttl=600, max_cache_size=1000)

primary = APIKeyRotator(
    api_keys=["primary_key_1", "primary_key_2"],
    total_timeout=20,
    circuit_breaker=True,             # a dead primary host fails fast -> fallback immediately
    middlewares=[cache],
)
backup = APIKeyRotator(api_keys=["fallback_key_1"], total_timeout=20)

router = FallbackRouter([
    ProviderRoute(primary, name="primary"),
    ProviderRoute(
        backup, name="backup",
        request_transformer=lambda m, url, kw: (m, url.replace("api.example.com", "backup.example.com"), kw),
    ),
])

def health_report() -> dict:
    metrics = primary.get_metrics()
    keys = primary.get_key_statistics()
    return {
        "success_rate": metrics["success_rate"],
        "healthy_keys": f"{sum(s['is_healthy'] for s in keys.values())}/{len(keys)}",
        "cache_hit_rate": cache.get_stats()["hit_rate"],
        "circuits": primary.get_circuit_states(),
    }

try:
    data = router.get("https://api.example.com/critical/data").json()
except AllProvidersExhaustedError:
    data = None
print(health_report())
```

### Many Workers Sharing Keys (Redis)

```python
# pip install "apikeyrotator[redis]"
from apikeyrotator import APIKeyRotator, RedisStateBackend

def make_rotator() -> APIKeyRotator:
    """Call in every worker process: limits, rejected keys and token buckets are shared."""
    return APIKeyRotator(
        env_var="PROVIDER_API_KEYS",
        state_backend=RedisStateBackend(url="redis://redis:6379/0", namespace="provider"),
        key_rate_limit=(500, 60),   # 500 requests/minute per key across ALL workers
        total_timeout=30,
        circuit_breaker=True,
    )
```

### Enterprise Client with Alerting

```python
import json
from datetime import datetime
from apikeyrotator import (
    APIKeyRotator, AllKeysExhaustedError, AWSSecretsManagerProvider,
    CachingMiddleware, CircuitOpenError, LoggingMiddleware, RateLimitMiddleware,
)

class EnterpriseAPIClient:
    def __init__(self, secret_name: str, alert_callback=None):
        self.cache = CachingMiddleware(ttl=900, max_cache_size=5000)
        self.rate_limit = RateLimitMiddleware(pause_on_limit=True, max_wait=30)
        self.rotator = APIKeyRotator(
            secret_provider=AWSSecretsManagerProvider(secret_name=secret_name),
            auto_refresh_interval=900,
            max_retries=3,
            base_delay=2.0,
            total_timeout=30,
            circuit_breaker=True,
            middlewares=[self.cache, LoggingMiddleware(verbose=True), self.rate_limit],
        )
        self.alert_callback = alert_callback
        self.started = datetime.now()

    def get(self, url: str, **kwargs) -> dict:
        try:
            return self.rotator.get(url, **kwargs).json()
        except CircuitOpenError as e:
            self._alert("API host down", f"{e.host}, retry in {e.retry_after:.0f}s")
            raise
        except AllKeysExhaustedError as e:
            self._alert("Request failed", str(e))
            raise

    def _alert(self, title: str, message: str) -> None:
        if self.alert_callback:
            self.alert_callback(title, message)

    def report(self) -> dict:
        metrics = self.rotator.get_metrics()
        return {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.started).total_seconds(),
            "attempts": metrics["total_requests"],
            "success_rate": metrics["success_rate"],
            "keys": self.rotator.export_config()["key_statistics"],   # masked keys
            "cache": self.cache.get_stats(),
            "rate_limits": self.rate_limit.get_stats(),
            "circuits": self.rotator.get_circuit_states(),
            "endpoints": metrics["endpoint_stats"],
        }

    def export_report(self, filename: str = "api_report.json") -> None:
        with open(filename, "w") as f:
            json.dump(self.report(), f, indent=2, default=str)

client = EnterpriseAPIClient("production-api-keys", alert_callback=lambda t, m: print(f"ALERT: {t} - {m}"))
for i in range(100):
    try:
        client.get(f"https://api.example.com/data/{i}")
    except AllKeysExhaustedError:
        pass
client.export_report()
client.rotator.close()
```

---

## Advanced Patterns

### Circuit Breaker

Built in - per host, no extra code:

```python
from apikeyrotator import APIKeyRotator, CircuitBreakerConfig, CircuitOpenError

rotator = APIKeyRotator(
    api_keys=["key1", "key2"],
    circuit_breaker=CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60),
)

for i in range(20):
    try:
        rotator.get(f"https://api.example.com/data/{i}")
    except CircuitOpenError as e:
        print(f"Skipping: {e.host} is down for {e.retry_after:.0f}s more")
    print(rotator.get_circuit_states())
```

The standalone `CircuitBreaker` class (`from apikeyrotator import CircuitBreaker`)
is available for protecting other calls.

### Retrying a Whole Operation

The rotator already retries individual requests. For a multi-step operation,
wrap it with `retry_with_backoff`:

```python
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError, retry_with_backoff

rotator = APIKeyRotator(api_keys=["key1", "key2"])

def sync_report():
    report_id = rotator.post("https://api.example.com/reports", json={"type": "daily"}).json()["id"]
    return rotator.get(f"https://api.example.com/reports/{report_id}").json()

report = retry_with_backoff(sync_report, retries=3, backoff_factor=5.0, exceptions=AllKeysExhaustedError)
```

### Measuring Performance

Use the bundled benchmark to measure the rotator itself
(`python benchmarks/bench_core.py`, see [benchmarks](../benchmarks/README.md)).
To time your own calls:

```python
import logging
from apikeyrotator import APIKeyRotator
from apikeyrotator.utils import measure_time

logging.basicConfig(level=logging.DEBUG)   # measure_time logs at DEBUG level
rotator = APIKeyRotator(api_keys=["key1", "key2"])

@measure_time
def fetch_page(i: int):
    return rotator.get(f"https://api.example.com/data/{i}")

for i in range(10):
    fetch_page(i)
```

---

## Next Steps

- [Middleware Guide](MIDDLEWARE.md)
- [Resilience & Scaling](RESILIENCE.md)
- [API Reference](API_REFERENCE.md)
- [Advanced Usage](ADVANCED_USAGE.md)
- [FAQ](FAQ.md)
