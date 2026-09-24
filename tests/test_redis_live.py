"""
Shared state against a real Redis, with several processes.

Runs when REDIS_URL is set (CI starts a Redis service); fakeredis-based tests in
test_features.py cover the logic without a server.
"""

import collections
import multiprocessing as mp
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


REDIS_URL = os.environ.get("REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="REDIS_URL not set")


class _Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    calls = collections.Counter()
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def do_GET(self):
        key = (self.headers.get("Authorization") or "")[7:]
        with self.lock:
            self.calls[(self.path, key)] += 1
        status = 401 if self.path == "/auth" and key == "key-a" else 200
        self.send_response(status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture(scope="module")
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _worker(url, namespace, count, kwargs, results):
    import logging

    logging.disable(logging.CRITICAL)
    from apikeyrotator import AllKeysExhaustedError, APIKeyRotator, RedisStateBackend

    rotator = APIKeyRotator(api_keys=["key-a", "key-b"], base_delay=0.01,
                            state_backend=RedisStateBackend(url=REDIS_URL, namespace=namespace), **kwargs)
    ok = 0
    for _ in range(count):
        try:
            rotator.get(url)
            ok += 1
        except AllKeysExhaustedError:
            pass
    results.put((ok, rotator.keys))


def _run(url, namespace, processes, count, kwargs):
    ctx = mp.get_context("spawn")
    results = ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(url, namespace, count, kwargs, results)) for _ in range(processes)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
    return [results.get(timeout=5) for _ in procs]


def test_token_bucket_is_global_across_processes(upstream):
    namespace = f"test-tb-{uuid.uuid4().hex[:8]}"
    results = _run(f"{upstream}/tb", namespace, processes=4, count=8,
                   kwargs={"key_rate_limit": (10, 60), "total_timeout": 0.5})
    sent = sum(v for (path, _), v in _Upstream.calls.items() if path == "/tb")
    assert sum(ok for ok, _ in results) == sent
    assert 20 <= sent <= 21          # 2 keys x 10 tokens (+ at most one refilled token)


def test_revoked_key_reaches_other_processes(upstream):
    namespace = f"test-inv-{uuid.uuid4().hex[:8]}"
    first = _run(f"{upstream}/auth", namespace, processes=1, count=3, kwargs={"state_sync_interval": 0})
    assert first[0][1] == ["key-b"]
    before = _Upstream.calls[("/auth", "key-a")]
    second = _run(f"{upstream}/auth", namespace, processes=2, count=5, kwargs={"state_sync_interval": 0})
    assert all(keys == ["key-b"] for _, keys in second)
    assert _Upstream.calls[("/auth", "key-a")] == before   # nobody sent the revoked key again
