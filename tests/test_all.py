import pytest
import os
import sys

# Добавляем путь к модулю если нужно
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import Mock, patch, MagicMock, AsyncMock

# ==== Импорты из корневого пакета apikeyrotator ====
from apikeyrotator import (
    APIKeyRotator,
    AsyncAPIKeyRotator,
    NoAPIKeysError,
    AllKeysExhaustedError,
    ErrorClassifier,
    ErrorType,
    create_rotation_strategy,
    RoundRobinRotationStrategy,
    RandomRotationStrategy,
    WeightedRotationStrategy,
)

# ==== Проверка опциональных зависимостей ====
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

try:
    from aioresponses import aioresponses
    HAS_AIORESPONSES = True
except ImportError:
    HAS_AIORESPONSES = False


# ============ BASIC TESTS ============

@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_init_with_list():
    rotator = APIKeyRotator(api_keys=["key1", "key2"], load_env_file=False)
    assert len(rotator.keys) == 2
    assert rotator.keys == ["key1", "key2"]


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_init_with_string():
    rotator = APIKeyRotator(api_keys="key1,key2,key3", load_env_file=False)
    assert len(rotator.keys) == 3
    assert rotator.keys == ["key1", "key2", "key3"]


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_no_api_keys():
    with pytest.raises(NoAPIKeysError):
        APIKeyRotator(api_keys=[], load_env_file=False)


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_env_var_loading(monkeypatch):
    monkeypatch.setenv('API_KEYS', 'key1,key2,key3')
    rotator = APIKeyRotator(load_env_file=False)
    assert rotator.keys == ['key1', 'key2', 'key3']


# ============ SYNC REQUEST TESTS ============

@pytest.mark.skipif(not HAS_REQUESTS or not HAS_REQUESTS_MOCK, reason="missing deps")
def test_successful_get_request():
    import requests_mock as rm
    with rm.Mocker() as m:
        url = "https://api.example.com/data"
        m.get(url, json={"status": "ok"}, status_code=200)

        rotator = APIKeyRotator(api_keys=["test_key"], load_env_file=False)
        response = rotator.get(url)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "test_key" in m.last_request.headers["Authorization"]


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_key_rotation():
    rotator = APIKeyRotator(api_keys=['key1', 'key2', 'key3'], load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = b''
        mock_request.return_value = mock_response

        response = rotator.get('http://example.com')
        assert mock_request.call_count == 1


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_retry_on_failure():
    rotator = APIKeyRotator(api_keys=["key1"], max_retries=3, load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_request.side_effect = [
            Mock(status_code=429, headers={}, content=b''),
            Mock(status_code=429, headers={}, content=b''),
            Mock(status_code=200, headers={}, content=b''),
        ]
        response = rotator.get('http://example.com')
        assert response.status_code == 200
        assert mock_request.call_count == 3


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_all_keys_exhausted():
    rotator = APIKeyRotator(api_keys=['key1', 'key2'], max_retries=1, load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_request.return_value = Mock(status_code=429, headers={}, content=b'')
        with pytest.raises(AllKeysExhaustedError):
            rotator.get('http://example.com')


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_custom_retry_logic():
    def custom_retry(response):
        return response.status_code == 429

    rotator = APIKeyRotator(api_keys=['key1'], should_retry_callback=custom_retry, load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_request.return_value = Mock(status_code=429, headers={}, content=b'')
        with pytest.raises(AllKeysExhaustedError):
            rotator.get('http://example.com')
        assert mock_request.call_count > 1


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_header_callback():
    def header_callback(key, existing_headers):
        return {'Authorization': f'Custom {key}'}, {}

    rotator = APIKeyRotator(api_keys=['test_key'], header_callback=header_callback, load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
        rotator.get('http://example.com')
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs['headers']['Authorization'] == 'Custom test_key'


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_user_agent_rotation():
    user_agents = ['UA1', 'UA2']
    rotator = APIKeyRotator(api_keys=["key1"], user_agents=user_agents, load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
        rotator.get('http://example.com/1')
        rotator.get('http://example.com/2')
        call1_headers = mock_request.call_args_list[0][1]['headers']
        call2_headers = mock_request.call_args_list[1][1]['headers']
        assert call1_headers['User-Agent'] in user_agents
        assert call2_headers['User-Agent'] in user_agents


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_delay_between_requests():
    rotator = APIKeyRotator(api_keys=['key1'], random_delay_range=(0.001, 0.002), load_env_file=False)
    with patch('requests.Session.request') as mock_request, patch('time.sleep') as mock_sleep:
        mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
        rotator.get('http://example.com/1')
        rotator.get('http://example.com/2')
        assert mock_sleep.call_count >= 2


@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_http_methods():
    rotator = APIKeyRotator(api_keys=['key1'], load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
        assert rotator.get('http://example.com').status_code == 200
        assert rotator.post('http://example.com', json={'test': 'data'}).status_code == 200
        assert rotator.put('http://example.com', data={'test': 'data'}).status_code == 200
        assert rotator.delete('http://example.com').status_code == 200


# ============ ASYNC TESTS ============

@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
@pytest.mark.asyncio
async def test_async_rotator():
    async with AsyncAPIKeyRotator(api_keys=['key1', 'key2'], load_env_file=False) as rotator:
        async def mock_request(*args, **kwargs):
            resp = AsyncMock()
            resp.status = 200
            resp.headers = {}
            resp.read = AsyncMock(return_value=b'')
            resp.release = AsyncMock()
            return resp

        with patch('aiohttp.ClientSession.request', side_effect=mock_request):
            response = await rotator.get('http://example.com')
            assert response.status == 200


@pytest.mark.skipif(not HAS_AIOHTTP or not HAS_AIORESPONSES, reason="missing deps")
@pytest.mark.asyncio
async def test_async_successful_get_request():
    from aioresponses import aioresponses
    url = "https://api.example.com/async_data"
    with aioresponses() as m:
        m.get(url, payload={"status": "ok"}, status=200)
        async with AsyncAPIKeyRotator(api_keys=["test_key"], load_env_file=False) as rotator:
            response = await rotator.get(url)
            assert response.status == 200


# ============ ERROR CLASSIFIER TESTS ============

def test_error_classifier_rate_limit():
    classifier = ErrorClassifier()
    mock_response = MagicMock(status_code=429)
    assert classifier.classify_error(response=mock_response) == ErrorType.RATE_LIMIT


def test_error_classifier_temporary_error():
    classifier = ErrorClassifier()
    mock_response = MagicMock(status_code=503)
    assert classifier.classify_error(response=mock_response) == ErrorType.TEMPORARY


def test_error_classifier_permanent_error():
    classifier = ErrorClassifier()
    assert classifier.classify_error(response=MagicMock(status_code=401)) == ErrorType.PERMANENT
    assert classifier.classify_error(response=MagicMock(status_code=403)) == ErrorType.PERMANENT
    assert classifier.classify_error(response=MagicMock(status_code=400)) == ErrorType.PERMANENT


def test_error_classifier_network_error():
    classifier = ErrorClassifier()
    assert classifier.classify_error(exception=requests.exceptions.ConnectionError()) == ErrorType.NETWORK
    assert classifier.classify_error(exception=requests.exceptions.Timeout()) == ErrorType.NETWORK


def test_error_classifier_unknown_error():
    classifier = ErrorClassifier()
    assert classifier.classify_error(response=MagicMock(status_code=200)) == ErrorType.UNKNOWN
    assert classifier.classify_error(exception=ValueError("other")) == ErrorType.UNKNOWN


# ============ ROTATION STRATEGY TESTS ============

def test_round_robin_rotation_strategy():
    strategy = RoundRobinRotationStrategy(['key1', 'key2', 'key3'])
    assert strategy.get_next_key() == 'key1'
    assert strategy.get_next_key() == 'key2'
    assert strategy.get_next_key() == 'key3'
    assert strategy.get_next_key() == 'key1'


def test_random_rotation_strategy():
    strategy = RandomRotationStrategy(['key1', 'key2', 'key3'])
    keys = [strategy.get_next_key() for _ in range(10)]
    assert all(key in ['key1', 'key2', 'key3'] for key in keys)


def test_weighted_rotation_strategy():
    strategy = WeightedRotationStrategy({'key1': 1, 'key2': 2})
    keys = [strategy.get_next_key() for _ in range(100)]
    ratio = keys.count('key2') / len(keys)
    assert 0.5 < ratio < 0.8


def test_create_rotation_strategy():
    assert isinstance(create_rotation_strategy('round_robin', ['key1', 'key2']), RoundRobinRotationStrategy)
    assert isinstance(create_rotation_strategy('random', ['key1', 'key2']), RandomRotationStrategy)
    assert isinstance(create_rotation_strategy('weighted', {'key1': 1, 'key2': 2}), WeightedRotationStrategy)
    with pytest.raises(ValueError):
        create_rotation_strategy('invalid', ['key1'])


# ============ CONFIG TESTS ============

@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
def test_config_persistence(tmp_path):
    config_file = tmp_path / "test_config.json"
    rotator = APIKeyRotator(api_keys=['key1'], config_file=str(config_file), load_env_file=False)
    with patch('requests.Session.request') as mock_request:
        mock_request.return_value = Mock(status_code=200, headers={}, content=b'')
        rotator.get('http://example.com')
    assert config_file.exists()


# ============ RUN DIAGNOSTICS ============

if __name__ == "__main__":
    print("=" * 60)
    print("Diagnostic Information:")
    print("=" * 60)
    print(f"Python version: {sys.version}")
    print(f"HAS_REQUESTS: {HAS_REQUESTS}")
    print(f"HAS_AIOHTTP: {HAS_AIOHTTP}")
    print(f"HAS_REQUESTS_MOCK: {HAS_REQUESTS_MOCK}")
    print(f"HAS_AIORESPONSES: {HAS_AIORESPONSES}")
    print("=" * 60)
    pytest.main([__file__, "-v", "-s"])