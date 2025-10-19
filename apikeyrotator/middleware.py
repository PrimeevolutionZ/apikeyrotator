from typing import Any, Dict, Optional, Protocol, Tuple, Union
import time
import asyncio


class RequestInfo:
    """
    Информация о HTTP запросе для middleware.

    Attributes:
        method: HTTP метод (GET, POST, etc.)
        url: URL запроса
        headers: Заголовки запроса
        cookies: Куки запроса
        key: API ключ, используемый для запроса
        attempt: Номер попытки (начиная с 0)
        kwargs: Дополнительные параметры запроса
    """

    def __init__(
            self,
            method: str,
            url: str,
            headers: Dict[str, str],
            cookies: Dict[str, str],
            key: str,
            attempt: int,
            kwargs: Dict[str, Any]
    ):
        self.method = method
        self.url = url
        self.headers = headers
        self.cookies = cookies
        self.key = key
        self.attempt = attempt
        self.kwargs = kwargs


class ResponseInfo:
    """
    Информация о HTTP ответе для middleware.

    Attributes:
        status_code: HTTP статус код
        headers: Заголовки ответа
        content: Тело ответа
        request_info: Информация об исходном запросе
    """

    def __init__(
            self,
            status_code: int,
            headers: Dict[str, str],
            content: Any,
            request_info: RequestInfo
    ):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.request_info = request_info


class ErrorInfo:
    """
    Информация об ошибке для middleware.

    Attributes:
        exception: Исключение, возникшее при запросе
        request_info: Информация об исходном запросе
        response_info: Информация об ответе (если доступна)
    """

    def __init__(
            self,
            exception: Exception,
            request_info: RequestInfo,
            response_info: Optional[ResponseInfo] = None
    ):
        self.exception = exception
        self.request_info = request_info
        self.response_info = response_info


class RotatorMiddleware(Protocol):
    """
    Протокол для middleware ротатора.

    Middleware позволяет перехватывать и модифицировать запросы,
    ответы и обрабатывать ошибки на разных этапах выполнения.

    Example:
        >>> class LoggingMiddleware:
        ...     async def before_request(self, request_info):
        ...         print(f"Sending request to {request_info.url}")
        ...         return request_info
        ...
        ...     async def after_request(self, response_info):
        ...         print(f"Received response: {response_info.status_code}")
        ...         return response_info
        ...
        ...     async def on_error(self, error_info):
        ...         print(f"Error occurred: {error_info.exception}")
        ...         return False
    """

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Вызывается перед отправкой запроса.

        Позволяет модифицировать параметры запроса, добавлять заголовки,
        логировать запросы, применять rate limiting и т.д.

        Args:
            request_info: Информация о запросе

        Returns:
            RequestInfo: Модифицированная информация о запросе
        """
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Вызывается после успешного получения ответа.

        Позволяет модифицировать ответ, кэшировать данные,
        обновлять метрики и т.д.

        Args:
            response_info: Информация об ответе

        Returns:
            ResponseInfo: Модифицированная информация об ответе
        """
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Вызывается при возникновении ошибки.

        Позволяет обрабатывать ошибки, логировать их,
        выполнять recovery действия и т.д.

        Args:
            error_info: Информация об ошибке

        Returns:
            bool: True если ошибка обработана и не должна пробрасываться дальше,
                  False если ошибка должна быть передана следующему обработчику
        """
        return False


class RateLimitMiddleware:
    """
    Middleware для управления rate limiting.

    Отслеживает rate limit заголовки в ответах и может автоматически
    задерживать запросы при приближении к лимитам.

    Attributes:
        rate_limits: Словарь с информацией о rate limit для каждого ключа
        pause_on_limit: Автоматически приостанавливать запросы при достижении лимита
    """

    def __init__(self, pause_on_limit: bool = True):
        """
        Инициализирует middleware.

        Args:
            pause_on_limit: Автоматически останавливать запросы при rate limit
        """
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        self.pause_on_limit = pause_on_limit

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Проверяет rate limit перед запросом.

        Если ключ находится в rate limit и pause_on_limit=True,
        ожидает до снятия ограничения.
        """
        key = request_info.key

        if key in self.rate_limits:
            limit_info = self.rate_limits[key]
            reset_time = limit_info.get('reset_time', 0)

            if self.pause_on_limit and reset_time > time.time():
                wait_time = reset_time - time.time()
                print(f"⏸️  Rate limit active for key {key[:8]}... Waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Обновляет информацию о rate limit из заголовков ответа.

        Поддерживает стандартные заголовки:
        - X-RateLimit-Limit
        - X-RateLimit-Remaining
        - X-RateLimit-Reset
        - Retry-After
        """
        key = response_info.request_info.key
        headers = response_info.headers

        # Парсим rate limit заголовки
        rate_limit_info = {}

        if 'X-RateLimit-Limit' in headers:
            rate_limit_info['limit'] = int(headers['X-RateLimit-Limit'])

        if 'X-RateLimit-Remaining' in headers:
            rate_limit_info['remaining'] = int(headers['X-RateLimit-Remaining'])

        if 'X-RateLimit-Reset' in headers:
            rate_limit_info['reset_time'] = int(headers['X-RateLimit-Reset'])

        if 'Retry-After' in headers:
            retry_after = headers['Retry-After']
            if retry_after.isdigit():
                rate_limit_info['reset_time'] = time.time() + int(retry_after)

        if rate_limit_info:
            self.rate_limits[key] = rate_limit_info

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Обрабатывает rate limit ошибки (429).

        При получении 429 статуса, сохраняет информацию о времени
        сброса лимита для последующих запросов.
        """
        if error_info.response_info and error_info.response_info.status_code == 429:
            key = error_info.request_info.key
            print(f"⚠️  Rate limit hit for key {key[:8]}...")

            # Устанавливаем время ожидания
            if 'Retry-After' in error_info.response_info.headers:
                retry_after = int(error_info.response_info.headers['Retry-After'])
                self.rate_limits[key] = {'reset_time': time.time() + retry_after}
            else:
                # По умолчанию ждём 60 секунд
                self.rate_limits[key] = {'reset_time': time.time() + 60}

            return True  # Ошибка обработана

        return False


class CachingMiddleware:
    """
    Middleware для кэширования ответов.

    Кэширует успешные GET запросы для уменьшения нагрузки на API.

    Attributes:
        cache: Словарь с кэшированными ответами
        ttl: Время жизни кэша в секундах
        cache_only_get: Кэшировать только GET запросы
    """

    def __init__(self, ttl: int = 300, cache_only_get: bool = True):
        """
        Инициализирует middleware.

        Args:
            ttl: Время жизни кэша в секундах (по умолчанию 5 минут)
            cache_only_get: Кэшировать только GET запросы
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl
        self.cache_only_get = cache_only_get

    def _get_cache_key(self, request_info: RequestInfo) -> str:
        """Генерирует ключ кэша из информации о запросе."""
        return f"{request_info.method}:{request_info.url}"

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Проверяет наличие закэшированного ответа.

        Если ответ найден в кэше и не истёк, возвращает его.
        """
        if self.cache_only_get and request_info.method.upper() != 'GET':
            return request_info

        cache_key = self._get_cache_key(request_info)

        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if time.time() - cached['timestamp'] < self.ttl:
                print(f"✅ Cache hit for {request_info.url}")
                # Здесь можно вернуть закэшированный ответ
                # Но это требует модификации протокола

        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Кэширует успешные ответы.

        Сохраняет в кэш только ответы с успешным статус кодом (2xx).
        """
        if self.cache_only_get and response_info.request_info.method.upper() != 'GET':
            return response_info

        if 200 <= response_info.status_code < 300:
            cache_key = self._get_cache_key(response_info.request_info)
            self.cache[cache_key] = {
                'response': response_info,
                'timestamp': time.time()
            }
            print(f"💾 Cached response for {response_info.request_info.url}")

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """Middleware не обрабатывает ошибки для кэширования."""
        return False

    def clear_cache(self):
        """Очищает весь кэш."""
        self.cache.clear()

    def remove_expired(self):
        """Удаляет истёкшие записи из кэша."""
        current_time = time.time()
        expired_keys = [
            key for key, value in self.cache.items()
            if current_time - value['timestamp'] >= self.ttl
        ]
        for key in expired_keys:
            del self.cache[key]


class LoggingMiddleware:
    """
    Middleware для логирования запросов и ответов.

    Записывает информацию о каждом запросе, ответе и ошибке.
    """

    def __init__(self, verbose: bool = True):
        """
        Инициализирует middleware.

        Args:
            verbose: Выводить детальную информацию
        """
        self.verbose = verbose

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Логирует информацию о запросе."""
        if self.verbose:
            print(f"📤 {request_info.method} {request_info.url} (key: {request_info.key[:8]}...)")
        else:
            print(f"📤 {request_info.method} {request_info.url}")
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """Логирует информацию об ответе."""
        if self.verbose:
            print(f"📥 {response_info.status_code} from {response_info.request_info.url}")
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """Логирует информацию об ошибке."""
        print(f"❌ Error: {error_info.exception} for {error_info.request_info.url}")
        return False


class RetryMiddleware:
    """
    Middleware для управления retry логикой.

    Позволяет настраивать поведение retry на уровне middleware.
    """

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0):
        """
        Инициализирует middleware.

        Args:
            max_retries: Максимальное количество повторных попыток
            backoff_factor: Множитель для экспоненциального backoff
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_counts: Dict[str, int] = {}

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Отслеживает количество попыток."""
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """Сбрасывает счетчик попыток при успехе."""
        url = response_info.request_info.url
        if url in self.retry_counts:
            del self.retry_counts[url]
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """Управляет retry при ошибках."""
        url = error_info.request_info.url
        retry_count = self.retry_counts.get(url, 0)

        if retry_count < self.max_retries:
            self.retry_counts[url] = retry_count + 1
            wait_time = self.backoff_factor ** retry_count
            print(f"🔄 Retry {retry_count + 1}/{self.max_retries} after {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            return True  # Ошибка обработана, продолжаем retry

        # Исчерпаны все попытки
        del self.retry_counts[url]
        return False