import pytest
import os
import json
import time
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from apikeyrotator import APIKeyRotator, AsyncAPIKeyRotator, NoAPIKeysError, AllKeysExhaustedError

# Проверяем наличие aiohttp для асинхронных тестов
try:
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


def test_no_api_keys():
    """Тест ошибки при отсутствии API ключей"""
    with pytest.raises(NoAPIKeysError):
        rotator = APIKeyRotator(api_keys=[], load_env_file=False)


def test_env_var_loading(monkeypatch):
    """Тест загрузки ключей из переменных окружения"""
    monkeypatch.setenv('API_KEYS', 'key1,key2,key3')

    rotator = APIKeyRotator(load_env_file=False)
    assert rotator.keys == ['key1', 'key2', 'key3']  # Исправлено: keys вместо api_keys


def test_key_rotation():
    """Тест ротации ключей"""
    rotator = APIKeyRotator(api_keys=['key1', 'key2', 'key3'], load_env_file=False)

    # Первый запрос использует первый ключ
    with patch('requests.Session.send') as mock_send:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_send.return_value = mock_response

        response = rotator.get('http://example.com')
        assert mock_send.call_count == 1


def test_retry_on_failure():
    """Тест повторных попыток при ошибках"""
    rotator = APIKeyRotator(
        api_keys=['key1'],
        max_retries=3,  # Увеличим количество попыток
        load_env_file=False
    )

    with patch('requests.Session.send') as mock_send:
        # Создаем разные ответы: две ошибки 429, потом успех 200
        mock_response_error = Mock()
        mock_response_error.status_code = 429  # Rate limit

        mock_response_success = Mock()
        mock_response_success.status_code = 200  # Success

        # Первые два вызова возвращают ошибку, третий - успех
        mock_send.side_effect = [
            mock_response_error,
            mock_response_error,
            mock_response_success
        ]

        response = rotator.get('http://example.com')
        assert response.status_code == 200
        assert mock_send.call_count == 3  # Две ошибки + один успех


def test_all_keys_exhausted():
    """Тест исчерпания всех ключей"""
    rotator = APIKeyRotator(
        api_keys=['key1', 'key2'],
        max_retries=1,
        load_env_file=False
    )

    with patch('requests.Session.send') as mock_send:
        # Все запросы fail
        mock_response = Mock()
        mock_response.status_code = 429
        mock_send.return_value = mock_response

        with pytest.raises(AllKeysExhaustedError):
            rotator.get('http://example.com')


def test_custom_retry_logic():
    """Тест кастомной логики повторных попыток"""

    def custom_retry(response):
        return response.status_code == 503  # Retry only on 503

    rotator = APIKeyRotator(
        api_keys=['key1'],
        should_retry_callback=custom_retry,
        load_env_file=False
    )

    with patch('requests.Session.send') as mock_send:
        # 429 не должно вызывать retry с нашей кастомной логикой
        mock_response = Mock()
        mock_response.status_code = 429
        mock_send.return_value = mock_response

        response = rotator.get('http://example.com')
        assert mock_send.call_count == 1  # Только одна попытка


def test_header_callback():
    """Тест кастомного callback для заголовков"""

    def header_callback(key, existing_headers):
        return {'Authorization': f'Custom {key}'}, {}

    rotator = APIKeyRotator(
        api_keys=['test_key'],
        header_callback=header_callback,
        load_env_file=False
    )

    with patch('requests.Session.send') as mock_send:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_send.return_value = mock_response

        rotator.get('http://example.com')

        # Проверяем, что callback был использован
        call_headers = mock_send.call_args[0][0].headers
        assert 'Authorization' in call_headers
        assert call_headers['Authorization'] == 'Custom test_key'


def test_config_persistence(tmp_path):
    """Тест сохранения конфигурации"""
    config_file = tmp_path / "test_config.json"

    rotator = APIKeyRotator(
        api_keys=['key1'],
        config_file=str(config_file),
        load_env_file=False
    )

    # Имитируем успешный запрос
    with patch('requests.Session.send') as mock_send:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_send.return_value = mock_response

        rotator.get('http://example.com')

    # Проверяем, что конфиг был сохранен
    assert config_file.exists()


def test_user_agent_rotation():
    """Тест ротации User-Agent"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0)',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)'
    ]

    rotator = APIKeyRotator(
        api_keys=['key1'],
        user_agents=user_agents,
        load_env_file=False
    )

    with patch('requests.Session.send') as mock_send:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_send.return_value = mock_response

        # Делаем несколько запросов
        rotator.get('http://example.com/1')
        rotator.get('http://example.com/2')

        # Проверяем, что User-Agent менялся
        call1_headers = mock_send.call_args_list[0][0][0].headers
        call2_headers = mock_send.call_args_list[1][0][0].headers

        assert 'User-Agent' in call1_headers
        assert 'User-Agent' in call2_headers
        # User-Agent должны быть из нашего списка
        assert call1_headers['User-Agent'] in user_agents
        assert call2_headers['User-Agent'] in user_agents


def test_delay_between_requests():
    """Тест задержки между запросами"""
    rotator = APIKeyRotator(
        api_keys=['key1'],
        random_delay_range=(0.001, 0.002),  # Короткая задержка для тестов
        load_env_file=False
    )

    with patch('requests.Session.send') as mock_send, \
            patch('time.sleep') as mock_sleep:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_send.return_value = mock_response

        rotator.get('http://example.com/1')
        rotator.get('http://example.com/2')

        # Проверяем, что sleep вызывался между запросами
        assert mock_sleep.call_count >= 1


@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
@pytest.mark.asyncio
async def test_async_rotator():
    """Тест асинхронного ротатора"""
    async with AsyncAPIKeyRotator(
            api_keys=['key1', 'key2'],
            load_env_file=False
    ) as rotator:
        # Создаем мок для асинхронного ответа
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        # Мокаем aiohttp запрос
        with patch('aiohttp.ClientSession._request', return_value=mock_response):
            response = await rotator.get('http://example.com')
            assert response.status == 200


# Простые тесты для проверки основных методов
def test_http_methods():
    """Тест основных HTTP методов"""
    rotator = APIKeyRotator(api_keys=['key1'], load_env_file=False)

    with patch('requests.Session.send') as mock_send:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_send.return_value = mock_response

        # Test GET
        response = rotator.get('http://example.com')
        assert response.status_code == 200

        # Test POST
        response = rotator.post('http://example.com', json={'test': 'data'})
        assert response.status_code == 200

        # Test PUT
        response = rotator.put('http://example.com', data={'test': 'data'})
        assert response.status_code == 200

        # Test DELETE
        response = rotator.delete('http://example.com')
        assert response.status_code == 200


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"])