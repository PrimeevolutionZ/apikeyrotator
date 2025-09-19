# APIKeyRotator

**Ultra simple API key rotation for bypassing rate limits**

`APIKeyRotator` - это Python библиотека, разработанная для упрощения ротации API ключей, автоматической обработки лимитов запросов, ошибок и повторных попыток. Она предоставляет как синхронный, так и асинхронный интерфейс, сохраняя при этом максимальную простоту использования.

## Особенности

*   **Простота использования:** Интуитивно понятный API, похожий на `requests` и `aiohttp`.
*   **Автоматическая ротация ключей:** Переключается на следующий ключ при возникновении ошибок или превышении лимитов.
*   **Экспоненциальная задержка:** Автоматически применяет экспоненциальную задержку при повторных попытках.
*   **Гибкая конфигурация:** Настраиваемые максимальное количество повторных попыток, базовая задержка и таймауты.
*   **Поддержка синхронных и асинхронных запросов:** Используйте `APIKeyRotator` для синхронных операций и `AsyncAPIKeyRotator` для асинхронных.
*   **Автоматическое определение заголовков:** Пытается определить тип авторизации (Bearer, X-API-Key, Key) на основе формата ключа.
*   **Кастомизируемая логика:** Возможность предоставить собственные функции для определения необходимости повторной попытки и формирования заголовков.
*   **Умный парсинг ключей:** Ключи могут быть переданы списком, строкой через запятую или из переменной окружения.

## Установка

```bash
pip install apikeyrotator
```

## Использование

### Синхронный режим (APIKeyRotator)

Используйте `APIKeyRotator` для выполнения синхронных HTTP-запросов. Его API очень похож на библиотеку `requests`.

```python
import os
import requests
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError

# Пример: ключи из переменной окружения (рекомендуется)
# export API_KEYS="your_key_1,your_key_2,your_key_3"

# Или передайте ключи напрямую
rotator = APIKeyRotator(
    api_keys=["key_sync_1", "key_sync_2", "key_sync_3"],
    max_retries=5, # Максимальное количество попыток для каждого ключа
    base_delay=0.5 # Базовая задержка между попытками
)

try:
    # Выполняем GET запрос
    response = rotator.get("https://api.example.com/data", params={"query": "test"})
    response.raise_for_status() # Вызовет исключение для 4xx/5xx ответов
    print(f"Успешный синхронный GET запрос: {response.status_code}")
    print(response.json())

    # Выполняем POST запрос
    response = rotator.post("https://api.example.com/submit", json={"data": "payload"})
    response.raise_for_status()
    print(f"Успешный синхронный POST запрос: {response.status_code}")
    print(response.json())

except AllKeysExhaustedError as e:
    print(f"Все ключи исчерпаны: {e}")
except Exception as e:
    print(f"Произошла ошибка: {e}")

# Пример с кастомной логикой определения повторных попыток
def custom_sync_retry_logic(response: requests.Response) -> bool:
    # Повторять, если статус 429 (Too Many Requests) или 403 (Forbidden)
    return response.status_code in [429, 403]

rotator_custom = APIKeyRotator(
    api_keys=["key_sync_custom_1"],
    should_retry_callback=custom_sync_retry_logic
)

try:
    response = rotator_custom.get("https://api.example.com/protected")
    print(f"Успешный синхронный запрос с кастомной логикой: {response.status_code}")
except AllKeysExhaustedError as e:
    print(f"Все ключи исчерпаны (кастомная логика): {e}")
```

### Асинхронный режим (AsyncAPIKeyRotator)

Используйте `AsyncAPIKeyRotator` для выполнения асинхронных HTTP-запросов. Его API очень похож на библиотеку `aiohttp`.

```python
import asyncio
import aiohttp
from apikeyrotator import AsyncAPIKeyRotator, AllKeysExhaustedError

async def main():
    # Пример: ключи из переменной окружения (рекомендуется)
    # export API_KEYS="your_async_key_1,your_async_key_2"

    # Или передайте ключи напрямую
    async with AsyncAPIKeyRotator(
        api_keys=["key_async_1", "key_async_2"],
        max_retries=5,
        base_delay=0.5
    ) as rotator:
        try:
            # Выполняем GET запрос
            async with rotator.get("https://api.example.com/async_data", params={"query": "async_test"}) as response:
                response.raise_for_status()
                data = await response.json()
                print(f"Успешный асинхронный GET запрос: {response.status}")
                print(data)

            # Выполняем POST запрос
            async with rotator.post("https://api.example.com/async_submit", json={"data": "async_payload"}) as response:
                response.raise_for_status()
                data = await response.json()
                print(f"Успешный асинхронный POST запрос: {response.status}")
                print(data)

        except AllKeysExhaustedError as e:
            print(f"Все ключи исчерпаны (асинхронно): {e}")
        except aiohttp.ClientError as e:
            print(f"Произошла асинхронная ошибка клиента: {e}")
        except Exception as e:
            print(f"Произошла непредвиденная ошибка: {e}")

# Пример с кастомной логикой определения повторных попыток и формирования заголовков
def custom_async_retry_logic(status_code: int) -> bool:
    # Повторять, если статус 429 (Too Many Requests) или 503 (Service Unavailable)
    return status_code in [429, 503]

def custom_header_callback(key: str, existing_headers: Optional[dict]) -> dict:
    headers = existing_headers.copy() if existing_headers else {}
    headers["X-Custom-Auth"] = f"Token {key}"
    headers["User-Agent"] = "MyAwesomeApp/1.0"
    return headers

async def main_custom_async():
    async with AsyncAPIKeyRotator(
        api_keys=["key_async_custom_1"],
        should_retry_callback=custom_async_retry_logic,
        header_callback=custom_header_callback
    ) as rotator:
        try:
            async with rotator.get("https://api.example.com/custom_auth") as response:
                response.raise_for_status()
                data = await response.json()
                print(f"Успешный асинхронный запрос с кастомной логикой: {response.status}")
                print(data)
        except AllKeysExhaustedError as e:
            print(f"Все ключи исчерпаны (кастомная асинхронная логика): {e}")
        except Exception as e:
            print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
    # asyncio.run(main_custom_async()) # Раскомментируйте для запуска примера с кастомной логикой
```

## Обработка ошибок

Библиотека выбрасывает следующие исключения:

*   `NoAPIKeysError`: Если ключи API не были предоставлены или не найдены.
*   `AllKeysExhaustedError`: Если все предоставленные ключи API были исчерпаны после всех попыток.

## Разработка

Для запуска тестов или разработки:

```bash
git clone https://github.com/PrimeevolutionZ/apikeyrotator.git
cd apikeyrotator
pip install -e .
# Запустите тесты, если они есть
```

## Лицензия

Эта библиотека распространяется под лицензией MIT. См. файл `LICENSE` для получения дополнительной информации.

