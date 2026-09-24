# Benchmarks

`bench_core.py` measures the rotator core in real numbers, so every change to the
core can be checked: **did it get faster / more resilient, or worse?**

```bash
python benchmarks/bench_core.py --list                  # list scenarios
python benchmarks/bench_core.py --quick                 # ~10s smoke run
python benchmarks/bench_core.py                         # full run (median of 3)
python benchmarks/bench_core.py -g resilience           # one group
python benchmarks/bench_core.py -k "select_.*_1000"     # regex filter
```

## Workflow: compare before/after a change

```bash
# 1. On the current code - save a baseline
python benchmarks/bench_core.py --save benchmarks/results/before.json

# 2. Change the core, then compare
python benchmarks/bench_core.py --compare benchmarks/results/before.json --threshold 10
```

`--compare` prints every metric that changed, marks changes above the threshold as
`better` / `WORSE` and exits with code `1` if there are regressions — so it can be
used in CI. `benchmarks/results/` is git-ignored: overhead numbers depend on the
machine, so compare runs made on the same machine.

## Scenario groups

| Group         | What is measured                                                                                      |
|---------------|-------------------------------------------------------------------------------------------------------|
| `overhead`    | Cost of the rotator itself per request (transport stubbed): strategies, middlewares, cache hits, async |
| `concurrency` | Throughput with 16 threads / 200 asyncio tasks (1 ms simulated upstream latency)                       |
| `resilience`  | Behaviour under failures: 10% 429s, a permanently rate-limited key, 5% 503s, 5% 404s                   |
| `selection`   | `strategy.get_next_key()` alone with 10 and 1000 keys                                                  |
| `e2e`         | Real HTTP round-trips to a local aiohttp server (sync and async)                                       |

Resilience scenarios use a **virtual clock**: `time.sleep`/`asyncio.sleep` return
instantly but advance `time.time()`, so `Retry-After` windows expire exactly as in
real time and the benchmark reports how long the rotator *would* have slept.

## Metrics

| Metric                    | Meaning                                          | Better |
|---------------------------|--------------------------------------------------|--------|
| `ops_per_sec`             | Throughput                                       | higher |
| `p50_us` / `p99_us`       | Latency percentiles per operation, microseconds  | lower  |
| `success_rate`            | Share of requests that ended with a 2xx/3xx      | higher |
| `upstream_calls_per_req`  | HTTP calls sent upstream per user request        | lower  |
| `sleep_s_per_1k_req`      | Seconds spent waiting (backoff) per 1000 requests | lower  |
| `keys_left`               | Keys still in rotation after the scenario        | higher |

## Reference: 0.6.1 → 0.7.0

Measured on the same machine (Python 3.11, 4 CPUs, `-n 3000 -r 3`):

| Scenario                               | 0.6.1                  | 0.7.0                    |
|----------------------------------------|------------------------|--------------------------|
| `overhead_sync_round_robin`            | 63.9k ops/s            | 86.5k ops/s (+35%)       |
| `overhead_sync_lru`                    | 51.1k ops/s            | 73.9k ops/s (+45%)       |
| `overhead_sync_weighted`               | crashes (ValueError)   | works                    |
| `overhead_sync_middlewares`            | hangs (60 s per request) | ~28k ops/s             |
| `resilience_rate_limit_10pct` sleep    | 119.6 s / 1k req       | 11.0 s / 1k req (−91%)   |
| `resilience_rate_limit_hot_key` sleep  | 1.05 s / 1k req        | 0 s                      |
| `resilience_client_errors_5pct`        | success 4%, 0 keys left | success 95%, 10 keys left |
| `select_round_robin_1000_keys`         | 7.9k ops/s             | 1.1M ops/s               |
| `select_weighted_1000_keys`            | 4.8k ops/s             | 887k ops/s               |
| `select_lru_1000_keys`                 | 3.6k ops/s             | 9.0k ops/s               |

Note: in `resilience_client_errors_5pct` 0.6.1 looks "faster" only because it had
destroyed the whole key pool and failed instantly — always read throughput together
with `success_rate` and `keys_left`.
