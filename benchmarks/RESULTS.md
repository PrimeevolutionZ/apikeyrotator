# Benchmark results

Reference run of [`bench_core.py`](bench_core.py) - what each scenario measures is described
in the [benchmark docs](README.md#scenario-groups). Results of every change on `master` are
published as **[history charts](https://primeevolutionz.github.io/apikeyrotator/bench/)** and
in the job summary of each CI run.

How to read the numbers:

- **ops/s, p50/p99, CPU µs/op** depend on the machine - compare runs made on the same machine.
  The transport is stubbed in `overhead`, `concurrency`, `resilience` and `selection`, so these
  show the cost of the rotator itself; `e2e` makes real HTTP requests to a local server.
- **success, calls/req, sleep s/1k, keys** come from a virtual clock and are identical on every
  run and machine: how many upstream calls a user request costs and how long the rotator waits.
- **B/key, growth, alloc KB/req** are measured with `tracemalloc`; growth 0 means no leak.

Reproduce: `python benchmarks/bench_core.py --markdown results.md` - the tables below are
exactly that output.

apikeyrotator **0.8.2** · CPython 3.12.3 · Linux-6.18.44-fc-v37-x86_64-with-glibc2.39 · 4 CPUs · 2026-09-24T13:26:49 · `-n 5000 -r 3`

| scenario | ops/s | p50 µs | p99 µs | CPU µs/op | success | calls/req | sleep s/1k | keys |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `overhead_sync_round_robin` | 100,043 | 9.00 | 30.30 | 10.27 | 1.00 | - | - | - |
| `overhead_sync_random` | 97,132 | 9.29 | 29.12 | 10.57 | 1.00 | - | - | - |
| `overhead_sync_weighted` | 94,097 | 9.34 | 32.12 | 10.73 | 1.00 | - | - | - |
| `overhead_sync_lru` | 85,314 | 10.87 | 31.22 | 11.95 | 1.00 | - | - | - |
| `overhead_sync_health_based` | 88,187 | 10.26 | 31.28 | 11.60 | 1.00 | - | - | - |
| `overhead_sync_middlewares` | 37,783 | 24.00 | 56.15 | 26.75 | 1.00 | - | - | - |
| `overhead_sync_all_features` | 65,276 | 14.05 | 39.99 | 15.58 | 1.00 | - | - | - |
| `overhead_sync_cache_hits` | 62,019 | 13.66 | 44.70 | 16.48 | 1.00 | 0.00 | - | - |
| `overhead_async` | 48,542 | 12.85 | 38.97 | 20.84 | 1.00 | - | - | - |
| `concurrency_sync_16_threads` | 11,772 | 1,144 | 2,068 | 76.88 | - | - | - | - |
| `concurrency_async_200_tasks` | 36,836 | 3,834 | 12,177 | 27.55 | 1.00 | - | - | - |
| `resilience_rate_limit_10pct` | 62,341 | 11.54 | 68.38 | 16.23 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_rate_limit_hot_key` | 96,964 | 9.23 | 30.85 | 10.59 | 1.00 | 1.00 | 0.00 | 10 |
| `resilience_async_rate_limit_10pct` | 33,123 | 15.49 | 514.96 | 30.41 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_server_errors_5pct` | 77,101 | 10.10 | 52.62 | 13.22 | 1.00 | 1.05 | 57.45 | 10 |
| `resilience_client_errors_5pct` | 86,920 | 9.79 | 33.75 | 11.81 | 0.95 | 1.00 | 0.00 | 10 |
| `resilience_host_down` | 11,679 | 81.19 | 126.06 | 86.85 | 0.00 | 3.00 | 3,154 | 10 |
| `resilience_host_down_breaker` | 132,126 | 6.51 | 19.53 | 8.79 | 0.00 | 0.01 | 12.73 | 10 |
| `resilience_quota_reactive` | 76,903 | 9.40 | 59.74 | 13.56 | 1.00 | 1.09 | 541.00 | 10 |
| `resilience_quota_headers` | 59,106 | 15.28 | 59.68 | 17.57 | 1.00 | 1.01 | 540.00 | 10 |
| `resilience_quota_token_bucket` | 56,506 | 16.29 | 43.20 | 18.22 | 1.00 | 1.00 | 540.00 | 10 |
| `select_round_robin_10_keys` | 1,258,493 | 0.64 | 1.04 | 0.97 | - | - | - | - |
| `select_round_robin_1000_keys` | 1,180,028 | 0.70 | 1.21 | 1.21 | - | - | - | - |
| `select_random_10_keys` | 1,123,436 | 0.75 | 1.15 | 1.07 | - | - | - | - |
| `select_random_1000_keys` | 1,065,307 | 0.78 | 1.26 | 1.31 | - | - | - | - |
| `select_weighted_10_keys` | 1,024,466 | 0.81 | 1.48 | 1.16 | - | - | - | - |
| `select_weighted_1000_keys` | 874,353 | 0.97 | 1.73 | 1.54 | - | - | - | - |
| `select_lru_10_keys` | 620,204 | 1.40 | 2.29 | 1.82 | - | - | - | - |
| `select_lru_1000_keys` | 13,691 | 68.85 | 119.58 | 73.29 | - | - | - | - |
| `select_health_based_10_keys` | 672,381 | 1.28 | 2.12 | 1.69 | - | - | - | - |
| `select_health_based_1000_keys` | 14,665 | 64.07 | 105.38 | 68.50 | - | - | - | - |
| `e2e_sync_local_http` | 965.20 | 993.02 | 2,052 | 992.36 | 1.00 | - | - | - |
| `e2e_async_local_http` | 2,942 | 14,335 | 42,813 | 355.16 | 1.00 | - | - | - |

| scenario | B/key | growth B/1k req | peak KB | alloc KB/req | import ms | import MB |
|---|---:|---:|---:|---:|---:|---:|
| `resources_memory_per_key_round_robin` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_lru` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_health_based` | 229.60 | - | 4,551 | - | - | - |
| `resources_steady_state_sync` | - | 0.00 | 16.50 | 3.06 | - | - |
| `resources_steady_state_sync_middlewares` | - | 0.00 | 20.90 | 3.93 | - | - |
| `resources_steady_state_async` | - | 0.00 | 23.30 | 9.55 | - | - |
| `resources_import_cost` | - | - | - | - | 66.50 | 13.90 |
