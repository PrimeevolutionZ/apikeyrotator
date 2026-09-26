"""Grouped settings: retry=RetryConfig(...) etc. instead of flat keyword arguments."""

import dataclasses
import inspect
import warnings

import pytest

from apikeyrotator import (
    APIKeyRotator,
    AsyncAPIKeyRotator,
    HTTPConfig,
    InMemoryStateBackend,
    RateLimitConfig,
    RequestConfig,
    RetryConfig,
    SharedStateConfig,
)
from apikeyrotator.core.config import FLAT_NAMES
from apikeyrotator.core.rotator import BaseKeyRotator


def _flat_defaults(cls):
    params = {**inspect.signature(BaseKeyRotator.__init__).parameters,
              **inspect.signature(cls.__init__).parameters}
    return {name: p.default for name, p in params.items()}


@pytest.mark.parametrize("config_cls", list(FLAT_NAMES))
def test_config_defaults_match_the_flat_arguments(config_cls):
    flat = _flat_defaults(APIKeyRotator)
    for field in dataclasses.fields(config_cls):
        name = FLAT_NAMES[config_cls][field.name]
        if config_cls is HTTPConfig and field.name == "backend":
            continue   # None = the rotator's own default
        assert field.default == flat[name], name


def test_every_flat_argument_of_a_group_is_covered():
    flat = _flat_defaults(APIKeyRotator)
    for names in FLAT_NAMES.values():
        assert set(names.values()) <= set(flat)


def test_config_objects_set_the_same_attributes_as_flat_arguments():
    backend = InMemoryStateBackend()
    grouped = APIKeyRotator(
        api_keys=["k1"],
        retry=RetryConfig(max_retries=5, base_delay=0.1, max_delay=2, timeout=3, total_timeout=9,
                          retry_non_idempotent=True, auto_idempotency_key="X-Req"),
        rate_limits=RateLimitConfig(key_rate_limit=(10, 60), respect_rate_limit_headers=False),
        shared_state=SharedStateConfig(backend=backend, sync_interval=0.5),
        request=RequestConfig(auth="x-api-key", user_agents=["UA"], proxy_list=["http://p"],
                              random_delay_range=(0.0, 0.0)),
        http=HTTPConfig(pool_size=7),
    )
    flat = APIKeyRotator(
        api_keys=["k1"], max_retries=5, base_delay=0.1, max_delay=2, timeout=3, total_timeout=9,
        retry_non_idempotent=True, auto_idempotency_key="X-Req", key_rate_limit=(10, 60),
        respect_rate_limit_headers=False, state_backend=backend, state_sync_interval=0.5,
        auth="x-api-key", user_agents=["UA"], proxy_list=["http://p"], random_delay_range=(0.0, 0.0),
        pool_size=7,
    )
    for attr in ("max_retries", "base_delay", "max_delay", "timeout", "total_timeout",
                 "retry_non_idempotent", "auto_idempotency_key", "key_rate_limit",
                 "respect_rate_limit_headers", "state_backend", "state_sync_interval", "auth",
                 "user_agents", "proxy_list", "random_delay_range", "pool_size", "http_backend"):
        assert getattr(grouped, attr) == getattr(flat, attr), attr


def test_one_config_is_shared_by_several_rotators():
    retry = RetryConfig(max_retries=7)
    a = APIKeyRotator(api_keys=["a"], retry=retry)
    b = APIKeyRotator(api_keys=["b"], retry=retry)
    a.max_retries = 2                      # changing one rotator doesn't touch the other
    assert (a.max_retries, b.max_retries, retry.max_retries) == (2, 7, 7)
    with pytest.raises(dataclasses.FrozenInstanceError):
        retry.max_retries = 1              # type: ignore[misc]


def test_value_given_twice_is_an_error():
    with pytest.raises(TypeError, match="max_retries given both directly and in retry="):
        APIKeyRotator(api_keys=["k"], max_retries=5, retry=RetryConfig(timeout=3))
    with pytest.raises(TypeError, match="pool_size"):
        APIKeyRotator(api_keys=["k"], pool_size=5, http=HTTPConfig(http2=False))
    # A flat argument equal to its default is not a conflict
    assert APIKeyRotator(api_keys=["k"], max_retries=3, retry=RetryConfig(max_retries=4)).max_retries == 4


def test_http_config_keeps_each_rotators_default_backend():
    assert APIKeyRotator(api_keys=["k"], http=HTTPConfig(pool_size=3)).http_backend == "requests"
    assert APIKeyRotator(api_keys=["k"], http=HTTPConfig(backend="httpx")).http_backend == "httpx"


@pytest.mark.asyncio
async def test_async_rotator_accepts_config_objects():
    async with AsyncAPIKeyRotator(api_keys=["k"], retry=RetryConfig(max_retries=4),
                                  http=HTTPConfig(backend="httpx", pool_size=3)) as rotator:
        assert (rotator.max_retries, rotator.http_backend, rotator.pool_size) == (4, "httpx", 3)
    async with AsyncAPIKeyRotator(api_keys=["k"], http=HTTPConfig()) as rotator:
        assert rotator.http_backend == "aiohttp"


def test_deprecated_helpers_warn():
    from apikeyrotator import RateLimitMiddleware

    with pytest.warns(DeprecationWarning, match="RateLimitMiddleware is deprecated"):
        RateLimitMiddleware()
    with pytest.warns(DeprecationWarning, match="measure_time is deprecated"):
        from apikeyrotator.utils import measure_time  # noqa: F401
    with pytest.warns(DeprecationWarning, match="exponential_backoff is deprecated"):
        from apikeyrotator.utils.retry import exponential_backoff
    assert exponential_backoff(3) == 8.0
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        from apikeyrotator.utils import (  # noqa: F401 - not deprecated
            CircuitBreaker,
            retry_with_backoff,
        )
