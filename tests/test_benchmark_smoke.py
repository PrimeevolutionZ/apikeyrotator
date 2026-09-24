"""
Smoke test for benchmarks/bench_core.py - keeps the benchmark runnable.
It does not assert on timings (those are machine dependent); use
`python benchmarks/bench_core.py --compare <baseline.json>` for that.
"""

import json
import os
import sys

import pytest

BENCH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'benchmarks'))
sys.path.insert(0, BENCH_DIR)

import bench_core  # noqa: E402


@pytest.mark.slow
def test_benchmark_runs_and_compares(tmp_path, capsys):
    out = tmp_path / "bench.json"
    pattern = r"^(overhead_sync_round_robin|overhead_sync_middlewares|resilience_.*|select_lru_10_keys)$"
    assert bench_core.main(["-n", "100", "-r", "1", "-k", pattern, "--save", str(out)]) == 0

    data = json.loads(out.read_text())
    results = data["results"]
    assert all("error" not in r for r in results.values())
    assert results["resilience_client_errors_5pct"]["keys_left"] == 10
    assert results["resilience_rate_limit_hot_key"]["sleep_s_per_1k_req"] == 0
    assert results["overhead_sync_middlewares"]["success_rate"] == 1.0

    # Comparing a run with itself must never report regressions
    assert bench_core.compare(results, data, threshold=10.0) == 0
