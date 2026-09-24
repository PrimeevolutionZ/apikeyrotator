"""Response objects the rotator builds itself (middleware short-circuits, classifier views)."""

from __future__ import annotations
import json
from http import HTTPStatus
from typing import Any

from apikeyrotator.middleware import ResponseInfo

from .exceptions import HTTPStatusError


class StatusView:
    """Status code + headers in the shape ErrorClassifier expects (async responses)."""
    __slots__ = ('status_code', 'headers')

    def __init__(self, status_code: int, headers: Any = None):
        self.status_code = status_code
        self.headers = headers if headers is not None else {}


class CachedAsyncResponse:
    """
    Minimal aiohttp/httpx-like response returned for middleware short-circuits
    (e.g. cache hits). Exposes both ``status`` (aiohttp) and ``status_code`` (httpx).
    """

    def __init__(self, status: int, headers: Any, content: Any, url: str = ""):
        self.status = status
        self.headers = dict(headers or {})
        self.url = url
        if content is None:
            content = b''
        self._content = content if isinstance(content, bytes) else str(content).encode('utf-8')

    @property
    def status_code(self) -> int:
        return self.status

    @property
    def content(self) -> bytes:
        return self._content

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400

    @property
    def reason(self) -> str:
        try:
            return HTTPStatus(self.status).phrase
        except ValueError:
            return ""

    async def read(self) -> bytes:
        return self._content

    async def aread(self) -> bytes:
        return self._content

    async def text(self, encoding: str = 'utf-8') -> str:
        return self._content.decode(encoding)

    async def json(self, **kwargs) -> Any:
        return json.loads(self._content)

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise HTTPStatusError(self.status)

    def release(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def build_async_response(info: ResponseInfo, url: str) -> CachedAsyncResponse:
    return CachedAsyncResponse(info.status_code, info.headers, info.content, url)


def build_sync_response(info: ResponseInfo, url: str, backend: str = "requests") -> Any:
    """Builds a response object from a middleware-provided ResponseInfo (e.g. cache hit)."""
    content = info.content
    if content is None:
        content = b''
    elif isinstance(content, str):
        content = content.encode('utf-8')
    headers = info.headers if isinstance(info.headers, dict) else {}

    if backend == "httpx":
        import httpx

        return httpx.Response(info.status_code, headers=headers, content=content,
                              request=httpx.Request("GET", url))

    import requests
    import requests.utils

    response = requests.Response()
    response.status_code = info.status_code
    response._content = content
    response._content_consumed = True
    response.headers.update(headers)
    response.url = url
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    try:
        response.reason = HTTPStatus(info.status_code).phrase
    except ValueError:
        response.reason = ""
    return response
