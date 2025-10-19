import pytest
import os
import json
import time
import requests
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from apikeyrotator import (
    APIKeyRotator,
    AsyncAPIKeyRotator,
    NoAPIKeysError,
    AllKeysExhaustedError
)
from apikeyrotator.error_classifier import ErrorClassifier, ErrorType
from apikeyrotator.rotation_strategies import (
    RoundRobinRotationStrategy,
    RandomRotationStrategy,
    WeightedRotationStrategy,
    create_rotation_strategy
)

# Проверяем наличие необходимых библиотек
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


# ============= BASIC INITIALIZATION TESTS =============

def test_init_with_list():
    """Тест инициализации со списком ключей"""
    rotator = APIKeyRotator(
        api_keys=["key1", "key2"],
        load_env_file=False
    )
    assert len(rotator.keys) == 2
    assert rotator.keys == ["key1", "key2"]


def test_init_with_string():
    """Тест инициализации со строкой ключей"""
    rotator = APIKeyRotator(
        api_keys="key1,key2,key3",
        load_env_file=False
    )
    assert len(rotator.keys) == 3
    assert rotator.keys == ["key1", "key2", "key3"]


def test_no_api_keys():
    """Тест ошибки при отсутствии API ключей"""
    with pytest.raises(NoAPIKeysError):
        APIKeyRotator(api_keys=[], load_env_file=False)


def test_env_var_loading(monkeypatch):
    """Тест загрузки ключей из переменных окружения"""
    monkeypatch.setenv('API_KEYS', 'key1,key2,key3')
    rotator = APIKeyRotator(load_env_file=False)
    assert rotator.keys == ['key1', 'key2', 'key3']


# ============= SYNC REQUEST TESTS =============

@pytest.mark.skipif(not HAS_REQUESTS_MOCK, reason="requests-mock not installed")
def test_successful_get_request():
    """Тест успешного GET запроса"""
    import requests_mock as rm

    with rm.Mocker() as m:
        url = "https://api.example.com/data"
        m.get(url, json={"status": "ok"}, status_code=200)

        rotator = APIKeyRotator(api_keys=["test_key"], load_env_file=False)
        response = rotator.get(url)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "Authorization" in m.last_request.headers
        assert m.last_request.headers["Authorization"] == "Bearer test_key"


def test_key_rotation():
    """Тест ротации ключей"""
    rotator = APIKeyRotator(
        api_keys=['key1', 'key2', 'key3'],
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        response = rotator.get('http://example.com')
        assert mock_request.call_count == 1


def test_retry_on_failure():
    """Тест повторных попыток при ошибках"""
    rotator = APIKeyRotator(
        api_keys=["key1"],
        max_retries=3,
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request:
        mock_response_error = Mock()
        mock_response_error.status_code = 429

        mock_response_success = Mock()
        mock_response_success.status_code = 200

        mock_request.side_effect = [
            mock_response_error,
            mock_response_error,
            mock_response_success
        ]

        response = rotator.get('http://example.com')
        assert response.status_code == 200
        assert mock_request.call_count == 3


def test_all_keys_exhausted():
    """Тест исчерпания всех ключей"""
    rotator = APIKeyRotator(
        api_keys=['key1', 'key2'],
        max_retries=1,
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 429
        mock_request.return_value = mock_response

        with pytest.raises(AllKeysExhaustedError):
            rotator.get('http://example.com')


def test_custom_retry_logic():
    """Тест кастомной логики повторных попыток"""

    def custom_retry(response):
        return response.status_code == 503

    rotator = APIKeyRotator(
        api_keys=['key1'],
        should_retry_callback=custom_retry,
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 429
        mock_request.return_value = mock_response

        response = rotator.get('http://example.com')
        assert mock_request.call_count == 1


def test_header_callback():
    """Тест кастомного callback для заголовков"""

    def header_callback(key, existing_headers):
        return {'Authorization': f'Custom {key}'}, {}

    rotator = APIKeyRotator(
        api_keys=['test_key'],
        header_callback=header_callback,
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rotator.get('http://example.com')

        call_kwargs = mock_request.call_args[1]
        assert 'headers' in call_kwargs
        assert call_kwargs['headers']['Authorization'] == 'Custom test_key'


def test_user_agent_rotation():
    """Тест ротации User-Agent"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0)',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)'
    ]

    rotator = APIKeyRotator(
        api_keys=["key1"],
        user_agents=user_agents,
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rotator.get('http://example.com/1')
        rotator.get('http://example.com/2')

        call1_headers = mock_request.call_args_list[0][1]['headers']
        call2_headers = mock_request.call_args_list[1][1]['headers']

        assert 'User-Agent' in call1_headers
        assert 'User-Agent' in call2_headers
        assert call1_headers['User-Agent'] in user_agents
        assert call2_headers['User-Agent'] in user_agents


def test_delay_between_requests():
    """Тест задержки между запросами"""
    rotator = APIKeyRotator(
        api_keys=['key1'],
        random_delay_range=(0.001, 0.002),
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request, \
            patch('time.sleep') as mock_sleep:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rotator.get('http://example.com/1')
        rotator.get('http://example.com/2')

        assert mock_sleep.call_count >= 2


def test_http_methods():
    """Тест основных HTTP методов"""
    rotator = APIKeyRotator(api_keys=['key1'], load_env_file=False)

    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        response = rotator.get('http://example.com')
        assert response.status_code == 200

        response = rotator.post('http://example.com', json={'test': 'data'})
        assert response.status_code == 200

        response = rotator.put('http://example.com', data={'test': 'data'})
        assert response.status_code == 200

        response = rotator.delete('http://example.com')
        assert response.status_code == 200


# ============= ASYNC TESTS =============

@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
@pytest.mark.asyncio
async def test_async_rotator():
    """Тест асинхронного ротатора"""
    async with AsyncAPIKeyRotator(
            api_keys=['key1', 'key2'],
            load_env_file=False
    ) as rotator:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.release = AsyncMock()

        with patch('aiohttp.ClientSession.request', return_value=mock_response):
            response = await rotator.get('http://example.com')
            assert response.status == 200


@pytest.mark.skipif(not HAS_AIOHTTP or not HAS_AIORESPONSES,
                    reason="aiohttp or aioresponses not installed")
@pytest.mark.asyncio
async def test_async_successful_get_request():
    """Тест успешного асинхронного GET запроса"""
    url = "https://api.example.com/async_data"

    with aioresponses() as m:
        m.get(url, payload={"status": "ok"}, status=200)

        async with AsyncAPIKeyRotator(
                api_keys=["test_key"],
                load_env_file=False
        ) as rotator:
            response = await rotator.get(url)
            assert response.status == 200


# ============= ERROR CLASSIFIER TESTS =============

def test_error_classifier_rate_limit():
    """Тест классификации rate limit ошибки"""
    classifier = ErrorClassifier()
    mock_response = MagicMock(status_code=429)
    assert classifier.classify_error(response=mock_response) == ErrorType.RATE_LIMIT


def test_error_classifier_temporary_error():
    """Тест классификации временной ошибки"""
    classifier = ErrorClassifier()
    mock_response = MagicMock(status_code=503)
    assert classifier.classify_error(response=mock_response) == ErrorType.TEMPORARY


def test_error_classifier_permanent_error():
    """Тест классификации постоянной ошибки"""
    classifier = ErrorClassifier()

    mock_response = MagicMock(status_code=401)
    assert classifier.classify_error(response=mock_response) == ErrorType.PERMANENT

    mock_response = MagicMock(status_code=403)
    assert classifier.classify_error(response=mock_response) == ErrorType.PERMANENT

    mock_response = MagicMock(status_code=400)
    assert classifier.classify_error(response=mock_response) == ErrorType.PERMANENT


def test_error_classifier_network_error():
    """Тест классификации сетевых ошибок"""
    classifier = ErrorClassifier()
    assert classifier.classify_error(
        exception=requests.exceptions.ConnectionError()
    ) == ErrorType.NETWORK
    assert classifier.classify_error(
        exception=requests.exceptions.Timeout()
    ) == ErrorType.NETWORK


def test_error_classifier_unknown_error():
    """Тест классификации неизвестной ошибки"""
    classifier = ErrorClassifier()
    mock_response = MagicMock(status_code=200)
    assert classifier.classify_error(response=mock_response) == ErrorType.UNKNOWN
    assert classifier.classify_error(
        exception=ValueError("some other error")
    ) == ErrorType.UNKNOWN


# ============= ROTATION STRATEGY TESTS =============

def test_round_robin_rotation_strategy():
    """Тест стратегии round-robin"""
    strategy = RoundRobinRotationStrategy(['key1', 'key2', 'key3'])
    assert strategy.get_next_key() == 'key1'
    assert strategy.get_next_key() == 'key2'
    assert strategy.get_next_key() == 'key3'
    assert strategy.get_next_key() == 'key1'


def test_random_rotation_strategy():
    """Тест стратегии случайного выбора"""
    strategy = RandomRotationStrategy(['key1', 'key2', 'key3'])
    keys = [strategy.get_next_key() for _ in range(10)]
    assert all(key in ['key1', 'key2', 'key3'] for key in keys)


def test_weighted_rotation_strategy():
    """Тест стратегии взвешенного выбора"""
    strategy = WeightedRotationStrategy({'key1': 1, 'key2': 2})
    keys = [strategy.get_next_key() for _ in range(100)]
    key1_count = keys.count('key1')
    key2_count = keys.count('key2')
    # Проверяем примерное соотношение 1:2
    ratio = key2_count / (key1_count + key2_count)
    assert 0.5 < ratio < 0.8


def test_create_rotation_strategy():
    """Тест фабрики стратегий"""
    strategy = create_rotation_strategy('round_robin', ['key1', 'key2'])
    assert isinstance(strategy, RoundRobinRotationStrategy)

    strategy = create_rotation_strategy('random', ['key1', 'key2'])
    assert isinstance(strategy, RandomRotationStrategy)

    strategy = create_rotation_strategy('weighted', {'key1': 1, 'key2': 2})
    assert isinstance(strategy, WeightedRotationStrategy)

    with pytest.raises(ValueError):
        create_rotation_strategy('invalid', ['key1'])


# ============= CONFIG TESTS =============

def test_config_persistence(tmp_path):
    """Тест сохранения конфигурации"""
    config_file = tmp_path / "test_config.json"

    rotator = APIKeyRotator(
        api_keys=['key1'],
        config_file=str(config_file),
        load_env_file=False
    )

    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rotator.get('http://example.com')

    # Конфиг должен быть создан
    assert config_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])