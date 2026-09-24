# Behavior Under Load and Edge Cases

What exactly happens when many threads share a rotator, a response is a 3 MB PDF, one
of two hosts is down, Redis goes away, or a key contains a comma. Every example on this
page was run against a local test server and the output below it is the real output
(host names are shown as `example.com`; counts from `random` / `weighted` differ
between runs).

- [1. Threads, async tasks and processes](#1-threads-async-tasks-and-processes)
- [2. Rotation strategies under concurrency](#2-rotation-strategies-under-concurrency)
- [3. Response bodies: binary, large, other encodings](#3-response-bodies-binary-large-other-encodings)
- [4. Partial failures: one host down, some keys bad](#4-partial-failures-one-host-down-some-keys-bad)
- [5. Several processes sharing keys (Redis)](#5-several-processes-sharing-keys-redis)
- [6. Passing keys: strings, lists, files, commas](#6-passing-keys-strings-lists-files-commas)
- [7. Which auth header is sent](#7-which-auth-header-is-sent)
- [8. Metrics: which call returns what](#8-metrics-which-call-returns-what)
- [Summary of guarantees](#summary-of-guarantees)

---

## 1. Threads, async tasks and processes

| Where the code runs | Use |
|---|---|
| Threads (web server threads, `ThreadPoolExecutor`) | **one** `APIKeyRotator` shared by all threads |
| asyncio tasks | **one** `AsyncAPIKeyRotator` per event loop |
| Several processes (gunicorn / uwsgi workers, Celery, `multiprocessing`) | one rotator **per process**, created after the fork; add `RedisStateBackend` to share limits |

### One rotator for all threads

Sharing matters: every thread sees which keys are rate limited or revoked, and all
threads reuse one connection pool. `pool_size` (default 100) should be at least the number
of threads that make requests at the same time.

```python
from concurrent.futures import ThreadPoolExecutor

from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key-1", "key-2", "key-3", "key-4"], pool_size=16)

def fetch(i: int) -> int:
    return rotator.get(f"https://api.example.com/items/{i}").json()["id"]

with ThreadPoolExecutor(max_workers=16) as executor:
    ids = list(executor.map(fetch, range(2000)))

print("responses:", len(ids), "- all distinct:", len(set(ids)) == 2000)
for key, stats in rotator.get_key_statistics().items():
    print(f"  {key}: {stats['total_requests']} requests")
print("total:", rotator.get_metrics()["total_requests"])
```

Output:

```text
responses: 2000 - all distinct: True
  key-1: 500 requests
  key-2: 500 requests
  key-3: 500 requests
  key-4: 500 requests
total: 2000
```

Selection of the next key, the counters, parking a rate-limited key and removing a
revoked key are atomic: the numbers add up exactly, and round robin stays exact with 16
threads. Do not create a rotator per request - it would forget key health and open a
new connection every time.

### Changing keys while requests are running

`rotator.keys = [...]` can be called from any thread at any time. Requests already in
flight finish with the key they started with; the next selections use the new list.
Statistics of keys that stay are kept.

```python
import threading
import time

from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key-1", "key-2", "key-3"])
stop = threading.Event()
errors = []

def worker():
    while not stop.is_set():
        try:
            rotator.get("https://api.example.com/items/1")
        except Exception as e:
            errors.append(e)

threads = [threading.Thread(target=worker) for _ in range(8)]
for t in threads:
    t.start()
time.sleep(0.5)
rotator.keys = ["key-2", "key-3", "key-4"]      # key-1 retired, key-4 added
time.sleep(0.5)
stop.set()
for t in threads:
    t.join()

print("errors:", errors)
print("keys now:", rotator.keys)
for key, stats in rotator.get_key_statistics().items():
    print(f"  {key}: {stats['total_requests']} requests")
```

Output:

```text
errors: []
keys now: ['key-2', 'key-3', 'key-4']
  key-2: 64 requests
  key-3: 62 requests
  key-4: 30 requests
```

`key-2` and `key-3` kept their counts from before the switch, so they have about twice
as many requests as `key-4`. The same applies to keys reloaded by
`auto_refresh_interval` from a secret provider.

### Custom strategies must be thread-safe

`get_next_key()` is called from many threads at once. Built-in strategies lock
internally; in your own strategy guard shared state with `self._lock` (a
`threading.RLock` provided by `BaseRotationStrategy`):

```python
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from apikeyrotator import APIKeyRotator, BaseRotationStrategy, KeyMetrics

class PrimaryMostly(BaseRotationStrategy):
    """Every 4th request goes to a backup key, the rest to the first key."""

    def __init__(self, keys):
        super().__init__(keys)
        self._count = 0

    def get_next_key(self, current_key_metrics: dict[str, KeyMetrics] | None = None) -> str:
        candidates = self._get_healthy_keys(current_key_metrics)   # skips limited / unhealthy keys
        with self._lock:                                           # read-modify-write of shared state
            self._count += 1
            count = self._count
        if count % 4 or len(candidates) == 1:
            return candidates[0]
        return candidates[1 + (count // 4) % (len(candidates) - 1)]

keys = ["primary", "backup-1", "backup-2"]
rotator = APIKeyRotator(api_keys=keys, rotation_strategy=PrimaryMostly(keys))
with ThreadPoolExecutor(max_workers=8) as executor:
    used = Counter(executor.map(lambda i: rotator.get("https://api.example.com/whoami").json()["key"],
                                range(1200)))
print(dict(used))
```

Output:

```text
{'primary': 900, 'backup-2': 150, 'backup-1': 150}
```

Without the lock two threads can read the same `_count`, and the split drifts.

### asyncio: one rotator per event loop

An async rotator owns an `aiohttp.ClientSession` (or `httpx.AsyncClient`) that belongs to
the event loop it was first used in. Create it inside the loop (`async with` or in an
`async def`) and share it between the tasks of that loop. Limit concurrency with a
semaphore - `pool_size` is the connection limit, extra requests wait for a connection.

```python
import asyncio

from apikeyrotator import AsyncAPIKeyRotator

async def main():
    async with AsyncAPIKeyRotator(api_keys=["key-1", "key-2", "key-3"], pool_size=50) as rotator:
        limit = asyncio.Semaphore(50)

        async def fetch(i: int) -> int:
            async with limit:
                response = await rotator.get(f"https://api.example.com/items/{i}")
                return (await response.json())["id"]

        ids = await asyncio.gather(*(fetch(i) for i in range(1000)))
        print("responses:", len(ids), "- all distinct:", len(set(ids)) == 1000)
        print({key: s["total_requests"] for key, s in rotator.get_key_statistics().items()})

asyncio.run(main())
```

Output:

```text
responses: 1000 - all distinct: True
{'key-1': 334, 'key-2': 333, 'key-3': 333}
```

Do not use one async rotator from several event loops (for example several threads,
each with `asyncio.run`): create one per loop. Do not call the sync `APIKeyRotator` from
async code either - it blocks the loop while it waits for the server and during backoff.

### Several processes: create the rotator after the fork

Connection pools, locks and the background refresh thread must not be inherited by a
forked worker. Create the rotator lazily, on first use in each process:

```python
import functools
import os

from apikeyrotator import APIKeyRotator, RedisStateBackend

@functools.cache
def get_rotator() -> APIKeyRotator:
    """One rotator per worker process, created on the first request it handles."""
    return APIKeyRotator(
        api_keys=os.environ["PAYMENTS_API_KEYS"].split(","),
        state_backend=RedisStateBackend(url="redis://redis:6379/0", namespace="payments-api"),
        key_rate_limit=(100, 60),            # per key, for all workers together
    )

def handle_request(order_id: str):
    return get_rotator().get(f"https://api.example.com/orders/{order_id}")
```

The same pattern works for gunicorn (sync or thread workers), uwsgi, Celery prefork
workers and `multiprocessing` pools. Without a state backend each process only knows
what it has seen itself; see [section 5](#5-several-processes-sharing-keys-redis).

---

## 2. Rotation strategies under concurrency

| Strategy | Distribution | Under concurrency |
|---|---|---|
| `round_robin` | exact rotation | exact: 2400 requests over 6 keys = 400 each |
| `lru` | least recently **selected** key next | exact (selection order is a counter, not a clock) |
| `random` | uniform | statistical: expect a few % spread |
| `weighted` | proportional to `weights` | statistical |
| `health_based` | random among healthy keys (own `failure_threshold`) | statistical, like `random` |
| `failover` | first working key | everything on the first key until it fails |

All strategies skip keys that are rate limited or unhealthy, so the distribution shifts
as soon as a key gets a `429`.

```python
import threading
from collections import Counter

from apikeyrotator import APIKeyRotator

keys = ["k1", "k2", "k3", "k4"]
setups = {
    "round_robin": {},
    "lru": {},
    "random": {},
    "weighted": {"weights": {"k1": 1, "k2": 1, "k3": 2, "k4": 4}},
    "health_based": {},
    "failover": {},
}
for name, kwargs in setups.items():
    rotator = APIKeyRotator(api_keys=keys, rotation_strategy=name, rotation_strategy_kwargs=kwargs)
    used = Counter()
    lock = threading.Lock()

    def worker():
        for _ in range(300):
            key = rotator.get("https://api.example.com/whoami").json()["key"]
            with lock:
                used[key] += 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"{name:13}", [used[k] for k in keys])
```

Output:

```text
round_robin   [600, 600, 600, 600]
lru           [600, 600, 600, 600]
random        [566, 603, 644, 587]
weighted      [293, 278, 597, 1232]
health_based  [618, 600, 587, 595]
failover      [2400, 0, 0, 0]
```

`weighted` with weights 1:1:2:4 aims at 300 / 300 / 600 / 1200.

**Clocks.** Before 0.9.1 `lru` ordered keys by `time.time()`. On Windows that clock moves
in steps of about 15 ms, so every selection within one step saw equal timestamps and one
key received nearly all requests. It now orders by a counter and does not depend on the
clock at all.

---

## 3. Response bodies: binary, large, other encodings

### Binary files

Bodies are passed through as bytes, byte for byte, with every backend. With
`unified_response=True` the body is read completely into `response.content`:

```python
import asyncio
import hashlib

from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator

url = "https://api.example.com/files/report.pdf"

rotator = APIKeyRotator(api_keys=["key-1"], unified_response=True)
expected = rotator.get(url + ".sha256").text
response = rotator.get(url)
print(response.status_code, response.headers["Content-Type"], len(response.content), "bytes")
print("requests:", hashlib.sha256(response.content).hexdigest() == expected)

with open("report.pdf", "wb") as f:
    f.write(response.content)

rotator = APIKeyRotator(api_keys=["key-1"], unified_response=True, http_backend="httpx")
print("httpx:", hashlib.sha256(rotator.get(url).content).hexdigest() == expected)

async def main():
    for backend in ("aiohttp", "httpx"):
        async with AsyncAPIKeyRotator(api_keys=["key-1"], unified_response=True,
                                      http_backend=backend) as rotator:
            response = await rotator.get(url)
            print(f"async {backend}:", hashlib.sha256(response.content).hexdigest() == expected)

asyncio.run(main())
```

Output:

```text
200 application/pdf 3145728 bytes
requests: True
httpx: True
async aiohttp: True
async httpx: True
```

### Large downloads: stream with the client's own response

A unified response keeps the whole body in memory. For large files use `stream=True`
without `unified_response` and write the body in chunks. The status is checked before
the body is read: a `429` or `503` is retried with another key, a `200` is returned to
you with the body still unread.

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key-1", "key-2"])

with rotator.get("https://api.example.com/files/report.pdf", stream=True) as response:
    response.raise_for_status()
    written = 0
    with open("report.pdf", "wb") as f:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            written += f.write(chunk)
print("written:", written, "bytes")

try:
    APIKeyRotator(api_keys=["key-1"], unified_response=True).get(
        "https://api.example.com/files/report.pdf", stream=True)
except ValueError as e:
    print("ValueError:", e)
```

Output:

```text
written: 3145728 bytes
ValueError: stream=True needs the client's own response; it is not supported with unified_response=True
```

Async rotators without `unified_response` return the client's response with the body
unread, so it can be streamed the same way:

```python
import asyncio

from apikeyrotator import AsyncAPIKeyRotator

async def main():
    async with AsyncAPIKeyRotator(api_keys=["key-1", "key-2"]) as rotator:
        response = await rotator.get("https://api.example.com/files/report.pdf")
        written = 0
        with open("report.pdf", "wb") as f:
            async for chunk in response.content.iter_chunked(64 * 1024):   # aiohttp
                written += f.write(chunk)
        response.release()
        print("written:", written, "bytes")

asyncio.run(main())
```

Output:

```text
written: 3145728 bytes
```

An error in the middle of a streamed body (connection dropped) is **not** retried: the
rotator has already handed the response to you. Retry the download yourself, for example
with a `Range` header.

### Text in other encodings

`text` and `json()` use the `charset` of the `Content-Type` header. `json()` without a
charset follows the JSON standard (UTF-8/16/32):

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key-1"], unified_response=True)

csv = rotator.get("https://api.example.com/legacy/prices.csv")
print(csv.headers["Content-Type"])
print(csv.text)
print(rotator.get("https://api.example.com/legacy/prices.json").json())
```

Output:

```text
text/csv; charset=windows-1251
товар;цена
чай;120
кофе;340

{'товар': 'чай', 'цена': 120}
```

### A body that is not JSON

Maintenance pages and proxies return HTML with status `200`. `json()` raises
`json.JSONDecodeError` (a `ValueError`) for every client, so one `except` covers them all:

```python
import json

from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key-1"], unified_response=True)
response = rotator.get("https://api.example.com/maintenance")
try:
    data = response.json()
except json.JSONDecodeError:
    print(response.status_code, response.headers["Content-Type"], "- not JSON:", response.text[:40])
```

Output:

```text
200 text/html - not JSON: <html><body>Down for maintenance</body><
```

`response.native` is the client's own object (`requests.Response`, `httpx.Response`,
`aiohttp.ClientResponse`) when you need something only that client has.

---

## 4. Partial failures: one host down, some keys bad

### One host down, another alive

With `circuit_breaker` enabled, failures are counted **per host**. A dead host opens
its own breaker; requests to other hosts are not affected:

```python
from apikeyrotator import AllKeysExhaustedError, APIKeyRotator, CircuitBreakerConfig, CircuitOpenError

rotator = APIKeyRotator(
    api_keys=["key-1", "key-2"],
    max_retries=3, base_delay=0.01,
    circuit_breaker=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30),
)

try:
    rotator.get("https://dead.example.com/v1/search")
except AllKeysExhaustedError as e:
    print("dead, 1st request:", type(e).__name__, e.last_response.status_code)
try:
    rotator.get("https://dead.example.com/v1/search")
except CircuitOpenError as e:
    print(f"dead, 2nd request: CircuitOpenError, retry in {e.retry_after:.0f}s (nothing sent)")

print("alive:", rotator.get("https://alive.example.com/v1/search").status_code)
print(rotator.get_circuit_states())
```

Output:

```text
dead, 1st request: AllKeysExhaustedError 503
dead, 2nd request: CircuitOpenError, retry in 30s (nothing sent)
alive: 200
{'dead.example.com': 'OPEN', 'alive.example.com': 'CLOSED'}
```

What counts as a failure of the host:

| Result | Breaker |
|---|---|
| `5xx`, connection error, timeout | failure |
| `2xx`, `3xx`, `4xx` (including `401`, `403`, `404`) | success - the host answered |
| `429` | neither - the host is alive, the key is limited |

So a revoked key never opens the breaker, and a host that answers `503` to everything
stops costing retries after `failure_threshold` requests.

### Recovery

After `recovery_timeout` the breaker lets `half_open_max_calls` probes through
(HALF_OPEN). A successful probe closes it, a failed one opens it again:

```python
import time

from apikeyrotator import AllKeysExhaustedError, APIKeyRotator, CircuitBreakerConfig, CircuitOpenError

rotator = APIKeyRotator(
    api_keys=["key-1"], max_retries=1,
    circuit_breaker=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.5),
)
url = "https://api.example.com/recovering"     # answers 503 for 0.4 s after the first call

for i in range(2):
    try:
        rotator.get(url)
    except AllKeysExhaustedError as e:
        print(f"request {i + 1}:", e.last_response.status_code)
print("state:", rotator.get_circuit_states())
try:
    rotator.get(url)
except CircuitOpenError:
    print("request 3: CircuitOpenError, nothing sent")
time.sleep(0.6)
print("after recovery_timeout:", rotator.get_circuit_states())
print("probe:", rotator.get(url).status_code, "->", rotator.get_circuit_states())
```

Output:

```text
request 1: 503
request 2: 503
state: {'api.example.com': 'OPEN'}
request 3: CircuitOpenError, nothing sent
after recovery_timeout: {'api.example.com': 'HALF_OPEN'}
probe: 200 -> {'api.example.com': 'CLOSED'}
```

### What is a "host"

The breaker key is `host[:port]` from the URL, lower-cased, without credentials:

| URLs | Same breaker? |
|---|---|
| `https://API.example.com/a`, `https://api.example.com/b?x=1` | yes |
| `https://user:pass@api.example.com/`, `https://api.example.com/` | yes |
| `https://api.example.com/`, `https://api.example.com:8443/` | no - different port |
| `http://localhost:8000/`, `http://127.0.0.1:8000/` | no - different names |
| `https://eu.api.example.com/`, `https://us.api.example.com/` | no |

### Falling back to another provider

`CircuitOpenError` is an `AllKeysExhaustedError`, so `FallbackRouter` moves on at once -
once the breaker of the primary is open, the primary gets no requests at all:

```python
from apikeyrotator import APIKeyRotator, CircuitBreakerConfig, FallbackRouter, ProviderRoute

primary = APIKeyRotator(api_keys=["a-1", "a-2"], max_retries=2, base_delay=0.01,
                        circuit_breaker=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=30))
backup = APIKeyRotator(api_keys=["b-1"])
router = FallbackRouter([
    ProviderRoute(primary, name="primary"),
    ProviderRoute(backup, name="backup", request_transformer=lambda m, u, kw: (
        m, u.replace("https://dead.example.com", "https://alive.example.com"), kw)),
])

for i in range(5):
    response = router.get(f"https://dead.example.com/v1/items/{i}")
    print(i, response.json()["host"], "| attempts at primary so far:", primary.get_metrics()["total_requests"])
```

Output:

```text
0 alive | attempts at primary so far: 2
1 alive | attempts at primary so far: 2
2 alive | attempts at primary so far: 2
3 alive | attempts at primary so far: 2
4 alive | attempts at primary so far: 2
```

The first request spent its two attempts at the primary, which opened the breaker
(`failure_threshold=2`); every later request went straight to the backup without touching
the primary until `recovery_timeout` passes.

### Some keys revoked, the host fine

`401` / `403` removes only that key (once the auth header has been confirmed by one
successful response); other keys and the breaker are untouched:

```python
import logging

from apikeyrotator import APIKeyRotator

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
rotator = APIKeyRotator(api_keys=["key-1", "revoked-2", "key-3", "revoked-4"], circuit_breaker=True)
for i in range(6):
    print(i, rotator.get("https://api.example.com/v1/data").json()["key"])
print("keys left:", rotator.keys, "| breaker:", rotator.get_circuit_states())
```

Output:

```text
0 key-1
ERROR Key revo**** permanently invalid (status 401); removing it from rotation
ERROR Key revo**** permanently invalid (status 401); removing it from rotation
1 key-1
2 key-3
3 key-1
4 key-3
5 key-1
keys left: ['key-1', 'key-3'] | breaker: {'api.example.com': 'CLOSED'}
```

---

## 5. Several processes sharing keys (Redis)

### What is shared and how fast

| State | Shared through Redis | Consistency |
|---|---|---|
| Token buckets (`key_rate_limit`) | yes | strong: every token is taken atomically in Redis |
| Rate-limited keys (`429`, `X-RateLimit-Remaining: 0`) | yes | eventual: within `state_sync_interval` (1 s) + one round trip |
| Revoked keys (`401` / `403`) | yes | eventual, same delay |
| Metrics, circuit breakers, rotation order, response cache | no - per process | - |

Only `sha256(key)` (or an HMAC with `salt=`) is stored in Redis, never the key itself.
Use one `namespace` per upstream provider (or per set of keys).

### A global limit across processes

Four worker processes, 2 keys, `key_rate_limit=(10, 60)`: all of them together get 20
requests per minute, not 20 each.

```python
import multiprocessing as mp

from apikeyrotator import APIKeyRotator, DeadlineExceededError, RedisStateBackend

def worker(n: int) -> str:
    rotator = APIKeyRotator(
        api_keys=["key-1", "key-2"],
        state_backend=RedisStateBackend(url="redis://redis:6379/0", namespace="demo-api"),
        key_rate_limit=(10, 60),
        total_timeout=0.5,
    )
    sent = denied = 0
    for _ in range(15):
        try:
            rotator.get("https://api.example.com/items/1")
            sent += 1
        except DeadlineExceededError:    # every key out of tokens for longer than the budget
            denied += 1
    return f"worker {n}: sent {sent}, denied {denied}"

if __name__ == "__main__":
    with mp.get_context("spawn").Pool(4) as pool:
        results = pool.map(worker, range(4))
    print("\n".join(results))
```

Output:

```text
worker 0: sent 5, denied 10
worker 1: sent 5, denied 10
worker 2: sent 5, denied 10
worker 3: sent 5, denied 10
```

Together exactly 20 requests got through (the split between workers depends on timing).

### A revoked key reaches the other processes

```python
import logging
import multiprocessing as mp

from apikeyrotator import APIKeyRotator, RedisStateBackend

def run(name: str, requests: int) -> None:
    logging.basicConfig(level=logging.WARNING, format=f"{name}: %(levelname)s %(message)s")
    rotator = APIKeyRotator(
        api_keys=["key-1", "revoked-2"],
        state_backend=RedisStateBackend(url="redis://redis:6379/0", namespace="demo-api"),
        state_sync_interval=0,
    )
    used = [rotator.get("https://api.example.com/v1/data").json()["key"] for _ in range(requests)]
    print(f"{name}: keys used {used}, keys left {rotator.keys}", flush=True)

if __name__ == "__main__":
    ctx = mp.get_context("spawn")
    for name in ("worker A", "worker B"):
        p = ctx.Process(target=run, args=(name, 3))
        p.start()
        p.join()
```

Output:

```text
worker A: ERROR Key revo**** permanently invalid (status 401); removing it from rotation
worker A: keys used ['key-1', 'key-1', 'key-1'], keys left ['key-1']
worker B: WARNING Key revo**** was invalidated by another instance
worker B: keys used ['key-1', 'key-1', 'key-1'], keys left ['key-1']
```

Worker A found out the hard way; worker B never sent `revoked-2` at all.

To use a re-enabled key again, clear it: `backend.clear_invalid(backend.key_id("the-key"))`
(or `backend.clear_invalid()` for all keys of the namespace).

### When Redis is unavailable

The rotator keeps working with local state ("fail open"):

- one warning per 30 s, no exceptions;
- after an error Redis is not contacted for 5 s, so an outage costs one timeout per 5 s,
  not one per request (the client created from `url=` has a 1 s `socket_timeout`);
- `key_rate_limit` is enforced **per process** in the meantime - with N processes up to
  N times the limit may be sent, so the upstream may answer `429`, which is handled as usual.

```python
import logging
import time

from apikeyrotator import APIKeyRotator, DeadlineExceededError, RedisStateBackend

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
rotator = APIKeyRotator(
    api_keys=["key-1"],
    state_backend=RedisStateBackend(url="redis://localhost:6390/0"),   # nothing listens here
    key_rate_limit=(3, 60),
    total_timeout=0.2,
)
started = time.monotonic()
for i in range(5):
    try:
        print(i, rotator.get("https://api.example.com/items/1").status_code)
    except DeadlineExceededError:
        print(i, "DeadlineExceededError (local limit of 3 per minute)")
print(f"took {time.monotonic() - started:.2f}s")
```

Output:

```text
WARNING State backend snapshot failed (continuing locally, retrying in 5s): Error 111 connecting to localhost:6390. Connection refused.
0 200
1 200
2 200
3 DeadlineExceededError (local limit of 3 per minute)
4 DeadlineExceededError (local limit of 3 per minute)
took 0.09s
```

---

## 6. Passing keys: strings, lists, files, commas

A string is split on commas; whitespace and empty items are dropped; duplicates are
removed with a warning:

```python
import logging

from apikeyrotator import APIKeyRotator

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
print(APIKeyRotator(api_keys=" key-1, key-2 ,, key-1 ,key-3 ").keys)
print(APIKeyRotator(api_keys=["key-1", " key-2 ", ""]).keys)
```

Output:

```text
WARNING Removed 1 duplicate API key(s)
['key-1', 'key-2', 'key-3']
['key-1', 'key-2']
```

### Keys that contain commas

Comma-separated strings - `api_keys="..."`, the `API_KEYS` environment variable,
comma-separated files - cannot hold such keys. Pass a list, or a JSON array in a file or
secret:

```python
import json

from apikeyrotator import APIKeyRotator, FileSecretProvider

print("string:", APIKeyRotator(api_keys="abc,def,ghi").keys)       # 3 keys - wrong
print("list:  ", APIKeyRotator(api_keys=["abc,def", "ghi"]).keys)  # 2 keys

with open("keys.json", "w") as f:
    json.dump(["abc,def", "ghi"], f)
print("file:  ", APIKeyRotator(secret_provider=FileSecretProvider("keys.json")).keys)
```

Output:

```text
string: ['abc', 'def', 'ghi']
list:   ['abc,def', 'ghi']
file:   ['abc,def', 'ghi']
```

`FileSecretProvider` accepts a JSON array, comma-separated values or one key per line
(`#` starts a comment); AWS / GCP secrets may hold a JSON array too.

---

## 7. Which auth header is sent

Without `auth=`, the header is inferred from the key:

| Key | Header |
|---|---|
| exactly 32 characters, not starting with `sk-` / `pk-` | `X-API-Key: <key>` |
| anything else | `Authorization: Bearer <key>` |

The guess is only a default. Set `auth=` whenever you know what the API expects:

```python
from apikeyrotator import APIKeyRotator

url = "https://api.example.com/whoami"
key32 = "0123456789abcdef0123456789abcdef"

print(APIKeyRotator(api_keys=[key32]).get(url).json()["header"])
print(APIKeyRotator(api_keys=["sk-proj-abc123"]).get(url).json()["header"])
print(APIKeyRotator(api_keys=[key32], auth="bearer").get(url).json()["header"])
print(APIKeyRotator(api_keys=["sk-proj-abc123"], auth="x-api-key").get(url).json()["header"])
print(APIKeyRotator(api_keys=["abc"], auth=("Authorization", "Token {key}")).get(url).json()["header"])
```

Output:

```text
X-API-Key
Authorization: Bearer
Authorization: Bearer
X-API-Key
Authorization: Token
```

If the header is wrong, every key is rejected. The rotator then raises
`AuthenticationError` and **keeps** the keys, since the header is the likely cause:

```python
from apikeyrotator import APIKeyRotator, AuthenticationError

key32 = "0123456789abcdef0123456789abcdef"
rotator = APIKeyRotator(api_keys=[key32, "fedcba9876543210fedcba9876543210"])
try:
    rotator.get("https://api.example.com/v1/data")          # this API wants Bearer
except AuthenticationError as e:
    print(e.auth_header, e.statuses)
    print("keys kept:", len(rotator.keys))

rotator.auth = "bearer"
print(rotator.get("https://api.example.com/v1/data").json()["ok"], "| keys:", len(rotator.keys))
```

Output:

```text
X-API-Key: 0123...cdef {'0123...cdef': 401, 'fedc...3210': 401}
keys kept: 2
True | keys: 2
```

---

## 8. Metrics: which call returns what

| Call | Returns | With `enable_metrics=False` |
|---|---|---|
| `rotator.metrics` | the live `RotatorMetrics` object | `None` |
| `rotator.get_metrics()` | a dict snapshot: totals, success rate, per endpoint | `{}` |
| `rotator.get_key_statistics()` | a dict per key (raw key -> stats), always collected | per-key stats |
| `rotator.get_circuit_states()` | `{host: "CLOSED" / "OPEN" / "HALF_OPEN"}` | same |
| `PrometheusExporter.export(rotator)` | Prometheus text format, masked keys | `ValueError` |
| `rotator.export_config()` | settings + per-key stats with masked keys, safe to log | same |

```python
from apikeyrotator import APIKeyRotator, PrometheusExporter

rotator = APIKeyRotator(api_keys=["sk-live-first-key-0001", "sk-live-second-key-0002"])
for i in range(3):
    rotator.get(f"https://api.example.com/items/{i}?page={i}")

snapshot = rotator.get_metrics()
print(type(rotator.metrics).__name__, "|", sorted(snapshot))
print("total:", snapshot["total_requests"], "| endpoints:", list(snapshot["endpoint_stats"]))
print({key[-4:]: s["total_requests"] for key, s in rotator.get_key_statistics().items()})
print("\n".join(line for line in PrometheusExporter.export(rotator).splitlines()
                if line.startswith("rotator_key_total_requests")))
```

Output:

```text
RotatorMetrics | ['endpoint_stats', 'failed_requests', 'success_rate', 'successful_requests', 'total_requests', 'uptime_seconds']
total: 3 | endpoints: ['https://api.example.com/items/0', 'https://api.example.com/items/1', 'https://api.example.com/items/2']
{'0001': 2, '0002': 1}
rotator_key_total_requests{key="sk-l...0001"} 2
rotator_key_total_requests{key="sk-l...0002"} 1
```

Query strings are cut from endpoint names, so `endpoint_stats` stays small. Every attempt
counts: a request that needed a retry adds 2 to `total_requests`.

---

## Summary of guarantees

| Situation | Behavior |
|---|---|
| Many threads, one rotator | thread-safe; counters exact; `round_robin` and `lru` exact |
| Keys replaced while requests run | in-flight requests finish; stats of kept keys preserved |
| asyncio | one async rotator per event loop |
| Several processes | one rotator per process after the fork; Redis for shared limits |
| Binary body | byte-exact with every backend |
| Large body | `stream=True` without `unified_response`; mid-body errors are not retried |
| Other text encodings | `charset` of `Content-Type` is used by `text` and `json()` |
| One host down | only its breaker opens; other hosts unaffected |
| Revoked key | only that key is removed; the breaker ignores 4xx |
| Redis down | fail open; local token buckets; retried every 5 s |
| Key with a comma | pass a list or a JSON array |
| Unknown auth scheme | set `auth=`; a wrong header raises `AuthenticationError` and keeps the keys |

Related pages: [Resilience & Scaling](RESILIENCE.md) (payments and idempotency, deadlines,
rate limits), [Error Handling](ERROR_HANDLING.md), [API Reference](API_REFERENCE.md).
