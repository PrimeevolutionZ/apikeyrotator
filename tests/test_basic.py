"""
Basic functionality tests for APIKeyRotator
Tests: initialization, sync/async requests, error handling
"""

import pytest
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import Mock, patch, AsyncMock

from apikeyrotator import (
    APIKeyRotator,
    AsyncAPIKeyRotator,
    NoAPIKeysError,
    AllKeysExhaustedError,
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

try:
    import requests_mock

    HAS_REQUESTS_MOCK = True
except ImportError:
    HAS_REQUESTS_MOCK = False


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestInitialization:
    """Test basic rotator initialization."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_init_with_list(self):
        rotator = APIKeyRotator(api_keys=["key1", "key2"], load_env_file=False)
        assert len(rotator.keys) == 2
        assert rotator.keys == ["key1", "key2"]

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_init_with_string(self):
        rotator = APIKeyRotator(api_keys="key1,key2,key3", load_env_file=False)
        assert len(rotator.keys) == 3
        assert rotator.keys == ["key1", "key2", "key3"]

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_no_api_keys(self):
        with pytest.raises(NoAPIKeysError):
            APIKeyRotator(api_keys=[], load_env_file=False)

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_env_var_loading(self, monkeypatch):
        monkeypatch.setenv('API_KEYS', 'key1,key2,key3')
        rotator = APIKeyRotator(load_env_file=False)
        assert rotator.keys == ['key1', 'key2', 'key3']

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_custom_env_var(self, monkeypatch):
        monkeypatch.setenv('MY_KEYS', 'keyA,keyB')
        rotator = APIKeyRotator(env_var='MY_KEYS', load_env_file=False)
        assert rotator.keys == ['keyA', 'keyB']

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_init_with_metrics_enabled(self):
        rotator = APIKeyRotator(
            api_keys=["key1"],
            enable_metrics=True,
            load_env_file=False
        )
        assert rotator.metrics is not None
        assert rotator.enable_metrics is True

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_init_with_metrics_disabled(self):
        rotator = APIKeyRotator(
            api_keys=["key1"],
            enable_metrics=False,
            load_env_file=False
        )
        assert rotator.metrics is None

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_init_with_custom_params(self):
        rotator = APIKeyRotator(
            api_keys=["key1"],
            max_retries=5,
            base_delay=2.0,
            timeout=30.0,
            load_env_file=False
        )
        assert rotator.max_retries == 5
        assert rotator.base_delay == 2.0
        assert rotator.timeout == 30.0


# ============================================================================
# SYNCHRONOUS REQUEST TESTS
# ============================================================================

class TestSyncRequests:
    """Test synchronous HTTP requests."""

    @pytest.mark.skipif(not HAS_REQUESTS or not HAS_REQUESTS_MOCK, reason="missing deps")
    def test_successful_get_request(self):
        import requests_mock as rm
        with rm.Mocker() as m:
            url = "https://api.example.com/data"
            m.get(url, json={"status": "ok"}, status_code=200)

            rotator = APIKeyRotator(api_keys=["test_key"], load_env_file=False)
            response = rotator.get(url)

            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_post_request(self):
        rotator = APIKeyRotator(api_keys=['key1'], load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=201, headers={}, content=b'')
            response = rotator.post('http://example.com', json={'test': 'data'})
            assert response.status_code == 201
            assert mock_request.call_args[0][0] == 'POST'

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_put_request(self):
        rotator = APIKeyRotator(api_keys=['key1'], load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
            response = rotator.put('http://example.com', json={'test': 'data'})
            assert response.status_code == 200
            assert mock_request.call_args[0][0] == 'PUT'

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_delete_request(self):
        rotator = APIKeyRotator(api_keys=['key1'], load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=204, headers={}, content=b'')
            response = rotator.delete('http://example.com')
            assert response.status_code == 204
            assert mock_request.call_args[0][0] == 'DELETE'

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_retry_on_failure(self):
        rotator = APIKeyRotator(api_keys=["key1"], max_retries=3, load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [
                Mock(status_code=429, headers={}, content=b''),
                Mock(status_code=500, headers={}, content=b''),
                Mock(status_code=200, headers={}, content=b''),
            ]
            response = rotator.get('http://example.com')
            assert response.status_code == 200
            assert mock_request.call_count == 3

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_all_keys_exhausted(self):
        rotator = APIKeyRotator(api_keys=['key1', 'key2'], max_retries=1, load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=429, headers={}, content=b'')
            with pytest.raises(AllKeysExhaustedError):
                rotator.get('http://example.com')

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_key_rotation_on_rate_limit(self):
        rotator = APIKeyRotator(api_keys=['key1', 'key2'], max_retries=2, load_env_file=False)
        with patch('requests.Session.request') as mock_request:
            # First key rate limited, second key succeeds
            mock_request.side_effect = [
                Mock(status_code=429, headers={}, content=b''),
                Mock(status_code=200, headers={}, content=b'')
            ]
            response = rotator.get('http://example.com')
            assert response.status_code == 200


# ============================================================================
# ASYNCHRONOUS REQUEST TESTS
# ============================================================================

class TestAsyncRequests:
    """Test asynchronous HTTP requests."""

    @pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
    @pytest.mark.asyncio
    async def test_async_get_request(self):
        async with AsyncAPIKeyRotator(api_keys=['key1'], load_env_file=False) as rotator:
            async def mock_request(*args, **kwargs):
                resp = AsyncMock()
                resp.status = 200
                resp.headers = {}
                resp.read = AsyncMock(return_value=b'{"status": "ok"}')
                resp.release = AsyncMock()
                return resp

            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                response = await rotator.get('http://example.com')
                assert response.status == 200

    @pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
    @pytest.mark.asyncio
    async def test_async_post_request(self):
        async with AsyncAPIKeyRotator(api_keys=['key1'], load_env_file=False) as rotator:
            async def mock_request(method, *args, **kwargs):
                resp = AsyncMock()
                resp.status = 201
                resp.headers = {}
                resp.read = AsyncMock(return_value=b'')
                resp.release = AsyncMock()
                return resp

            with patch('aiohttp.ClientSession.request', side_effect=mock_request):
                response = await rotator.post('http://example.com', json={'test': 'data'})
                assert response.status == 201

    @pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with AsyncAPIKeyRotator(api_keys=['key1'], load_env_file=False) as rotator:
            assert rotator._session is not None


# ============================================================================
# CUSTOM CALLBACKS TESTS
# ============================================================================

class TestCustomCallbacks:
    """Test custom callback functionality."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_custom_retry_callback(self):
        def custom_retry(response):
            return response.status_code in [429, 503]

        rotator = APIKeyRotator(
            api_keys=['key1'],
            should_retry_callback=custom_retry,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.side_effect = [
                Mock(status_code=503, headers={}, content=b''),
                Mock(status_code=200, headers={}, content=b'')
            ]

            response = rotator.get('http://example.com')
            assert response.status_code == 200
            assert mock_request.call_count == 2

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_header_callback_with_dict(self):
        def header_callback(key, existing):
            return {'X-Custom-Key': key, 'X-Custom-Header': 'value'}

        rotator = APIKeyRotator(
            api_keys=['test_key'],
            header_callback=header_callback,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
            rotator.get('http://example.com')

            headers = mock_request.call_args[1]['headers']
            assert headers['X-Custom-Key'] == 'test_key'
            assert headers['X-Custom-Header'] == 'value'

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_header_callback_with_tuple(self):
        def header_callback(key, existing):
            headers = {'X-Custom': 'header'}
            cookies = {'session': 'cookie_value'}
            return headers, cookies

        rotator = APIKeyRotator(
            api_keys=['test_key'],
            header_callback=header_callback,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
            rotator.get('http://example.com')

            headers = mock_request.call_args[1]['headers']
            cookies = mock_request.call_args[1]['cookies']
            assert headers['X-Custom'] == 'header'
            assert cookies['session'] == 'cookie_value'


# ============================================================================
# ANTI-BOT FEATURES TESTS
# ============================================================================

class TestAntiBotFeatures:
    """Test anti-bot evasion features."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_user_agent_rotation(self):
        user_agents = ['UA1', 'UA2', 'UA3']

        rotator = APIKeyRotator(
            api_keys=["key1"],
            user_agents=user_agents,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            uas = []
            for _ in range(6):
                rotator.get('http://example.com')
                ua = mock_request.call_args[1]['headers']['User-Agent']
                uas.append(ua)

            # Should cycle through UAs
            assert set(uas) == set(user_agents)

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_random_delay(self):
        rotator = APIKeyRotator(
            api_keys=['key1'],
            random_delay_range=(0.01, 0.02),
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request, \
                patch('time.sleep') as mock_sleep:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            rotator.get('http://example.com/1')
            rotator.get('http://example.com/2')

            # Should have delays
            assert mock_sleep.call_count >= 2

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_proxy_rotation(self):
        proxies = ['http://proxy1:8080', 'http://proxy2:8080']

        rotator = APIKeyRotator(
            api_keys=['key1'],
            proxy_list=proxies,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            mock_request.return_value = Mock(status_code=200, headers={}, content=b'')

            used_proxies = []
            for _ in range(4):
                rotator.get('http://example.com')
                proxy = mock_request.call_args[1]['proxies']['http']
                used_proxies.append(proxy)

            # Should rotate through proxies
            assert set(used_proxies) == set(proxies)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_empty_url(self):
        rotator = APIKeyRotator(api_keys=['key1'], load_env_file=False)

        with pytest.raises(ValueError):
            rotator.get('')

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_invalid_key_removal(self):
        rotator = APIKeyRotator(
            api_keys=['key1', 'key2'],
            max_retries=1,
            load_env_file=False
        )

        with patch('requests.Session.request') as mock_request:
            # First key returns 401 (invalid), second key succeeds
            mock_request.side_effect = [
                Mock(status_code=401, headers={}, content=b''),
                Mock(status_code=200, headers={}, content=b'')
            ]

            response = rotator.get('http://example.com')

            assert response.status_code == 200
            # key1 should be removed
            assert len(rotator.keys) == 1

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_reset_key_health(self):
        rotator = APIKeyRotator(api_keys=['key1', 'key2'], load_env_file=False)

        # Mark keys as unhealthy
        rotator._key_metrics['key1'].is_healthy = False
        rotator._key_metrics['key2'].is_healthy = False

        # Reset specific key
        rotator.reset_key_health('key1')

        assert rotator._key_metrics['key1'].is_healthy is True
        assert rotator._key_metrics['key2'].is_healthy is False

        # Reset all keys
        rotator.reset_key_health()

        assert rotator._key_metrics['key1'].is_healthy is True
        assert rotator._key_metrics['key2'].is_healthy is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])