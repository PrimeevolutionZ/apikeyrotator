import time
from typing import Callable, Any


def retry_with_backoff(
        func: Callable,
        retries: int = 3,
        backoff_factor: float = 0.5,
        exceptions: tuple = (Exception,)
) -> Any:
    """
    Повторяет вызов функции с экспоненциальной задержкой при ошибках.

    :param func: Вызываемая функция
    :param retries: Количество попыток
    :param backoff_factor: Множитель для задержки (0.5 → 0.5s, 1s, 2s...)
    :param exceptions: Какие исключения ловить для повтора
    """
    for attempt in range(retries):
        try:
            return func()
        except exceptions as e:
            if attempt == retries - 1:
                raise e
            delay = backoff_factor * (2 ** attempt)
            time.sleep(delay)