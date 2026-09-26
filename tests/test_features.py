"""
Tests for 0.8.0 features: safe retries of non-idempotent requests, request
deadlines, per-host circuit breaker, client-side key rate limiting, shared
state (Redis), background key refresh, httpx backend and lazy imports.
"""

import asyncio
import json
import subprocess
import sys
import threading
import time
from unittest.mock import Mock, patch

import httpx
import pytest
import requests
import urllib3

from apikeyrotator import (
    AllKeysExhaustedError,
    APIKeyRotator,
    AsyncAPIKeyRotator,
    CachingMiddleware,
    CircuitOpenError,
    DeadlineExceededError,
    FallbackRouter,
    FileSecretProvider,
    ProviderRoute,
)
from apikeyrotator.state import InMemoryStateBackend, RedisStateBackend, TokenBucket, key_id
from apikeyrotator.utils import CircuitBreaker, CircuitBreakerConfig


def resp(status=200, headers=None, content=b'{"ok": true}'):
    return Mock(status_code=status, headers=headers or {}, content=content)


def make(keys=('k1', 'k2'), **kwargs):
    kwargs.setdefault('load_env_file', False)
    kwargs.setdefault('base_delay', 0.01)
    return APIKeyRotator(api_keys=list(keys), **kwargs)


def used_keys(mock_request):
    return [c[1]['headers']['Authorization'].replace('Bearer ', '') for c in mock_request.call_args_list]


def connect_refused():
    reason = urllib3.exceptions.NewConnectionError(None, "Connection refused")
    return requests.exceptions.ConnectionError(urllib3.exceptions.MaxRetryError(None, "/", reason))


# ============================================================================
# 1. SAFE RETRIES OF NON-IDEMPOTENT REQUESTS
# ============================================================================

class TestIdempotency:

    @pytest.mark.parametrize("status", [500, 502, 504])
    def test_post_is_not_retried_after_possibly_processed_error(self, status):
        rotator = make()
        with patch('requests.Session.request', return_value=resp(status)) as mock_request:
            assert rotator.post('http://api.test/charge').status_code == status
        assert mock_request.call_count == 1

    @pytest.mark.parametrize("status", [429, 503, 408, 425])
    def test_post_is_retried_when_request_was_not_processed(self, status):
        rotator = make()
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(status), resp(200)]
            assert rotator.post('http://api.test/charge').status_code == 200
        assert mock_request.call_count == 2

    def test_get_is_still_retried_on_500(self):
        rotator = make()
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(500), resp(200)]
            assert rotator.get('http://api.test/x').status_code == 200

    def test_idempotency_key_header_allows_retry(self):
        rotator = make()
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(500), resp(200)]
            response = rotator.post('http://api.test/charge', headers={'idempotency-key': 'abc'})
        assert response.status_code == 200

    def test_retry_non_idempotent_option(self):
        rotator = make(retry_non_idempotent=True)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(500), resp(200)]
            assert rotator.patch('http://api.test/x').status_code == 200

    def test_post_read_timeout_is_raised_not_retried(self):
        rotator = make()
        with patch('requests.Session.request', side_effect=requests.ReadTimeout("slow")) as mock_request:
            with pytest.raises(requests.ReadTimeout):
                rotator.post('http://api.test/charge')
        assert mock_request.call_count == 1

    def test_post_connection_refused_is_retried(self):
        rotator = make()
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [connect_refused(), resp(200)]
            assert rotator.post('http://api.test/charge').status_code == 200

    def test_post_connect_timeout_is_retried(self):
        rotator = make()
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [requests.ConnectTimeout("t/o"), resp(200)]
            assert rotator.post('http://api.test/charge').status_code == 200

    def test_post_401_still_switches_key(self):
        rotator = make(['bad', 'good'])
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(401), resp(200)]
            assert rotator.post('http://api.test/x').status_code == 200
        assert rotator.keys == ['good']

    @pytest.mark.asyncio
    async def test_async_post_500_not_retried(self):
        calls = 0

        async def mock_request(*args, **kwargs):
            nonlocal calls
            calls += 1
            r = Mock()
            r.status = 500
            r.headers = {}
            return r

        async with AsyncAPIKeyRotator(api_keys=['a'], load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                response = await rotator.post('http://api.test/charge')
        assert response.status == 500 and calls == 1


# ============================================================================
# 2. DEADLINE (total_timeout)
# ============================================================================

class TestDeadline:

    def test_deadline_stops_retries_instead_of_sleeping(self, virtual_clock):
        rotator = make(['k1'], max_retries=5, total_timeout=2.0)
        with patch('requests.Session.request', return_value=resp(503, {'Retry-After': '10'})):
            with pytest.raises(DeadlineExceededError) as exc_info:
                rotator.get('http://api.test/x')
        assert virtual_clock.sleeps == []  # never waited 10s knowing the budget is 2s
        assert exc_info.value.last_response.status_code == 503
        assert isinstance(exc_info.value, TimeoutError)
        assert isinstance(exc_info.value, AllKeysExhaustedError)

    def test_per_request_total_timeout_overrides_default(self, virtual_clock):
        rotator = make(['k1'], max_retries=5)
        with patch('requests.Session.request', return_value=resp(503, {'Retry-After': '3'})) as mock_request:
            with pytest.raises(DeadlineExceededError):
                rotator.get('http://api.test/x', total_timeout=5)
        # 1st attempt, wait 3s, 2nd attempt, next 3s wait would cross the 5s budget
        assert mock_request.call_count == 2
        assert 'total_timeout' not in mock_request.call_args[1]

    def test_attempt_timeout_is_clipped_to_remaining_budget(self):
        rotator = make(['k1'], timeout=30, total_timeout=2)
        with patch('requests.Session.request', return_value=resp(200)) as mock_request:
            rotator.get('http://api.test/x')
        assert mock_request.call_args[1]['timeout'] <= 2

    def test_router_does_not_fall_back_after_deadline(self, virtual_clock):
        primary = make(['p1'], max_retries=5, total_timeout=1)
        backup = make(['b1'])
        router = FallbackRouter([ProviderRoute(primary, 'primary'), ProviderRoute(backup, 'backup')])
        with patch('requests.Session.request', return_value=resp(503, {'Retry-After': '5'})) as mock_request:
            with pytest.raises(DeadlineExceededError):
                router.get('http://api.test/x')
        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_async_deadline(self, virtual_clock):
        async def mock_request(*args, **kwargs):
            r = Mock()
            r.status = 503
            r.headers = {'Retry-After': '10'}
            return r

        async with AsyncAPIKeyRotator(api_keys=['a'], max_retries=5, total_timeout=2,
                                      load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                with pytest.raises(DeadlineExceededError):
                    await rotator.get('http://api.test/x')


# ============================================================================
# 3. CIRCUIT BREAKER
# ============================================================================

class TestCircuitBreaker:

    def test_unit_open_half_open_close(self, virtual_clock):
        breaker = CircuitBreaker(failure_threshold=2, timeout=10)
        breaker.record_failure()
        assert breaker.allow_request()
        breaker.record_failure()
        assert breaker.get_state() == 'OPEN'
        assert not breaker.allow_request()
        assert 9 < breaker.retry_after() <= 10

        virtual_clock.advance(10)
        assert breaker.allow_request()  # probe
        assert not breaker.allow_request()  # only one probe at a time
        breaker.record_success()
        assert breaker.get_state() == 'CLOSED'
        assert breaker.allow_request()

    def test_failed_probe_reopens(self, virtual_clock):
        breaker = CircuitBreaker(failure_threshold=1, timeout=5)
        breaker.record_failure()
        virtual_clock.advance(5)
        assert breaker.allow_request()
        breaker.record_failure()
        assert breaker.get_state() == 'OPEN'
        assert not breaker.allow_request()

    def test_probe_slot_released_when_attempt_dies(self, virtual_clock):
        """A HALF_OPEN probe that ends in an exception must not block the circuit forever."""
        rotator = make(['k1'], max_retries=1, circuit_breaker=CircuitBreakerConfig(failure_threshold=1,
                                                                                 recovery_timeout=5))
        with patch('requests.Session.request', return_value=resp(500)):
            with pytest.raises(AllKeysExhaustedError):
                rotator.get('http://flaky.test/')
        virtual_clock.advance(5)
        with patch('requests.Session.request', side_effect=RuntimeError("bug in a hook")):
            with pytest.raises(RuntimeError):
                rotator.get('http://flaky.test/')  # probe dies without a verdict
        with patch('requests.Session.request', return_value=resp(200)):
            assert rotator.get('http://flaky.test/').status_code == 200
        assert rotator.get_circuit_states()['flaky.test'] == 'CLOSED'

    def test_config_validation(self):
        with pytest.raises(ValueError):
            CircuitBreakerConfig(failure_threshold=0)

    def test_rotator_fails_fast_when_host_is_down(self, virtual_clock):
        rotator = make(['k1'], max_retries=2,
                       circuit_breaker=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30))
        with patch('requests.Session.request', return_value=resp(500)) as mock_request:
            with pytest.raises(AllKeysExhaustedError):
                rotator.get('http://down.test/a')  # 2 failures
            with pytest.raises(CircuitOpenError) as exc_info:
                rotator.get('http://down.test/b')  # 3rd failure opens, then fails fast
            calls = mock_request.call_count
            with pytest.raises(CircuitOpenError):
                rotator.get('http://down.test/c')
            assert mock_request.call_count == calls  # no network call while open
        assert exc_info.value.host == 'down.test'
        assert rotator.get_circuit_states() == {'down.test': 'OPEN'}

        # Other hosts are not affected
        with patch('requests.Session.request', return_value=resp(200)):
            assert rotator.get('http://up.test/').status_code == 200

        # After the recovery timeout a probe goes through and closes the circuit
        virtual_clock.advance(30)
        with patch('requests.Session.request', return_value=resp(200)):
            assert rotator.get('http://down.test/d').status_code == 200
        assert rotator.get_circuit_states()['down.test'] == 'CLOSED'

    def test_network_errors_count_as_failures(self):
        rotator = make(['k1'], max_retries=5, circuit_breaker=CircuitBreakerConfig(failure_threshold=2))
        with patch('requests.Session.request', side_effect=requests.ConnectionError("down")) as mock_request:
            with pytest.raises(CircuitOpenError):
                rotator.get('http://down.test/')
        assert mock_request.call_count == 2  # stopped retrying once the circuit opened

    def test_client_errors_and_rate_limits_keep_circuit_closed(self):
        rotator = make(['k1', 'k2', 'k3'], circuit_breaker=CircuitBreakerConfig(failure_threshold=1))
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(404), resp(429), resp(200)]
            rotator.get('http://api.test/missing')
            rotator.get('http://api.test/x')
        assert rotator.get_circuit_states() == {'api.test': 'CLOSED'}

    def test_router_falls_back_on_open_circuit(self):
        primary = make(['p1'], max_retries=1, circuit_breaker=CircuitBreakerConfig(failure_threshold=1))
        backup = make(['b1'])
        router = FallbackRouter([ProviderRoute(primary, 'primary'), ProviderRoute(backup, 'backup')])
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(500), resp(200), resp(200)]
            router.get('http://api.test/x')  # primary 500 -> exhausted -> backup
            assert router.get('http://api.test/x').status_code == 200  # primary open -> backup
        assert mock_request.call_count == 3


# ============================================================================
# 4. CLIENT-SIDE RATE LIMIT (token bucket + X-RateLimit headers)
# ============================================================================

class TestKeyRateLimit:

    def test_token_bucket_unit(self):
        bucket = TokenBucket(capacity=2, refill_per_sec=1.0, now=0.0)
        assert bucket.acquire(0.0) == 0.0
        assert bucket.acquire(0.0) == 0.0
        assert bucket.acquire(0.0) == pytest.approx(1.0)
        assert bucket.acquire(1.0) == 0.0

    def test_keys_are_spread_by_their_limits(self, virtual_clock):
        rotator = make(['k1', 'k2'], key_rate_limit=(2, 60))
        with patch('requests.Session.request', return_value=resp(200)) as mock_request:
            for _ in range(4):
                rotator.get('http://api.test/x')
            assert virtual_clock.sleeps == []
            assert sorted(used_keys(mock_request)) == ['k1', 'k1', 'k2', 'k2']
            # 5th request: both keys used their budget -> wait for a token (30s)
            rotator.get('http://api.test/x')
        assert len(virtual_clock.sleeps) == 1
        assert 29 < virtual_clock.sleeps[0] <= 30.5

    def test_rate_limited_wait_respects_deadline(self, virtual_clock):
        rotator = make(['k1'], key_rate_limit=(1, 60), total_timeout=5)
        with patch('requests.Session.request', return_value=resp(200)):
            rotator.get('http://api.test/x')
            with pytest.raises(DeadlineExceededError):
                rotator.get('http://api.test/x')

    def test_invalid_key_rate_limit(self):
        with pytest.raises(ValueError):
            make(key_rate_limit=(0, 60))

    def test_remaining_zero_header_skips_key_before_429(self):
        reset = str(int(time.time()) + 60)
        rotator = make(['k1', 'k2'])
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [
                resp(200, {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': reset}),
                resp(200), resp(200),
            ]
            for _ in range(3):
                rotator.get('http://api.test/x')
        assert used_keys(mock_request) == ['k1', 'k2', 'k2']

    def test_remaining_headers_can_be_ignored(self):
        rotator = make(['k1', 'k2'], respect_rate_limit_headers=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(200, {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '60'}),
                                        resp(200), resp(200)]
            for _ in range(3):
                rotator.get('http://api.test/x')
        assert used_keys(mock_request) == ['k1', 'k2', 'k1']

    @pytest.mark.asyncio
    async def test_async_key_rate_limit(self, virtual_clock):
        async def mock_request(*args, **kwargs):
            r = Mock()
            r.status = 200
            r.headers = {}
            return r

        async with AsyncAPIKeyRotator(api_keys=['a'], key_rate_limit=(1, 10), load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                await rotator.get('http://api.test/x')
                await rotator.get('http://api.test/x')
        assert any(9 < s <= 10.5 for s in virtual_clock.sleeps)


# ============================================================================
# 5. SHARED STATE (Redis)
# ============================================================================

@pytest.fixture
def redis_client():
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeRedis()


class TestSharedState:

    def _pair(self, client, **kwargs):
        backend = RedisStateBackend(client=client, namespace="test")
        a = make(['k1', 'k2'], state_backend=backend, state_sync_interval=0, **kwargs)
        b = make(['k1', 'k2'], state_backend=RedisStateBackend(client=client, namespace="test"),
                 state_sync_interval=0, **kwargs)
        return a, b

    def test_invalid_key_is_shared(self, redis_client):
        a, b = self._pair(redis_client)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(401), resp(200)]
            a.get('http://api.test/x')
        assert a.keys == ['k2']
        with patch('requests.Session.request', return_value=resp(200)) as mock_request:
            b.get('http://api.test/x')
        assert b.keys == ['k2']
        assert used_keys(mock_request) == ['k2']

    def test_rate_limit_is_shared(self, redis_client):
        a, b = self._pair(redis_client)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(429, {'Retry-After': '120'}), resp(200)]
            a.get('http://api.test/x')
        with patch('requests.Session.request', return_value=resp(200)) as mock_request:
            for _ in range(3):
                b.get('http://api.test/x')
        assert set(used_keys(mock_request)) == {'k2'}

    def test_token_bucket_is_shared(self, redis_client):
        a, b = self._pair(redis_client, key_rate_limit=(1, 3600), total_timeout=1)
        with patch('requests.Session.request', return_value=resp(200)):
            a.get('http://api.test/x')
            a.get('http://api.test/x')  # both keys' tokens are now used
            with pytest.raises(DeadlineExceededError):
                b.get('http://api.test/x')

    def test_raw_keys_are_never_stored(self, redis_client):
        a, _ = self._pair(redis_client, key_rate_limit=(5, 60))
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(429, {'Retry-After': '5'}), resp(401), resp(200)]
            a.get('http://api.test/x')
        dump = []
        for name in redis_client.keys('*'):
            dump.append(name)
            kind = redis_client.type(name)
            if kind == b'zset':
                dump.extend(m for m, _ in redis_client.zrange(name, 0, -1, withscores=True))
            elif kind == b'set':
                dump.extend(redis_client.smembers(name))
        blob = b'|'.join(dump)
        assert b'k1' not in blob and b'k2' not in blob
        assert key_id('k1').encode() in blob or key_id('k2').encode() in blob

    def test_revoked_keys_expire_after_invalid_ttl(self, redis_client):
        backend = RedisStateBackend(client=redis_client, namespace="ttl", invalid_ttl=0.3)
        backend.report_invalid("id1")
        assert backend.snapshot().invalid == {"id1"}
        time.sleep(0.4)
        assert backend.snapshot().invalid == frozenset()

    def test_revoked_keys_can_be_kept_until_cleared(self, redis_client):
        backend = RedisStateBackend(client=redis_client, namespace="forever", invalid_ttl=None)
        backend.report_invalid("id1")
        redis_client.sadd("forever:invalid", "id-legacy")      # set written by 0.9.1 and earlier
        assert backend.snapshot().invalid == {"id1"}
        backend.clear_invalid()
        assert backend.snapshot().invalid == frozenset() and not redis_client.exists("forever:invalid")

    def test_ban_learned_from_others_expires_but_own_rejection_stays(self, redis_client):
        def backend():
            return RedisStateBackend(client=redis_client, namespace="ban", invalid_ttl=0.3)

        a = make(['k1', 'k2'], state_backend=backend(), state_sync_interval=0)
        with patch('requests.Session.request', side_effect=[resp(200), resp(401), resp(200)]):
            a.get('http://api.test/x')   # k1 ok: auth confirmed
            a.get('http://api.test/x')   # k2 rejected
        b = make(['k1', 'k2'], state_backend=backend(), state_sync_interval=0)
        with patch('requests.Session.request', return_value=resp(200)):
            b.get('http://api.test/x')
        assert b._state.filter_invalid(['k1', 'k2']) == ['k1']
        time.sleep(0.4)
        with patch('requests.Session.request', return_value=resp(200)):
            a.get('http://api.test/x')
            b.get('http://api.test/x')
        assert b._state.filter_invalid(['k1', 'k2']) == ['k1', 'k2']   # a provider refresh may bring it back
        assert a._state.filter_invalid(['k1', 'k2']) == ['k1']         # a saw the 401 itself
        c = make(['k1', 'k2'], state_backend=backend(), state_sync_interval=0)
        with patch('requests.Session.request', return_value=resp(200)) as mock_request:
            c.get('http://api.test/x')
            c.get('http://api.test/x')
        assert set(used_keys(mock_request)) == {'k1', 'k2'}            # a new worker uses k2 again

    def test_redis_outage_does_not_break_requests(self):
        broken = Mock()
        broken.register_script.return_value = Mock(side_effect=ConnectionError("redis down"))
        broken.pipeline.side_effect = ConnectionError("redis down")
        broken.zadd.side_effect = ConnectionError("redis down")
        backend = RedisStateBackend(client=broken)
        rotator = make(['k1', 'k2'], state_backend=backend, state_sync_interval=0, key_rate_limit=(5, 1))
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(429, {'Retry-After': '1'}), resp(200)]
            assert rotator.get('http://api.test/x').status_code == 200

    def test_in_memory_backend_shared_between_rotators(self):
        backend = InMemoryStateBackend()
        a = make(['k1', 'k2'], state_backend=backend, state_sync_interval=0)
        b = make(['k1', 'k2'], state_backend=backend, state_sync_interval=0)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(403), resp(200), resp(200)]
            a.get('http://api.test/x')
            b.get('http://api.test/x')
        assert b.keys == ['k2']

    def test_salted_key_ids(self):
        assert key_id('k1') != key_id('k1', salt=b'secret')
        assert key_id('k1', salt=b'secret') == key_id('k1', salt=b'secret')

    @pytest.mark.asyncio
    async def test_async_rotator_with_redis(self, redis_client):
        backend = RedisStateBackend(client=redis_client, namespace="async")
        responses = iter([401, 200])

        async def mock_request(*args, **kwargs):
            r = Mock()
            r.status = next(responses)
            r.headers = {}
            return r

        async with AsyncAPIKeyRotator(api_keys=['k1', 'k2'], state_backend=backend, state_sync_interval=0,
                                      key_rate_limit=(10, 1), load_env_file=False) as rotator:
            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                response = await rotator.get('http://api.test/x')
        assert response.status == 200
        assert [m for m, _ in redis_client.zrange("async:revoked", 0, -1, withscores=True)] == [key_id("k1").encode()]


# ============================================================================
# 6. BACKGROUND KEY REFRESH
# ============================================================================

class TestAutoRefresh:

    def _wait_for(self, predicate, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return predicate()

    def test_sync_auto_refresh(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("k1\nk2")
        rotator = APIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False,
                                auto_refresh_interval=0.05)
        try:
            path.write_text("k2\nk3")
            assert self._wait_for(lambda: rotator.keys == ['k2', 'k3'])
        finally:
            rotator.close()
        assert rotator._refresh_thread is None

    def test_refresh_does_not_bring_back_invalid_keys(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("bad\ngood")
        rotator = APIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [resp(401), resp(200)]
            rotator.get('http://api.test/x')
        assert rotator.refresh_keys_from_provider_sync() == ['good']

    def test_auto_refresh_requires_provider(self):
        with pytest.raises(ValueError):
            make(auto_refresh_interval=10)

    def test_refresh_thread_does_not_keep_rotator_alive(self, tmp_path):
        import gc
        import weakref

        path = tmp_path / "keys.txt"
        path.write_text("k1")
        rotator = APIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False,
                                auto_refresh_interval=0.05)
        ref = weakref.ref(rotator)
        thread = rotator._refresh_thread
        del rotator
        gc.collect()
        assert ref() is None
        thread.join(timeout=2)
        assert not thread.is_alive()

    @pytest.mark.asyncio
    async def test_async_auto_refresh(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("k1")
        async with AsyncAPIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False,
                                      auto_refresh_interval=0.05) as rotator:
            path.write_text("k1\nk9")
            for _ in range(100):
                if rotator.keys == ['k1', 'k9']:
                    break
                await asyncio.sleep(0.02)
            assert rotator.keys == ['k1', 'k9']
            task = rotator._refresh_task
        assert task.done()


# ============================================================================
# 9. HTTPX BACKEND
# ============================================================================

def _httpx_handler(statuses, seen):
    it = iter(statuses)

    def handler(request):
        seen.append(request)
        status = next(it)
        if isinstance(status, Exception):
            raise status
        return httpx.Response(status, json={"status": status})
    return handler


class TestHttpxBackend:

    def test_sync_httpx_rotation(self):
        seen = []
        transport = httpx.MockTransport(_httpx_handler([429, 200], seen))
        rotator = make(['k1', 'k2'], http_backend='httpx', http_client_kwargs={'transport': transport})
        response = rotator.get('https://api.test/x', params={'q': 1})
        assert isinstance(response, httpx.Response)
        assert response.status_code == 200 and response.json() == {"status": 200}
        assert [r.headers['Authorization'] for r in seen] == ['Bearer k1', 'Bearer k2']
        assert seen[0].url.params['q'] == '1'
        rotator.close()

    def test_sync_httpx_connect_error_retried_for_post(self):
        seen = []
        handler = _httpx_handler([httpx.ConnectError("refused"), 201], seen)
        rotator = make(['k1'], http_backend='httpx', http_client_kwargs={'transport': httpx.MockTransport(handler)})
        assert rotator.post('https://api.test/x', json={'a': 1}).status_code == 201
        assert json.loads(seen[1].content) == {'a': 1}

    def test_sync_httpx_read_error_not_retried_for_post(self):
        handler = _httpx_handler([httpx.ReadTimeout("slow")], [])
        rotator = make(['k1'], http_backend='httpx', http_client_kwargs={'transport': httpx.MockTransport(handler)})
        with pytest.raises(httpx.ReadTimeout):
            rotator.post('https://api.test/x')

    def test_sync_httpx_cache_hit_returns_httpx_response(self):
        handler = _httpx_handler([200], [])
        rotator = make(['k1'], http_backend='httpx', middlewares=[CachingMiddleware()],
                       http_client_kwargs={'transport': httpx.MockTransport(handler)})
        rotator.get('https://api.test/x')
        cached = rotator.get('https://api.test/x')
        assert isinstance(cached, httpx.Response) and cached.json() == {"status": 200}

    def test_sync_httpx_stream(self):
        handler = _httpx_handler([200], [])
        rotator = make(['k1'], http_backend='httpx', http_client_kwargs={'transport': httpx.MockTransport(handler)})
        response = rotator.get('https://api.test/x', stream=True)
        assert json.loads(response.read()) == {"status": 200}
        response.close()

    def test_http2_requires_httpx(self):
        with pytest.raises(ValueError):
            make(http2=True)

    def test_unknown_backend(self):
        with pytest.raises(ValueError):
            make(http_backend='curl')

    def test_unsupported_per_request_argument(self):
        handler = _httpx_handler([200], [])
        rotator = make(['k1'], http_backend='httpx', http_client_kwargs={'transport': httpx.MockTransport(handler)})
        with pytest.raises(TypeError, match="verify"):
            rotator.get('https://api.test/x', verify=False)

    @pytest.mark.asyncio
    async def test_async_httpx_rotation(self):
        seen = []

        async def handler(request):
            seen.append(request)
            status = 503 if len(seen) == 1 else 200
            return httpx.Response(status, json={"n": len(seen)})

        async with AsyncAPIKeyRotator(api_keys=['k1'], base_delay=0.01, load_env_file=False, http_backend='httpx',
                                      http_client_kwargs={'transport': httpx.MockTransport(handler)}) as rotator:
            response = await rotator.get('https://api.test/x')
            assert isinstance(response, httpx.Response)
            assert response.status_code == 200 and response.json() == {"n": 2}

    @pytest.mark.asyncio
    async def test_async_httpx_with_middlewares(self):
        async def handler(request):
            return httpx.Response(200, json={"cached": True})

        cache = CachingMiddleware()
        async with AsyncAPIKeyRotator(api_keys=['k1'], load_env_file=False, http_backend='httpx',
                                      middlewares=[cache],
                                      http_client_kwargs={'transport': httpx.MockTransport(handler)}) as rotator:
            first = await rotator.get('https://api.test/x')
            second = await rotator.get('https://api.test/x')
        assert first.json() == {"cached": True}
        assert second.status_code == 200 and await second.json() == {"cached": True}


# ============================================================================
# 8. LOGGING & IMPORT COST
# ============================================================================

class TestPackaging:

    def test_library_does_not_configure_logging(self):
        import logging

        logger = logging.getLogger('apikeyrotator')
        assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)
        make()
        rotator_logger = logging.getLogger('apikeyrotator.core.rotator')
        assert not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.NullHandler)
                       for h in rotator_logger.handlers)

    def test_http_libraries_are_imported_lazily(self):
        code = (
            "import sys, apikeyrotator\n"
            "print(','.join(m for m in ('aiohttp', 'requests', 'httpx', 'redis', 'yaml') if m in sys.modules))"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        assert out.stdout.strip() == ""

    def test_sync_rotator_does_not_import_aiohttp(self):
        code = (
            "import sys, apikeyrotator\n"
            "apikeyrotator.APIKeyRotator(api_keys=['k'], load_env_file=False)\n"
            "print('aiohttp' in sys.modules)"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "False"


# ============================================================================
# THREAD SAFETY OF NEW PATHS
# ============================================================================

def test_concurrent_requests_with_all_features():
    rotator = make([f'k{i}' for i in range(5)], key_rate_limit=(1000, 1),
                   circuit_breaker=True, total_timeout=30)
    errors = []

    def worker():
        try:
            for _ in range(50):
                assert rotator.get('http://api.test/x').status_code == 200
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    with patch('requests.Session.request', return_value=resp(200)):
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert errors == []
    assert rotator.get_metrics()['total_requests'] == 400
