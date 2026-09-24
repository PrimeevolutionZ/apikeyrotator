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

apikeyrotator **0.8.0** · CPython 3.12.3 · Linux-6.18.44-fc-v37-x86_64-with-glibc2.39 · 4 CPUs · 2026-09-24T11:37:36 · `-n 5000 -r 3`

| scenario | ops/s | p50 µs | p99 µs | CPU µs/op | success | calls/req | sleep s/1k | keys |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `overhead_sync_round_robin` | 93,110 | 9.40 | 31.24 | 10.79 | 1.00 | - | - | - |
| `overhead_sync_random` | 96,559 | 9.42 | 28.08 | 10.59 | 1.00 | - | - | - |
| `overhead_sync_weighted` | 95,136 | 9.58 | 28.45 | 10.76 | 1.00 | - | - | - |
| `overhead_sync_lru` | 81,890 | 10.89 | 32.55 | 12.45 | 1.00 | - | - | - |
| `overhead_sync_health_based` | 85,675 | 10.49 | 32.08 | 11.90 | 1.00 | - | - | - |
| `overhead_sync_middlewares` | 32,044 | 26.77 | 70.51 | 31.27 | 1.00 | - | - | - |
| `overhead_sync_all_features` | 60,101 | 14.84 | 43.20 | 16.85 | 1.00 | - | - | - |
| `overhead_sync_cache_hits` | 59,330 | 15.09 | 42.95 | 17.07 | 1.00 | 0.00 | - | - |
| `overhead_async` | 45,496 | 13.97 | 38.80 | 22.29 | 1.00 | - | - | - |
| `concurrency_sync_16_threads` | 12,354 | 1,126 | 1,604 | 64.28 | - | - | - | - |
| `concurrency_async_200_tasks` | 35,768 | 3,951 | 11,376 | 28.36 | 1.00 | - | - | - |
| `resilience_rate_limit_10pct` | 61,842 | 11.58 | 70.83 | 16.48 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_rate_limit_hot_key` | 94,878 | 9.49 | 30.40 | 10.78 | 1.00 | 1.00 | 0.00 | 10 |
| `resilience_async_rate_limit_10pct` | 32,360 | 16.98 | 553.54 | 31.44 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_server_errors_5pct` | 75,592 | 10.24 | 51.10 | 13.51 | 1.00 | 1.05 | 57.45 | 10 |
| `resilience_client_errors_5pct` | 84,696 | 9.97 | 31.27 | 12.07 | 0.95 | 1.00 | 0.00 | 10 |
| `resilience_host_down` | 10,257 | 91.29 | 141.76 | 98.47 | 0.00 | 3.00 | 3,154 | 10 |
| `resilience_host_down_breaker` | 118,558 | 7.20 | 27.67 | 9.33 | 0.00 | 0.01 | 12.73 | 10 |
| `resilience_quota_reactive` | 70,517 | 9.93 | 52.41 | 14.67 | 1.00 | 1.09 | 541.00 | 10 |
| `resilience_quota_headers` | 55,350 | 16.27 | 60.28 | 18.53 | 1.00 | 1.01 | 540.00 | 10 |
| `resilience_quota_token_bucket` | 51,870 | 17.53 | 44.28 | 19.81 | 1.00 | 1.00 | 540.00 | 10 |
| `select_round_robin_10_keys` | 1,091,115 | 0.75 | 1.42 | 1.11 | - | - | - | - |
| `select_round_robin_1000_keys` | 1,023,940 | 0.82 | 1.63 | 1.37 | - | - | - | - |
| `select_random_10_keys` | 986,817 | 0.85 | 1.49 | 1.20 | - | - | - | - |
| `select_random_1000_keys` | 938,058 | 0.87 | 2.23 | 1.45 | - | - | - | - |
| `select_weighted_10_keys` | 877,540 | 0.96 | 1.86 | 1.32 | - | - | - | - |
| `select_weighted_1000_keys` | 818,742 | 1.06 | 1.93 | 1.61 | - | - | - | - |
| `select_lru_10_keys` | 553,316 | 1.59 | 2.95 | 1.99 | - | - | - | - |
| `select_lru_1000_keys` | 12,118 | 78.31 | 120.48 | 82.52 | - | - | - | - |
| `select_health_based_10_keys` | 588,254 | 1.48 | 3.19 | 1.89 | - | - | - | - |
| `select_health_based_1000_keys` | 12,690 | 74.10 | 120.28 | 79.20 | - | - | - | - |
| `e2e_sync_local_http` | 1,265 | 752.33 | 1,341 | 787.98 | 1.00 | - | - | - |
| `e2e_async_local_http` | 3,336 | 12,256 | 27,612 | 318.39 | 1.00 | - | - | - |

| scenario | B/key | growth B/1k req | peak KB | alloc KB/req | import ms | import MB |
|---|---:|---:|---:|---:|---:|---:|
| `resources_memory_per_key_round_robin` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_lru` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_health_based` | 229.60 | - | 4,551 | - | - | - |
| `resources_steady_state_sync` | - | 0.00 | 16.40 | 3.05 | - | - |
| `resources_steady_state_sync_middlewares` | - | 0.00 | 20.90 | 3.92 | - | - |
| `resources_steady_state_async` | - | 0.00 | 23.30 | 9.54 | - | - |
| `resources_import_cost` | - | - | - | - | 67.60 | 13.90 |
