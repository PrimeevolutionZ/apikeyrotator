"""Response objects the rotator builds itself (middleware short-circuits, classifier views)."""

from __future__ import annotations
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import timedelta
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


# ============================================================================
# Unified response (unified_response=True)
# ============================================================================

_CHARSET = re.compile(r"charset=([\w.:-]+)", re.I)


class Headers(Mapping[str, str]):
    """
    Case-insensitive, read-only response headers.

    ``headers["content-type"]`` works whatever the server's spelling; repeated
    headers are joined with ", " (like requests/httpx), ``get_list()`` returns
    them separately (e.g. ``Set-Cookie``). Built lazily from the client's headers
    on first access.
    """

    __slots__ = ("_source", "_items", "_index")

    def __init__(self, items: Any = ()):
        self._source = items
        self._items: list[tuple[str, str]] | None = None
        self._index: dict[str, list[str]] | None = None

    def _load(self) -> dict[str, list[str]]:
        items = [(str(k), str(v)) for k, v in _header_items(self._source)]
        index: dict[str, list[str]] = {}
        for k, v in items:
            index.setdefault(k.lower(), []).append(v)
        self._items, self._index, self._source = items, index, None
        return index

    def __getitem__(self, name: str) -> str:
        index = self._index if self._index is not None else self._load()
        return ", ".join(index[name.lower()])

    def __contains__(self, name: object) -> bool:
        index = self._index if self._index is not None else self._load()
        return isinstance(name, str) and name.lower() in index

    def __iter__(self) -> Iterator[str]:
        if self._index is None:
            self._load()
        seen = set()
        for k, _ in self._items:
            if k.lower() not in seen:
                seen.add(k.lower())
                yield k

    def __len__(self) -> int:
        index = self._index if self._index is not None else self._load()
        return len(index)

    def get_list(self, name: str) -> list[str]:
        """All values of a (repeated) header."""
        index = self._index if self._index is not None else self._load()
        return list(index.get(name.lower(), ()))

    def multi_items(self) -> list[tuple[str, str]]:
        """All (name, value) pairs as sent, including repeated headers."""
        if self._index is None:
            self._load()
        return list(self._items)

    def __repr__(self) -> str:
        return f"Headers({dict(self)!r})"


def _header_items(headers: Any) -> Iterable[tuple[str, str]]:
    if headers is None:
        return ()
    multi = getattr(headers, "multi_items", None)  # httpx
    if multi is not None:
        return multi()
    items = getattr(headers, "items", None)       # requests/urllib3, aiohttp (multidict), dict
    return items() if items is not None else headers


_PHRASES = {status.value: status.phrase for status in HTTPStatus}


class UnifiedResponse:
    """
    One response type for every HTTP client (``unified_response=True``).

    The body is already read, so the API is the same for ``APIKeyRotator`` and
    ``AsyncAPIKeyRotator`` and for the requests, aiohttp and httpx backends -
    ``response.json()`` is never awaited. The client's own object is ``native``
    (its connection is already released).

    Like httpx, and unlike ``requests.Response``, the object is always truthy:
    check ``response.ok``, not ``if response:``.
    """

    __slots__ = ("status_code", "headers", "content", "url", "reason", "native",
                 "_elapsed", "_encoding")

    def __init__(self, status_code: int, headers: Any = None, content: bytes | str | None = b"",
                 url: str = "", reason: str | None = None, elapsed: float | timedelta = 0.0,
                 native: Any = None):
        self.status_code = status_code
        self.headers = headers if headers.__class__ is Headers else Headers(headers)
        if content.__class__ is not bytes:
            content = b"" if content is None else (
                content.encode("utf-8") if isinstance(content, str) else bytes(content))
        self.content: bytes = content
        self.url = url if url.__class__ is str else str(url or "")
        self.reason: str = reason or _PHRASES.get(status_code, "")
        self._elapsed = elapsed
        self.native = native
        self._encoding: str | None = None

    @classmethod
    def from_native(cls, response: Any, status_code: int, content: bytes | None,
                    elapsed: float = 0.0) -> UnifiedResponse:
        """Wraps a requests / aiohttp / httpx response whose body was read (``content``)."""
        reason = getattr(response, "reason", None) or getattr(response, "reason_phrase", None)
        headers = response.headers
        # requests merges repeated headers; urllib3 underneath keeps them (e.g. Set-Cookie)
        raw_headers = getattr(getattr(response, "raw", None), "headers", None)
        if raw_headers is not None and hasattr(raw_headers, "getlist"):
            headers = raw_headers
        return cls(status_code, headers, content, getattr(response, "url", ""),
                   reason if isinstance(reason, str) else None, elapsed, response)

    @classmethod
    def from_info(cls, info: ResponseInfo, url: str) -> UnifiedResponse:
        """Response answered by a middleware (e.g. a cache hit)."""
        return cls(info.status_code, info.headers, info.content, url, elapsed=info.response_time or 0.0)

    @property
    def elapsed(self) -> timedelta:
        """Time from sending the request to receiving the response (like requests/httpx)."""
        elapsed = self._elapsed
        return elapsed if isinstance(elapsed, timedelta) else timedelta(seconds=elapsed)

    # --- aliases for code written against a specific client ---

    @property
    def status(self) -> int:
        """Same as ``status_code`` (aiohttp name)."""
        return self.status_code

    @property
    def reason_phrase(self) -> str:
        """Same as ``reason`` (httpx name)."""
        return self.reason

    # --- body ---

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    @property
    def encoding(self) -> str:
        """Charset from ``Content-Type`` (default utf-8); can be set."""
        if self._encoding:
            return self._encoding
        match = _CHARSET.search(self.headers.get("content-type", ""))
        return match.group(1) if match else "utf-8"

    @encoding.setter
    def encoding(self, value: str) -> None:
        self._encoding = value

    @property
    def text(self) -> str:
        try:
            return self.content.decode(self.encoding, errors="replace")
        except LookupError:  # unknown charset
            return self.content.decode("utf-8", errors="replace")

    def json(self, **kwargs) -> Any:
        """Parses the body as JSON (raises json.JSONDecodeError for non-JSON bodies)."""
        try:
            return json.loads(self.content, **kwargs)
        except UnicodeDecodeError:  # not UTF-8/16/32: decode with the declared charset
            return json.loads(self.text, **kwargs)

    def raise_for_status(self) -> UnifiedResponse:
        """Raises HTTPStatusError (with ``.response``) for 4xx/5xx; returns self otherwise."""
        if self.status_code >= 400:
            kind = "Client" if self.status_code < 500 else "Server"
            raise HTTPStatusError(
                self.status_code, f"{kind} error {self.status_code} {self.reason} for url: {self.url}",
                response=self,
            )
        return self

    # --- no-op resource management (the connection is already released) ---

    def close(self) -> None:
        pass

    async def aclose(self) -> None:
        pass

    def release(self) -> None:
        pass

    def __enter__(self) -> UnifiedResponse:
        return self

    def __exit__(self, *exc) -> None:
        return None

    async def __aenter__(self) -> UnifiedResponse:
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def __repr__(self) -> str:
        return f"<UnifiedResponse [{self.status_code}]>"
