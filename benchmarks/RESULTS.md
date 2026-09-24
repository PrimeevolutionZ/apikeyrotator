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

apikeyrotator **0.8.1** · CPython 3.12.3 · Linux-6.18.44-fc-v37-x86_64-with-glibc2.39 · 4 CPUs · 2026-09-24T13:08:40 · `-n 5000 -r 3`

| scenario | ops/s | p50 µs | p99 µs | CPU µs/op | success | calls/req | sleep s/1k | keys |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `overhead_sync_round_robin` | 108,706 | 8.26 | 25.49 | 9.45 | 1.00 | - | - | - |
| `overhead_sync_random` | 106,495 | 8.45 | 26.28 | 9.65 | 1.00 | - | - | - |
| `overhead_sync_weighted` | 104,709 | 8.64 | 27.77 | 9.80 | 1.00 | - | - | - |
| `overhead_sync_lru` | 92,335 | 9.92 | 30.92 | 11.10 | 1.00 | - | - | - |
| `overhead_sync_health_based` | 93,387 | 9.60 | 30.40 | 10.91 | 1.00 | - | - | - |
| `overhead_sync_middlewares` | 39,848 | 22.90 | 53.48 | 25.31 | 1.00 | - | - | - |
| `overhead_sync_all_features` | 71,693 | 12.59 | 36.65 | 14.08 | 1.00 | - | - | - |
| `overhead_sync_cache_hits` | 68,193 | 13.23 | 38.46 | 14.98 | 1.00 | 0.00 | - | - |
| `overhead_async` | 46,002 | 11.82 | 65.43 | 20.97 | 1.00 | - | - | - |
| `concurrency_sync_16_threads` | 9,816 | 1,262 | 2,703 | 98.68 | - | - | - | - |
| `concurrency_async_200_tasks` | 38,796 | 3,606 | 11,423 | 25.96 | 1.00 | - | - | - |
| `resilience_rate_limit_10pct` | 65,976 | 10.46 | 66.40 | 15.32 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_rate_limit_hot_key` | 98,983 | 8.54 | 31.73 | 10.38 | 1.00 | 1.00 | 0.00 | 10 |
| `resilience_async_rate_limit_10pct` | 36,125 | 14.90 | 482.57 | 28.30 | 1.00 | 1.10 | 12.20 | 10 |
| `resilience_server_errors_5pct` | 86,840 | 8.98 | 44.79 | 11.79 | 1.00 | 1.05 | 57.45 | 10 |
| `resilience_client_errors_5pct` | 95,572 | 8.89 | 30.17 | 10.71 | 0.95 | 1.00 | 0.00 | 10 |
| `resilience_host_down` | 11,790 | 78.65 | 152.52 | 85.86 | 0.00 | 3.00 | 3,154 | 10 |
| `resilience_host_down_breaker` | 132,991 | 6.42 | 26.76 | 8.41 | 0.00 | 0.01 | 12.73 | 10 |
| `resilience_quota_reactive` | 76,535 | 9.09 | 116.03 | 13.47 | 1.00 | 1.09 | 541.00 | 10 |
| `resilience_quota_headers` | 62,600 | 14.30 | 55.70 | 16.62 | 1.00 | 1.01 | 540.00 | 10 |
| `resilience_quota_token_bucket` | 59,772 | 15.39 | 42.67 | 17.38 | 1.00 | 1.00 | 540.00 | 10 |
| `select_round_robin_10_keys` | 1,271,547 | 0.64 | 1.08 | 0.97 | - | - | - | - |
| `select_round_robin_1000_keys` | 1,183,646 | 0.71 | 1.21 | 1.21 | - | - | - | - |
| `select_random_10_keys` | 1,102,629 | 0.75 | 1.23 | 1.08 | - | - | - | - |
| `select_random_1000_keys` | 1,083,828 | 0.77 | 1.26 | 1.28 | - | - | - | - |
| `select_weighted_10_keys` | 1,046,491 | 0.80 | 1.22 | 1.14 | - | - | - | - |
| `select_weighted_1000_keys` | 894,610 | 0.96 | 1.56 | 1.55 | - | - | - | - |
| `select_lru_10_keys` | 631,171 | 1.40 | 2.29 | 1.81 | - | - | - | - |
| `select_lru_1000_keys` | 13,508 | 70.11 | 103.86 | 73.78 | - | - | - | - |
| `select_health_based_10_keys` | 670,029 | 1.29 | 2.25 | 1.68 | - | - | - | - |
| `select_health_based_1000_keys` | 14,530 | 64.80 | 108.17 | 69.26 | - | - | - | - |
| `e2e_sync_local_http` | 1,011 | 912.92 | 2,072 | 943.46 | 1.00 | - | - | - |
| `e2e_async_local_http` | 3,234 | 13,247 | 31,802 | 333.87 | 1.00 | - | - | - |

| scenario | B/key | growth B/1k req | peak KB | alloc KB/req | import ms | import MB |
|---|---:|---:|---:|---:|---:|---:|
| `resources_memory_per_key_round_robin` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_lru` | 229.60 | - | 2,473 | - | - | - |
| `resources_memory_per_key_health_based` | 229.60 | - | 4,551 | - | - | - |
| `resources_steady_state_sync` | - | 0.00 | 16.40 | 3.05 | - | - |
| `resources_steady_state_sync_middlewares` | - | 0.00 | 20.90 | 3.92 | - | - |
| `resources_steady_state_async` | - | 0.00 | 23.60 | 9.80 | - | - |
| `resources_import_cost` | - | - | - | - | 62.80 | 14.00 |
