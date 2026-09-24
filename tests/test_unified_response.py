"""
unified_response=True: the same response object from every HTTP client.

A real local HTTP server is used, so the test covers what requests, httpx and
aiohttp actually return (header types, reasons, URLs, released connections).
"""

import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apikeyrotator import (
    AllKeysExhaustedError,
    APIKeyRotator,
    AsyncAPIKeyRotator,
    CachingMiddleware,
    HTTPStatusError,
    UnifiedResponse,
)
from apikeyrotator.core.responses import Headers


BODY = {"hello": "мир"}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/data"):
            payload = json.dumps(BODY).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-Custom", "1")
            self.send_header("Set-Cookie", "a=1")
            self.send_header("Set-Cookie", "b=2")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path.startswith("/plain"):
            payload = json.dumps(BODY).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        status = 404 if self.path.startswith("/missing") else 500
        payload = json.dumps({"error": status}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


SYNC_BACKENDS = ["requests", "httpx"]
ASYNC_BACKENDS = ["aiohttp", "httpx"]


def _check_success(response, base, native_module):
    assert isinstance(response, UnifiedResponse)
    assert response.status_code == response.status == 200
    assert response.ok and response.reason == "OK" == response.reason_phrase
    assert response.json() == BODY
    assert response.text == json.dumps(BODY) or json.loads(response.text) == BODY
    assert isinstance(response.content, bytes)
    assert response.encoding == "utf-8"
    assert response.headers["x-custom"] == response.headers["X-CUSTOM"] == "1"
    assert "content-type" in response.headers
    assert response.headers.get_list("set-cookie") == ["a=1", "b=2"]
    assert response.url == f"{base}/data"
    assert isinstance(response.elapsed, timedelta)
    assert response.raise_for_status() is response
    assert type(response.native).__module__.split(".")[0] == native_module


@pytest.mark.parametrize("backend", SYNC_BACKENDS)
def test_sync_backends_return_the_same_response(server, backend):
    if backend == "httpx":
        pytest.importorskip("httpx")
    with APIKeyRotator(api_keys=["k1"], http_backend=backend, unified_response=True) as rotator:
        _check_success(rotator.get(f"{server}/data"), server, backend)


@pytest.mark.parametrize("backend", ASYNC_BACKENDS)
@pytest.mark.asyncio
async def test_async_backends_return_the_same_response(server, backend):
    if backend == "httpx":
        pytest.importorskip("httpx")
    async with AsyncAPIKeyRotator(api_keys=["k1"], http_backend=backend, unified_response=True) as rotator:
        response = await rotator.get(f"{server}/data")
        _check_success(response, server, backend)
        if backend == "aiohttp":
            assert response.native.connection is None  # released back to the pool


@pytest.mark.parametrize("backend", SYNC_BACKENDS)
def test_client_error_and_raise_for_status(server, backend):
    if backend == "httpx":
        pytest.importorskip("httpx")
    with APIKeyRotator(api_keys=["k1"], http_backend=backend, unified_response=True) as rotator:
        response = rotator.get(f"{server}/missing")
    assert response.status_code == 404 and not response.ok
    with pytest.raises(HTTPStatusError) as exc:
        response.raise_for_status()
    assert exc.value.status_code == 404
    assert exc.value.response is response


@pytest.mark.parametrize("backend", ASYNC_BACKENDS)
@pytest.mark.asyncio
async def test_last_response_is_readable_in_async_too(server, backend):
    if backend == "httpx":
        pytest.importorskip("httpx")
    async with AsyncAPIKeyRotator(api_keys=["k1"], http_backend=backend, unified_response=True,
                                  max_retries=2, base_delay=0.001) as rotator:
        with pytest.raises(AllKeysExhaustedError) as exc:
            await rotator.get(f"{server}/boom")
    last = exc.value.last_response
    assert isinstance(last, UnifiedResponse)
    assert last.status_code == 500
    assert last.json() == {"error": 500}  # the body survives the released connection


def test_cache_hit_is_a_unified_response(server):
    with APIKeyRotator(api_keys=["k1"], unified_response=True,
                       middlewares=[CachingMiddleware()]) as rotator:
        first = rotator.get(f"{server}/plain")
        cached = rotator.get(f"{server}/plain")
    assert isinstance(cached, UnifiedResponse) and cached.native is None
    assert cached.json() == first.json() == BODY


def test_should_retry_callback_gets_the_unified_response(server):
    seen = []
    with APIKeyRotator(api_keys=["k1"], unified_response=True,
                       should_retry_callback=lambda r: seen.append(r) or False) as rotator:
        rotator.get(f"{server}/data")
    assert isinstance(seen[0], UnifiedResponse) and seen[0].json() == BODY


def test_stream_is_rejected(server):
    with APIKeyRotator(api_keys=["k1"], unified_response=True) as rotator:
        with pytest.raises(ValueError, match="stream=True"):
            rotator.get(f"{server}/data", stream=True)


def test_native_responses_stay_the_default(server):
    import requests

    with APIKeyRotator(api_keys=["k1"]) as rotator:
        assert isinstance(rotator.get(f"{server}/data"), requests.Response)
        rotator.unified_response = True
        assert isinstance(rotator.get(f"{server}/data"), UnifiedResponse)


class TestHeaders:
    def test_case_insensitive_mapping(self):
        headers = Headers([("Content-Type", "text/plain"), ("Set-Cookie", "a=1"), ("set-cookie", "b=2")])
        assert headers["content-type"] == "text/plain"
        assert headers["SET-COOKIE"] == "a=1, b=2"
        assert headers.get_list("Set-Cookie") == ["a=1", "b=2"]
        assert list(headers) == ["Content-Type", "Set-Cookie"]
        assert len(headers) == 2
        assert headers.get("missing") is None
        assert dict(headers) == {"Content-Type": "text/plain", "Set-Cookie": "a=1, b=2"}

    def test_response_defaults(self):
        response = UnifiedResponse(503, {"Content-Type": "text/html; charset=latin-1"}, "é".encode("latin-1"))
        assert response.reason == "Service Unavailable"
        assert response.text == "é"
        assert repr(response) == "<UnifiedResponse [503]>"
        assert bool(response) is True  # always truthy - check .ok instead
