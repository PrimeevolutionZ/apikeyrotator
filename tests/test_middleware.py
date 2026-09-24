"""
Middleware tests for APIKeyRotator
Tests: CachingMiddleware, LoggingMiddleware, RateLimitMiddleware and their
integration with the sync/async rotators.
"""

import pytest
import os
import sys
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import Mock, AsyncMock, patch

from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator
from apikeyrotator.middleware import (
    RequestInfo,
    ResponseInfo,
    ErrorInfo,
    RotatorMiddleware,
    CachingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
)


def create_request_info(
    method: str = "GET",
    url: str = "http://example.com",
    headers: dict = None,
    key: str = "test_key",
    kwargs: dict = None,
) -> RequestInfo:
    return RequestInfo(
        method=method,
        url=url,
        headers=headers or {},
        cookies={},
        key=key,
        attempt=0,
        kwargs=kwargs or {}
    )


def create_response_info(
    status_code: int = 200,
    request_info: RequestInfo = None,
    headers: dict = None,
    content: bytes = b'{"status": "ok"}'
) -> ResponseInfo:
    if request_info is None:
        request_info = create_request_info()
    return ResponseInfo(
        status_code=status_code,
        headers=headers or {},
        content=content,
        request_info=request_info
    )


def create_error_info(
    exception: Exception = None,
    request_info: RequestInfo = None,
    response_info: ResponseInfo = None
) -> ErrorInfo:
    if exception is None:
        exception = ValueError("Test error")
    if request_info is None:
        request_info = create_request_info()
    return ErrorInfo(
        exception=exception,
        request_info=request_info,
        response_info=response_info
    )


def _mock_response(status=200, headers=None, content=b'{"ok": true}'):
    return Mock(status_code=status, headers=headers or {}, content=content)


# ============================================================================
# CACHING
# ============================================================================

class TestCachingMiddleware:

    def test_cache_hit_returns_cached_response(self):
        cache = CachingMiddleware(ttl=60)
        req = create_request_info()
        cache.after_request_sync(create_response_info(request_info=req))

        result = cache.before_request_sync(create_request_info())
        assert isinstance(result, ResponseInfo)
        assert cache.hits == 1

    def test_cache_miss(self):
        cache = CachingMiddleware()
        result = cache.before_request_sync(create_request_info())
        assert isinstance(result, RequestInfo)
        assert cache.misses == 1

    def test_cache_ignores_auth_headers_in_key(self):
        cache = CachingMiddleware()
        req1 = create_request_info(headers={'Authorization': 'Bearer a'}, key='a')
        req2 = create_request_info(headers={'Authorization': 'Bearer b'}, key='b')
        assert cache._get_cache_key(req1) == cache._get_cache_key(req2)

    def test_cache_key_includes_params(self):
        """Regression: GET ?q=a and ?q=b passed via params must not collide."""
        cache = CachingMiddleware()
        req_a = create_request_info(kwargs={'params': {'q': 'a'}})
        req_b = create_request_info(kwargs={'params': {'q': 'b'}})
        assert cache._get_cache_key(req_a) != cache._get_cache_key(req_b)

        cache.after_request_sync(create_response_info(request_info=req_a, content=b'A'))
        assert isinstance(cache.before_request_sync(req_b), RequestInfo)

    def test_non_get_not_cached(self):
        cache = CachingMiddleware()
        req = create_request_info(method="POST")
        cache.after_request_sync(create_response_info(request_info=req))
        assert len(cache.cache) == 0

    def test_error_response_not_cached(self):
        cache = CachingMiddleware()
        cache.after_request_sync(create_response_info(status_code=500))
        assert len(cache.cache) == 0

    def test_unsafe_responses_not_cached(self):
        cache = CachingMiddleware()
        for headers in ({'set-cookie': 'a=b'}, {'cache-control': 'no-store'},
                        {'Content-Type': 'text/event-stream'}):
            cache.after_request_sync(create_response_info(headers=headers))
        assert len(cache.cache) == 0

    def test_ttl_expiry(self):
        cache = CachingMiddleware(ttl=1)
        req = create_request_info()
        cache.after_request_sync(create_response_info(request_info=req))
        with patch('apikeyrotator.middleware.caching.time.time', return_value=time.time() + 5):
            assert isinstance(cache.before_request_sync(req), RequestInfo)
        assert len(cache.cache) == 0

    def test_lru_eviction_by_count(self):
        cache = CachingMiddleware(max_cache_size=2)
        for i in range(3):
            req = create_request_info(url=f"http://example.com/{i}")
            cache.after_request_sync(create_response_info(request_info=req))
        assert len(cache.cache) == 2
        assert isinstance(cache.before_request_sync(create_request_info(url="http://example.com/0")), RequestInfo)

    def test_size_accounting_and_byte_limit(self):
        cache = CachingMiddleware(max_cache_size_bytes=250, max_cacheable_size=200)
        for i in range(5):
            req = create_request_info(url=f"http://example.com/{i}")
            cache.after_request_sync(create_response_info(request_info=req, content=b'x' * 100))
        assert cache._get_total_cache_size() <= 250
        assert cache._get_total_cache_size() == sum(e['size'] for e in cache.cache.values())

    def test_overwrite_same_key_keeps_size_consistent(self):
        cache = CachingMiddleware()
        req = create_request_info()
        for _ in range(3):
            cache.after_request_sync(create_response_info(request_info=req, content=b'x' * 10))
        assert len(cache.cache) == 1
        assert cache._get_total_cache_size() == sum(e['size'] for e in cache.cache.values())

    @pytest.mark.asyncio
    async def test_cache_with_none_content(self):
        cache = CachingMiddleware()
        await cache.after_request(create_response_info(content=None))
        assert len(cache.cache) == 1

    def test_sync_rotator_serves_from_cache(self):
        cache = CachingMiddleware(ttl=60)
        rotator = APIKeyRotator(api_keys=['key1'], middlewares=[cache], load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = _mock_response(content=b'{"v": 1}')
            first = rotator.get('http://example.com/data')
            second = rotator.get('http://example.com/data')
        assert mock_request.call_count == 1
        assert second.status_code == 200
        assert second.json() == {"v": 1}
        assert first.content == second.content

    @pytest.mark.asyncio
    async def test_async_rotator_serves_body_from_cache(self):
        """Regression: async responses were cached with content=None."""
        cache = CachingMiddleware(ttl=60)
        calls = 0

        async def mock_request(*args, **kwargs):
            nonlocal calls
            calls += 1
            resp = Mock()
            resp.status = 200
            resp.headers = {}
            resp.read = AsyncMock(return_value=b'{"v": 2}')
            resp.release = Mock()
            return resp

        async with AsyncAPIKeyRotator(api_keys=['key1'], middlewares=[cache], load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                await rotator.get('http://example.com/data')
                cached = await rotator.get('http://example.com/data')

        assert calls == 1
        assert cached.status == 200
        assert await cached.json() == {"v": 2}


# ============================================================================
# LOGGING
# ============================================================================

class TestLoggingMiddleware:

    def test_masks_sensitive_headers(self):
        mw = LoggingMiddleware()
        formatted = mw._format_headers({'Authorization': 'Bearer secret', 'X-Other': '1'})
        assert 'secret' not in formatted
        assert '[REDACTED]' in formatted

    def test_masks_key(self):
        mw = LoggingMiddleware(max_key_chars=4)
        assert mw._mask_key('sk-1234567890') == 'sk-1****'

    def test_log_rate_limiting(self):
        mw = LoggingMiddleware(max_logs_per_second=2)
        results = [mw._should_log() for _ in range(5)]
        assert results.count(True) == 2

    def test_logs_response_time(self, caplog):
        logger = logging.getLogger('test_logging_mw')
        mw = LoggingMiddleware(logger=logger)
        info = create_response_info()
        info.response_time = 0.123
        with caplog.at_level(logging.INFO, logger='test_logging_mw'):
            mw.after_request_sync(info)
        assert any('0.123s' in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_logger_with_missing_attributes(self):
        mw = LoggingMiddleware()
        with patch.object(mw.logger, 'log'):
            await mw.after_request(create_response_info())

    def test_logs_errors(self, caplog):
        logger = logging.getLogger('test_logging_mw_err')
        mw = LoggingMiddleware(logger=logger)
        with caplog.at_level(logging.ERROR, logger='test_logging_mw_err'):
            mw.on_error_sync(create_error_info(exception=RuntimeError("boom")))
        assert any('boom' in r.message for r in caplog.records)


# ============================================================================
# RATE LIMIT
# ============================================================================

class TestRateLimitMiddleware:

    def test_extracts_headers(self):
        mw = RateLimitMiddleware()
        reset = int(time.time()) + 30
        info = mw._extract_rate_limit_info({
            'x-ratelimit-limit': '100', 'X-RateLimit-Remaining': '5', 'X-RateLimit-Reset': str(reset)
        })
        assert info == {'limit': 100, 'remaining': 5, 'reset_time': reset}

    def test_delta_reset_is_converted_to_timestamp(self):
        """RateLimit-Reset (IETF draft) is seconds-until-reset, not an epoch."""
        mw = RateLimitMiddleware()
        info = mw._extract_rate_limit_info({'RateLimit-Reset': '30'})
        assert time.time() + 25 < info['reset_time'] <= time.time() + 30

    @pytest.mark.asyncio
    async def test_rate_limit_with_invalid_headers(self):
        mw = RateLimitMiddleware()
        resp = create_response_info(headers={
            'X-RateLimit-Limit': 'invalid',
            'X-RateLimit-Remaining': 'also-invalid'
        })
        await mw.after_request(resp)
        assert mw.get_stats()['tracked_keys'] == 0

    def test_no_pause_while_quota_remains(self):
        """Regression: a future reset header alone used to pause every request."""
        mw = RateLimitMiddleware(pause_on_limit=True)
        req = create_request_info()
        mw.after_request_sync(create_response_info(request_info=req, headers={
            'X-RateLimit-Remaining': '50', 'X-RateLimit-Reset': str(int(time.time()) + 60)
        }))
        assert mw._check_rate_limit(req.key) == 0.0

    def test_pause_when_quota_exhausted(self):
        mw = RateLimitMiddleware(pause_on_limit=True, max_wait=5)
        req = create_request_info()
        mw.after_request_sync(create_response_info(request_info=req, headers={
            'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(int(time.time()) + 60)
        }))
        wait = mw._check_rate_limit(req.key)
        assert 0 < wait <= 5 * 1.1

    def test_on_error_429_records_retry_after(self):
        mw = RateLimitMiddleware()
        req = create_request_info()
        resp = create_response_info(status_code=429, request_info=req, headers={'retry-after': '1.5'})
        assert mw.on_error_sync(create_error_info(request_info=req, response_info=resp)) is True
        reset = mw.rate_limits[req.key]['reset_time']
        assert time.time() < reset <= time.time() + 1.5

    def test_rotator_calls_on_error_for_429(self):
        """Regression: on_error hooks were never invoked by the rotator."""
        mw = RateLimitMiddleware(pause_on_limit=False)
        rotator = APIKeyRotator(api_keys=['k1', 'k2'], middlewares=[mw], load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [
                _mock_response(429, headers={'Retry-After': '30'}),
                _mock_response(200),
            ]
            assert rotator.get('http://example.com').status_code == 200
        assert 'k1' in mw.rate_limits
        assert mw.rate_limits['k1']['remaining'] == 0

    def test_eviction_bounds_memory(self):
        mw = RateLimitMiddleware(max_tracked_keys=10)
        for i in range(50):
            mw._store_rate_limit_info(f"key{i}", {'remaining': 1, 'reset_time': time.time() + i})
        assert len(mw.rate_limits) <= 10


# ============================================================================
# CUSTOM MIDDLEWARE
# ============================================================================

class TestCustomMiddleware:

    def test_before_request_can_modify_headers(self):
        class AddHeader(RotatorMiddleware):
            def before_request_sync(self, request_info):
                request_info.headers['X-Trace'] = 'abc'
                return request_info

        rotator = APIKeyRotator(api_keys=['k1'], middlewares=[AddHeader()], load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = _mock_response()
            rotator.get('http://example.com')
        assert mock_request.call_args[1]['headers']['X-Trace'] == 'abc'

    def test_failing_on_error_hook_does_not_break_retries(self):
        class Broken(RotatorMiddleware):
            def on_error_sync(self, error_info):
                raise RuntimeError("bad middleware")

        rotator = APIKeyRotator(api_keys=['k1'], middlewares=[Broken()], base_delay=0.01,
                                load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [_mock_response(500), _mock_response(200)]
            assert rotator.get('http://example.com').status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
