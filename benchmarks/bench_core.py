#!/usr/bin/env python
"""
Benchmark suite for the apikeyrotator core.

Measures, in real numbers, how the rotator behaves so that changes to the core
can be compared against a saved baseline:

* overhead  - cost of the rotator itself (key selection, headers, classification,
              metrics, middlewares) with the HTTP transport stubbed out;
* resilience - behaviour under failures (rate limits, client errors): upstream
              calls per request, time spent sleeping, success rate, keys left;
* concurrency - throughput with many threads / asyncio tasks;
* e2e       - real HTTP round-trips against a local in-process server.

Usage:
    python benchmarks/bench_core.py                     # full run, print table
    python benchmarks/bench_core.py --quick             # fast smoke run
    python benchmarks/bench_core.py -k rate_limit       # only matching scenarios
    python benchmarks/bench_core.py --save base.json    # save results
    python benchmarks/bench_core.py --compare base.json # compare with saved results
                                                        # (exit code 1 on regression)

All scenarios are deterministic (fixed random seed); overhead numbers still
depend on the machine, so compare results produced on the same machine.
"""

import argparse
import asyncio
import contextlib
import gc
import json
import logging
import os
import platform
import random
import re
import socket
import statistics
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest import mock


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# HTTP libraries are imported lazily by apikeyrotator. Import them up front so the
# one-time import cost is not attributed to whichever scenario runs first.
with contextlib.suppress(ImportError):
    import aiohttp  # noqa: F401,E402
    import requests  # noqa: F401,E402

import apikeyrotator  # noqa: E402
from apikeyrotator import (  # noqa: E402
    AllKeysExhaustedError,
    APIKeyRotator,
    AsyncAPIKeyRotator,
    CachingMiddleware,
    KeyMetrics,
    LoggingMiddleware,
    RateLimitMiddleware,
    create_rotation_strategy,
)


SEED = 1234

# Metrics where a higher value is better; everything else is "lower is better".
HIGHER_IS_BETTER = {"ops_per_sec", "success_rate", "keys_left"}
# Metrics used by --compare to detect regressions
COMPARED_METRICS = [
    "ops_per_sec", "p50_us", "p99_us", "cpu_us_per_op", "upstream_calls_per_req",
    "sleep_s_per_1k_req", "success_rate", "keys_left",
    "mem_bytes_per_key", "mem_growth_bytes_per_1k_req", "mem_peak_kb", "alloc_kb_per_req",
    "import_ms", "import_rss_mb",
]
# Metrics that don't depend on machine speed - safe to gate CI on (--gate deterministic)
DETERMINISTIC_METRICS = {
    "upstream_calls_per_req", "sleep_s_per_1k_req", "success_rate", "keys_left",
    "mem_bytes_per_key", "mem_growth_bytes_per_1k_req",
}


def _quiet_logger() -> logging.Logger:
    logger = logging.getLogger("apikeyrotator.benchmark")
    logger.handlers[:] = [logging.NullHandler()]
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    return logger


def _keys(n: int) -> list[str]:
    return [f"bench-key-{i:04d}" for i in range(n)]


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(round(pct / 100.0 * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def _latency_stats(latencies_ns: list[int], wall_s: float, n_ops: int) -> dict[str, float]:
    lat_us = sorted(v / 1000.0 for v in latencies_ns)
    return {
        "ops": n_ops,
        "wall_s": round(wall_s, 4),
        "ops_per_sec": round(n_ops / wall_s, 1) if wall_s > 0 else 0.0,
        "mean_us": round(statistics.fmean(lat_us), 2) if lat_us else 0.0,
        "p50_us": round(_percentile(lat_us, 50), 2),
        "p95_us": round(_percentile(lat_us, 95), 2),
        "p99_us": round(_percentile(lat_us, 99), 2),
    }


# ============================================================================
# Stub transport
# ============================================================================

class FakeResponse:
    """Cheap stand-in for requests.Response."""
    __slots__ = ("status_code", "headers", "content", "ok")

    def __init__(self, status_code: int, headers: dict[str, str] | None = None, content: bytes = b'{"ok":true}'):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/json"}
        self.content = content
        self.ok = status_code < 400

    def close(self):
        pass

    def json(self):
        return json.loads(self.content)


class FakeAsyncResponse:
    __slots__ = ("status", "headers", "_content")

    def __init__(self, status: int, headers: dict[str, str] | None = None, content: bytes = b'{"ok":true}'):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._content = content

    async def read(self):
        return self._content

    def release(self):
        pass


class Upstream:
    """
    Simulated upstream API. `behaviour(key, n)` returns (status, headers) for the
    n-th request; it is shared by the sync and async stubs and counts calls.
    """

    def __init__(self, behaviour: Callable[[str, int], Any] | None = None, latency_s: float = 0.0):
        self.behaviour = behaviour or (lambda key, n: (200, None))
        self.latency_s = latency_s
        self.calls = 0
        self._lock = threading.Lock()

    def _next(self, headers: dict[str, str]):
        with self._lock:
            n = self.calls
            self.calls += 1
        auth = headers.get("Authorization") or headers.get("X-API-Key") or ""
        key = auth.split(" ", 1)[-1]
        return self.behaviour(key, n)

    def sync_request(self, method, url, **kwargs):
        status, headers = self._next(kwargs.get("headers") or {})
        if self.latency_s:
            time.sleep(self.latency_s)
        return FakeResponse(status, headers)

    async def async_request(self, method, url, **kwargs):
        status, headers = self._next(kwargs.get("headers") or {})
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        return FakeAsyncResponse(status, headers)


class FakeAsyncSession:
    closed = False

    def __init__(self, upstream: Upstream):
        self.request = upstream.async_request

    async def close(self):
        self.closed = True


class SleepRecorder:
    """
    Virtual clock: replaces time.sleep / asyncio.sleep so waits return instantly,
    records the requested wait time and advances time.time() by the same amount,
    so rate-limit windows (Retry-After) expire exactly as they would in real time.
    """

    def __init__(self):
        self.total = 0.0
        self.count = 0
        self._lock = threading.Lock()
        self._real_async_sleep = asyncio.sleep
        self._real_time = time.time

    def _advance(self, seconds) -> None:
        with self._lock:
            self.total += max(0.0, seconds)
            self.count += 1

    def now(self) -> float:
        return self._real_time() + self.total

    def sync(self, seconds):
        self._advance(seconds)

    async def async_(self, seconds, *args, **kwargs):
        self._advance(seconds)
        await self._real_async_sleep(0)

    @contextlib.contextmanager
    def patched(self):
        with mock.patch("time.sleep", self.sync), mock.patch("asyncio.sleep", self.async_), \
                mock.patch("time.time", self.now):
            yield self


def make_sync_rotator(upstream: Upstream, keys: list[str], **kwargs) -> APIKeyRotator:
    kwargs.setdefault("load_env_file", False)
    kwargs.setdefault("logger", _quiet_logger())
    rotator = APIKeyRotator(api_keys=keys, config_file=os.devnull + ".json", **kwargs)
    rotator.session.request = upstream.sync_request
    return rotator


def make_async_rotator(upstream: Upstream, keys: list[str], **kwargs) -> AsyncAPIKeyRotator:
    kwargs.setdefault("load_env_file", False)
    kwargs.setdefault("logger", _quiet_logger())
    rotator = AsyncAPIKeyRotator(api_keys=keys, config_file=os.devnull + ".json", **kwargs)
    rotator._session = FakeAsyncSession(upstream)
    return rotator


# ============================================================================
# Runners
# ============================================================================

def run_sync(rotator: APIKeyRotator, n: int, url: str = "http://bench.local/v1/items") -> dict[str, Any]:
    latencies: list[int] = []
    ok = failed = 0
    perf = time.perf_counter_ns
    t0 = perf()
    for _ in range(n):
        start = perf()
        try:
            response = rotator.get(url)
            if response.status_code < 400:
                ok += 1
            else:
                failed += 1
        except AllKeysExhaustedError:
            failed += 1
        latencies.append(perf() - start)
    wall = (perf() - t0) / 1e9
    stats = _latency_stats(latencies, wall, n)
    stats["success_rate"] = round(ok / n, 4)
    return stats


def run_sync_threads(rotator: APIKeyRotator, n: int, threads: int) -> dict[str, Any]:
    latencies: list[int] = []
    lock = threading.Lock()
    per_thread = n // threads
    perf = time.perf_counter_ns

    def worker():
        local = []
        for _ in range(per_thread):
            start = perf()
            rotator.get("http://bench.local/v1/items")
            local.append(perf() - start)
        with lock:
            latencies.extend(local)

    t0 = perf()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for f in [pool.submit(worker) for _ in range(threads)]:
            f.result()
    wall = (perf() - t0) / 1e9
    return _latency_stats(latencies, wall, per_thread * threads)


async def run_async(rotator: AsyncAPIKeyRotator, n: int, concurrency: int,
                    url: str = "http://bench.local/v1/items") -> dict[str, Any]:
    latencies: list[int] = []
    ok = 0
    perf = time.perf_counter_ns
    sem = asyncio.Semaphore(concurrency)

    async def one():
        nonlocal ok
        async with sem:
            start = perf()
            try:
                response = await rotator.get(url)
                if response.status < 400:
                    ok += 1
                release = getattr(response, "release", None)
                if release is not None:
                    result = release()
                    if asyncio.iscoroutine(result):
                        await result
            except AllKeysExhaustedError:
                pass
            latencies.append(perf() - start)

    t0 = perf()
    await asyncio.gather(*(one() for _ in range(n)))
    wall = (perf() - t0) / 1e9
    stats = _latency_stats(latencies, wall, n)
    stats["success_rate"] = round(ok / n, 4)
    return stats


# ============================================================================
# Scenarios
# ============================================================================

SCENARIOS: dict[str, dict[str, Any]] = {}


def scenario(name: str, group: str, description: str):
    def decorator(fn):
        SCENARIOS[name] = {"fn": fn, "group": group, "description": description}
        return fn
    return decorator


def _strategy_scenario(strategy: str):
    def fn(n: int) -> dict[str, Any]:
        upstream = Upstream()
        rotator = make_sync_rotator(upstream, _keys(10), rotation_strategy=strategy)
        return run_sync(rotator, n)
    return fn


for _strategy in ("round_robin", "random", "weighted", "lru", "health_based"):
    scenario(
        f"overhead_sync_{_strategy}", "overhead",
        f"Sync request overhead, 10 keys, strategy={_strategy}, stub transport",
    )(_strategy_scenario(_strategy))


@scenario("overhead_sync_middlewares", "overhead",
          "Sync overhead with Logging+RateLimit middlewares (all misses)")
def _overhead_middlewares(n: int) -> dict[str, Any]:
    upstream = Upstream(lambda key, i: (200, {"X-RateLimit-Remaining": "100",
                                              "X-RateLimit-Reset": str(int(time.time()) + 60)}))
    rotator = make_sync_rotator(upstream, _keys(10), middlewares=[
        LoggingMiddleware(logger=_quiet_logger(), log_level=logging.WARNING),
        RateLimitMiddleware(pause_on_limit=True, logger=_quiet_logger()),
    ])
    return run_sync(rotator, n)


@scenario("overhead_sync_all_features", "overhead",
          "Sync overhead with circuit breaker, key token bucket and request deadline enabled")
def _overhead_all_features(n: int) -> dict[str, Any]:
    rotator = make_sync_rotator(Upstream(), _keys(10), circuit_breaker=True,
                                key_rate_limit=(10 ** 9, 1), total_timeout=30)
    return run_sync(rotator, n)


@scenario("overhead_sync_cache_hits", "overhead",
          "Sync requests served by CachingMiddleware (same URL)")
def _overhead_cache(n: int) -> dict[str, Any]:
    upstream = Upstream()
    rotator = make_sync_rotator(upstream, _keys(10), middlewares=[CachingMiddleware(ttl=3600)])
    stats = run_sync(rotator, n)
    stats["upstream_calls_per_req"] = round(upstream.calls / n, 4)
    return stats


@scenario("overhead_async", "overhead", "Async request overhead, 10 keys, sequential")
def _overhead_async(n: int) -> dict[str, Any]:
    upstream = Upstream()
    rotator = make_async_rotator(upstream, _keys(10))
    return asyncio.run(run_async(rotator, n, concurrency=1))


@scenario("concurrency_sync_16_threads", "concurrency",
          "16 threads, 1ms simulated upstream latency")
def _concurrency_threads(n: int) -> dict[str, Any]:
    upstream = Upstream(latency_s=0.001)
    rotator = make_sync_rotator(upstream, _keys(10))
    return run_sync_threads(rotator, max(n // 5, 160), threads=16)


@scenario("concurrency_async_200_tasks", "concurrency",
          "200 concurrent asyncio tasks, 1ms simulated upstream latency")
def _concurrency_async(n: int) -> dict[str, Any]:
    upstream = Upstream(latency_s=0.001)
    rotator = make_async_rotator(upstream, _keys(10))
    return asyncio.run(run_async(rotator, n, concurrency=200))


def _resilience(n: int, keys: int, behaviour, is_async: bool = False, **rotator_kwargs) -> dict[str, Any]:
    random.seed(SEED)
    upstream = Upstream(behaviour)
    sleeps = SleepRecorder()
    with sleeps.patched():
        if is_async:
            rotator = make_async_rotator(upstream, _keys(keys), **rotator_kwargs)
            stats = asyncio.run(run_async(rotator, n, concurrency=20))
        else:
            rotator = make_sync_rotator(upstream, _keys(keys), **rotator_kwargs)
            stats = run_sync(rotator, n)
    stats["upstream_calls_per_req"] = round(upstream.calls / n, 4)
    stats["sleep_s_per_1k_req"] = round(sleeps.total / n * 1000, 3)
    stats["keys_left"] = rotator.key_count
    return stats


def _rate_limit_behaviour(p: float):
    rng = random.Random(SEED)
    lock = threading.Lock()

    def behaviour(key, i):
        with lock:
            hit = rng.random() < p
        return (429, {"Retry-After": "1"}) if hit else (200, None)
    return behaviour


@scenario("resilience_rate_limit_10pct", "resilience",
          "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated")
def _resilience_rl(n: int) -> dict[str, Any]:
    return _resilience(n, 10, _rate_limit_behaviour(0.10))


@scenario("resilience_rate_limit_hot_key", "resilience",
          "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated")
def _resilience_hot_key(n: int) -> dict[str, Any]:
    hot = _keys(10)[0]
    return _resilience(n, 10, lambda key, i: (429, {"Retry-After": "30"}) if key == hot else (200, None))


@scenario("resilience_async_rate_limit_10pct", "resilience",
          "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated")
def _resilience_async_rl(n: int) -> dict[str, Any]:
    return _resilience(n, 10, _rate_limit_behaviour(0.10), is_async=True)


@scenario("resilience_server_errors_5pct", "resilience",
          "10 keys, 5% of responses are 503. Sleeps are simulated")
def _resilience_5xx(n: int) -> dict[str, Any]:
    rng = random.Random(SEED)
    return _resilience(n, 10, lambda key, i: (503, None) if rng.random() < 0.05 else (200, None))


@scenario("resilience_client_errors_5pct", "resilience",
          "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)")
def _resilience_404(n: int) -> dict[str, Any]:
    rng = random.Random(SEED)
    return _resilience(n, 10, lambda key, i: (404, None) if rng.random() < 0.05 else (200, None))



@scenario("resilience_host_down", "resilience",
          "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)")
def _resilience_down(n: int) -> dict[str, Any]:
    return _resilience(max(n // 10, 100), 10, lambda key, i: (503, None))


@scenario("resilience_host_down_breaker", "resilience",
          "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it")
def _resilience_down_breaker(n: int) -> dict[str, Any]:
    from apikeyrotator.utils import CircuitBreakerConfig
    return _resilience(max(n // 10, 100), 10, lambda key, i: (503, None),
                       circuit_breaker=CircuitBreakerConfig(failure_threshold=5, recovery_timeout=30))


def _quota_upstream(per_key: int = 10, window: float = 60.0):
    """Each key may make `per_key` requests per `window` seconds; answers carry X-RateLimit-* headers."""
    counts: dict[tuple[str, int], int] = {}
    lock = threading.Lock()

    def behaviour(key, i):
        now = time.time()
        slot = int(now // window)
        reset_in = str(int((slot + 1) * window - now) + 1)
        with lock:
            used = counts[(key, slot)] = counts.get((key, slot), 0) + 1
        if used > per_key:
            return 429, {"Retry-After": reset_in}
        return 200, {"X-RateLimit-Remaining": str(per_key - used), "X-RateLimit-Reset": reset_in}
    return behaviour


@scenario("resilience_quota_reactive", "resilience",
          "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)")
def _resilience_quota_reactive(n: int) -> dict[str, Any]:
    return _resilience(max(n // 5, 200), 10, _quota_upstream(), max_retries=30,
                       respect_rate_limit_headers=False)


@scenario("resilience_quota_headers", "resilience",
          "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0")
def _resilience_quota_headers(n: int) -> dict[str, Any]:
    return _resilience(max(n // 5, 200), 10, _quota_upstream(), max_retries=30)


@scenario("resilience_quota_token_bucket", "resilience",
          "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)")
def _resilience_quota_bucket(n: int) -> dict[str, Any]:
    return _resilience(max(n // 5, 200), 10, _quota_upstream(), max_retries=30,
                       key_rate_limit=(10, 60))


def _selection_scenario(strategy: str, n_keys: int):
    def fn(n: int) -> dict[str, Any]:
        keys = _keys(n_keys)
        source: Any = {k: 1.0 for k in keys} if strategy == "weighted" else keys
        strat = create_rotation_strategy(strategy, source)
        metrics = {k: KeyMetrics(k) for k in keys}
        perf = time.perf_counter_ns
        latencies = []
        t0 = perf()
        for _ in range(n):
            s = perf()
            strat.get_next_key(metrics)
            latencies.append(perf() - s)
        return _latency_stats(latencies, (perf() - t0) / 1e9, n)
    return fn


for _strategy in ("round_robin", "random", "weighted", "lru", "health_based"):
    for _n_keys in (10, 1000):
        scenario(
            f"select_{_strategy}_{_n_keys}_keys", "selection",
            f"strategy.get_next_key() with {_n_keys} keys and metrics",
        )(_selection_scenario(_strategy, _n_keys))


# ---------------------------------------------------------------------------
# Resources: memory and import cost
# ---------------------------------------------------------------------------

def _traced(fn):
    """Runs fn() under tracemalloc, returns (result, current_bytes_delta, peak_bytes_delta)."""
    import tracemalloc
    gc.collect()
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        result = fn()
        gc.collect()
        after, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, after - before, peak - before


def _memory_per_key_scenario(strategy: str, n_keys: int = 10000):
    def fn(n: int) -> dict[str, Any]:
        keys = _keys(n_keys)
        holder: list[Any] = []
        # Warm-up: pay one-time costs (lazy imports, caches) outside the measurement
        make_sync_rotator(Upstream(), _keys(2), rotation_strategy=strategy)

        def build():
            upstream = Upstream()
            holder.append(make_sync_rotator(upstream, list(keys), rotation_strategy=strategy))

        t0 = time.perf_counter()
        _, current, peak = _traced(build)
        wall = time.perf_counter() - t0
        return {
            "ops": n_keys, "wall_s": round(wall, 4), "ops_per_sec": round(n_keys / wall, 1),
            "mem_bytes_per_key": round(current / n_keys, 1),
            "mem_total_mb": round(current / 1e6, 3),
            "mem_peak_kb": round(peak / 1024, 1),
        }
    return fn


for _strategy in ("round_robin", "lru", "health_based"):
    scenario(
        f"resources_memory_per_key_{_strategy}", "resources",
        f"Memory retained per key: rotator with 10k keys, strategy={_strategy}",
    )(_memory_per_key_scenario(_strategy))


_LEAK_NOISE_FLOOR = 1024  # bytes


def _steady_state(make, is_async: bool, n: int) -> dict[str, Any]:
    """Memory growth after warm-up (leak detector) and transient allocations per request."""
    import tracemalloc
    # Warm-up with more unique URLs than any bounded internal cache holds, so that
    # bounded caches (ours or stdlib's) are full and only real growth is measured.
    warmup = max(n // 2, 3000)
    measured = max(n, 3000)
    counter = iter(range(10 ** 9))

    def urls(count):
        # Distinct query strings - must not grow endpoint metrics without bound
        return [f"http://bench.local/v1/items?id={next(counter)}" for _ in range(count)]

    rotator = make()

    async def run_async_batch(batch):
        for u in batch:
            await rotator.get(u)

    def run(batch):
        if is_async:
            asyncio.run(run_async_batch(batch))
        else:
            for u in batch:
                rotator.get(u)

    # Tracing starts BEFORE the warm-up: objects allocated before tracemalloc.start()
    # are invisible when freed, so replaced cache entries would look like growth.
    tracemalloc.start()
    try:
        run(urls(warmup))
        batch = urls(measured)
        gc.collect()
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        t0 = time.perf_counter()
        run(batch)
        wall = time.perf_counter() - t0
        gc.collect()
        after, peak = tracemalloc.get_traced_memory()
        # Transient allocations of a single request
        tracemalloc.reset_peak()
        base_single, _ = tracemalloc.get_traced_memory()
        run(urls(1))
        _, peak_single = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "ops": measured, "wall_s": round(wall, 4),
        "ops_per_sec": round(measured / wall, 1),  # under tracemalloc - not comparable with other groups
        # Growth below 1 KB over the whole window is allocator/bookkeeping noise
        # (e.g. counters re-allocated as bigger ints), not a leak.
        "mem_growth_bytes_per_1k_req": (
            round((after - before) / measured * 1000, 1) if after - before >= _LEAK_NOISE_FLOOR else 0.0
        ),
        "mem_peak_kb": round((peak - before) / 1024, 1),
        "alloc_kb_per_req": round(max(0, peak_single - base_single) / 1024, 2),
    }


@scenario("resources_steady_state_sync", "resources",
          "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)")
def _res_steady_sync(n: int) -> dict[str, Any]:
    return _steady_state(lambda: make_sync_rotator(Upstream(), _keys(10)), False, n)


@scenario("resources_steady_state_sync_middlewares", "resources",
          "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests")
def _res_steady_sync_mw(n: int) -> dict[str, Any]:
    def make():
        return make_sync_rotator(Upstream(), _keys(10), middlewares=[
            LoggingMiddleware(logger=_quiet_logger(), log_level=logging.WARNING),
            RateLimitMiddleware(pause_on_limit=False, logger=_quiet_logger()),
            CachingMiddleware(ttl=3600, max_cache_size=500),
        ])
    return _steady_state(make, False, n)


@scenario("resources_steady_state_async", "resources",
          "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)")
def _res_steady_async(n: int) -> dict[str, Any]:
    return _steady_state(lambda: make_async_rotator(Upstream(), _keys(10)), True, n)


@scenario("resources_import_cost", "resources",
          "Time and RSS added by `import apikeyrotator` in a fresh interpreter")
def _res_import(n: int) -> dict[str, Any]:
    import subprocess
    # Current RSS from /proc (ru_maxrss is inherited from the parent across fork+exec on Linux)
    code = (
        "import os, time\n"
        "def rss():\n"
        "    try:\n"
        "        with open('/proc/self/statm') as f:\n"
        "            return int(f.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')\n"
        "    except OSError:\n"
        "        return 0\n"
        "r0 = rss()\n"
        "t0 = time.perf_counter()\n"
        "import apikeyrotator\n"
        "t1 = time.perf_counter()\n"
        "print((t1 - t0) * 1000, (rss() - r0) / 1e6)\n"
    )
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    samples = []
    for _ in range(5):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             cwd=root, env={**os.environ, "PYTHONPATH": root}, check=True)
        ms, mb = map(float, out.stdout.split())
        samples.append((ms, mb))
    samples.sort()
    ms, mb = samples[len(samples) // 2]
    return {"ops": 1, "wall_s": round(ms / 1000, 4), "ops_per_sec": round(1000 / ms, 1),
            "import_ms": round(ms, 1), "import_rss_mb": round(mb, 1)}


# ---------------------------------------------------------------------------
# End-to-end against a local HTTP server
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def local_server():
    """Starts an aiohttp server on 127.0.0.1 in a background thread."""
    from aiohttp import web

    async def handler(request):
        return web.json_response({"ok": True})

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    state: dict[str, Any] = {}

    def serve():
        asyncio.set_event_loop(loop)
        app = web.Application()
        app.router.add_get("/{tail:.*}", handler)
        runner = web.AppRunner(app, access_log=None)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", port)
        loop.run_until_complete(site.start())
        state["runner"] = runner
        ready.set()
        loop.run_forever()
        loop.run_until_complete(runner.cleanup())
        loop.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    ready.wait(10)
    try:
        yield f"http://127.0.0.1:{port}/v1/items"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(10)


@scenario("e2e_sync_local_http", "e2e", "Real HTTP round-trips to a local server (sync, keep-alive)")
def _e2e_sync(n: int) -> dict[str, Any]:
    with local_server() as url:
        rotator = APIKeyRotator(api_keys=_keys(10), load_env_file=False, logger=_quiet_logger(),
                                config_file=os.devnull + ".json")
        n = max(n // 5, 100)
        rotator.get(url)  # warm up connection pool
        return run_sync(rotator, n, url=url)


@scenario("e2e_async_local_http", "e2e", "Real HTTP round-trips to a local server (async, 50 concurrent)")
def _e2e_async(n: int) -> dict[str, Any]:
    with local_server() as url:
        async def main():
            rotator = AsyncAPIKeyRotator(api_keys=_keys(10), load_env_file=False, logger=_quiet_logger(),
                                         config_file=os.devnull + ".json")
            try:
                return await run_async(rotator, max(n // 2, 100), concurrency=50, url=url)
            finally:
                session = rotator._session
                if session is not None and not session.closed:
                    await session.close()
        return asyncio.run(main())


# ============================================================================
# CLI
# ============================================================================

class ScenarioTimeout(Exception):
    pass


@contextlib.contextmanager
def _time_limit(seconds: float | None):
    """Aborts a scenario that runs too long (e.g. an old version that hangs) - Unix only."""
    import signal

    if not seconds or not hasattr(signal, "setitimer"):
        yield
        return

    def handler(signum, frame):
        raise ScenarioTimeout(f"scenario exceeded {seconds:.0f}s")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def run_scenarios(pattern: str | None, n: int, repeat: int, groups: list[str] | None,
                  scenario_timeout: float | None = None) -> dict[str, Any]:
    results = {}
    regex = re.compile(pattern) if pattern else None
    for name, spec in SCENARIOS.items():
        if regex and not regex.search(name):
            continue
        if groups and spec["group"] not in groups:
            continue
        runs = []
        error = None
        for _ in range(repeat):
            gc.collect()
            try:
                cpu0 = time.process_time()
                with _time_limit(scenario_timeout):
                    run = spec["fn"](n)
                cpu = time.process_time() - cpu0
                if spec["group"] != "resources" and run.get("ops"):
                    # Process CPU time per operation (includes all threads of the process)
                    run["cpu_us_per_op"] = round(cpu / run["ops"] * 1e6, 2)
                runs.append(run)
            except (Exception, ScenarioTimeout) as e:  # keep going - report the failure
                error = f"{type(e).__name__}: {e}"
                break
        if error:
            results[name] = {"group": spec["group"], "error": error}
            print(f"  {name:<40} ERROR {error}", file=sys.stderr)
            continue
        # Best run by throughput (like timeit): interference from other processes only
        # ever slows a run down, so the fastest repeat is the least noisy estimate.
        # Resilience/resource metrics are deterministic and identical across repeats.
        best = dict(max(runs, key=lambda r: r.get("ops_per_sec", 0)))
        best["group"] = spec["group"]
        best["description"] = spec["description"]
        results[name] = best
        print(f"  {name:<40} {best['ops_per_sec']:>12,.0f} ops/s", file=sys.stderr)
    return results


def environment_info() -> dict[str, Any]:
    return {
        "apikeyrotator_version": getattr(apikeyrotator, "__version__", "?"),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}" if abs(value) < 1000 else f"{value:,.0f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _print_rows(headers: list[str], rows: list[list[str]]) -> None:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = "  ".join(h.ljust(w) if i == 0 else h.rjust(w) for i, (h, w) in enumerate(zip(headers, widths)))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(x).ljust(w) if i == 0 else str(x).rjust(w)
                        for i, (x, w) in enumerate(zip(row, widths))))


def print_table(results: dict[str, Any]) -> None:
    perf = {k: v for k, v in results.items() if v.get("group") != "resources"}
    res = {k: v for k, v in results.items() if v.get("group") == "resources"}

    tables = [
        (perf, ["ops_per_sec", "p50_us", "p99_us", "cpu_us_per_op", "success_rate",
                "upstream_calls_per_req", "sleep_s_per_1k_req", "keys_left"],
         ["scenario", "ops/s", "p50 µs", "p99 µs", "CPU µs/op", "success", "calls/req", "sleep s/1k", "keys"]),
        (res, ["mem_bytes_per_key", "mem_growth_bytes_per_1k_req", "mem_peak_kb", "alloc_kb_per_req",
               "import_ms", "import_rss_mb"],
         ["scenario", "B/key", "growth B/1k req", "peak KB", "alloc KB/req", "import ms", "import MB"]),
    ]
    first = True
    for subset, columns, headers in tables:
        if not subset:
            continue
        if not first:
            print()
        first = False
        rows = []
        for name, r in subset.items():
            if "error" in r:
                rows.append([name, "ERROR: " + r["error"]] + [""] * (len(headers) - 2))
                continue
            rows.append([name] + [_fmt(r[c]) if c in r else "-" for c in columns])
        _print_rows(headers, rows)


def compare(current: dict[str, Any], baseline: dict[str, Any], threshold: float,
            gate: str = "all") -> int:
    """
    Prints a diff table; returns number of regressions beyond threshold (percent).

    gate="deterministic" counts regressions only for machine-independent metrics
    (useful on noisy shared CI runners); other changes are still printed.
    """
    regressions = 0
    base_results = baseline.get("results", {})
    print(f"\nComparison with baseline "
          f"(v{baseline.get('environment', {}).get('apikeyrotator_version', '?')}, "
          f"threshold {threshold:.0f}%):\n")
    header = f"{'scenario':<40} {'metric':<24} {'baseline':>14} {'current':>14} {'change':>9}"
    print(header)
    print("-" * len(header))
    for name, cur in current.items():
        base = base_results.get(name)
        if not base or "error" in base or "error" in cur:
            continue
        for metric in COMPARED_METRICS:
            if metric not in cur or metric not in base:
                continue
            b, c = base[metric], cur[metric]
            if b == c:
                continue
            if b == 0:
                change = float("inf") if c > b else float("-inf")
            else:
                change = (c - b) / abs(b) * 100
            better = (c > b) if metric in HIGHER_IS_BETTER else (c < b)
            # Latency/throughput on tiny absolute values are noisy - ignore sub-threshold changes
            flag = ""
            if abs(change) >= threshold:
                flag = "  better" if better else "  WORSE"
                if not better and (gate == "all" or metric in DETERMINISTIC_METRICS):
                    regressions += 1
                elif not better:
                    flag = "  worse (not gated)"
            change_s = f"{change:+.1f}%" if abs(change) != float("inf") else ("+inf" if c > b else "-inf")
            print(f"{name:<40} {metric:<24} {_fmt(b):>14} {_fmt(c):>14} {change_s:>9}{flag}")
    print(f"\n{regressions} regression(s) beyond {threshold:.0f}%")
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-k", "--scenario", help="regex filter for scenario names")
    parser.add_argument("-g", "--group", action="append",
                        choices=["overhead", "concurrency", "resilience", "selection", "resources", "e2e"],
                        help="run only these groups (repeatable)")
    parser.add_argument("-n", "--requests", type=int, default=5000, help="operations per scenario")
    parser.add_argument("-r", "--repeat", type=int, default=3, help="repeats per scenario (best run is reported)")
    parser.add_argument("--quick", action="store_true", help="fast smoke run (-n 300 -r 1)")
    parser.add_argument("--save", metavar="FILE", help="save results as JSON")
    parser.add_argument("--compare", metavar="FILE", help="compare with results saved by --save")
    parser.add_argument("--threshold", type=float, default=10.0,
                        help="regression threshold in percent for --compare (default 10)")
    parser.add_argument("--gate", choices=["all", "deterministic"], default="all",
                        help="which metrics count as regressions for --compare (default: all)")
    parser.add_argument("--scenario-timeout", type=float, default=None, metavar="SEC",
                        help="abort a scenario after SEC seconds and report it as an error")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args(argv)

    if args.list:
        for name, spec in SCENARIOS.items():
            print(f"{name:<40} [{spec['group']}] {spec['description']}")
        return 0

    if args.quick:
        args.requests, args.repeat = 300, 1

    env = environment_info()
    print(f"apikeyrotator {env['apikeyrotator_version']} | Python {env['python']} | "
          f"{env['platform']} | {env['cpu_count']} CPUs", file=sys.stderr)
    results = run_scenarios(args.scenario, args.requests, args.repeat, args.group, args.scenario_timeout)
    print()
    print_table(results)

    payload = {"environment": env, "settings": {"requests": args.requests, "repeat": args.repeat},
               "results": results}
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nSaved results to {args.save}")

    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            baseline = json.load(f)
        if compare(results, baseline, args.threshold, args.gate):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
