"""
Middleware tests for APIKeyRotator
Tests: CachingMiddleware, LoggingMiddleware, RateLimitMiddleware, RetryMiddleware
"""

import pytest
import os
import sys
import time
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import Mock, AsyncMock, patch

from apikeyrotator.middleware import (
    RequestInfo,
    ResponseInfo,
    ErrorInfo,
    CachingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    RetryMiddleware
)

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_request_info(
    method: str = "GET",
    url: str = "http://example.com",
    headers: dict = None,
    key: str = "test_key"
) -> RequestInfo:
    """Helper to create RequestInfo objects"""
    return RequestInfo(
        method=method,
        url=url,
        headers=headers or {},
        cookies={},
        key=key,
        attempt=0,
        kwargs={}
    )


def create_response_info(
    status_code: int = 200,
    request_info: RequestInfo = None,
    headers: dict = None,
    content: bytes = b'{"status": "ok"}'
) -> ResponseInfo:
    """Helper to create ResponseInfo objects"""
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
    """Helper to create ErrorInfo objects"""
    if exception is None:
        exception = ValueError("Test error")
    if request_info is None:
        request_info = create_request_info()

    return ErrorInfo(
        exception=exception,
        request_info=request_info,
        response_info=response_info
    )


# ============================================================================
# CACHING MIDDLEWARE TESTS
# ============================================================================

class TestCachingMiddleware:
    """Test CachingMiddleware functionality"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        cache = CachingMiddleware(ttl=300, max_cache_size=100)
        assert cache.ttl == 300
        assert cache.max_cache_size == 100
        assert cache.cache_only_get is True
        assert cache.hits == 0
        assert cache.misses == 0

    @pytest.mark.asyncio
    async def test_cache_key_generation(self):
        cache = CachingMiddleware()

        req1 = create_request_info(method="GET", url="http://example.com/api")
        req2 = create_request_info(method="GET", url="http://example.com/api")
        req3 = create_request_info(method="GET", url="http://example.com/other")

        key1 = cache._get_cache_key(req1)
        key2 = cache._get_cache_key(req2)
        key3 = cache._get_cache_key(req3)

        # Same requests should have same cache key
        assert key1 == key2
        # Different URLs should have different keys
        assert key1 != key3

    @pytest.mark.asyncio
    async def test_before_request_cache_miss(self):
        cache = CachingMiddleware()
        req = create_request_info()

        result = await cache.before_request(req)

        assert result == req
        assert cache.misses == 1
        assert cache.hits == 0

    @pytest.mark.asyncio
    async def test_after_request_caches_success(self):
        cache = CachingMiddleware()
        req = create_request_info()
        resp = create_response_info(status_code=200, request_info=req)

        result = await cache.after_request(resp)

        assert result == resp
        assert len(cache.cache) == 1

    @pytest.mark.asyncio
    async def test_after_request_ignores_errors(self):
        cache = CachingMiddleware()
        req = create_request_info()
        resp = create_response_info(status_code=500, request_info=req)

        await cache.after_request(resp)

        assert len(cache.cache) == 0

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        cache = CachingMiddleware(ttl=10)
        req = create_request_info()
        resp = create_response_info(status_code=200, request_info=req)

        # Cache the response
        await cache.after_request(resp)

        # Request again - should be cache hit
        result = await cache.before_request(req)

        assert cache.hits == 1
        assert cache.misses == 0

    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        cache = CachingMiddleware(ttl=1)  # 1 second TTL
        req = create_request_info()
        resp = create_response_info(status_code=200, request_info=req)

        # Cache the response
        await cache.after_request(resp)
        assert len(cache.cache) == 1

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Request again - should be cache miss (expired)
        await cache.before_request(req)

        assert cache.misses == 1
        assert len(cache.cache) == 0  # Expired entry removed

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        cache = CachingMiddleware(max_cache_size=3)

        # Cache 4 responses (exceeds max size)
        for i in range(4):
            req = create_request_info(url=f"http://example.com/api/{i}")
            resp = create_response_info(status_code=200, request_info=req)
            await cache.after_request(resp)

        # Should have evicted oldest entry
        assert len(cache.cache) == 3

    @pytest.mark.asyncio
    async def test_cache_only_get(self):
        cache = CachingMiddleware(cache_only_get=True)

        # POST request
        post_req = create_request_info(method="POST")
        post_resp = create_response_info(status_code=200, request_info=post_req)

        await cache.after_request(post_resp)

        # Should not cache POST requests
        assert len(cache.cache) == 0

    @pytest.mark.asyncio
    async def test_clear_cache(self):
        cache = CachingMiddleware()

        # Cache some responses
        for i in range(3):
            req = create_request_info(url=f"http://example.com/api/{i}")
            resp = create_response_info(status_code=200, request_info=req)
            await cache.after_request(resp)

        assert len(cache.cache) == 3

        cache.clear_cache()

        assert len(cache.cache) == 0
        assert cache.hits == 0
        assert cache.misses == 0

    @pytest.mark.asyncio
    async def test_get_stats(self):
        cache = CachingMiddleware()

        req = create_request_info()
        resp = create_response_info(status_code=200, request_info=req)

        # Cache miss
        await cache.before_request(req)
        # Cache response
        await cache.after_request(resp)
        # Cache hit
        await cache.before_request(req)

        stats = cache.get_stats()

        assert stats['cache_size'] == 1
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 0.5
        assert stats['total_requests'] == 2


# ============================================================================
# LOGGING MIDDLEWARE TESTS
# ============================================================================

class TestLoggingMiddleware:
    """Test LoggingMiddleware functionality"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        logger = LoggingMiddleware(verbose=True)
        assert logger.verbose is True
        assert logger.log_response_time is True

    @pytest.mark.asyncio
    async def test_mask_key(self):
        logger = LoggingMiddleware(max_key_chars=4)

        masked = logger._mask_key("sk-abcdefgh123456")

        assert masked == "sk-a****"
        assert "abcdefgh" not in masked

    @pytest.mark.asyncio
    async def test_format_headers_redacts_sensitive(self):
        logger = LoggingMiddleware()

        headers = {
            "Authorization": "Bearer secret_token",
            "X-API-Key": "secret_key",
            "User-Agent": "MyApp/1.0",
            "Content-Type": "application/json"
        }

        formatted = logger._format_headers(headers)

        assert "[REDACTED]" in formatted
        assert "secret_token" not in formatted
        assert "secret_key" not in formatted
        assert "MyApp/1.0" in formatted

    @pytest.mark.asyncio
    async def test_before_request_logs(self):
        logger = LoggingMiddleware(verbose=True)
        req = create_request_info()

        with patch.object(logger.logger, 'info') as mock_log:
            await logger.before_request(req)
            mock_log.assert_called()

    @pytest.mark.asyncio
    async def test_after_request_logs_success(self):
        logger = LoggingMiddleware()
        req = create_request_info()
        resp = create_response_info(status_code=200, request_info=req)

        with patch.object(logger.logger, 'log') as mock_log:
            await logger.after_request(resp)
            mock_log.assert_called()

    @pytest.mark.asyncio
    async def test_after_request_logs_error(self):
        logger = LoggingMiddleware()
        req = create_request_info()
        resp = create_response_info(status_code=500, request_info=req)

        with patch.object(logger.logger, 'log') as mock_log:
            await logger.after_request(resp)
            # Should use ERROR level
            assert mock_log.call_args[0][0] == logging.ERROR

    @pytest.mark.asyncio
    async def test_on_error_logs(self):
        logger = LoggingMiddleware()
        error = create_error_info()

        with patch.object(logger.logger, 'error') as mock_log:
            result = await logger.on_error(error)
            mock_log.assert_called()
            assert result is False  # Should not handle error


# ============================================================================
# RATE LIMIT MIDDLEWARE TESTS
# ============================================================================

class TestRateLimitMiddleware:
    """Test RateLimitMiddleware functionality"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        rate_limit = RateLimitMiddleware(pause_on_limit=True)
        assert rate_limit.pause_on_limit is True
        assert len(rate_limit.rate_limits) == 0

    @pytest.mark.asyncio
    async def test_before_request_no_limit(self):
        rate_limit = RateLimitMiddleware()
        req = create_request_info()

        result = await rate_limit.before_request(req)

        assert result == req

    @pytest.mark.asyncio
    async def test_after_request_extracts_headers(self):
        rate_limit = RateLimitMiddleware()
        req = create_request_info()
        resp = create_response_info(
            status_code=200,
            request_info=req,
            headers={
                'X-RateLimit-Limit': '100',
                'X-RateLimit-Remaining': '50',
                'X-RateLimit-Reset': str(int(time.time() + 60))
            }
        )

        await rate_limit.after_request(resp)

        assert 'test_key' in rate_limit.rate_limits
        assert rate_limit.rate_limits['test_key']['limit'] == 100
        assert rate_limit.rate_limits['test_key']['remaining'] == 50

    @pytest.mark.asyncio
    async def test_after_request_retry_after(self):
        rate_limit = RateLimitMiddleware()
        req = create_request_info()
        resp = create_response_info(
            status_code=429,
            request_info=req,
            headers={'Retry-After': '60'}
        )

        await rate_limit.after_request(resp)

        assert 'test_key' in rate_limit.rate_limits

    @pytest.mark.asyncio
    async def test_on_error_handles_429(self):
        rate_limit = RateLimitMiddleware()
        req = create_request_info()
        resp = create_response_info(
            status_code=429,
            request_info=req,
            headers={'Retry-After': '5'}
        )
        error = create_error_info(
            exception=Exception("Rate limited"),
            request_info=req,
            response_info=resp
        )

        result = await rate_limit.on_error(error)

        assert result is True  # Should handle the error
        assert 'test_key' in rate_limit.rate_limits

    @pytest.mark.asyncio
    async def test_pause_on_limit(self):
        rate_limit = RateLimitMiddleware(pause_on_limit=True)
        req = create_request_info()

        # Set rate limit that expires in 0.5 seconds
        rate_limit.rate_limits['test_key'] = {
            'reset_time': time.time() + 0.5
        }

        start = time.time()
        await rate_limit.before_request(req)
        elapsed = time.time() - start

        # Should have waited approximately 0.5 seconds
        assert elapsed >= 0.4  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_get_stats(self):
        rate_limit = RateLimitMiddleware()

        # Add some rate limits
        rate_limit.rate_limits['key1'] = {'reset_time': time.time() + 60}
        rate_limit.rate_limits['key2'] = {'reset_time': time.time() - 60}  # Expired

        stats = rate_limit.get_stats()

        assert stats['tracked_keys'] == 2
        assert stats['active_limits'] == 1  # Only one is active

    @pytest.mark.asyncio
    async def test_clear_limits(self):
        rate_limit = RateLimitMiddleware()

        rate_limit.rate_limits['key1'] = {'reset_time': time.time() + 60}
        rate_limit.rate_limits['key2'] = {'reset_time': time.time() + 60}

        rate_limit.clear_limits()

        assert len(rate_limit.rate_limits) == 0


# ============================================================================
# RETRY MIDDLEWARE TESTS
# ============================================================================

class TestRetryMiddleware:
    """Test RetryMiddleware functionality"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        retry = RetryMiddleware(max_retries=5, backoff_factor=2.0)
        assert retry.max_retries == 5
        assert retry.backoff_factor == 2.0
        assert len(retry.retry_counts) == 0

    @pytest.mark.asyncio
    async def test_before_request_passthrough(self):
        retry = RetryMiddleware()
        req = create_request_info()

        result = await retry.before_request(req)

        assert result == req

    @pytest.mark.asyncio
    async def test_after_request_successful(self):
        retry = RetryMiddleware()
        req = create_request_info(url="http://example.com/api")
        resp = create_response_info(status_code=200, request_info=req)

        # Set retry count
        retry.retry_counts["http://example.com/api"] = 2

        await retry.after_request(resp)

        # Should remove successful URL from tracking
        assert "http://example.com/api" not in retry.retry_counts

    @pytest.mark.asyncio
    async def test_on_error_retries(self):
        retry = RetryMiddleware(max_retries=3, backoff_factor=2.0)
        req = create_request_info(url="http://example.com/api")
        error = create_error_info(request_info=req)

        start = time.time()
        result = await retry.on_error(error)
        elapsed = time.time() - start

        assert result is True  # Should retry
        assert retry.retry_counts["http://example.com/api"] == 1
        # Should have waited (backoff_factor ^ 0 = 1 second)
        assert elapsed >= 0.9

    @pytest.mark.asyncio
    async def test_on_error_max_retries_exceeded(self):
        retry = RetryMiddleware(max_retries=2, backoff_factor=1.0)
        req = create_request_info(url="http://example.com/api")
        error = create_error_info(request_info=req)

        # Exhaust retries
        retry.retry_counts["http://example.com/api"] = 2

        result = await retry.on_error(error)

        assert result is False  # Should not retry
        assert "http://example.com/api" not in retry.retry_counts

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        retry = RetryMiddleware(max_retries=3, backoff_factor=2.0)
        req = create_request_info(url="http://example.com/api")

        # First retry - should wait 1 second (2^0)
        error1 = create_error_info(request_info=req)
        start1 = time.time()
        await retry.on_error(error1)
        elapsed1 = time.time() - start1
        assert 0.9 <= elapsed1 <= 1.5

        # Second retry - should wait 2 seconds (2^1)
        error2 = create_error_info(request_info=req)
        start2 = time.time()
        await retry.on_error(error2)
        elapsed2 = time.time() - start2
        assert 1.9 <= elapsed2 <= 2.5

    @pytest.mark.asyncio
    async def test_get_stats(self):
        retry = RetryMiddleware()

        retry.retry_counts["http://example.com/api1"] = 1
        retry.retry_counts["http://example.com/api2"] = 2

        stats = retry.get_stats()

        assert stats['tracked_urls'] == 2
        assert stats['active_retries'] == 2

    @pytest.mark.asyncio
    async def test_clear_retries(self):
        retry = RetryMiddleware()

        retry.retry_counts["http://example.com/api1"] = 1
        retry.retry_counts["http://example.com/api2"] = 2

        retry.clear_retries()

        assert len(retry.retry_counts) == 0

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        retry = RetryMiddleware(max_tracked_urls=3)

        # Add 4 URLs (exceeds limit)
        for i in range(4):
            req = create_request_info(url=f"http://example.com/api{i}")
            error = create_error_info(request_info=req)
            await retry.on_error(error)
            print(f"After adding URL {i}: retry_counts size = {len(retry.retry_counts)}")

        # Should have evicted oldest
        print(f"Final retry_counts size: {len(retry.retry_counts)}, expected: 3")
        print(f"URLs: {list(retry.retry_counts.keys())}")
        assert len(retry.retry_counts) == 3


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestMiddlewareIntegration:
    """Test middleware working together"""

    @pytest.mark.asyncio
    async def test_multiple_middleware_before_request(self):
        cache = CachingMiddleware()
        logger = LoggingMiddleware()
        req = create_request_info()

        # Both should process the request
        result1 = await cache.before_request(req)
        result2 = await logger.before_request(result1)

        assert result2 == req

    @pytest.mark.asyncio
    async def test_multiple_middleware_after_request(self):
        cache = CachingMiddleware()
        rate_limit = RateLimitMiddleware()
        req = create_request_info()
        resp = create_response_info(
            status_code=200,
            request_info=req,
            headers={'X-RateLimit-Remaining': '50'}
        )

        # Both should process the response
        result1 = await cache.after_request(resp)
        result2 = await rate_limit.after_request(result1)

        assert result2 == resp
        assert len(cache.cache) == 1
        assert 'test_key' in rate_limit.rate_limits

    @pytest.mark.asyncio
    async def test_middleware_error_handling_chain(self):
        retry = RetryMiddleware(max_retries=1, backoff_factor=1.0)
        logger = LoggingMiddleware()
        req = create_request_info()
        error = create_error_info(request_info=req)

        # Retry handles error
        with patch.object(logger.logger, 'error'):
            retry_result = await retry.on_error(error)
            logger_result = await logger.on_error(error)

        assert retry_result is True  # Retry handles it
        assert logger_result is False  # Logger only logs


# ============================================================================
# EDGE CASES
# ============================================================================

class TestMiddlewareEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_cache_with_none_content(self):
        cache = CachingMiddleware()
        req = create_request_info()
        resp = create_response_info(status_code=200, request_info=req, content=None)

        await cache.after_request(resp)

        # Should still cache
        assert len(cache.cache) == 1

    @pytest.mark.asyncio
    async def test_rate_limit_with_invalid_headers(self):
        rate_limit = RateLimitMiddleware()
        req = create_request_info()
        resp = create_response_info(
            status_code=200,
            request_info=req,
            headers={
                'X-RateLimit-Limit': 'invalid',  # Not a number
                'X-RateLimit-Remaining': 'also-invalid'
            }
        )

        # Should not crash
        await rate_limit.after_request(resp)

    @pytest.mark.asyncio
    async def test_retry_with_zero_backoff(self):
        # backoff_factor ** 0 = 1 regardless of the factor value
        # So even with backoff_factor=0.1, first retry waits 0.1^0 = 1 second
        retry = RetryMiddleware(max_retries=1, backoff_factor=0.1)
        req = create_request_info()
        error = create_error_info(request_info=req)

        start = time.time()
        await retry.on_error(error)
        elapsed = time.time() - start

        # First retry: backoff_factor^0 = 1 second
        assert 0.9 <= elapsed <= 1.5

    @pytest.mark.asyncio
    async def test_logger_with_missing_attributes(self):
        logger = LoggingMiddleware()
        req = create_request_info()
        resp = create_response_info(status_code=200, request_info=req)

        # Should not crash even without response_time attribute
        with patch.object(logger.logger, 'log'):
            await logger.after_request(resp)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])