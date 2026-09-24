window.BENCHMARK_DATA = {
  "lastUpdate": 1790257480069,
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
      },
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
          "id": "da1660fa88fc6180b2f64a4efbc706d3d7e2f35a",
          "message": "release: 0.8.2 - explicit auth, safe key rejection, no implicit file reads, no emoji\n\n- auth= (\"bearer\", \"x-api-key\", (header, template), False); the default for\n  non-32-character keys is now Bearer instead of the non-standard \"Key\".\n- Until a request has been accepted, 401/403 no longer removes keys: the\n  other keys are tried and AuthenticationError shows the header that was\n  sent. Keys rejected earlier are removed once a request succeeds.\n- load_env_file=False and config_file=None by default; load_env_file=True\n  now finds the application's .env (it searched from the library's dir).\n- should_retry_callback gets the response in both rotators; the async\n  chain runs *_sync hooks of duck-typed middlewares; APIKeyRotator warns\n  about async-only middlewares.\n- No emoji in logs, errors or docs. Benchmark history uses -n 5000.\n- Release workflow accepts ref/latest inputs; one-off workflow backfills\n  the 0.8.0 tag and release.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01F6FRG9xUgZ3KxwroGa993w",
          "timestamp": "2026-09-24T13:27:47Z",
          "tree_id": "f5bc5bd9a4915964d6ff550eaeb8f1cf1c83f0f2",
          "url": "https://github.com/PrimeevolutionZ/apikeyrotator/commit/da1660fa88fc6180b2f64a4efbc706d3d7e2f35a"
        },
        "date": 1790256524251,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · ops_per_sec",
            "value": 76768,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · ops_per_sec",
            "value": 75129,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · ops_per_sec",
            "value": 74298.2,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · ops_per_sec",
            "value": 69972,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · ops_per_sec",
            "value": 69644.6,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · ops_per_sec",
            "value": 39905.8,
            "unit": "ops/s",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · ops_per_sec",
            "value": 62249.3,
            "unit": "ops/s",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · ops_per_sec",
            "value": 58480.2,
            "unit": "ops/s",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_async · ops_per_sec",
            "value": 48746.4,
            "unit": "ops/s",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "concurrency_sync_16_threads · ops_per_sec",
            "value": 14130.5,
            "unit": "ops/s",
            "extra": "16 threads, 1ms simulated upstream latency"
          },
          {
            "name": "concurrency_async_200_tasks · ops_per_sec",
            "value": 30058.9,
            "unit": "ops/s",
            "extra": "200 concurrent asyncio tasks, 1ms simulated upstream latency"
          },
          {
            "name": "resilience_rate_limit_10pct · ops_per_sec",
            "value": 59660.6,
            "unit": "ops/s",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · ops_per_sec",
            "value": 75983.8,
            "unit": "ops/s",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · ops_per_sec",
            "value": 35516.3,
            "unit": "ops/s",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · ops_per_sec",
            "value": 68595.7,
            "unit": "ops/s",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · ops_per_sec",
            "value": 73527.1,
            "unit": "ops/s",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · ops_per_sec",
            "value": 12543.2,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · ops_per_sec",
            "value": 101294.8,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · ops_per_sec",
            "value": 60565.4,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · ops_per_sec",
            "value": 54381.1,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · ops_per_sec",
            "value": 52839.8,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "select_round_robin_10_keys · ops_per_sec",
            "value": 902922.1,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_round_robin_1000_keys · ops_per_sec",
            "value": 822123.7,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_random_10_keys · ops_per_sec",
            "value": 759854.9,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_random_1000_keys · ops_per_sec",
            "value": 728831.7,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_weighted_10_keys · ops_per_sec",
            "value": 693901.9,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_weighted_1000_keys · ops_per_sec",
            "value": 607953.6,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_lru_10_keys · ops_per_sec",
            "value": 422019.3,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_lru_1000_keys · ops_per_sec",
            "value": 8788.3,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_health_based_10_keys · ops_per_sec",
            "value": 437774.7,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_health_based_1000_keys · ops_per_sec",
            "value": 9548.5,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "e2e_sync_local_http · ops_per_sec",
            "value": 1359.7,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · ops_per_sec",
            "value": 3467.4,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      },
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
          "id": "bfa53885e209c46d0237c9c40117a242fa4b0456",
          "message": "ci: drop the 0.8.0 tag backfill, move actions to Node 24 versions\n\nGitHub rejects tags created by the workflow token on commits whose workflow\nfiles differ from the current ones, so 0.8.0 cannot be tagged from CI; the\none-off backfill workflow is removed. checkout@v5, setup-python@v6,\nupload/download-artifact@v5 replace the deprecated Node 20 versions.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01F6FRG9xUgZ3KxwroGa993w",
          "timestamp": "2026-09-24T13:30:35Z",
          "tree_id": "73c07d4c1a59d236b67156692c1b94f81454654c",
          "url": "https://github.com/PrimeevolutionZ/apikeyrotator/commit/bfa53885e209c46d0237c9c40117a242fa4b0456"
        },
        "date": 1790256699495,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · ops_per_sec",
            "value": 88905.6,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · ops_per_sec",
            "value": 86703.1,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · ops_per_sec",
            "value": 89104.6,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · ops_per_sec",
            "value": 79074.1,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · ops_per_sec",
            "value": 80664.8,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · ops_per_sec",
            "value": 34197.8,
            "unit": "ops/s",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · ops_per_sec",
            "value": 63405.8,
            "unit": "ops/s",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · ops_per_sec",
            "value": 65965.5,
            "unit": "ops/s",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_async · ops_per_sec",
            "value": 47740.8,
            "unit": "ops/s",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "concurrency_sync_16_threads · ops_per_sec",
            "value": 13824.8,
            "unit": "ops/s",
            "extra": "16 threads, 1ms simulated upstream latency"
          },
          {
            "name": "concurrency_async_200_tasks · ops_per_sec",
            "value": 35487.8,
            "unit": "ops/s",
            "extra": "200 concurrent asyncio tasks, 1ms simulated upstream latency"
          },
          {
            "name": "resilience_rate_limit_10pct · ops_per_sec",
            "value": 57253.8,
            "unit": "ops/s",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · ops_per_sec",
            "value": 89444.6,
            "unit": "ops/s",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · ops_per_sec",
            "value": 32172.7,
            "unit": "ops/s",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · ops_per_sec",
            "value": 72648,
            "unit": "ops/s",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · ops_per_sec",
            "value": 80346.9,
            "unit": "ops/s",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · ops_per_sec",
            "value": 10627.6,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · ops_per_sec",
            "value": 116408.3,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · ops_per_sec",
            "value": 66269.1,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · ops_per_sec",
            "value": 53902.6,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · ops_per_sec",
            "value": 51299.5,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "select_round_robin_10_keys · ops_per_sec",
            "value": 1043924.6,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_round_robin_1000_keys · ops_per_sec",
            "value": 956532.3,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_random_10_keys · ops_per_sec",
            "value": 878295.8,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_random_1000_keys · ops_per_sec",
            "value": 840269.1,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_weighted_10_keys · ops_per_sec",
            "value": 807075,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_weighted_1000_keys · ops_per_sec",
            "value": 709887.8,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_lru_10_keys · ops_per_sec",
            "value": 525112.8,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_lru_1000_keys · ops_per_sec",
            "value": 12635.6,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_health_based_10_keys · ops_per_sec",
            "value": 536646.7,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_health_based_1000_keys · ops_per_sec",
            "value": 13222.6,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "e2e_sync_local_http · ops_per_sec",
            "value": 1400.2,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · ops_per_sec",
            "value": 4519.6,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      },
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
          "id": "6abeed4a3176b2fc4f9ba0f7b560b2805df1a4e8",
          "message": "feat: unified_response - one response type for requests, httpx and aiohttp\n\nWith unified_response=True every rotator and backend returns UnifiedResponse:\nstatus_code, case-insensitive Headers (get_list for repeated headers),\ncontent/text/json() without await, ok, reason, url, elapsed,\nraise_for_status() and the client's object as .native. The body is read in\nthe engine (so the connection is back in the pool), and the same object is\nused for AllKeysExhaustedError.last_response, cache hits and\nshould_retry_callback. Construction is lazy (~2-3 us per request); off by\ndefault. Adds HTTPStatusError.response and benchmark scenarios\noverhead_sync_unified / overhead_async_unified.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01F6FRG9xUgZ3KxwroGa993w",
          "timestamp": "2026-09-24T13:43:45Z",
          "tree_id": "59f2f461deb295d5d09dc80ebacea11eb7bbbefc",
          "url": "https://github.com/PrimeevolutionZ/apikeyrotator/commit/6abeed4a3176b2fc4f9ba0f7b560b2805df1a4e8"
        },
        "date": 1790257476681,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · ops_per_sec",
            "value": 57286.1,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · ops_per_sec",
            "value": 57275.6,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · ops_per_sec",
            "value": 55692.2,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · ops_per_sec",
            "value": 52665.3,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · ops_per_sec",
            "value": 53215.9,
            "unit": "ops/s",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · ops_per_sec",
            "value": 27207.4,
            "unit": "ops/s",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · ops_per_sec",
            "value": 43183.8,
            "unit": "ops/s",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · ops_per_sec",
            "value": 41715,
            "unit": "ops/s",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_sync_unified · ops_per_sec",
            "value": 51097.5,
            "unit": "ops/s",
            "extra": "Sync overhead with unified_response=True"
          },
          {
            "name": "overhead_async_unified · ops_per_sec",
            "value": 31482.6,
            "unit": "ops/s",
            "extra": "Async overhead with unified_response=True, sequential"
          },
          {
            "name": "overhead_async · ops_per_sec",
            "value": 34808.4,
            "unit": "ops/s",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "concurrency_sync_16_threads · ops_per_sec",
            "value": 13701.9,
            "unit": "ops/s",
            "extra": "16 threads, 1ms simulated upstream latency"
          },
          {
            "name": "concurrency_async_200_tasks · ops_per_sec",
            "value": 25769.4,
            "unit": "ops/s",
            "extra": "200 concurrent asyncio tasks, 1ms simulated upstream latency"
          },
          {
            "name": "resilience_rate_limit_10pct · ops_per_sec",
            "value": 41881.2,
            "unit": "ops/s",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · ops_per_sec",
            "value": 58654.7,
            "unit": "ops/s",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · ops_per_sec",
            "value": 24886.5,
            "unit": "ops/s",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · ops_per_sec",
            "value": 49687.6,
            "unit": "ops/s",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · ops_per_sec",
            "value": 53918.5,
            "unit": "ops/s",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · ops_per_sec",
            "value": 8508.8,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · ops_per_sec",
            "value": 94343.9,
            "unit": "ops/s",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · ops_per_sec",
            "value": 44221.7,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · ops_per_sec",
            "value": 38676.8,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · ops_per_sec",
            "value": 36827.3,
            "unit": "ops/s",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "select_round_robin_10_keys · ops_per_sec",
            "value": 867722.8,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_round_robin_1000_keys · ops_per_sec",
            "value": 787210.8,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_random_10_keys · ops_per_sec",
            "value": 737158.3,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_random_1000_keys · ops_per_sec",
            "value": 702540.5,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_weighted_10_keys · ops_per_sec",
            "value": 663824.5,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_weighted_1000_keys · ops_per_sec",
            "value": 595520.8,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_lru_10_keys · ops_per_sec",
            "value": 426637.8,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_lru_1000_keys · ops_per_sec",
            "value": 9202.4,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "select_health_based_10_keys · ops_per_sec",
            "value": 440911.5,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 10 keys and metrics"
          },
          {
            "name": "select_health_based_1000_keys · ops_per_sec",
            "value": 10127.3,
            "unit": "ops/s",
            "extra": "strategy.get_next_key() with 1000 keys and metrics"
          },
          {
            "name": "e2e_sync_local_http · ops_per_sec",
            "value": 1180.2,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · ops_per_sec",
            "value": 2833.8,
            "unit": "ops/s",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      }
    ],
    "Latency, upstream calls, waiting and memory (lower is better)": [
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
        "date": 1790255430205,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · p50_us",
            "value": 9.36,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · p50_us",
            "value": 9.68,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · p50_us",
            "value": 9.58,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · p50_us",
            "value": 10.22,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · p50_us",
            "value": 10.46,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · p50_us",
            "value": 18.24,
            "unit": "µs",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · p50_us",
            "value": 11.85,
            "unit": "µs",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · p50_us",
            "value": 12.87,
            "unit": "µs",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_sync_cache_hits · upstream_calls_per_req",
            "value": 0.0003,
            "unit": "calls/req",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_async · p50_us",
            "value": 10.48,
            "unit": "µs",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "resilience_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1037,
            "unit": "calls/req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 11.667,
            "unit": "s per 1k req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · upstream_calls_per_req",
            "value": 1.0003,
            "unit": "calls/req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1037,
            "unit": "calls/req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 11.667,
            "unit": "s per 1k req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · upstream_calls_per_req",
            "value": 1.0503,
            "unit": "calls/req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · sleep_s_per_1k_req",
            "value": 56.195,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_client_errors_5pct · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · upstream_calls_per_req",
            "value": 3,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down · sleep_s_per_1k_req",
            "value": 3155.032,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · upstream_calls_per_req",
            "value": 0.0167,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_host_down_breaker · sleep_s_per_1k_req",
            "value": 21.226,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · upstream_calls_per_req",
            "value": 1.0833,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_reactive · sleep_s_per_1k_req",
            "value": 501.667,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · upstream_calls_per_req",
            "value": 1.0083,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_headers · sleep_s_per_1k_req",
            "value": 500,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resilience_quota_token_bucket · sleep_s_per_1k_req",
            "value": 500,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resources_memory_per_key_round_robin · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=round_robin"
          },
          {
            "name": "resources_memory_per_key_lru · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=lru"
          },
          {
            "name": "resources_memory_per_key_health_based · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=health_based"
          },
          {
            "name": "resources_steady_state_sync · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync · alloc_kb_per_req",
            "value": 3.7,
            "unit": "KB/req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync_middlewares · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_sync_middlewares · alloc_kb_per_req",
            "value": 3.98,
            "unit": "KB/req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_async · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_async · alloc_kb_per_req",
            "value": 10.04,
            "unit": "KB/req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_import_cost · import_ms",
            "value": 56.5,
            "unit": "ms",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "resources_import_cost · import_rss_mb",
            "value": 14.6,
            "unit": "MB",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "e2e_sync_local_http · p50_us",
            "value": 551.66,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · p50_us",
            "value": 7376.4,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      },
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
          "id": "da1660fa88fc6180b2f64a4efbc706d3d7e2f35a",
          "message": "release: 0.8.2 - explicit auth, safe key rejection, no implicit file reads, no emoji\n\n- auth= (\"bearer\", \"x-api-key\", (header, template), False); the default for\n  non-32-character keys is now Bearer instead of the non-standard \"Key\".\n- Until a request has been accepted, 401/403 no longer removes keys: the\n  other keys are tried and AuthenticationError shows the header that was\n  sent. Keys rejected earlier are removed once a request succeeds.\n- load_env_file=False and config_file=None by default; load_env_file=True\n  now finds the application's .env (it searched from the library's dir).\n- should_retry_callback gets the response in both rotators; the async\n  chain runs *_sync hooks of duck-typed middlewares; APIKeyRotator warns\n  about async-only middlewares.\n- No emoji in logs, errors or docs. Benchmark history uses -n 5000.\n- Release workflow accepts ref/latest inputs; one-off workflow backfills\n  the 0.8.0 tag and release.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01F6FRG9xUgZ3KxwroGa993w",
          "timestamp": "2026-09-24T13:27:47Z",
          "tree_id": "f5bc5bd9a4915964d6ff550eaeb8f1cf1c83f0f2",
          "url": "https://github.com/PrimeevolutionZ/apikeyrotator/commit/da1660fa88fc6180b2f64a4efbc706d3d7e2f35a"
        },
        "date": 1790256528261,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · p50_us",
            "value": 12.63,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · p50_us",
            "value": 12.97,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · p50_us",
            "value": 13.08,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · p50_us",
            "value": 13.94,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · p50_us",
            "value": 13.93,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · p50_us",
            "value": 24.09,
            "unit": "µs",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · p50_us",
            "value": 15.65,
            "unit": "µs",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · p50_us",
            "value": 16.66,
            "unit": "µs",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_sync_cache_hits · upstream_calls_per_req",
            "value": 0.0002,
            "unit": "calls/req",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_async · p50_us",
            "value": 13.63,
            "unit": "µs",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "resilience_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1024,
            "unit": "calls/req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 12.2,
            "unit": "s per 1k req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · upstream_calls_per_req",
            "value": 1.0002,
            "unit": "calls/req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1024,
            "unit": "calls/req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 12.2,
            "unit": "s per 1k req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · upstream_calls_per_req",
            "value": 1.0514,
            "unit": "calls/req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · sleep_s_per_1k_req",
            "value": 57.446,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_client_errors_5pct · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · upstream_calls_per_req",
            "value": 3,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down · sleep_s_per_1k_req",
            "value": 3153.706,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · upstream_calls_per_req",
            "value": 0.01,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_host_down_breaker · sleep_s_per_1k_req",
            "value": 12.735,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · upstream_calls_per_req",
            "value": 1.09,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_reactive · sleep_s_per_1k_req",
            "value": 541,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · upstream_calls_per_req",
            "value": 1.009,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_headers · sleep_s_per_1k_req",
            "value": 540,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resilience_quota_token_bucket · sleep_s_per_1k_req",
            "value": 540,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resources_memory_per_key_round_robin · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=round_robin"
          },
          {
            "name": "resources_memory_per_key_lru · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=lru"
          },
          {
            "name": "resources_memory_per_key_health_based · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=health_based"
          },
          {
            "name": "resources_steady_state_sync · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync · alloc_kb_per_req",
            "value": 3.71,
            "unit": "KB/req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync_middlewares · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_sync_middlewares · alloc_kb_per_req",
            "value": 3.98,
            "unit": "KB/req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_async · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_async · alloc_kb_per_req",
            "value": 10.05,
            "unit": "KB/req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_import_cost · import_ms",
            "value": 76.4,
            "unit": "ms",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "resources_import_cost · import_rss_mb",
            "value": 14.6,
            "unit": "MB",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "e2e_sync_local_http · p50_us",
            "value": 734.23,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · p50_us",
            "value": 10824.9,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      },
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
          "id": "bfa53885e209c46d0237c9c40117a242fa4b0456",
          "message": "ci: drop the 0.8.0 tag backfill, move actions to Node 24 versions\n\nGitHub rejects tags created by the workflow token on commits whose workflow\nfiles differ from the current ones, so 0.8.0 cannot be tagged from CI; the\none-off backfill workflow is removed. checkout@v5, setup-python@v6,\nupload/download-artifact@v5 replace the deprecated Node 20 versions.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01F6FRG9xUgZ3KxwroGa993w",
          "timestamp": "2026-09-24T13:30:35Z",
          "tree_id": "73c07d4c1a59d236b67156692c1b94f81454654c",
          "url": "https://github.com/PrimeevolutionZ/apikeyrotator/commit/bfa53885e209c46d0237c9c40117a242fa4b0456"
        },
        "date": 1790256706498,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · p50_us",
            "value": 10.77,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · p50_us",
            "value": 11.01,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · p50_us",
            "value": 10.73,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · p50_us",
            "value": 12.14,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · p50_us",
            "value": 11.85,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · p50_us",
            "value": 28.11,
            "unit": "µs",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · p50_us",
            "value": 15.23,
            "unit": "µs",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · p50_us",
            "value": 14.46,
            "unit": "µs",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_sync_cache_hits · upstream_calls_per_req",
            "value": 0.0002,
            "unit": "calls/req",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_async · p50_us",
            "value": 14.38,
            "unit": "µs",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "resilience_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1024,
            "unit": "calls/req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 12.2,
            "unit": "s per 1k req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · upstream_calls_per_req",
            "value": 1.0002,
            "unit": "calls/req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1024,
            "unit": "calls/req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 12.2,
            "unit": "s per 1k req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · upstream_calls_per_req",
            "value": 1.0514,
            "unit": "calls/req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · sleep_s_per_1k_req",
            "value": 57.446,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_client_errors_5pct · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · upstream_calls_per_req",
            "value": 3,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down · sleep_s_per_1k_req",
            "value": 3153.706,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · upstream_calls_per_req",
            "value": 0.01,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_host_down_breaker · sleep_s_per_1k_req",
            "value": 12.735,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · upstream_calls_per_req",
            "value": 1.09,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_reactive · sleep_s_per_1k_req",
            "value": 541,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · upstream_calls_per_req",
            "value": 1.009,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_headers · sleep_s_per_1k_req",
            "value": 540,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resilience_quota_token_bucket · sleep_s_per_1k_req",
            "value": 540,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resources_memory_per_key_round_robin · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=round_robin"
          },
          {
            "name": "resources_memory_per_key_lru · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=lru"
          },
          {
            "name": "resources_memory_per_key_health_based · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=health_based"
          },
          {
            "name": "resources_steady_state_sync · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync · alloc_kb_per_req",
            "value": 3.71,
            "unit": "KB/req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync_middlewares · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_sync_middlewares · alloc_kb_per_req",
            "value": 3.98,
            "unit": "KB/req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_async · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_async · alloc_kb_per_req",
            "value": 10.18,
            "unit": "KB/req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_import_cost · import_ms",
            "value": 64.3,
            "unit": "ms",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "resources_import_cost · import_rss_mb",
            "value": 14.6,
            "unit": "MB",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "e2e_sync_local_http · p50_us",
            "value": 703.65,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · p50_us",
            "value": 7986.73,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      },
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
          "id": "6abeed4a3176b2fc4f9ba0f7b560b2805df1a4e8",
          "message": "feat: unified_response - one response type for requests, httpx and aiohttp\n\nWith unified_response=True every rotator and backend returns UnifiedResponse:\nstatus_code, case-insensitive Headers (get_list for repeated headers),\ncontent/text/json() without await, ok, reason, url, elapsed,\nraise_for_status() and the client's object as .native. The body is read in\nthe engine (so the connection is back in the pool), and the same object is\nused for AllKeysExhaustedError.last_response, cache hits and\nshould_retry_callback. Construction is lazy (~2-3 us per request); off by\ndefault. Adds HTTPStatusError.response and benchmark scenarios\noverhead_sync_unified / overhead_async_unified.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01F6FRG9xUgZ3KxwroGa993w",
          "timestamp": "2026-09-24T13:43:45Z",
          "tree_id": "59f2f461deb295d5d09dc80ebacea11eb7bbbefc",
          "url": "https://github.com/PrimeevolutionZ/apikeyrotator/commit/6abeed4a3176b2fc4f9ba0f7b560b2805df1a4e8"
        },
        "date": 1790257479790,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "overhead_sync_round_robin · p50_us",
            "value": 16.74,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=round_robin, stub transport"
          },
          {
            "name": "overhead_sync_random · p50_us",
            "value": 16.89,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=random, stub transport"
          },
          {
            "name": "overhead_sync_weighted · p50_us",
            "value": 17.35,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=weighted, stub transport"
          },
          {
            "name": "overhead_sync_lru · p50_us",
            "value": 18.33,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=lru, stub transport"
          },
          {
            "name": "overhead_sync_health_based · p50_us",
            "value": 18.1,
            "unit": "µs",
            "extra": "Sync request overhead, 10 keys, strategy=health_based, stub transport"
          },
          {
            "name": "overhead_sync_middlewares · p50_us",
            "value": 34.85,
            "unit": "µs",
            "extra": "Sync overhead with Logging+RateLimit middlewares (all misses)"
          },
          {
            "name": "overhead_sync_all_features · p50_us",
            "value": 22.41,
            "unit": "µs",
            "extra": "Sync overhead with circuit breaker, key token bucket and request deadline enabled"
          },
          {
            "name": "overhead_sync_cache_hits · p50_us",
            "value": 22.88,
            "unit": "µs",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_sync_cache_hits · upstream_calls_per_req",
            "value": 0.0002,
            "unit": "calls/req",
            "extra": "Sync requests served by CachingMiddleware (same URL)"
          },
          {
            "name": "overhead_sync_unified · p50_us",
            "value": 18.88,
            "unit": "µs",
            "extra": "Sync overhead with unified_response=True"
          },
          {
            "name": "overhead_async_unified · p50_us",
            "value": 22.88,
            "unit": "µs",
            "extra": "Async overhead with unified_response=True, sequential"
          },
          {
            "name": "overhead_async · p50_us",
            "value": 20.2,
            "unit": "µs",
            "extra": "Async request overhead, 10 keys, sequential"
          },
          {
            "name": "resilience_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1024,
            "unit": "calls/req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 12.2,
            "unit": "s per 1k req",
            "extra": "10 keys, 10% of responses are 429 (Retry-After: 1). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · upstream_calls_per_req",
            "value": 1.0002,
            "unit": "calls/req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_rate_limit_hot_key · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, one key always answers 429 (Retry-After: 30). Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · upstream_calls_per_req",
            "value": 1.1024,
            "unit": "calls/req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_async_rate_limit_10pct · sleep_s_per_1k_req",
            "value": 12.2,
            "unit": "s per 1k req",
            "extra": "Async, 20 concurrent tasks, 10 keys, 10% 429s. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · upstream_calls_per_req",
            "value": 1.0514,
            "unit": "calls/req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_server_errors_5pct · sleep_s_per_1k_req",
            "value": 57.446,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of responses are 503. Sleeps are simulated"
          },
          {
            "name": "resilience_client_errors_5pct · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_client_errors_5pct · sleep_s_per_1k_req",
            "value": 0,
            "unit": "s per 1k req",
            "extra": "10 keys, 5% of requests hit a 404 endpoint (must not destroy the key pool)"
          },
          {
            "name": "resilience_host_down · upstream_calls_per_req",
            "value": 3,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down · sleep_s_per_1k_req",
            "value": 3153.706,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, no circuit breaker (baseline for the next scenario)"
          },
          {
            "name": "resilience_host_down_breaker · upstream_calls_per_req",
            "value": 0.01,
            "unit": "calls/req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_host_down_breaker · sleep_s_per_1k_req",
            "value": 12.735,
            "unit": "s per 1k req",
            "extra": "Host answers 503 to everything, circuit breaker on: fail fast instead of hammering it"
          },
          {
            "name": "resilience_quota_reactive · upstream_calls_per_req",
            "value": 1.09,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_reactive · sleep_s_per_1k_req",
            "value": 541,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator reacts to 429 only (header hints off)"
          },
          {
            "name": "resilience_quota_headers · upstream_calls_per_req",
            "value": 1.009,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_headers · sleep_s_per_1k_req",
            "value": 540,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; rotator skips keys at X-RateLimit-Remaining: 0"
          },
          {
            "name": "resilience_quota_token_bucket · upstream_calls_per_req",
            "value": 1,
            "unit": "calls/req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resilience_quota_token_bucket · sleep_s_per_1k_req",
            "value": 540,
            "unit": "s per 1k req",
            "extra": "10 keys x 10 req/min quota; client-side token bucket key_rate_limit=(10, 60)"
          },
          {
            "name": "resources_memory_per_key_round_robin · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=round_robin"
          },
          {
            "name": "resources_memory_per_key_lru · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=lru"
          },
          {
            "name": "resources_memory_per_key_health_based · mem_bytes_per_key",
            "value": 229.6,
            "unit": "B/key",
            "extra": "Memory retained per key: rotator with 10k keys, strategy=health_based"
          },
          {
            "name": "resources_steady_state_sync · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync · alloc_kb_per_req",
            "value": 3.74,
            "unit": "KB/req",
            "extra": "Sync, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_sync_middlewares · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_sync_middlewares · alloc_kb_per_req",
            "value": 4.02,
            "unit": "KB/req",
            "extra": "Sync + Logging/RateLimit/Caching middlewares: memory growth per 1k requests"
          },
          {
            "name": "resources_steady_state_async · mem_growth_bytes_per_1k_req",
            "value": 0,
            "unit": "B per 1k req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_steady_state_async · alloc_kb_per_req",
            "value": 9.94,
            "unit": "KB/req",
            "extra": "Async, 10 keys: memory growth per 1k requests with unique URLs (leak check)"
          },
          {
            "name": "resources_import_cost · import_ms",
            "value": 71.9,
            "unit": "ms",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "resources_import_cost · import_rss_mb",
            "value": 14.8,
            "unit": "MB",
            "extra": "Time and RSS added by `import apikeyrotator` in a fresh interpreter"
          },
          {
            "name": "e2e_sync_local_http · p50_us",
            "value": 842.2,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (sync, keep-alive)"
          },
          {
            "name": "e2e_async_local_http · p50_us",
            "value": 14018.07,
            "unit": "µs",
            "extra": "Real HTTP round-trips to a local server (async, 50 concurrent)"
          }
        ]
      }
    ]
  }
}