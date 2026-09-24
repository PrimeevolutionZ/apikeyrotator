"""
Circuit breaker ("предохранитель") - stops hammering a host that keeps failing.

States:
- CLOSED:    normal operation, requests pass; consecutive failures are counted.
- OPEN:      after ``failure_threshold`` consecutive failures requests fail fast
             (no network call) for ``recovery_timeout`` seconds.
- HALF_OPEN: after the timeout up to ``half_open_max_calls`` probe requests are let
             through. A successful probe closes the circuit, a failed one opens it
             again for another ``recovery_timeout``.
"""

from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass


logger = logging.getLogger(__name__)

CLOSED = "CLOSED"
OPEN = "OPEN"
HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    """
    Settings of the per-host circuit breaker used by the rotators.

    Attributes:
        failure_threshold: Consecutive failures (5xx or network errors) that open the circuit.
        recovery_timeout: Seconds the circuit stays open before a probe is allowed.
        half_open_max_calls: Probe requests allowed concurrently in HALF_OPEN state.
    """
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1

    def __post_init__(self):
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_timeout < 0:
            raise ValueError("recovery_timeout must be >= 0")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")


class CircuitBreaker:
    """
    Thread-safe circuit breaker.

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        >>> if breaker.allow_request():
        ...     try:
        ...         response = do_request()
        ...         breaker.record_success()
        ...     except Exception:
        ...         breaker.record_failure()
        ...         raise
    """

    __slots__ = (
        "failure_threshold", "timeout", "half_open_max_calls", "name",
        "failures", "last_failure_time", "state", "_half_open_in_flight", "_lock",
    )

    def __init__(
            self,
            failure_threshold: int = 5,
            timeout: float = 60,
            half_open_max_calls: int = 1,
            name: str = "",
    ):
        """
        Args:
            failure_threshold: Number of consecutive errors to open the circuit
            timeout: Seconds until transition from OPEN to HALF_OPEN
            half_open_max_calls: Probe requests allowed in HALF_OPEN state
            name: Name used in log messages (e.g. host)
        """
        self.failure_threshold = max(1, failure_threshold)
        self.timeout = timeout
        self.half_open_max_calls = max(1, half_open_max_calls)
        self.name = name
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = CLOSED
        self._half_open_in_flight = 0
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, config: CircuitBreakerConfig, name: str = "") -> CircuitBreaker:
        return cls(config.failure_threshold, config.recovery_timeout, config.half_open_max_calls, name)

    def allow_request(self) -> bool:
        """Whether a request may be sent now. In HALF_OPEN this reserves a probe slot."""
        if self.state == CLOSED:  # fast path: attribute reads are atomic, no lock needed
            return True
        with self._lock:
            if self.state == CLOSED:
                return True
            if self.state == OPEN:
                if time.time() - self.last_failure_time < self.timeout:
                    return False
                self.state = HALF_OPEN
                self._half_open_in_flight = 0
            # HALF_OPEN: only a limited number of probes
            if self._half_open_in_flight >= self.half_open_max_calls:
                return False
            self._half_open_in_flight += 1
            return True

    def retry_after(self) -> float:
        """Seconds until the next request may be allowed (0 if allowed now)."""
        with self._lock:
            if self.state != OPEN:
                return 0.0
            return max(0.0, self.timeout - (time.time() - self.last_failure_time))

    def record_success(self) -> None:
        if self.state == CLOSED and self.failures == 0:  # fast path: nothing to change
            return
        with self._lock:
            if self.state != CLOSED:
                logger.info(f"Circuit breaker {self.name} closed (probe succeeded)")
            self.failures = 0
            self.state = CLOSED
            self._half_open_in_flight = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.state == HALF_OPEN or (
                    self.state == CLOSED and self.failures >= self.failure_threshold
            ):
                self.state = OPEN
                self._half_open_in_flight = 0
                logger.warning(
                    f"Circuit breaker {self.name} opened after {self.failures} failures; "
                    f"requests fail fast for {self.timeout}s"
                )

    def release_probe(self) -> None:
        """Frees a HALF_OPEN probe slot without a verdict (e.g. request was cancelled)."""
        with self._lock:
            if self._half_open_in_flight > 0:
                self._half_open_in_flight -= 1

    def get_state(self) -> str:
        """'CLOSED', 'OPEN' or 'HALF_OPEN' (OPEN turns into HALF_OPEN once the timeout passed)."""
        with self._lock:
            if self.state == OPEN and time.time() - self.last_failure_time >= self.timeout:
                return HALF_OPEN
            return self.state

    def reset(self) -> None:
        with self._lock:
            self.failures = 0
            self.last_failure_time = 0.0
            self.state = CLOSED
            self._half_open_in_flight = 0
