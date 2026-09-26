"""Builds the per-attempt request: auth header, custom headers/cookies, user agent, proxy."""

from __future__ import annotations
import threading
from collections.abc import Callable
from typing import Any, Literal

from apikeyrotator.middleware import RequestInfo

from .util import host_of, mask_key


#: Kept for backwards compatibility (re-exported by apikeyrotator.core.rotator)
API_KEY_PATTERNS: dict[str, Any] = {
    'bearer': ('sk-', 'pk-'),
    'api_key': 32,
}
_BEARER_PREFIXES = ('sk-', 'pk-')
_X_API_KEY_LENGTH = 32

DEFAULT_AUTH_HEADERS = {
    'bearer': 'Authorization',
    'api_key': 'X-API-Key',
}

_AUTH_CACHE_SIZE = 4096

HeaderCallback = Callable[[str, dict | None], dict | tuple[dict, dict]]


def infer_auth_header(key: str) -> tuple[str, str]:
    """Default auth header for a key: 32 characters -> X-API-Key, anything else -> Bearer."""
    if len(key) == _X_API_KEY_LENGTH and not key.startswith(_BEARER_PREFIXES):
        return DEFAULT_AUTH_HEADERS['api_key'], key
    return DEFAULT_AUTH_HEADERS['bearer'], f"Bearer {key}"


AuthSpec = str | tuple[str, str] | bool | None

_AUTH_ALIASES = {
    "bearer": ("Authorization", "Bearer {key}"),
    "x-api-key": ("X-API-Key", "{key}"),
}


def resolve_auth(auth: AuthSpec) -> tuple[str, str] | Literal[False] | None:
    """
    Normalizes the ``auth`` argument.

    None -> infer per key (see infer_auth_header); False -> no auth header;
    "bearer" / "x-api-key" -> that scheme; (header, template) -> e.g.
    ("Authorization", "Token {key}") or ("x-goog-api-key", "{key}").
    """
    if auth is None:
        return None
    if auth is False:
        return False
    if isinstance(auth, str):
        alias = _AUTH_ALIASES.get(auth.lower())
        if alias is None:
            raise ValueError(
                f"Unknown auth scheme {auth!r}. Use 'bearer', 'x-api-key', "
                f"a (header, template) tuple such as ('Authorization', 'Token {{key}}'), "
                f"False (no auth header) or header_callback="
            )
        return alias
    if (isinstance(auth, tuple) and len(auth) == 2 and all(isinstance(x, str) for x in auth)
            and "{key}" in auth[1]):
        return auth[0], auth[1]
    raise ValueError("auth must be 'bearer', 'x-api-key', (header, template with '{key}'), False or None")


class RequestBuilder:
    __slots__ = ('header_callback', 'user_agents', 'proxy_list', 'save_sensitive_headers',
                 'config', '_ua_index', '_proxy_index', '_lock', '_auth_cache', '_auth', '_auth_spec')

    def __init__(self, header_callback: HeaderCallback | None = None,
                 user_agents: list[str] | None = None, proxy_list: list[str] | None = None,
                 save_sensitive_headers: bool = False, config: dict | None = None,
                 auth: AuthSpec = None):
        self.header_callback = header_callback
        self.user_agents = user_agents or []
        self.proxy_list = proxy_list or []
        self.save_sensitive_headers = save_sensitive_headers
        self.config = config if config is not None else {}
        self._ua_index = 0
        self._proxy_index = 0
        self._lock = threading.Lock()
        # key -> auth header; bounded (reset when full) because keys can be rotated
        self._auth_cache: dict[str, tuple[str, str]] = {}
        self.auth = auth

    @property
    def auth(self) -> AuthSpec:
        return self._auth_spec

    @auth.setter
    def auth(self, auth: AuthSpec) -> None:
        self._auth = resolve_auth(auth)
        self._auth_spec = auth
        self._auth_cache = {}

    def masked_auth_header(self, key: str) -> str | None:
        """The auth header for `key` as text, with the key masked (for error messages)."""
        mode = self._auth
        if mode is False:
            return None
        if mode is None:
            name, value = infer_auth_header(key)
            return f"{name}: {value[:len(value) - len(key)]}{mask_key(key)}"
        return f"{mode[0]}: {mode[1].format(key=mask_key(key))}"

    def auth_header(self, key: str) -> tuple[str, str] | None:
        """The auth header sent with `key` (None when auth=False)."""
        mode = self._auth
        if mode is False:
            return None
        header = self._auth_cache.get(key)
        if header is None:
            if len(self._auth_cache) >= _AUTH_CACHE_SIZE:
                self._auth_cache = {}
            header = infer_auth_header(key) if mode is None else (mode[0], mode[1].format(key=key))
            self._auth_cache[key] = header
        return header

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

        key_in_callback = False
        if self.header_callback:
            # Any: user code - checked below instead of trusting its annotation
            result: Any = self.header_callback(key, custom_headers)
            if isinstance(result, tuple) and len(result) == 2:
                callback_headers = result[0]
                cookies.update(result[1])
            elif isinstance(result, dict):
                callback_headers = result
            else:
                callback_headers = {}
            headers.update(callback_headers)
            # The callback already sends the key (in any header) - don't send it twice
            key_in_callback = any(isinstance(v, str) and key in v for v in callback_headers.values())

        present = {h.lower() for h in headers} if headers else ()
        if not key_in_callback and "authorization" not in present and "x-api-key" not in present:
            auth = self.auth_header(key)
            if auth is not None and auth[0].lower() not in present:
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
