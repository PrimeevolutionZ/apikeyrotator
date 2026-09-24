"""Thread safety: many threads share one rotator (the documented way to use it)."""

import collections
import random
import threading
from unittest.mock import patch

import pytest

from apikeyrotator import (
    AllKeysExhaustedError,
    APIKeyRotator,
    CircuitBreakerConfig,
    CircuitOpenError,
)


class _Resp:
    __slots__ = ("status_code", "headers", "content")

    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.content = b"{}"

    def close(self):
        pass


def _run_threads(target, count=8):
    errors = []

    def wrapped():
        try:
            target()
        except Exception as e:  # pragma: no cover - reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=wrapped) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


@pytest.mark.parametrize("strategy", ["round_robin", "random", "weighted", "lru", "health_based", "failover"])
def test_counters_add_up_under_concurrency(strategy):
    keys = [f"key-{i}" for i in range(6)]
    rotator = APIKeyRotator(api_keys=keys, rotation_strategy=strategy)
    sent = collections.Counter()
    lock = threading.Lock()

    def fake(method, url, kwargs, proxy, timeout):
        with lock:
            sent[kwargs["headers"]["Authorization"][7:]] += 1
        return _Resp()

    rotator._transport.request = fake
    per_thread, threads = 300, 8
    errors = _run_threads(lambda: [rotator.get("http://x/y") for _ in range(per_thread)], threads)

    total = per_thread * threads
    assert errors == []
    assert sum(sent.values()) == total
    assert sum(s["total_requests"] for s in rotator.get_key_statistics().values()) == total
    assert rotator.get_metrics()["total_requests"] == total
    if strategy in ("round_robin", "lru"):
        assert set(sent.values()) == {total // len(keys)}   # perfectly even


def test_concurrent_removal_parking_and_replacement():
    keys = [f"key-{i}" for i in range(30)]
    revoked = {f"key-{i}" for i in range(0, 30, 5)}
    rotator = APIKeyRotator(api_keys=keys, base_delay=0, max_retries=5)

    def fake(method, url, kwargs, proxy, timeout):
        key = kwargs["headers"]["Authorization"][7:]
        if key in revoked:
            return _Resp(401)
        if random.random() < 0.05:
            return _Resp(429, {"Retry-After": "0.01"})
        return _Resp(200)

    rotator._transport.request = fake
    rotator.get("http://x/warmup")                      # auth confirmed
    stop = threading.Event()

    def requests_loop():
        for _ in range(300):
            try:
                rotator.get("http://x/y")
            except AllKeysExhaustedError:
                pass

    def mutations():
        while not stop.is_set():
            rotator.keys = random.sample(keys, 20)
            rotator.reset_key_health()

    mutator = threading.Thread(target=mutations)
    mutator.start()
    try:
        errors = _run_threads(requests_loop, 8)
    finally:
        stop.set()
        mutator.join()
    assert errors == []
    rotator.keys = keys
    for _ in range(100):
        rotator.get("http://x/y")
    assert not set(rotator.keys) & revoked


def test_circuit_breakers_are_per_host():
    rotator = APIKeyRotator(api_keys=["k"], max_retries=2, base_delay=0,
                            circuit_breaker=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=30))

    def fake(self, method, url, **kwargs):
        return _Resp(503 if "dead.example.com" in url else 200)

    with patch("requests.Session.request", fake):
        with pytest.raises(AllKeysExhaustedError):
            rotator.get("https://dead.example.com/v1")
        with pytest.raises(CircuitOpenError):
            rotator.get("https://dead.example.com/v1")
        assert rotator.get("https://alive.example.com/v1").status_code == 200
    assert rotator.get_circuit_states() == {"dead.example.com": "OPEN", "alive.example.com": "CLOSED"}


def test_prometheus_export_accepts_the_rotator():
    from apikeyrotator import PrometheusExporter

    rotator = APIKeyRotator(api_keys=["sk-live-secret-key-1"])
    with patch("requests.Session.request", return_value=_Resp()):
        rotator.get("https://api.example.com/x")
    text = PrometheusExporter.export(rotator)
    assert "rotator_total_requests 1" in text
    assert 'rotator_key_total_requests{key="sk-l...ey-1"} 1' in text
    explicit = PrometheusExporter.export(rotator.metrics, key_metrics=rotator.get_key_statistics())

    def without_uptime(t):
        return [line for line in t.splitlines() if "uptime" not in line]

    assert without_uptime(text) == without_uptime(explicit)


def test_lru_rotates_even_with_a_coarse_clock():
    """On Windows time.time() moves in ~15 ms steps; equal timestamps must not pin one key."""
    rotator = APIKeyRotator(api_keys=[f"key-{i}" for i in range(4)], rotation_strategy="lru")
    sent = collections.Counter()
    rotator._transport.request = lambda m, u, kwargs, p, t: (
        sent.update([kwargs["headers"]["Authorization"][7:]]) or _Resp())
    with patch("time.time", lambda: 1_800_000_000.0):
        for _ in range(40):
            rotator.get("http://x/y")
    assert set(sent.values()) == {10}
