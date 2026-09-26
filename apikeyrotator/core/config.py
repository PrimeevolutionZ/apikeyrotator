"""
Grouped settings of the rotators.

Every group can be passed as one object instead of its flat keyword arguments::

    retry = RetryConfig(max_retries=5, total_timeout=30)
    a = APIKeyRotator(api_keys=keys_a, retry=retry)
    b = APIKeyRotator(api_keys=keys_b, retry=retry)      # same settings, one place

The objects are frozen, so one instance can be shared by several rotators. Setting a
value both in an object and as a flat argument raises ``TypeError``.
"""

from __future__ import annotations
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from .policy import DEFAULT_MAX_DELAY


if TYPE_CHECKING:
    from apikeyrotator.state import StateBackend


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Attempts, backoff, timeouts and what may be retried (``retry=``)."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = DEFAULT_MAX_DELAY
    timeout: float = 10.0
    total_timeout: float | None = None
    retry_non_idempotent: bool = False
    auto_idempotency_key: bool | str = False
    should_retry_callback: Callable[[Any], bool] | None = None


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Client-side rate limits (``rate_limits=``)."""
    key_rate_limit: tuple[int, float] | None = None
    respect_rate_limit_headers: bool = True


@dataclass(frozen=True, slots=True)
class SharedStateConfig:
    """State shared between rotators / processes, e.g. through Redis (``shared_state=``)."""
    backend: StateBackend | None = None
    sync_interval: float = 1.0


@dataclass(frozen=True, slots=True)
class RequestConfig:
    """How requests are built: auth header, extra headers, user agents, proxies (``request=``)."""
    auth: str | tuple[str, str] | bool | None = None
    header_callback: Callable[[str, dict | None], dict | tuple[dict, dict]] | None = None
    user_agents: list[str] | None = None
    proxy_list: list[str] | None = None
    random_delay_range: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class HTTPConfig:
    """HTTP client (``http=``). ``backend=None`` = the rotator's default (requests / aiohttp)."""
    backend: str | None = None
    http2: bool = False
    pool_size: int = 100
    client_kwargs: dict[str, Any] | None = None


#: Config class -> {field: flat keyword argument}
FLAT_NAMES: dict[type, dict[str, str]] = {
    RetryConfig: {f.name: f.name for f in fields(RetryConfig)},
    RateLimitConfig: {f.name: f.name for f in fields(RateLimitConfig)},
    SharedStateConfig: {"backend": "state_backend", "sync_interval": "state_sync_interval"},
    RequestConfig: {f.name: f.name for f in fields(RequestConfig)},
    HTTPConfig: {"backend": "http_backend", "http2": "http2", "pool_size": "pool_size",
                 "client_kwargs": "http_client_kwargs"},
}


def merge_config(param: str, config: Any, flat: Mapping[str, Any],
                 flat_defaults: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """
    Effective flat values of one group.

    Args:
        param: Name of the constructor argument holding ``config`` (for error messages).
        config: The config object, or None to use ``flat`` as is.
        flat: Flat keyword arguments of the group as passed to the constructor.
        flat_defaults: Defaults of flat arguments that differ from the config's defaults.
    """
    if config is None:
        return dict(flat)
    names = FLAT_NAMES[type(config)]
    defaults = {names[f.name]: f.default for f in fields(config)}
    defaults.update(flat_defaults or {})
    conflicts = [name for name, value in flat.items() if value != defaults[name]]
    if conflicts:
        raise TypeError(f"{', '.join(conflicts)} given both directly and in {param}=; use one of them")
    result = dict(flat)
    for field in fields(config):
        name = names[field.name]
        value = getattr(config, field.name)
        if value is None and flat_defaults and name in flat_defaults:
            value = flat_defaults[name]   # e.g. HTTPConfig(backend=None): the rotator's default
        result[name] = value
    return result
