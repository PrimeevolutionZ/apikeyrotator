"""Builds the per-attempt request: auth header, custom headers/cookies, user agent, proxy."""

from __future__ import annotations
import threading
from collections.abc import Callable
from typing import Any

from apikeyrotator.middleware import RequestInfo

from .util import host_of


API_KEY_PATTERNS = {
    'bearer': ('sk-', 'pk-'),
    'api_key': 32,
}

DEFAULT_AUTH_HEADERS = {
    'bearer': 'Authorization',
    'api_key': 'X-API-Key',
}

_AUTH_CACHE_SIZE = 4096

HeaderCallback = Callable[[str, dict | None], dict | tuple[dict, dict]]


def infer_auth_header(key: str) -> tuple[str, str]:
    """Default auth header for a key: sk-/pk- -> Bearer, 32 chars -> X-API-Key, else 'Key ...'."""
    for prefix in API_KEY_PATTERNS['bearer']:
        if key.startswith(prefix):
            return DEFAULT_AUTH_HEADERS['bearer'], f"Bearer {key}"
    if len(key) == API_KEY_PATTERNS['api_key']:
        return DEFAULT_AUTH_HEADERS['api_key'], key
    return DEFAULT_AUTH_HEADERS['bearer'], f"Key {key}"


class RequestBuilder:
    __slots__ = ('header_callback', 'user_agents', 'proxy_list', 'save_sensitive_headers',
                 'config', '_ua_index', '_proxy_index', '_lock', '_auth_cache')

    def __init__(self, header_callback: HeaderCallback | None = None,
                 user_agents: list[str] | None = None, proxy_list: list[str] | None = None,
                 save_sensitive_headers: bool = False, config: dict | None = None):
        self.header_callback = header_callback
        self.user_agents = user_agents or []
        self.proxy_list = proxy_list or []
        self.save_sensitive_headers = save_sensitive_headers
        self.config = config if config is not None else {}
        self._ua_index = 0
        self._proxy_index = 0
        self._lock = threading.Lock()
        # key -> inferred auth header; bounded (reset when full) because keys can be rotated
        self._auth_cache: dict[str, tuple[str, str]] = {}

    def next_user_agent(self) -> str | None:
        agents = self.user_agents
        if not agents:
            return None
        with self._lock:
            ua = agents[self._ua_index % len(agents)]
            self._ua_index = (self._ua_index + 1) % len(agents)
        return ua

    def next_proxy(self) -> str | None:
        proxies = self.proxy_list
        if not proxies:
            return None
        with self._lock:
            proxy = proxies[self._proxy_index % len(proxies)]
            self._proxy_index = (self._proxy_index + 1) % len(proxies)
        return proxy

    def headers_and_cookies(self, key: str, custom_headers: dict[str, str] | None,
                            url: str) -> tuple[dict[str, str], dict[str, str]]:
        headers = dict(custom_headers) if custom_headers else {}
        cookies: dict[str, str] = {}

        if self.save_sensitive_headers:
            domain = host_of(url) if url else ""
            if domain:
                saved = self.config.get("successful_headers", {}).get(domain, {})
                headers.update(
                    (k, v) for k, v in saved.items() if k.lower() not in ("authorization", "x-api-key")
                )

        if self.header_callback:
            result = self.header_callback(key, custom_headers)
            if isinstance(result, tuple) and len(result) == 2:
                headers.update(result[0])
                cookies.update(result[1])
            elif isinstance(result, dict):
                headers.update(result)

        present = {h.lower() for h in headers} if headers else ()
        # Add the inferred auth header only if the request/callback set no auth header
        # itself - otherwise the key would be sent twice (e.g. X-API-Key + Authorization).
        if "authorization" not in present and "x-api-key" not in present:
            auth = self._auth_cache.get(key)
            if auth is None:
                if len(self._auth_cache) >= _AUTH_CACHE_SIZE:
                    self._auth_cache = {}
                auth = self._auth_cache[key] = infer_auth_header(key)
            headers[auth[0]] = auth[1]

        if self.user_agents and "user-agent" not in present:
            user_agent = self.next_user_agent()
            if user_agent:
                headers["User-Agent"] = user_agent

        return headers, cookies

    def build(self, method: str, url: str, key: str, kwargs: dict[str, Any], attempt: int,
              with_info: bool) -> tuple[dict[str, Any], RequestInfo | None]:
        """Request kwargs for one attempt (+ RequestInfo for middlewares when `with_info`)."""
        headers, cookies = self.headers_and_cookies(key, kwargs.get("headers"), url)

        request_kwargs = dict(kwargs)
        request_kwargs["headers"] = headers
        user_cookies = kwargs.get("cookies")
        if isinstance(user_cookies, dict):
            cookies = {**user_cookies, **cookies}
        request_kwargs["cookies"] = cookies

        request_info = None
        if with_info:
            request_info = RequestInfo(
                method=method, url=url, headers=headers, cookies=cookies,
                key=key, attempt=attempt, kwargs=request_kwargs
            )
        return request_kwargs, request_info
