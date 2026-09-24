"""Key pool: the active keys, their metrics and the strategy that picks among them."""

from __future__ import annotations
import logging
import threading
import time

from apikeyrotator.strategies import (
    BaseRotationStrategy,
    KeyMetrics,
    RotationStrategy,
    create_rotation_strategy,
)

from .exceptions import AllKeysExhaustedError


StrategySpec = str | RotationStrategy | BaseRotationStrategy


def build_strategy(spec: StrategySpec, keys: list[str], kwargs: dict) -> BaseRotationStrategy:
    if isinstance(spec, BaseRotationStrategy):
        strategy = spec
    else:
        name = spec.value if isinstance(spec, RotationStrategy) else str(spec).lower()
        kwargs = dict(kwargs)
        selection: list[str] | dict[str, float] = list(keys)
        if name == "weighted":
            # Weighted strategy needs {key: weight}; default to equal weights
            weights = kwargs.pop("weights", None) or {}
            selection = {k: float(weights.get(k, 1.0)) for k in keys}
        strategy = create_rotation_strategy(name, selection, **kwargs)
    # The pool owns per-key metrics - strategies must not keep a second copy
    release = getattr(strategy, 'use_external_metrics', None)
    if release is not None:
        release()
    return strategy


class KeyPool:
    """
    Thread-safe key list + per-key metrics + rotation strategy.

    The metrics dict is copy-on-write: it is replaced, never mutated, so the hot
    path can read it without a lock or a copy (metrics_view()).

    The strategy is created on the first non-empty key list, so a pool can start
    empty when keys are loaded later (async secret providers).
    """

    __slots__ = ('_lock', '_keys', '_key_metrics', '_strategy', '_spec', '_spec_kwargs',
                 '_recovery_timeout', 'logger', 'auth_confirmed', '_suspects')

    def __init__(self, keys: list[str], strategy: StrategySpec, strategy_kwargs: dict | None,
                 logger: logging.Logger, recovery_timeout: float | None = None):
        self._lock = threading.Lock()
        self._keys = list(keys)
        self._key_metrics: dict[str, KeyMetrics] = {key: KeyMetrics(key) for key in self._keys}
        self._spec = strategy
        self._spec_kwargs = strategy_kwargs or {}
        self._recovery_timeout = recovery_timeout
        self._strategy: BaseRotationStrategy | None = None
        self.logger = logger
        #: True once any request was accepted by the API. Until then a 401/403 may mean
        #: "wrong auth header" rather than "bad key", so rejected keys are only remembered.
        self.auth_confirmed = False
        self._suspects: dict[str, int] = {}
        if self._keys or isinstance(strategy, BaseRotationStrategy):
            self._init_strategy()

    def _init_strategy(self) -> None:
        self._strategy = build_strategy(self._spec, self._keys, self._spec_kwargs)
        if self._recovery_timeout is not None:
            self._strategy.recovery_timeout = self._recovery_timeout

    # --- strategy ---

    @property
    def strategy(self) -> BaseRotationStrategy | None:
        return self._strategy

    @strategy.setter
    def strategy(self, strategy: BaseRotationStrategy) -> None:
        self._spec = strategy
        self._init_strategy()

    @property
    def recovery_timeout(self) -> float | None:
        strategy = self._strategy
        return strategy.recovery_timeout if strategy is not None else self._recovery_timeout

    # --- keys ---

    def keys(self) -> list[str]:
        with self._lock:
            return self._keys.copy()

    def count(self) -> int:
        return len(self._key_metrics)

    def select(self) -> str:
        """Picks the next key with the rotation strategy."""
        metrics = self._key_metrics
        if not metrics:
            raise AllKeysExhaustedError("No valid keys available")
        try:
            return self._strategy.get_next_key(metrics)
        except ValueError as e:
            raise AllKeysExhaustedError(f"No valid keys available: {e}") from e

    def first_other(self, excluded: set[str] | dict[str, int]) -> str | None:
        """First key (in pool order) that is not in `excluded`."""
        for key in self._key_metrics:
            if key not in excluded:
                return key
        return None

    def remove(self, key: str) -> bool:
        with self._lock:
            if key not in self._key_metrics:
                return False
            self._keys.remove(key)
            metrics = dict(self._key_metrics)
            del metrics[key]
            self._key_metrics = metrics
            keys = self._keys.copy()
        self._strategy.update_keys(keys)
        return True

    def replace(self, new_keys: list[str]) -> None:
        """Replaces the key list, preserving metrics of keys that are kept."""
        with self._lock:
            old = self._key_metrics
            self._keys = list(new_keys)
            self._key_metrics = {key: old.get(key) or KeyMetrics(key) for key in self._keys}
            keys = self._keys.copy()
            self._suspects = {k: v for k, v in self._suspects.items() if k in self._key_metrics}
        if self._strategy is None:
            if keys:
                self._init_strategy()
        else:
            self._strategy.update_keys(keys)

    # --- auth confirmation ---

    def add_suspect(self, key: str, status: int) -> None:
        """Remembers a key rejected (401/403) before auth was confirmed."""
        self._suspects[key] = status

    def suspects(self) -> dict[str, int]:
        return dict(self._suspects)

    def confirm_auth(self) -> dict[str, int]:
        """Marks auth as working; returns the suspects, which are now known to be invalid."""
        self.auth_confirmed = True
        suspects, self._suspects = self._suspects, {}
        return {k: v for k, v in suspects.items() if k in self._key_metrics}

    # --- metrics ---

    def metrics_view(self) -> dict[str, KeyMetrics]:
        """Current metrics dict without copying (read-only for callers)."""
        return self._key_metrics

    def metric_objects(self) -> dict[str, KeyMetrics]:
        return dict(self._key_metrics)

    def metrics_dict(self, key: str | None = None) -> dict[str, dict]:
        metrics = self._key_metrics
        if key:
            m = metrics.get(key)
            return {key: m.to_dict()} if m is not None else {}
        return {k: v.to_dict() for k, v in metrics.items()}

    def update(self, key: str, success: bool, response_time: float, is_rate_limited: bool = False) -> None:
        metrics = self._key_metrics.get(key)
        if metrics is not None:
            metrics.update_from_request(success, response_time, is_rate_limited)

    def mark_rate_limited(self, key: str, until: float) -> None:
        metrics = self._key_metrics.get(key)
        if metrics is not None:
            metrics.mark_rate_limited(until)

    def reset_health(self, key: str | None = None) -> None:
        metrics = self._key_metrics
        if key:
            targets = [metrics[key]] if key in metrics else []
        else:
            targets = list(metrics.values())
        for m in targets:
            with m._lock:
                m.is_healthy = True
                m.consecutive_failures = 0
                m.rate_limit_reset = 0.0

    # --- availability ---

    def has_available_key(self) -> bool:
        now = time.time()
        recovery_timeout = self.recovery_timeout
        return any(m.is_available(now, recovery_timeout) for m in self._key_metrics.values())

    def time_until_key_available(self) -> float | None:
        """Seconds until the earliest rate-limited key becomes usable again (None if unknown)."""
        now = time.time()
        waits = [m.rate_limit_reset - now for m in self._key_metrics.values() if m.rate_limit_reset > now]
        return min(waits) if waits else None

    # --- backwards-compatible names (0.8.0 _ThreadSafeKeyManager) ---

    get_keys = keys
    get_key_count = count
    get_metrics_view = metrics_view
    get_metric_objects = metric_objects
    get_metrics = metrics_dict
    update_metrics = update
    remove_key = remove
    reinit_keys = replace
