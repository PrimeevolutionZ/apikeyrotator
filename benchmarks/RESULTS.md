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

apikeyrotator **0.9.0** · CPython 3.12.3 · Linux-6.18.44-fc-v37-x86_64-with-glibc2.39 · 4 CPUs · 2026-09-24T14:08:05 · `-n 5000 -r 3`

| scenario | ops/s | p50 µs | p99 µs | CPU µs/op | success | calls/req | sleep s/1k | keys |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `overhead_sync_round_robin` | 103,353 | 8.73 | 28.22 | 9.94 | 1.00 | - | - | - |
| `overhead_sync_random` | 100,884 | 9.03 | 29.15 | 10.16 | 1.00 | - | - | - |
| `overhead_sync_weighted` | 98,530 | 9.19 | 29.07 | 10.40 | 1.00 | - | - | - |
| `overhead_sync_lru` | 83,068 | 11.04 | 32.38 | 12.30 | 1.00 | - | - | - |
| `overhead_sync_health_based` | 88,794 | 10.40 | 31.70 | 11.50 | 1.00 | - | - | - |
| `overhead_sync_middlewares` | 37,944 | 24.05 | 56.01 | 26.53 | 1.00 | - | - | - |
| `overhead_sync_all_features` | 65,484 | 13.90 | 41.02 | 15.49 | 1.00 | - | - | - |
| `overhead_sync_cache_hits` | 63,399 | 14.19 | 41.78 | 15.97 | 1.00 | 0.00 | - | - |
| `overhead_sync_unified` | 79,580 | 11.25 | 35.81 | 12.81 | 1.00 | - | - | - |
| `overhead_async_unified` | 43,795 | 14.91 | 41.44 | 22.89 | 1.00 | - | - | - |
| `overhead_async` | 51,774 | 12.72 | 34.75 | 19.79 | 1.00 | - | - | - |
| `concurrency_sync_16_threads` | 11,764 | 1,153 | 1,648 | 74.79 | - | - | - | - |
| `concurrency_async_200_tasks` | 38,992 | 3,595 | 12,459 | 26.12 | 1.00 | - | - | - |
| `resilience_rate_limit_10pct` | 63,531 | 11.51 | 66.82 | 16.05 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_rate_limit_hot_key` | 95,967 | 9.07 | 33.35 | 10.55 | 1.00 | 1.00 | 0.00 | 10 |
| `resilience_async_rate_limit_10pct` | 33,225 | 16.16 | 518.13 | 30.37 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_server_errors_5pct` | 82,526 | 9.53 | 46.15 | 12.41 | 1.00 | 1.05 | 57.45 | 10 |
| `resilience_client_errors_5pct` | 88,283 | 9.59 | 33.44 | 11.63 | 0.95 | 1.00 | 0.00 | 10 |
| `resilience_host_down` | 11,360 | 81.73 | 131.34 | 89.22 | 0.00 | 3.00 | 3,154 | 10 |
| `resilience_host_down_breaker` | 129,178 | 6.55 | 21.97 | 8.73 | 0.00 | 0.01 | 12.73 | 10 |
| `resilience_quota_reactive` | 72,747 | 9.97 | 58.04 | 14.35 | 1.00 | 1.09 | 541.00 | 10 |
| `resilience_quota_headers` | 58,305 | 15.41 | 61.24 | 17.75 | 1.00 | 1.01 | 540.00 | 10 |
| `resilience_quota_token_bucket` | 51,466 | 17.07 | 58.82 | 19.79 | 1.00 | 1.00 | 540.00 | 10 |
| `select_round_robin_10_keys` | 1,250,259 | 0.64 | 1.13 | 0.98 | - | - | - | - |
| `select_round_robin_1000_keys` | 1,195,234 | 0.70 | 1.18 | 1.21 | - | - | - | - |
| `select_random_10_keys` | 1,075,168 | 0.75 | 1.32 | 1.12 | - | - | - | - |
| `select_random_1000_keys` | 1,043,734 | 0.79 | 1.45 | 1.38 | - | - | - | - |
| `select_weighted_10_keys` | 1,000,938 | 0.82 | 1.52 | 1.19 | - | - | - | - |
| `select_weighted_1000_keys` | 841,694 | 0.98 | 2.00 | 1.60 | - | - | - | - |
| `select_lru_10_keys` | 485,033 | 1.42 | 2.27 | 1.87 | - | - | - | - |
| `select_lru_1000_keys` | 13,896 | 68.36 | 100.86 | 72.37 | - | - | - | - |
| `select_health_based_10_keys` | 677,182 | 1.29 | 1.78 | 1.68 | - | - | - | - |
| `select_health_based_1000_keys` | 14,450 | 65.17 | 115.03 | 69.18 | - | - | - | - |
| `e2e_sync_local_http` | 993.90 | 987.49 | 1,508 | 977.26 | 1.00 | - | - | - |
| `e2e_async_local_http` | 3,116 | 12,968 | 43,711 | 340.15 | 1.00 | - | - | - |

| scenario | B/key | growth B/1k req | peak KB | alloc KB/req | import ms | import MB |
|---|---:|---:|---:|---:|---:|---:|
| `resources_memory_per_key_round_robin` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_lru` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_health_based` | 229.60 | - | 4,551 | - | - | - |
| `resources_steady_state_sync` | - | 0.00 | 16.60 | 3.18 | - | - |
| `resources_steady_state_sync_middlewares` | - | 0.00 | 21.10 | 4.04 | - | - |
| `resources_steady_state_async` | - | 0.00 | 23.60 | 9.80 | - | - |
| `resources_import_cost` | - | - | - | - | 65.70 | 14.20 |
