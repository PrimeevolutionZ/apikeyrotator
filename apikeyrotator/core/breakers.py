"""Per-host circuit breakers."""

from __future__ import annotations
import threading

from apikeyrotator.utils import CircuitBreaker, CircuitBreakerConfig

from .util import host_of


class BreakerRegistry:
    """Creates one CircuitBreaker per host on first use (disabled when config is None)."""

    __slots__ = ('config', '_breakers', '_lock')

    def __init__(self, config: bool | CircuitBreakerConfig | None):
        if config is True:
            config = CircuitBreakerConfig()
        self.config: CircuitBreakerConfig | None = config or None
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def for_url(self, url: str) -> CircuitBreaker | None:
        config = self.config
        if config is None:
            return None
        host = host_of(url)
        breaker = self._breakers.get(host)
        if breaker is None:
            with self._lock:
                breaker = self._breakers.get(host)
                if breaker is None:
                    breaker = self._breakers[host] = CircuitBreaker.from_config(config, name=host)
        return breaker

    def states(self) -> dict[str, str]:
        """Circuit state per host ('CLOSED' / 'OPEN' / 'HALF_OPEN')."""
        with self._lock:
            breakers = dict(self._breakers)
        return {host: b.get_state() for host, b in breakers.items()}
