# Benchmarks

`bench_core.py` measures the rotator core in real numbers - speed, CPU, memory and
behaviour under failures - so every change to the core can be checked:
**did it get faster / leaner / more resilient, or worse?**

```bash
python benchmarks/bench_core.py --list                  # list scenarios
python benchmarks/bench_core.py --quick                 # fast smoke run
python benchmarks/bench_core.py                         # full run (best of 3)
python benchmarks/bench_core.py -g resources            # one group
python benchmarks/bench_core.py -k "select_.*_1000"     # regex filter
python benchmarks/bench_core.py --markdown out.md        # Markdown report
```

## Published results

- **[RESULTS.md](RESULTS.md)** - the latest reference run (all scenarios, one machine).
- **History charts**: every push to `master` that touches the library runs the benchmark
  (`.github/workflows/benchmark.yml`) and appends the results to the `gh-pages` branch -
  <https://primeevolutionz.github.io/apikeyrotator/bench/> (one chart per scenario and metric,
  one point per commit). A drop beyond the alert threshold is commented on the commit.
- **Every CI run** (push and PR) has the results table in its job summary; PRs also show the
  comparison with the base branch.

Throughput numbers from shared GitHub runners are noisy (±10-20%); upstream calls,
waiting time, success rate and memory are deterministic and comparable across runs.
`--export-github PREFIX` writes the chart data (`PREFIX-bigger.json`, `PREFIX-smaller.json`)
in the format of [github-action-benchmark](https://github.com/benchmark-action/github-action-benchmark).

## Workflow: compare before/after a change

```bash
# 1. On the current code - save a baseline
python benchmarks/bench_core.py --save benchmarks/results/before.json

# 2. Change the core, then compare
python benchmarks/bench_core.py --compare benchmarks/results/before.json --threshold 10
```

`--compare` prints every metric that changed, marks changes above the threshold as
`better` / `WORSE` and exits with code `1` if there are regressions.

- `--gate deterministic` counts only machine-independent metrics as regressions
  (upstream calls, sleep time, success rate, keys left, memory per key, memory growth);
  throughput changes are still printed. CI uses this on shared runners.
- `--scenario-timeout 120` aborts a scenario that hangs (e.g. an old version) and reports it
  as an error instead of blocking the run.
- `benchmarks/results/` is git-ignored: speed numbers depend on the machine, so compare runs
  made on the same machine, ideally back-to-back.

**Comparing two versions**: copy the *same* `bench_core.py` into a worktree of the other
version and run it there - the script imports the library next to it:

```bash
git worktree add ../base origin/main
cp benchmarks/bench_core.py ../base/benchmarks/
(cd ../base && python benchmarks/bench_core.py --save /tmp/base.json)
python benchmarks/bench_core.py --compare /tmp/base.json
```

This is exactly what the `benchmark` job in `.github/workflows/ci.yml` does for every PR.

## Scenario groups

| Group         | What is measured                                                                                       |
|---------------|--------------------------------------------------------------------------------------------------------|
| `overhead`    | Cost of the rotator itself per request (transport stubbed): strategies, middlewares, cache hits, async, all resilience features on |
| `concurrency` | Throughput with 16 threads / 200 asyncio tasks (1 ms simulated upstream latency)                        |
| `resilience`  | Behaviour under failures: 429s, a permanently limited key, 503s, 404s, a dead host (with/without circuit breaker), per-key quotas (reactive / header hints / token bucket) |
| `selection`   | `strategy.get_next_key()` alone with 10 and 1000 keys                                                   |
| `resources`   | Memory per key (10k keys), memory growth per 1000 requests (leak check), transient allocations per request, import time and RSS |
| `e2e`         | Real HTTP round-trips to a local aiohttp server (sync and async)                                        |

Resilience scenarios use a **virtual clock**: `time.sleep`/`asyncio.sleep` return instantly
but advance `time.time()`, so `Retry-After` windows, token buckets and circuit breaker
timeouts expire exactly as in real time, and the benchmark reports how long the rotator
*would* have waited. The clock starts at a fixed, minute-aligned epoch and moves only on
sleeps, so these metrics are identical on every run and every machine.

Speed numbers are the **best of N repeats** (like `timeit`): interference from other
processes only slows a run down, so the fastest repeat is the least noisy estimate.

## Metrics

| Metric                        | Meaning                                                   | Better |
|-------------------------------|-----------------------------------------------------------|--------|
| `ops_per_sec`                 | Throughput                                                | higher |
| `p50_us` / `p99_us`           | Latency percentiles per operation, microseconds           | lower  |
| `cpu_us_per_op`               | Process CPU time per operation, microseconds              | lower  |
| `success_rate`                | Share of requests that ended with a 2xx/3xx               | higher |
| `upstream_calls_per_req`      | HTTP calls sent upstream per user request                 | lower  |
| `sleep_s_per_1k_req`          | Seconds spent waiting (backoff) per 1000 requests         | lower  |
| `keys_left`                   | Keys still in rotation after the scenario                 | higher |
| `mem_bytes_per_key`           | Memory retained per API key (tracemalloc)                 | lower  |
| `mem_growth_bytes_per_1k_req` | Memory growth after warm-up; > 0 means a leak (< 1 KB total is reported as 0) | lower |
| `alloc_kb_per_req`            | Peak transient allocations of one request                 | lower  |
| `import_ms` / `import_rss_mb` | Cost of `import apikeyrotator` in a fresh interpreter     | lower  |

## Reference: 0.7.0 → 0.8.0

Same machine (Python 3.12, 4 CPUs), back-to-back runs, `-n 4000 -r 7`.

**Resources**

| Metric | 0.7.0 | 0.8.0 |
|---|---|---|
| Memory per key, round-robin | 374 B | **230 B** (−38%) |
| Memory per key, LRU / health-based | 730 B | **230 B** (−69%) |
| Transient allocations per sync request | 2.96 KB | 3.05 KB (+3%)³ |
| `import apikeyrotator` time | 245 ms | **69 ms** (−72%) |
| `import apikeyrotator` RSS | 33.5 MB | **13.8 MB** (−59%) |
| Memory growth per 1k requests (leak check) | 0 | 0 |

**Speed** (stubbed transport, ops/s)

| Scenario | 0.7.0 | 0.8.0 |
|---|---|---|
| `overhead_sync_round_robin` | 91.5k | 98.9k (+8%) |
| `overhead_sync_lru` | 76.7k | 82.8k (+8%) |
| `concurrency_async_200_tasks` | 35.2k | 38.4k (+9%) |
| `select_lru_1000_keys` | 10.5k | 12.2k (+17%) |
| `select_random_1000_keys` | 880k | 962k (+9%) |
| `overhead_sync_middlewares` | 39.3k | 35.2k (−11%)¹ |
| `overhead_async` | 51.1k | 48.8k (−4%)² |

¹ The rotator now reads `X-RateLimit-Remaining` on every success (proactive rate limiting),
and `RateLimitMiddleware` reads the same headers again - about 2.6 µs per request.
² Extra transport layer (pluggable aiohttp/httpx backends), about 0.8 µs per request.
³ The request loop is shared by the sync and async rotators and runs as a generator
(`apikeyrotator/core/engine.py`); its frame lives on the heap for the duration of a request
(~0.5 KB, freed afterwards - memory growth stays 0).

**New resilience features** (virtual clock)

| Scenario | Upstream calls / request | Waiting per 1k requests |
|---|---|---|
| Host answers 503 to everything, no breaker | 3.00 | 3154 s |
| Same, `circuit_breaker=True` | **0.01** | **13 s** |
| 10 keys × 10 req/min quota, reacting to 429 only | 1.09 | 541 s |
| Same, `X-RateLimit-Remaining` hints (default) | **1.01** | 540 s |
| Same, `key_rate_limit=(10, 60)` token bucket | **1.00** (no 429s) | 540 s |

With 200 requests against 100 requests/minute of total quota, every variant has to wait the
same ~540 s per 1000 requests; the difference is how many requests are wasted on 429s.

## Reference: 0.6.1 → 0.7.0

Python 3.11, `-n 3000 -r 3`:

| Scenario                               | 0.6.1                  | 0.7.0                    |
|----------------------------------------|------------------------|--------------------------|
| `overhead_sync_round_robin`            | 63.9k ops/s            | 86.5k ops/s (+35%)       |
| `overhead_sync_weighted`               | crashes (ValueError)   | works                    |
| `overhead_sync_middlewares`            | hangs (60 s per request) | ~28k ops/s             |
| `resilience_rate_limit_10pct` sleep    | 119.6 s / 1k req       | 11.0 s / 1k req (−91%)   |
| `resilience_client_errors_5pct`        | success 4%, 0 keys left | success 95%, 10 keys left |
| `select_round_robin_1000_keys`         | 7.9k ops/s             | 1.1M ops/s               |

Note: in `resilience_client_errors_5pct` 0.6.1 looks "faster" only because it had
destroyed the whole key pool and failed instantly — always read throughput together
with `success_rate` and `keys_left`.
