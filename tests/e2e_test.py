import os
import logging
from apikeyrotator import APIKeyRotator, NoAPIKeysError, AllKeysExhaustedError

# Настройка логирования для отладки
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestRotator")

def test_apikeyrotator_basic():
    """Базовый тест: инициализация и GET-запрос без реальных API-ключей."""
    try:
        # Инициализируем ротатор с фейковыми ключами
        rotator = APIKeyRotator(
            api_keys=["fake_key_1", "fake_key_2"],  # Фейковые ключи
            max_retries=2,
            base_delay=0.5,
            timeout=10.0,
            user_agents=[
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
            ],
            random_delay_range=(0.1, 0.5),  # Небольшая задержка для теста
            logger=logger
        )

        # Тестируем запрос к httpbin.org — он просто вернёт заголовки
        url = "https://httpbin.org/headers"
        logger.info(f"Отправка GET-запроса к {url}...")

        response = rotator.get(url)
        response.raise_for_status()  # Проверка на HTTP ошибки

        data = response.json()
        logger.info("✅ Успешный ответ от сервера!")
        logger.info(f"Ответ: {data}")

        # Проверим, что в заголовках есть наш User-Agent (должен быть один из списка)
        headers = data.get("headers", {})
        user_agent = headers.get("User-Agent", "")
        assert any(ua in user_agent for ua in rotator.user_agents), "User-Agent не соответствует ожидаемому!"

        logger.info("✅ User-Agent успешно применён и возвращён сервером.")

    except NoAPIKeysError:
        logger.error("❌ Ошибка: не предоставлены API-ключи.")
        raise
    except AllKeysExhaustedError:
        logger.error("❌ Ошибка: все ключи исчерпаны после попыток.")
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        raise

async def test_apikeyrotator_async_run():
    """Тест асинхронной версии (если поддерживается)."""
    try:
        from apikeyrotator import AsyncAPIKeyRotator

        async with AsyncAPIKeyRotator(
            api_keys=["fake_async_key_1"],
            max_retries=1,
            timeout=10.0,
            logger=logger
        ) as rotator:
            url = "https://httpbin.org/headers"
            logger.info(f"Отправка асинхронного GET-запроса к {url}...")

            # Ключевое изменение: необходимо использовать 'await' перед rotator.get(url)
            # так как rotator.get(url) возвращает корутину, а не асинхронный контекстный менеджер.
            # aiohttp.ClientResponse, который возвращается после await, сам является асинхронным контекстным менеджером.
            async with await rotator.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                logger.info("✅ Асинхронный запрос успешен!")
                logger.info(f"Ответ: {data}")

    except ImportError:
        logger.warning("⚠️ Асинхронная версия недоступна или не поддерживается в этой сборке.")
    except Exception as e:
        logger.error(f"❌ Ошибка в асинхронном тесте: {e}")
        raise

if __name__ == "__main__":
    import asyncio

    print("🧪 Запуск тестов для apikeyrotator...")

    # Тестируем синхронную версию
    test_apikeyrotator_basic()

    # Тестируем асинхронную версию
    asyncio.run(test_apikeyrotator_async_run())

    print("✅ Все тесты пройдены успешно!")

