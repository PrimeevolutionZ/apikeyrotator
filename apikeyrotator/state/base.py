"""Base interface of state backends."""

from __future__ import annotations
import hashlib
import hmac
from dataclasses import dataclass, field


def key_id(key: str, salt: bytes | None = None) -> str:
    """
    Stable, non-reversible identifier of an API key used in shared storage.

    Raw keys are never written to a state backend - only this hash
    (HMAC-SHA256 when a salt is configured).
    """
    data = key.encode("utf-8")
    if salt:
        digest = hmac.new(salt, data, hashlib.sha256).hexdigest()
    else:
        digest = hashlib.sha256(data).hexdigest()
    return digest[:32]


@dataclass(frozen=True, slots=True)
class SharedState:
    """Snapshot of shared state."""
    rate_limited: dict[str, float] = field(default_factory=dict)  # key_id -> UNIX ts until limited
    invalid: frozenset[str] = frozenset()  # key_ids rejected with 401/403


class StateBackend:
    """
    Interface of a state backend.

    Attributes:
        shared: State is visible to other rotators/processes, so the rotator
                periodically pulls a snapshot (``state_sync_interval``).
        blocking: Calls perform network I/O; async rotators run them in a thread.
        salt: Optional salt for key ids (HMAC) - use the same value on all instances.
    """

    shared: bool = False
    blocking: bool = False
    salt: bytes | None = None

    def key_id(self, key: str) -> str:
        return key_id(key, self.salt)

    def report_rate_limited(self, key_id: str, until: float) -> None:
        """Key is rate limited until the UNIX timestamp ``until``."""

    def report_invalid(self, key_id: str) -> None:
        """Key was rejected (401/403) and must not be used by anyone."""

    def clear_invalid(self, key_id: str | None = None) -> None:
        """Forgets an invalid key (or all of them)."""

    def snapshot(self) -> SharedState:
        return SharedState()

    def acquire_token(self, key_id: str, capacity: int, refill_per_sec: float) -> float:
        """
        Takes one token from the key's bucket.

        Returns:
            0.0 if a token was taken, otherwise seconds until one is available.
        """
        return 0.0

    def close(self) -> None:
        pass
