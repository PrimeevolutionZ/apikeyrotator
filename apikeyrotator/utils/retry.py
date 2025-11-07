import asyncio
import time
from typing import Callable, Any, Type, Union, Tuple
import requests


def retry_with_backoff(
        func: Callable,
        retries: int = 3,
        backoff_factor: float = 0.5,
        exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
) -> Any:
    """
    Универсальная функция для повторных попыток с экспоненциальной задержкой.

    Выполняет функцию с автоматическими повторными попытками при возникновении
    исключений. Задержка между попытками увеличивается экспоненциально.

    Args:
        func: Функция для выполнения
        retries: Максимальное количество попыток (по умолчанию 3)
        backoff_factor: Базовая задержка для экспоненциального роста (по умолчанию 0.5)
        exceptions: Тип(ы) исключений для перехвата (по умолчанию Exception)

    Returns:
        Any: Результат выполнения функции

    Raises:
        Exception: Пробрасывает последнее исключение если все попытки исчерпаны

    Examples:
        >>> # Простой пример
        >>> def flaky_request():
        ...     return requests.get('https://api.example.com/data')
        >>> response = retry_with_backoff(flaky_request, retries=5)

        >>> # С конкретными исключениями
        >>> response = retry_with_backoff(
        ...     lambda: requests.get('https://api.example.com'),
        ...     retries=3,
        ...     exceptions=requests.RequestException
        ... )

        >>> # С кастомными параметрами
        >>> response = retry_with_backoff(
        ...     func=my_api_call,
        ...     retries=5,
        ...     backoff_factor=1.0,  # Начинаем с 1 секунды
        ...     exceptions=(ConnectionError, TimeoutError)
        ... )

    Note:
        Задержка вычисляется как: backoff_factor * (2 ** attempt)
        Например, с backoff_factor=0.5:
        - Попытка 0: без задержки
        - Попытка 1: 0.5 сек
        - Попытка 2: 1.0 сек
        - Попытка 3: 2.0 сек
        - Попытка 4: 4.0 сек
    """
    for attempt in range(retries):
        try:
            return func()
        except exceptions as e:
            if attempt == retries - 1:
                # Последняя попытка - пробрасываем исключение
                raise e

            delay = backoff_factor * (2 ** attempt)
            print(f"⚠️  Retry {attempt + 1}/{retries} after {delay:.1f}s delay (error: {type(e).__name__})")
            time.sleep(delay)


async def async_retry_with_backoff(
        func: Callable,
        retries: int = 3,
        backoff_factor: float = 0.5,
        exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
) -> Any:
    """
    Асинхронная универсальная функция для повторных попыток с экспоненциальной задержкой.

    Выполняет асинхронную функцию с автоматическими повторными попытками.
    Задержка между попытками увеличивается экспоненциально.

    Args:
        func: Асинхронная функция для выполнения (корутина)
        retries: Максимальное количество попыток (по умолчанию 3)
        backoff_factor: Базовая задержка для экспоненциального роста (по умолчанию 0.5)
        exceptions: Тип(ы) исключений для перехвата (по умолчанию Exception)

    Returns:
        Any: Результат выполнения функции

    Raises:
        Exception: Пробрасывает последнее исключение если все попытки исчерпаны

    Examples:
        >>> # Простой пример
                  async def flaky_request():
        ...     async with aiohttp.ClientSession() as session:
        ...         async with session.get('https://api.example.com') as resp:
        ...             return await resp.json()
        ... response = await async_retry_with_backoff(flaky_request, retries=5)

        ... # С конкретными исключениями
        ... response = await async_retry_with_backoff( response = await async_retry_with_backoff(
        ...     lambda: session.get('https://api.example.com'),
        ...     retries=3,
        ...     exceptions=aiohttp.ClientError
        ... )

        >>> # В контексте async/await
        >>> async def main():
        ...     result = await async_retry_with_backoff(
        ...         my_async_api_call,
        ...         retries=5,
        ...         backoff_factor=1.0
        ...     )
        ...     return result

    Note:
        Использует asyncio.sleep() для неблокирующей задержки между попытками.
    """
    for attempt in range(retries):
        try:
            return await func()
        except exceptions as e:
            if attempt == retries - 1:
                # Последняя попытка - пробрасываем исключение
                raise e

            delay = backoff_factor * (2 ** attempt)
            print(f"⚠️  Async Retry {attempt + 1}/{retries} after {delay:.1f}s delay (error: {type(e).__name__})")
            await asyncio.sleep(delay)


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Вычисляет задержку для экспоненциального backoff.

    Args:
        attempt: Номер попытки (начиная с 0)
        base_delay: Базовая задержка в секундах (по умолчанию 1.0)
        max_delay: Максимальная задержка в секундах (по умолчанию 60.0)

    Returns:
        float: Задержка в секундах

    Examples:
        >>> for i in range(5):
        ...     delay = exponential_backoff(i)
        ...     print(f"Attempt {i}: {delay}s")
        Attempt 0: 1.0s
        Attempt 1: 2.0s
        Attempt 2: 4.0s
        Attempt 3: 8.0s
        Attempt 4: 16.0s
    """
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


def jittered_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Вычисляет задержку с добавлением случайного jitter.

    Добавление jitter помогает избежать "thundering herd problem",
    когда множество клиентов одновременно повторяют запросы.

    Args:
        attempt: Номер попытки (начиная с 0)
        base_delay: Базовая задержка в секундах (по умолчанию 1.0)
        max_delay: Максимальная задержка в секундах (по умолчанию 60.0)

    Returns:
        float: Задержка в секундах с jitter

    Examples:
        >>> import random
        >>> random.seed(42)
        >>> for i in range(3):
        ...     delay = jittered_backoff(i)
        ...     print(f"Attempt {i}: {delay:.2f}s")
    """
    import random
    base = exponential_backoff(attempt, base_delay, max_delay)
    jitter = random.uniform(0, base * 0.1)  # Добавляем до 10% случайного jitter
    return min(base + jitter, max_delay)


class CircuitBreaker:
    """
    Паттерн Circuit Breaker для предотвращения каскадных отказов.

    Отслеживает количество последовательных ошибок и временно
    прекращает отправку запросов при превышении порога.

    Состояния:
    - CLOSED: Нормальная работа, запросы проходят
    - OPEN: Слишком много ошибок, запросы блокируются
    - HALF_OPEN: Пробный период после восстановления

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        >>>
        >>> def make_request():
        ...     if breaker.allow_request():
        ...         try:
        ...             response = requests.get('https://api.example.com')
        ...             breaker.record_success()
        ...             return response
        ...         except Exception as e:
        ...             breaker.record_failure()
        ...             raise
        ...     else:
        ...         raise Exception("Circuit breaker is OPEN")
    """

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        """
        Инициализирует Circuit Breaker.

        Args:
            failure_threshold: Количество ошибок для открытия circuit
            timeout: Время в секундах до перехода в HALF_OPEN
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def allow_request(self) -> bool:
        """
        Проверяет, можно ли выполнить запрос.

        Returns:
            bool: True если запрос разрешён, False иначе
        """
        if self.state == 'CLOSED':
            return True

        if self.state == 'OPEN':
            # Проверяем, прошло ли достаточно времени для перехода в HALF_OPEN
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = 'HALF_OPEN'
                return True
            return False

        # HALF_OPEN state
        return True

    def record_success(self):
        """Записывает успешный запрос."""
        self.failures = 0
        self.state = 'CLOSED'

    def record_failure(self):
        """Записывает неудачный запрос."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.failure_threshold:
            self.state = 'OPEN'
            print(f"⚠️  Circuit breaker opened after {self.failures} failures")

    def get_state(self) -> str:
        """
        Получить текущее состояние circuit breaker.

        Returns:
            str: 'CLOSED', 'OPEN' или 'HALF_OPEN'
        """
        return self.state

    def reset(self):
        """Сбрасывает circuit breaker в исходное состояние."""
        self.failures = 0
        self.last_failure_time = 0
        self.state = 'CLOSED'


def measure_time(func: Callable) -> Callable:
    """
    Декоратор для измерения времени выполнения функции.

    Args:
        func: Функция для измерения

    Returns:
        Callable: Обёрнутая функция

    Examples:
        >>> @measure_time
        ... def slow_function():
        ...     time.sleep(1)
        ...     return "done"
        >>> result = slow_function()
        ⏱️  slow_function took 1.00s
    """

    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"⏱️  {func.__name__} took {elapsed:.2f}s")
        return result

    return wrapper


def measure_time_async(func: Callable) -> Callable:
    """
    Декоратор для измерения времени выполнения асинхронной функции.

    Args:
        func: Асинхронная функция для измерения

    Returns:
        Callable: Обёрнутая функция

    Examples:
        >>> @measure_time_async
        ... async def slow_function():
        ...     await asyncio.sleep(1)
        ...     return "done"
         result = await slow_function()
        ⏱️  slow_function took 1.00s
    """

    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"⏱️  {func.__name__} took {elapsed:.2f}s")
        return result

    return wrapper