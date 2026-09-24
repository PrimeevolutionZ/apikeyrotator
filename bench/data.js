window.BENCHMARK_DATA = {
  "lastUpdate": 1790255428859,
  "repoUrl": "https://github.com/PrimeevolutionZ/apikeyrotator",
  "entries": {
    "Throughput (higher is better)": [
      {
        "commit": {
          "author": {
            "email": "noreply@anthropic.com",
            "name": "Claude",
            "username": "claude"
          },
          "committer": {
            "email": "noreply@anthropic.com",
            "name": "Claude",
            "username": "claude"
          },
          "distinct": false,
          "id": "1443a6b0f58b8d310f5916bcbbca86d45d7e607a",
          "message": "release: 0.8.1; CI on tags, automated tag + GitHub release, Pages via Actions\n\n- Version 0.8.1; changelog section for the component refactor, lazy async\n  key loading and published benchmark results.\n- CI runs on tags too. After lint/docs/tests pass on master or a tag, the\n  new reusable Release workflow creates the tag for the pyproject version\n  (if missing) and a GitHub release with wheel, sdist and changelog notes.\n  It can also be run by hand for any commit; PyPI publishing is opt-in.\n- Benchmark history is deployed to GitHub Pages with GitHub Actions (data\n  kept in the gh-pages branch).\n- CONTRIBUTING: new release process.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01F6FRG9xUgZ3KxwroGa993w",
          "timestamp": "2026-09-24T13:09:49Z",
          "tree_id": "ef082e3fc79a012cb4a2af9bd11574d9f7f12ba2",
          "url": "https://github.com/PrimeevolutionZ/apikeyrotator/commit/1443a6b0f58b8d310f5916bcbbca86d45d7e607a"
        },
        "date": 1790255428158,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · ops_per_sec",
            "value": 103984.4,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · ops_per_sec",
            "value": 100775.9,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · ops_per_sec",
            "value": 101761.4,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · ops_per_sec",
            "value": 94978.6,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · ops_per_sec",
            "value": 93329.9,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · ops_per_sec",
            "value": 52300.5,
            "unit": "ops/s",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · ops_per_sec",
            "value": 82180.7,
            "unit": "ops/s",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · ops_per_sec",
            "value": 75856.1,
            "unit": "ops/s",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_async · ops_per_sec",
            "value": 64220.5,
            "unit": "ops/s",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "concurrency_sync_16_threads · ops_per_sec",
            "value": 14204.2,
            "unit": "ops/s",
            "extra": "16 threads, 1ms simulated upstream latency"
          },
          {
            "name": "concurrency_async_200_tasks · ops_per_sec",
            "value": 40939.2,
            "unit": "ops/s",
            "extra": "200 concurrent asyncio tasks, 1ms simulated upstream latency"
          },
          {
            "name": "resilience_rate_limit_10pct · ops_per_sec",
            "value": 77102.8,
            "unit": "ops/s",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · ops_per_sec",
            "value": 100997,
            "unit": "ops/s",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · ops_per_sec",
            "value": 48583.5,
            "unit": "ops/s",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · ops_per_sec",
            "value": 91818.1,
            "unit": "ops/s",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · ops_per_sec",
            "value": 97844.5,
            "unit": "ops/s",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · ops_per_sec",
            "value": 16487,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · ops_per_sec",
            "value": 128877.8,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · ops_per_sec",
            "value": 80499.3,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · ops_per_sec",
            "value": 72244.8,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · ops_per_sec",
            "value": 69649.7,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "select_round_robin_10_keys · ops_per_sec",
            "value": 1181979.5,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_round_robin_1000_keys · ops_per_sec",
            "value": 1074083.5,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_random_10_keys · ops_per_sec",
            "value": 996048.7,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_random_1000_keys · ops_per_sec",
            "value": 955274.4,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_weighted_10_keys · ops_per_sec",
            "value": 918466.5,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_weighted_1000_keys · ops_per_sec",
            "value": 791230.2,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_lru_10_keys · ops_per_sec",
            "value": 551115.1,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_lru_1000_keys · ops_per_sec",
            "value": 11447,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_health_based_10_keys · ops_per_sec",
            "value": 569255.1,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_health_based_1000_keys · ops_per_sec",
            "value": 12444.1,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "e2e_sync_local_http · ops_per_sec",
            "value": 1806.9,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · ops_per_sec",
            "value": 5018.3,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      }
    ]
  }
}