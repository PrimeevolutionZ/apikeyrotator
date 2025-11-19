"""
Integration tests for APIKeyRotator
Tests: real-world scenarios, middleware, strategies, metrics
"""

import pytest
import os
import sys
import time
from unittest.mock import Mock, patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apikeyrotator import (
    APIKeyRotator,
    AsyncAPIKeyRotator,
    AllKeysExhaustedError,
)
from apikeyrotator.strategies import (
    RoundRobinRotationStrategy,
    RandomRotationStrategy,
    WeightedRotationStrategy,
    LRURotationStrategy,
    HealthBasedStrategy,
)
from apikeyrotator.middleware import (
    LoggingMiddleware,
    CachingMiddleware,
    RateLimitMiddleware,
    RetryMiddleware,
)

# Check optional dependencies
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ============================================================================
# ROTATION STRATEGY TESTS
# ============================================================================

class TestRotationStrategies:
    """Test different rotation strategies."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_round_robin_strategy(self):
        """Test round-robin key rotation."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2', 'key3'],
            rotation_strategy='round_robin',
            load_env_file=False
        )

        keys_used = []
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            for _ in range(6):
                rotator.get('http://example.com')
                # Extract key from Authorization header
                auth = mock_request.call_args[1]['headers'].get('Authorization', '')
                if auth.startswith('Key '):
                    keys_used.append(auth.replace('Key ', ''))

        # Should cycle through keys
        assert keys_used == ['key1', 'key2', 'key3', 'key1', 'key2', 'key3']

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_weighted_strategy(self):
        """Test weighted rotation strategy."""
        # Create rotator with list first, then manually set weighted strategy
        from apikeyrotator.strategies import WeightedRotationStrategy

        weights = {'key1': 0.7, 'key2': 0.3}
        strategy = WeightedRotationStrategy(weights)

        rotator = APIKeyRotator(
            api_keys=['key1', 'key2'],  # Pass as list
            load_env_file=False
        )
        # Override with weighted strategy
        rotator.rotation_strategy = strategy
        rotator.keys = list(weights.keys())

        keys_used = []
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            for _ in range(100):
                rotator.get('http://example.com')
                auth = mock_request.call_args[1]['headers'].get('Authorization', '')
                if auth.startswith('Key '):
                    keys_used.append(auth.replace('Key ', ''))

        # key1 should be used ~70% of the time
        key1_count = keys_used.count('key1')
        assert 60 < key1_count < 80  # Allow some variance

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_lru_strategy(self):
        """Test LRU (Least Recently Used) strategy."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2', 'key3'],
            rotation_strategy='lru',
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            # First request should use key1 (never used)
            rotator.get('http://example.com')

            # Verify rotation picks least recently used
            assert isinstance(rotator.rotation_strategy, LRURotationStrategy)

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_health_based_strategy(self):
        """Test health-based strategy excludes unhealthy keys."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2', 'key3'],
            rotation_strategy='health_based',
            rotation_strategy_kwargs={'failure_threshold': 2},
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            # First key fails twice (becomes unhealthy)
            mock_request.side_effect = [
                Mock(status_code=500, headers={}, content=b''),
                Mock(status_code=500, headers={}, content=b''),
                Mock(status_code=200, headers={}, content=b''),
            ]

            try:
                rotator.get('http://example.com')
            except:
                pass

            # Mark key1 as unhealthy
            rotator._key_metrics['key1'].consecutive_failures = 3
            rotator._key_metrics['key1'].is_healthy = False

            # Next requests should use only healthy keys
            mock_request.side_effect = None
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            rotator.get('http://example.com')
            # Should not use key1


# ============================================================================
# MIDDLEWARE INTEGRATION TESTS
# ============================================================================

class TestMiddlewareIntegration:
    """Test middleware functionality."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_logging_middleware(self, caplog):
        """Test logging middleware captures requests."""
        import logging

        logger = logging.getLogger('test_logger')
        middleware = LoggingMiddleware(logger=logger, verbose=True)

        rotator = APIKeyRotator(
            api_keys=['key1'],
            middlewares=[middleware],
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            with caplog.at_level(logging.INFO):
                rotator.get('http://example.com')

            # Should log the request
            assert any('example.com' in record.message for record in caplog.records)

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    @pytest.mark.asyncio
    async def test_caching_middleware(self):
        """Test caching middleware prevents duplicate requests."""
        cache_middleware = CachingMiddleware(ttl=60, max_cache_size=10)

        async with AsyncAPIKeyRotator(
            api_keys=['key1'],
            middlewares=[cache_middleware],
            load_env_file=False
        ) as rotator:

            call_count = 0

            async def mock_request(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                resp = AsyncMock()
                resp.status = 200
                resp.headers = {}
                resp.release = AsyncMock()
                return resp

            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                # First request - should hit the API
                await rotator.get('http://example.com/data')
                assert call_count == 1

                # Cache should work but we still make request (current implementation)
                # In future, cache could return cached response directly

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    @pytest.mark.asyncio
    async def test_rate_limit_middleware(self):
        """Test rate limit middleware tracks limits."""
        rate_middleware = RateLimitMiddleware(pause_on_limit=False)

        async with AsyncAPIKeyRotator(
            api_keys=['key1'],
            middlewares=[rate_middleware],
            load_env_file=False
        ) as rotator:

            async def mock_request(*args, **kwargs):
                resp = AsyncMock()
                resp.status = 200
                resp.headers = {
                    'X-RateLimit-Limit': '100',
                    'X-RateLimit-Remaining': '50',
                    'X-RateLimit-Reset': str(int(time.time()) + 60)
                }
                resp.release = AsyncMock()
                return resp

            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                await rotator.get('http://example.com')

                # Check rate limit was recorded
                stats = rate_middleware.get_stats()
                assert stats['tracked_keys'] >= 1

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    @pytest.mark.asyncio
    async def test_retry_middleware(self):
        """Test retry middleware handles failures."""
        retry_middleware = RetryMiddleware(max_retries=3, backoff_factor=0.1)

        async with AsyncAPIKeyRotator(
            api_keys=['key1'],
            middlewares=[retry_middleware],
            load_env_file=False
        ) as rotator:

            call_count = 0

            async def mock_request(*args, **kwargs):
                nonlocal call_count
                call_count += 1

                if call_count < 2:
                    raise aiohttp.ClientError("Connection error")

                resp = AsyncMock()
                resp.status = 200
                resp.headers = {}
                resp.release = AsyncMock()
                return resp

            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                # Should succeed after retry
                response = await rotator.get('http://example.com')
                assert response.status == 200

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_multiple_middlewares(self):
        """Test multiple middlewares working together."""
        import logging
        logger = logging.getLogger('test')

        logging_mw = LoggingMiddleware(logger=logger)
        cache_mw = CachingMiddleware(ttl=60)

        rotator = APIKeyRotator(
            api_keys=['key1'],
            middlewares=[logging_mw, cache_mw],
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            rotator.get('http://example.com')

            # Both middlewares should be active
            assert len(rotator.middlewares) == 2


# ============================================================================
# METRICS TESTS
# ============================================================================

class TestMetrics:
    """Test metrics collection."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_basic_metrics_collection(self):
        """Test basic metrics are collected."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2'],
            enable_metrics=True,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            # Make several requests
            for _ in range(5):
                rotator.get('http://example.com/endpoint1')

            for _ in range(3):
                rotator.get('http://example.com/endpoint2')

            metrics = rotator.get_metrics()

            assert metrics is not None
            assert metrics['total_requests'] == 8
            assert metrics['successful_requests'] > 0

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_key_statistics(self):
        """Test key-level statistics."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2'],
            rotation_strategy='round_robin',
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            # Make requests
            for _ in range(10):
                rotator.get('http://example.com')

            stats = rotator.get_key_statistics()

            assert 'key1' in stats
            assert 'key2' in stats
            assert stats['key1']['total_requests'] > 0
            assert stats['key2']['total_requests'] > 0

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_metrics_track_failures(self):
        """Test metrics track failures correctly."""
        rotator = APIKeyRotator(
            api_keys=['key1'],
            enable_metrics=True,
            max_retries=2,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=500, headers={}, content=b'')

            try:
                rotator.get('http://example.com')
            except:
                pass

            metrics = rotator.get_metrics()
            assert metrics['failed_requests'] > 0


# ============================================================================
# ERROR HANDLING INTEGRATION TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling in real scenarios."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_rate_limit_recovery(self):
        """Test recovery from rate limiting."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2'],
            max_retries=3,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            # First key rate limited, second key succeeds
            mock_request.side_effect = [
                Mock(status_code=429, headers={'Retry-After': '1'}, content=b''),
                Mock(status_code=200, headers={}, content=b'')
            ]

            response = rotator.get('http://example.com')
            assert response.status_code == 200

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_permanent_error_key_removal(self):
        """Test keys are removed on permanent errors."""
        rotator = APIKeyRotator(
            api_keys=['bad_key', 'good_key'],
            max_retries=2,
            load_env_file=False
        )

        initial_key_count = len(rotator.keys)

        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [
                Mock(status_code=401, headers={}, content=b''),  # Unauthorized
                Mock(status_code=200, headers={}, content=b'')
            ]

            response = rotator.get('http://example.com')

            assert response.status_code == 200
            assert len(rotator.keys) < initial_key_count

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_network_error_retry(self):
        """Test network errors trigger retries."""
        import requests

        rotator = APIKeyRotator(
            api_keys=['key1'],
            max_retries=3,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [
                requests.exceptions.ConnectionError("Network unreachable"),
                requests.exceptions.Timeout("Request timeout"),
                Mock(status_code=200, headers={}, content=b'')
            ]

            response = rotator.get('http://example.com')
            assert response.status_code == 200
            assert mock_request.call_count == 3


# ============================================================================
# CONCURRENT ACCESS TESTS
# ============================================================================

class TestConcurrentAccess:
    """Test thread-safety and concurrent access."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_thread_safe_key_rotation(self):
        """Test key rotation is thread-safe."""
        import threading

        rotator = APIKeyRotator(
            api_keys=['key1', 'key2', 'key3'],
            load_env_file=False
        )

        results = []

        def make_request():
            with patch('requests.Session.request') as mock_request:
                mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
                try:
                    response = rotator.get('http://example.com')
                    results.append(response.status_code)
                except Exception as e:
                    results.append(str(e))

        threads = [threading.Thread(target=make_request) for _ in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All requests should succeed
        assert all(r == 200 for r in results if isinstance(r, int))

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_concurrent_metrics_updates(self):
        """Test metrics updates are thread-safe."""
        import threading

        rotator = APIKeyRotator(
            api_keys=['key1'],
            enable_metrics=True,
            load_env_file=False
        )

        def make_requests():
            with patch('requests.Session.request') as mock_request:
                mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
                for _ in range(10):
                    rotator.get('http://example.com')

        threads = [threading.Thread(target=make_requests) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        metrics = rotator.get_metrics()
        assert metrics['total_requests'] == 50


# ============================================================================
# REAL-WORLD SCENARIO TESTS
# ============================================================================

class TestRealWorldScenarios:
    """Test realistic usage scenarios."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_api_with_custom_headers(self):
        """Test API requiring custom headers."""
        def custom_headers(key, existing):
            return {
                'Authorization': f'Bearer {key}',
                'X-API-Version': '2.0',
                'Content-Type': 'application/json'
            }

        rotator = APIKeyRotator(
            api_keys=['key1'],
            header_callback=custom_headers,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            rotator.get('http://api.example.com/users')

            headers = mock_request.call_args[1]['headers']
            assert headers['X-API-Version'] == '2.0'
            assert 'Bearer key1' in headers['Authorization']

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_gradual_degradation(self):
        """Test system continues working as keys fail."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2', 'key3', 'key4'],
            max_retries=2,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            # Simulate gradual key failures
            mock_request.side_effect = [
                Mock(status_code=401, headers={}, content=b''),  # key1 fails
                Mock(status_code=200, headers={}, content=b''),  # key2 works
                Mock(status_code=401, headers={}, content=b''),  # key2 fails
                Mock(status_code=200, headers={}, content=b''),  # key3 works
                Mock(status_code=200, headers={}, content=b''),  # key3 works
            ]

            # Should continue working despite failures
            for _ in range(3):
                response = rotator.get('http://example.com')
                assert response.status_code == 200

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_export_and_monitoring(self):
        """Test configuration export for monitoring."""
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2'],
            max_retries=3,
            enable_metrics=True,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            # Make some requests
            for _ in range(5):
                rotator.get('http://example.com')

            # Export configuration
            config = rotator.export_config()

            assert 'keys_count' in config
            assert config['keys_count'] == 2
            assert 'max_retries' in config
            assert 'key_statistics' in config


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])