"""
HTTP transports used by the rotators.

A transport hides the differences between HTTP client libraries (requests,
aiohttp, httpx): how a request is sent, how per-attempt timeouts and proxies
are passed, how the status/body are read, how a response is released and which
exceptions are network errors.

HTTP libraries are imported lazily, so importing apikeyrotator does not load
aiohttp for sync-only users (and vice versa).
"""

from __future__ import annotations
import asyncio
from collections.abc import Callable
from typing import Any


# Error classes that mean "the request never reached the server" are safe to
# retry even for non-idempotent methods (POST/PATCH).


def _unsupported(backend: str, name: str) -> TypeError:
    return TypeError(
        f"Argument {name!r} is not supported per request by the {backend} backend; "
        f"configure it via http_client_kwargs"
    )


# ============================================================================
# SYNC
# ============================================================================

class SyncTransport:
    """Interface of a synchronous transport."""

    name = "base"
    network_errors: tuple[type[Exception], ...] = ()
    session: Any = None

    def request(self, method: str, url: str, kwargs: dict[str, Any],
                proxy: str | None, timeout: float | None) -> Any:
        raise NotImplementedError

    @staticmethod
    def status(response: Any) -> int:
        status: int = response.status_code
        return status

    @staticmethod
    def content(response: Any) -> bytes:
        content: bytes = response.content
        return content

    @staticmethod
    def close_response(response: Any) -> None:
        close = getattr(response, "close", None)
        if close is not None:
            close()

    def is_safe_to_retry_error(self, exc: BaseException) -> bool:
        """True if the request certainly never reached the server."""
        return False

    def close(self) -> None:
        pass


class RequestsTransport(SyncTransport):
    """Transport based on ``requests.Session`` (default for APIKeyRotator)."""

    name = "requests"

    def __init__(self, pool_size: int, http_client_kwargs: dict[str, Any] | None = None):
        import requests
        import requests.adapters

        self._requests = requests
        self.network_errors = (requests.RequestException,)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=pool_size, pool_maxsize=pool_size, max_retries=0
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        for attr, value in (http_client_kwargs or {}).items():
            setattr(self.session, attr, value)  # e.g. verify=False, cert=..., trust_env=False

    def request(self, method, url, kwargs, proxy, timeout):
        if timeout is not None:
            kwargs["timeout"] = timeout
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        return self.session.request(method, url, **kwargs)

    def is_safe_to_retry_error(self, exc):
        requests = self._requests
        if isinstance(exc, requests.exceptions.ConnectTimeout):
            return True
        if isinstance(exc, requests.exceptions.ConnectionError):
            try:
                from urllib3.exceptions import NewConnectionError
            except ImportError:  # pragma: no cover
                return False
            reason = exc.args[0] if exc.args else None
            reason = getattr(reason, "reason", reason)
            return isinstance(reason, NewConnectionError)
        return False

    def close(self):
        self.session.close()


_HTTPX_PASSTHROUGH = frozenset({
    "params", "headers", "cookies", "json", "files", "content", "extensions",
})


def _httpx_kwargs(kwargs: dict[str, Any], timeout: float | None) -> tuple[dict[str, Any], bool]:
    """Translates requests-style kwargs into httpx ones. Returns (kwargs, stream)."""
    out: dict[str, Any] = {}
    stream = False
    follow = True  # requests follows redirects by default; keep the same behaviour
    for name, value in kwargs.items():
        if name in _HTTPX_PASSTHROUGH:
            out[name] = value
        elif name == "data":
            if isinstance(value, (bytes, str)) or hasattr(value, "read"):
                out["content"] = value
            else:
                out["data"] = value
        elif name in ("allow_redirects", "follow_redirects"):
            follow = bool(value)
        elif name == "stream":
            stream = bool(value)
        elif name == "timeout":
            if timeout is None:
                out["timeout"] = value  # e.g. httpx.Timeout object
        elif name in ("proxies", "proxy", "verify", "cert", "auth", "hooks", "trust_env"):
            raise _unsupported("httpx", name)
        else:
            raise TypeError(f"Unsupported request argument for the httpx backend: {name!r}")
    out["follow_redirects"] = follow
    if timeout is not None:
        out["timeout"] = timeout
    return out, stream


class _HttpxClients:
    """One httpx client per proxy (httpx configures proxies per client)."""

    def __init__(self, factory: Callable[[str | None], Any]):
        self._factory = factory
        self.clients: dict[str | None, Any] = {}

    def get(self, proxy: str | None) -> Any:
        client = self.clients.get(proxy)
        if client is None:
            client = self.clients[proxy] = self._factory(proxy)
        return client


class HttpxSyncTransport(SyncTransport):
    """Transport based on ``httpx.Client`` (``pip install apikeyrotator[httpx]``)."""

    name = "httpx"

    def __init__(self, pool_size: int, http2: bool = False,
                 http_client_kwargs: dict[str, Any] | None = None):
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx backend requires httpx: pip install 'apikeyrotator[httpx]'"
            ) from e
        self._httpx = httpx
        self.network_errors = (httpx.TransportError,)
        self._safe = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
        limits = httpx.Limits(max_connections=pool_size, max_keepalive_connections=pool_size)
        client_kwargs = dict(http_client_kwargs or {})

        def factory(proxy):
            return httpx.Client(limits=limits, http2=http2, proxy=proxy, **client_kwargs)

        self._clients = _HttpxClients(factory)
        self.session = self._clients.get(None)

    def request(self, method, url, kwargs, proxy, timeout):
        client = self._clients.get(proxy) if proxy else self.session
        params, stream = _httpx_kwargs(kwargs, timeout)
        if stream:
            follow = params.pop("follow_redirects")
            timeout_value = params.pop("timeout", None)
            extra = {"timeout": timeout_value} if timeout_value is not None else {}
            request = client.build_request(method, url, **params, **extra)
            return client.send(request, stream=True, follow_redirects=follow)
        return client.request(method, url, **params)

    def is_safe_to_retry_error(self, exc):
        return isinstance(exc, self._safe)

    def close(self):
        for client in self._clients.clients.values():
            client.close()


def create_sync_transport(backend: str, pool_size: int, http2: bool,
                          http_client_kwargs: dict[str, Any] | None) -> SyncTransport:
    backend = (backend or "requests").lower()
    if backend == "requests":
        if http2:
            raise ValueError("HTTP/2 requires http_backend='httpx'")
        return RequestsTransport(pool_size, http_client_kwargs)
    if backend == "httpx":
        return HttpxSyncTransport(pool_size, http2, http_client_kwargs)
    raise ValueError(f"Unknown sync http_backend {backend!r}; use 'requests' or 'httpx'")


# ============================================================================
# ASYNC
# ============================================================================

class AsyncTransport:
    """Interface of an asynchronous transport."""

    name = "base"
    network_errors: tuple[type[Exception], ...] = ()
    session: Any = None

    async def request(self, method: str, url: str, kwargs: dict[str, Any],
                      proxy: str | None, timeout: float | None) -> Any:
        raise NotImplementedError

    @staticmethod
    def status(response: Any) -> int:
        raise NotImplementedError

    async def read(self, response: Any) -> bytes:
        raise NotImplementedError

    async def release(self, response: Any) -> None:
        pass

    def is_safe_to_retry_error(self, exc: BaseException) -> bool:
        return False

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    if hasattr(value, "__await__"):
        return await value
    return value


class AiohttpTransport(AsyncTransport):
    """Transport based on ``aiohttp.ClientSession`` (default for AsyncAPIKeyRotator)."""

    name = "aiohttp"

    def __init__(self, pool_size: int, default_timeout: float,
                 http_client_kwargs: dict[str, Any] | None = None):
        import aiohttp

        self._aiohttp = aiohttp
        self.network_errors = (aiohttp.ClientError, asyncio.TimeoutError)
        safe = [aiohttp.ClientConnectorError]
        connection_timeout = getattr(aiohttp, "ConnectionTimeoutError", None)
        if connection_timeout is not None:
            safe.append(connection_timeout)
        self._safe = tuple(safe)
        self._pool_size = pool_size
        self._default_timeout = default_timeout
        self._client_kwargs = dict(http_client_kwargs or {})
        self.session = None

    async def open(self):
        aiohttp = self._aiohttp
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._default_timeout),
                connector=aiohttp.TCPConnector(limit=self._pool_size),
                **self._client_kwargs,
            )
        return self.session

    async def request(self, method, url, kwargs, proxy, timeout):
        session = self.session
        if session is None or session.closed:
            session = await self.open()
        if timeout is not None:
            kwargs["timeout"] = self._aiohttp.ClientTimeout(total=timeout)
        if proxy:
            kwargs["proxy"] = proxy
        kwargs.pop("stream", None)
        return await session.request(method, url, **kwargs)

    @staticmethod
    def status(response):
        return response.status

    async def read(self, response):
        return await response.read()

    async def release(self, response):
        release = getattr(response, "release", None)
        if release is not None:
            try:
                await _maybe_await(release())
            except Exception:
                pass

    def is_safe_to_retry_error(self, exc):
        return isinstance(exc, self._safe)

    async def close(self):
        if self.session is not None and not self.session.closed:
            await self.session.close()
        self.session = None


class HttpxAsyncTransport(AsyncTransport):
    """Transport based on ``httpx.AsyncClient`` (``pip install apikeyrotator[httpx]``)."""

    name = "httpx"

    def __init__(self, pool_size: int, default_timeout: float, http2: bool = False,
                 http_client_kwargs: dict[str, Any] | None = None):
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx backend requires httpx: pip install 'apikeyrotator[httpx]'"
            ) from e
        self._httpx = httpx
        self.network_errors = (httpx.TransportError,)
        self._safe = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
        limits = httpx.Limits(max_connections=pool_size, max_keepalive_connections=pool_size)
        client_kwargs = {"timeout": default_timeout, **(http_client_kwargs or {})}

        def factory(proxy):
            return httpx.AsyncClient(limits=limits, http2=http2, proxy=proxy, **client_kwargs)

        self._factory = factory
        self._clients = _HttpxClients(factory)
        self.session = None

    async def open(self):
        if self.session is None or self.session.is_closed:
            self._clients = _HttpxClients(self._factory)
            self.session = self._clients.get(None)
        return self.session

    async def request(self, method, url, kwargs, proxy, timeout):
        if self.session is None or self.session.is_closed:
            await self.open()
        client = self._clients.get(proxy) if proxy else self.session
        params, stream = _httpx_kwargs(kwargs, timeout)
        if stream:
            follow = params.pop("follow_redirects")
            timeout_value = params.pop("timeout", None)
            extra = {"timeout": timeout_value} if timeout_value is not None else {}
            request = client.build_request(method, url, **params, **extra)
            return await client.send(request, stream=True, follow_redirects=follow)
        return await client.request(method, url, **params)

    @staticmethod
    def status(response):
        return response.status_code

    async def read(self, response):
        return await response.aread()

    async def release(self, response):
        try:
            await response.aclose()
        except Exception:
            pass

    def is_safe_to_retry_error(self, exc):
        return isinstance(exc, self._safe)

    async def close(self):
        for client in list(self._clients.clients.values()):
            await client.aclose()
        self._clients = _HttpxClients(self._factory)
        self.session = None


def create_async_transport(backend: str, pool_size: int, default_timeout: float, http2: bool,
                           http_client_kwargs: dict[str, Any] | None) -> AsyncTransport:
    backend = (backend or "aiohttp").lower()
    if backend == "aiohttp":
        if http2:
            raise ValueError("HTTP/2 requires http_backend='httpx'")
        return AiohttpTransport(pool_size, default_timeout, http_client_kwargs)
    if backend == "httpx":
        return HttpxAsyncTransport(pool_size, default_timeout, http2, http_client_kwargs)
    raise ValueError(f"Unknown async http_backend {backend!r}; use 'aiohttp' or 'httpx'")
