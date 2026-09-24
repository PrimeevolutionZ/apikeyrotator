"""
Regression tests for bugs fixed in 0.7.0 and for load-resilience behaviour
of the rotator core.
"""

import os
import sys
import threading
import time
from unittest.mock import Mock, patch

import pytest
import requests


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apikeyrotator import (
    AllKeysExhaustedError,
    AllProvidersExhaustedError,
    APIKeyRotator,
    AsyncAPIKeyRotator,
    ErrorClassifier,
    FallbackRouter,
    KeyMetrics,
    ProviderRoute,
    RotatorMetrics,
    WeightedRotationStrategy,
)
from apikeyrotator.strategies import LRURotationStrategy, RoundRobinRotationStrategy


def resp(status=200, headers=None, content=b''):
    return Mock(status_code=status, headers=headers or {}, content=content)


def make_rotator(keys=('k1', 'k2'), **kwargs):
    kwargs.setdefault('load_env_file', False)
    kwargs.setdefault('base_delay', 0.01)
    return APIKeyRotator(api_keys=list(keys), **kwargs)


def used_keys(mock_request):
    return [c[1]['headers']['Authorization'].replace('Key ', '') for c in mock_request.call_args_list]


# ============================================================================
# ERROR HANDLING
# ============================================================================

class TestClientErrors:

    def test_404_does_not_remove_key(self):
        """A wrong URL must not burn through the whole key pool."""
        rotator = make_rotator(['k1', 'k2', 'k3'])
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(404)
            response = rotator.get('http://example.com/missing')
        assert response.status_code == 404
        assert mock_request.call_count == 1
        assert rotator.keys == ['k1', 'k2', 'k3']

    @pytest.mark.parametrize("status", [400, 404, 422])
    def test_client_errors_are_returned_without_retry(self, status):
        rotator = make_rotator()
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(status)
            assert rotator.get('http://example.com').status_code == status
        assert mock_request.call_count == 1
        assert rotator.get_metrics()['failed_requests'] == 1

    def test_401_removes_key_and_switches(self):
        rotator = make_rotator(['bad', 'good'])
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(401), resp(200)]
            assert rotator.get('http://example.com').status_code == 200
        assert rotator.keys == ['good']

    def test_all_keys_invalid_raises(self):
        rotator = make_rotator(['a', 'b'])
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(403)
            with pytest.raises(AllKeysExhaustedError):
                rotator.get('http://example.com')
        assert rotator.keys == []

    def test_should_remove_key_with_real_falsy_response(self):
        """requests.Response is falsy for error codes - classifier must not rely on truthiness."""
        response = requests.Response()
        response.status_code = 401
        assert not bool(response)
        assert ErrorClassifier().should_remove_key(response) is True

    def test_get_retry_delay_with_real_falsy_response(self):
        response = requests.Response()
        response.status_code = 429
        response.headers['Retry-After'] = '7'
        assert ErrorClassifier().get_retry_delay(response) == 7.0

    def test_exhausted_error_carries_last_response(self):
        rotator = make_rotator(['k1'], max_retries=2)
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(503)
            with pytest.raises(AllKeysExhaustedError) as exc_info:
                rotator.get('http://example.com')
        assert exc_info.value.last_response.status_code == 503

    def test_exhausted_error_chains_network_exception(self):
        rotator = make_rotator(['k1'], max_retries=2)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = requests.ConnectionError("down")
            with pytest.raises(AllKeysExhaustedError) as exc_info:
                rotator.get('http://example.com')
        assert isinstance(exc_info.value.last_exception, requests.ConnectionError)
        assert "down" in str(exc_info.value)


# ============================================================================
# RATE LIMITS
# ============================================================================

class TestRateLimitHandling:

    def test_429_switches_key_without_sleeping(self):
        rotator = make_rotator(['k1', 'k2'], base_delay=5.0)
        with patch('requests.Session.request') as mock_request, \
                patch('apikeyrotator.core.rotator.time.sleep') as mock_sleep:
            mock_request.side_effect = [resp(429), resp(200)]
            assert rotator.get('http://example.com').status_code == 200
        assert used_keys(mock_request) == ['k1', 'k2']
        mock_sleep.assert_not_called()

    def test_retry_after_marks_key_and_it_is_skipped(self):
        rotator = make_rotator(['k1', 'k2', 'k3'])
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(429, {'Retry-After': '120'})] + [resp(200)] * 4
            for _ in range(3):
                rotator.get('http://example.com')
        keys = used_keys(mock_request)
        assert keys[0] == 'k1'
        assert 'k1' not in keys[1:]
        assert rotator._key_metrics['k1'].rate_limit_reset > time.time() + 100

    def test_all_keys_rate_limited_waits_for_earliest_reset(self):
        rotator = make_rotator(['k1', 'k2'], base_delay=0.01, max_delay=30)
        with patch('requests.Session.request') as mock_request, \
                patch('apikeyrotator.core.rotator.time.sleep') as mock_sleep:
            mock_request.side_effect = [
                resp(429, {'Retry-After': '20'}),
                resp(429, {'Retry-After': '5'}),
                resp(200),
            ]
            assert rotator.get('http://example.com').status_code == 200
        waits = [c[0][0] for c in mock_sleep.call_args_list]
        assert len(waits) == 1
        assert 4 < waits[0] <= 5

    def test_rate_limit_wait_is_capped(self):
        rotator = make_rotator(['k1'], max_delay=2)
        with patch('requests.Session.request') as mock_request, \
                patch('apikeyrotator.core.rotator.time.sleep') as mock_sleep:
            mock_request.side_effect = [resp(429, {'Retry-After': '3600'}), resp(200)]
            rotator.get('http://example.com')
        assert mock_sleep.call_args[0][0] <= 2

    def test_rate_limit_does_not_mark_key_unhealthy_forever(self):
        metrics = KeyMetrics('k')
        metrics.mark_rate_limited(time.time() + 1)
        metrics.update_from_request(success=False, is_rate_limited=True)
        assert metrics.is_healthy is True
        assert metrics.is_available(time.time() + 2) is True

    def test_backoff_is_capped(self):
        rotator = make_rotator(base_delay=1.0, max_delay=10.0)
        assert rotator._calculate_backoff_delay(50) <= 10.0


# ============================================================================
# KEY HEALTH & RECOVERY
# ============================================================================

class TestKeyRecovery:

    def test_unhealthy_key_is_probed_after_recovery_timeout(self):
        strategy = RoundRobinRotationStrategy(['k1', 'k2'])
        strategy.recovery_timeout = 10
        m1, m2 = KeyMetrics('k1'), KeyMetrics('k2')
        for _ in range(3):
            m1.update_from_request(success=False)
        assert m1.is_healthy is False
        metrics = {'k1': m1, 'k2': m2}

        assert set(strategy.get_next_key(metrics) for _ in range(4)) == {'k2'}

        m1.last_failure = time.time() - 11
        assert 'k1' in {strategy.get_next_key(metrics) for _ in range(4)}

    def test_rotator_recovery_timeout_param(self):
        rotator = make_rotator(recovery_timeout=5)
        assert rotator.rotation_strategy.recovery_timeout == 5

    def test_reset_key_health_clears_rate_limit(self):
        rotator = make_rotator()
        rotator._key_metrics['k1'].mark_rate_limited(time.time() + 100)
        rotator.reset_key_health('k1')
        assert rotator._key_metrics['k1'].rate_limit_reset == 0.0

    def test_keys_setter_preserves_metrics(self):
        rotator = make_rotator(['k1', 'k2'])
        rotator._key_metrics['k1'].update_from_request(success=True, response_time=0.2)
        rotator.keys = ['k1', 'k3']
        stats = rotator.get_key_statistics()
        assert stats['k1']['total_requests'] == 1
        assert stats['k3']['total_requests'] == 0

    def test_duplicate_keys_are_removed(self):
        rotator = make_rotator(['k1', 'k1', 'k2'])
        assert rotator.keys == ['k1', 'k2']


# ============================================================================
# STRATEGIES
# ============================================================================

class TestStrategies:

    def test_weighted_strategy_by_name(self):
        """Regression: rotation_strategy='weighted' always raised ValueError."""
        rotator = make_rotator(['k1', 'k2'], rotation_strategy='weighted',
                               rotation_strategy_kwargs={'weights': {'k1': 9, 'k2': 1}})
        assert isinstance(rotator.rotation_strategy, WeightedRotationStrategy)
        picks = [rotator.get_next_key() for _ in range(500)]
        assert picks.count('k1') > picks.count('k2') * 3

    def test_weighted_strategy_by_name_default_equal_weights(self):
        rotator = make_rotator(['k1', 'k2'], rotation_strategy='weighted')
        picks = {rotator.get_next_key() for _ in range(100)}
        assert picks == {'k1', 'k2'}

    def test_weighted_rejects_invalid_weights(self):
        with pytest.raises(ValueError):
            WeightedRotationStrategy({'k1': 0, 'k2': 0})
        with pytest.raises(ValueError):
            WeightedRotationStrategy({'k1': -1})

    def test_lru_is_unique_under_concurrency(self):
        keys = [f'k{i}' for i in range(20)]
        strategy = LRURotationStrategy(keys)
        picked, lock = [], threading.Lock()
        barrier = threading.Barrier(20)

        def worker():
            barrier.wait()
            k = strategy.get_next_key()
            with lock:
                picked.append(k)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(picked) == sorted(keys)


# ============================================================================
# METRICS & REQUEST HANDLING
# ============================================================================

class TestMetricsAndRequests:

    def test_response_time_is_per_attempt(self):
        """Regression: response time included all previous retries and sleeps."""
        rotator = make_rotator(['k1'], base_delay=0.2)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(500), resp(200)]
            rotator.get('http://example.com')
        assert rotator.get_key_statistics()['k1']['avg_response_time'] < 0.1

    def test_endpoint_metrics_ignore_query_string(self):
        rotator = make_rotator()
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(200)
            for i in range(50):
                rotator.get(f'http://example.com/items?id={i}')
        assert list(rotator.get_metrics()['endpoint_stats']) == ['http://example.com/items']

    def test_endpoint_metrics_are_bounded(self):
        metrics = RotatorMetrics(max_endpoints=10)
        for i in range(100):
            metrics.record_request('k', f'http://e.com/{i}', True, 0.01)
        assert len(metrics.endpoint_stats) == 11
        assert metrics.get_endpoint_stats(RotatorMetrics.OVERFLOW_ENDPOINT)['total_requests'] == 90

    def test_existing_auth_header_is_respected_case_insensitively(self):
        rotator = make_rotator(['k1'])
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(200)
            rotator.get('http://example.com', headers={'authorization': 'Bearer custom'})
        headers = mock_request.call_args[1]['headers']
        assert headers == {'authorization': 'Bearer custom'}

    def test_user_cookies_are_kept(self):
        rotator = make_rotator(['k1'])
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(200)
            rotator.get('http://example.com', cookies={'sid': '1'})
        assert mock_request.call_args[1]['cookies'] == {'sid': '1'}

    def test_stream_response_body_not_consumed(self):
        from apikeyrotator import LoggingMiddleware
        rotator = make_rotator(['k1'], middlewares=[LoggingMiddleware()])
        response = Mock(status_code=200, headers={})
        type(response).content = property(lambda self: pytest.fail("body consumed"))
        with patch('requests.Session.request', return_value=response):
            assert rotator.get('http://example.com', stream=True) is response

    def test_patch_and_head_methods(self):
        rotator = make_rotator(['k1'])
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = resp(200)
            rotator.patch('http://example.com')
            rotator.head('http://example.com')
        assert [c[0][0] for c in mock_request.call_args_list] == ['PATCH', 'HEAD']

    def test_context_manager_closes_session(self):
        with make_rotator() as rotator:
            session = rotator.session
        with patch.object(session, 'close') as close:
            rotator.close()
            close.assert_called_once()

    def test_invalid_max_retries(self):
        with pytest.raises(ValueError):
            make_rotator(max_retries=0)


# ============================================================================
# ROUTER
# ============================================================================

class TestRouter:

    def test_sync_fallback(self):
        primary = make_rotator(['p1'], max_retries=1)
        backup = make_rotator(['b1'])
        router = FallbackRouter([ProviderRoute(primary, 'primary'), ProviderRoute(backup, 'backup')])
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(429), resp(200)]
            assert router.get('http://example.com').status_code == 200

    def test_all_providers_exhausted(self):
        router = FallbackRouter([ProviderRoute(make_rotator(['p1'], max_retries=1))])
        with patch('requests.Session.request', return_value=resp(429)):
            with pytest.raises(AllProvidersExhaustedError):
                router.get('http://example.com')

    @pytest.mark.asyncio
    async def test_async_route_works(self):
        """Regression: request_async() called a non-existent rotator method."""
        rotator = AsyncAPIKeyRotator(api_keys=['a1'], load_env_file=False)
        router = FallbackRouter([ProviderRoute(rotator, 'async')])

        async def mock_request(*args, **kwargs):
            r = Mock()
            r.status = 200
            r.headers = {}
            return r

        with patch('aiohttp.ClientSession.request', side_effect=mock_request):
            response = await router.get_async('http://example.com')
        await rotator.close()
        assert response.status == 200

    def test_transformer_does_not_mutate_caller_kwargs(self):
        rotator = make_rotator(['k1'])

        def transformer(method, url, kwargs):
            kwargs['json'] = {'changed': True}
            return method, url, kwargs

        router = FallbackRouter([ProviderRoute(rotator, request_transformer=transformer)])
        original = {'json': {'changed': False}}
        with patch('requests.Session.request', return_value=resp(200)):
            router.request('POST', 'http://example.com', **original)
        assert original == {'json': {'changed': False}}


# ============================================================================
# ASYNC
# ============================================================================

class TestAsyncRotator:

    @pytest.mark.asyncio
    async def test_async_404_returned_and_key_kept(self):
        async def mock_request(*args, **kwargs):
            r = Mock()
            r.status = 404
            r.headers = {}
            return r

        async with AsyncAPIKeyRotator(api_keys=['a', 'b'], load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                response = await rotator.get('http://example.com')
            assert response.status == 404
            assert rotator.keys == ['a', 'b']

    @pytest.mark.asyncio
    async def test_async_retry_releases_failed_responses(self):
        responses = []

        async def mock_request(*args, **kwargs):
            r = Mock()
            r.status = 503 if not responses else 200
            r.headers = {}
            responses.append(r)
            return r

        async with AsyncAPIKeyRotator(api_keys=['a'], base_delay=0.01, load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                response = await rotator.get('http://example.com')
        assert response.status == 200
        responses[0].release.assert_called_once()
        responses[1].release.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_numeric_timeout_is_converted(self):
        import aiohttp
        captured = {}

        async def mock_request(*args, **kwargs):
            captured.update(kwargs)
            r = Mock()
            r.status = 200
            r.headers = {}
            return r

        async with AsyncAPIKeyRotator(api_keys=['a'], load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                await rotator.get('http://example.com', timeout=3)
        assert isinstance(captured['timeout'], aiohttp.ClientTimeout)
        assert captured['timeout'].total == 3
