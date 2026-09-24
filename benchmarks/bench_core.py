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
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import apikeyrotator  # noqa: E402
from apikeyrotator import (  # noqa: E402
    APIKeyRotator,
    AsyncAPIKeyRotator,
    AllKeysExhaustedError,
    CachingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    create_rotation_strategy,
    KeyMetrics,
)

SEED = 1234

# Metrics where a higher value is better; everything else is "lower is better".
HIGHER_IS_BETTER = {"ops_per_sec", "success_rate", "keys_left"}
# Metrics used by --compare to detect regressions
COMPARED_METRICS = [
    "ops_per_sec", "p50_us", "p99_us", "upstream_calls_per_req",
    "sleep_s_per_1k_req", "success_rate", "keys_left",
]


def _quiet_logger() -> logging.Logger:
    logger = logging.getLogger("apikeyrotator.benchmark")
    logger.handlers[:] = [logging.NullHandler()]
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    return logger


def _keys(n: int) -> List[str]:
    return [f"bench-key-{i:04d}" for i in range(n)]


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(round(pct / 100.0 * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def _latency_stats(latencies_ns: List[int], wall_s: float, n_ops: int) -> Dict[str, float]:
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

    def __init__(self, status_code: int, headers: Optional[Dict[str, str]] = None, content: bytes = b'{"ok":true}'):
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

    def __init__(self, status: int, headers: Optional[Dict[str, str]] = None, content: bytes = b'{"ok":true}'):
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

    def __init__(self, behaviour: Optional[Callable[[str, int], Any]] = None, latency_s: float = 0.0):
        self.behaviour = behaviour or (lambda key, n: (200, None))
        self.latency_s = latency_s
        self.calls = 0
        self._lock = threading.Lock()

    def _next(self, headers: Dict[str, str]):
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


def make_sync_rotator(upstream: Upstream, keys: List[str], **kwargs) -> APIKeyRotator:
    kwargs.setdefault("load_env_file", False)
    kwargs.setdefault("logger", _quiet_logger())
    rotator = APIKeyRotator(api_keys=keys, config_file=os.devnull + ".json", **kwargs)
    rotator.session.request = upstream.sync_request
    return rotator


def make_async_rotator(upstream: Upstream, keys: List[str], **kwargs) -> AsyncAPIKeyRotator:
    kwargs.setdefault("load_env_file", False)
    kwargs.setdefault("logger", _quiet_logger())
    rotator = AsyncAPIKeyRotator(api_keys=keys, config_file=os.devnull + ".json", **kwargs)
    rotator._session = FakeAsyncSession(upstream)
    return rotator


# ============================================================================
# Runners
# ============================================================================

def run_sync(rotator: APIKeyRotator, n: int, url: str = "http://bench.local/v1/items") -> Dict[str, Any]:
    latencies: List[int] = []
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


def run_sync_threads(rotator: APIKeyRotator, n: int, threads: int) -> Dict[str, Any]:
    latencies: List[int] = []
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
                    url: str = "http://bench.local/v1/items") -> Dict[str, Any]:
    latencies: List[int] = []
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

SCENARIOS: Dict[str, Dict[str, Any]] = {}


def scenario(name: str, group: str, description: str):
    def decorator(fn):
        SCENARIOS[name] = {"fn": fn, "group": group, "description": description}
        return fn
    return decorator


def _strategy_scenario(strategy: str):
    def fn(n: int) -> Dict[str, Any]:
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
def _overhead_middlewares(n: int) -> Dict[str, Any]:
    upstream = Upstream(lambda key, i: (200, {"X-RateLimit-Remaining": "100",
                                              "X-RateLimit-Reset": str(int(time.time()) + 60)}))
    rotator = make_sync_rotator(upstream, _keys(10), middlewares=[
        LoggingMiddleware(logger=_quiet_logger(), log_level=logging.WARNING),
        RateLimitMiddleware(pause_on_limit=True, logger=_quiet_logger()),
    ])
    return run_sync(rotator, n)


@scenario("overhead_sync_cache_hits", "overhead",
          "Sync requests served by CachingMiddleware (same URL)")
def _overhead_cache(n: int) -> Dict[str, Any]:
    upstream = Upstream()
    rotator = make_sync_rotator(upstream, _keys(10), middlewares=[CachingMiddleware(ttl=3600)])
    stats = run_sync(rotator, n)
    stats["upstream_calls_per_req"] = round(upstream.calls / n, 4)
    return stats


@scenario("overhead_async", "overhead", "Async request overhead, 10 keys, sequential")
def _overhead_async(n: int) -> Dict[str, Any]:
    upstream = Upstream()
    rotator = make_async_rotator(upstream, _keys(10))
    return asyncio.run(run_async(rotator, n, concurrency=1))


@scenario("concurrency_sync_16_threads", "concurrency",
          "16 threads, 1ms simulated upstream latency")
def _concurrency_threads(n: int) -> Dict[str, Any]:
    upstream = Upstream(latency_s=0.001)
    rotator = make_sync_rotator(upstream, _keys(10))
    return run_sync_threads(rotator, max(n // 5, 160), threads=16)


@scenario("concurrency_async_200_tasks", "concurrency",
          "200 concurrent asyncio tasks, 1ms simulated upstream latency")
def _concurrency_async(n: int) -> Dict[str, Any]:
    upstream = Upstream(latency_s=0.001)
    rotator = make_async_rotator(upstream, _keys(10))
    return asyncio.run(run_async(rotator, n, concurrency=200))


def _resilience(n: int, keys: int, behaviour, is_async: bool = False, **rotator_kwargs) -> Dict[str, Any]:
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
def _resilience_rl(n: int) -> Dict[str, Any]:
    return _resilience(n, 10, _rate_limit_behaviour(0.10))


@scenario("resilience_rate_limit_hot_key", "resilience",
          "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated")
def _resilience_hot_key(n: int) -> Dict[str, Any]:
    hot = _keys(10)[0]
    return _resilience(n, 10, lambda key, i: (429, {"Retry-After": "30"}) if key == hot else (200, None))


@scenario("resilience_async_rate_limit_10pct", "resilience",
          "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated")
def _resilience_async_rl(n: int) -> Dict[str, Any]:
    return _resilience(n, 10, _rate_limit_behaviour(0.10), is_async=True)


@scenario("resilience_server_errors_5pct", "resilience",
          "10 keys, 5% of responses are 503. Sleeps are simulated")
def _resilience_5xx(n: int) -> Dict[str, Any]:
    rng = random.Random(SEED)
    return _resilience(n, 10, lambda key, i: (503, None) if rng.random() < 0.05 else (200, None))


@scenario("resilience_client_errors_5pct", "resilience",
          "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)")
def _resilience_404(n: int) -> Dict[str, Any]:
    rng = random.Random(SEED)
    return _resilience(n, 10, lambda key, i: (404, None) if rng.random() < 0.05 else (200, None))


def _selection_scenario(strategy: str, n_keys: int):
    def fn(n: int) -> Dict[str, Any]:
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
    state: Dict[str, Any] = {}

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
def _e2e_sync(n: int) -> Dict[str, Any]:
    with local_server() as url:
        rotator = APIKeyRotator(api_keys=_keys(10), load_env_file=False, logger=_quiet_logger(),
                                config_file=os.devnull + ".json")
        n = max(n // 5, 100)
        rotator.get(url)  # warm up connection pool
        return run_sync(rotator, n, url=url)


@scenario("e2e_async_local_http", "e2e", "Real HTTP round-trips to a local server (async, 50 concurrent)")
def _e2e_async(n: int) -> Dict[str, Any]:
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

def run_scenarios(pattern: Optional[str], n: int, repeat: int, groups: Optional[List[str]]) -> Dict[str, Any]:
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
                runs.append(spec["fn"](n))
            except Exception as e:  # keep going - report the failure
                error = f"{type(e).__name__}: {e}"
                break
        if error:
            results[name] = {"group": spec["group"], "error": error}
            print(f"  {name:<40} ERROR {error}", file=sys.stderr)
            continue
        # Median run by throughput
        runs.sort(key=lambda r: r["ops_per_sec"])
        best = dict(runs[len(runs) // 2])
        best["group"] = spec["group"]
        best["description"] = spec["description"]
        results[name] = best
        print(f"  {name:<40} {best['ops_per_sec']:>12,.0f} ops/s", file=sys.stderr)
    return results


def environment_info() -> Dict[str, Any]:
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


def print_table(results: Dict[str, Any]) -> None:
    columns = ["ops_per_sec", "p50_us", "p99_us", "success_rate",
               "upstream_calls_per_req", "sleep_s_per_1k_req", "keys_left"]
    headers = ["scenario", "ops/s", "p50 µs", "p99 µs", "success", "calls/req", "sleep s/1k", "keys"]
    rows = []
    for name, r in results.items():
        if "error" in r:
            rows.append([name, "ERROR: " + r["error"]] + [""] * (len(headers) - 2))
            continue
        rows.append([name] + [_fmt(r[c]) if c in r else "-" for c in columns])
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = "  ".join(h.ljust(w) if i == 0 else h.rjust(w) for i, (h, w) in enumerate(zip(headers, widths)))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(x).ljust(w) if i == 0 else str(x).rjust(w)
                        for i, (x, w) in enumerate(zip(row, widths))))


def compare(current: Dict[str, Any], baseline: Dict[str, Any], threshold: float) -> int:
    """Prints a diff table; returns number of regressions beyond threshold (percent)."""
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
                if not better:
                    regressions += 1
            change_s = f"{change:+.1f}%" if abs(change) != float("inf") else ("+inf" if c > b else "-inf")
            print(f"{name:<40} {metric:<24} {_fmt(b):>14} {_fmt(c):>14} {change_s:>9}{flag}")
    print(f"\n{regressions} regression(s) beyond {threshold:.0f}%")
    return regressions


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-k", "--scenario", help="regex filter for scenario names")
    parser.add_argument("-g", "--group", action="append",
                        choices=["overhead", "concurrency", "resilience", "selection", "e2e"],
                        help="run only these groups (repeatable)")
    parser.add_argument("-n", "--requests", type=int, default=5000, help="operations per scenario")
    parser.add_argument("-r", "--repeat", type=int, default=3, help="repeats per scenario (median is reported)")
    parser.add_argument("--quick", action="store_true", help="fast smoke run (-n 300 -r 1)")
    parser.add_argument("--save", metavar="FILE", help="save results as JSON")
    parser.add_argument("--compare", metavar="FILE", help="compare with results saved by --save")
    parser.add_argument("--threshold", type=float, default=10.0,
                        help="regression threshold in percent for --compare (default 10)")
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
    results = run_scenarios(args.scenario, args.requests, args.repeat, args.group)
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
        if compare(results, baseline, args.threshold):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
