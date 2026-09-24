"""
LRU (Least Recently Used) rotation strategy
"""

import time
from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class LRURotationStrategy(BaseRotationStrategy):
    """
    Least Recently Used strategy - selects the least recently used key.

    Tracks the last usage time of each key and always
    selects the one that was used the longest ago.

    Useful for even load distribution and preventing
    "forgetting" of rarely used keys.

    Example:
        >>> strategy = LRURotationStrategy(['key1', 'key2', 'key3'])
        >>> strategy.get_next_key()  # Returns key with smallest last_used
    """

    def __init__(self, keys: List[str]):
        """
        Initializes LRU strategy.

        Args:
            keys: List of API keys for rotation
        """
        super().__init__(keys)
        # Create metrics to track usage time
        self._key_metrics: Dict[str, KeyMetrics] = {
            key: KeyMetrics(key) for key in keys
        }

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Selects the least recently used healthy key.

        Selection and marking the key as used happen atomically, so concurrent
        callers never receive the same "least recently used" key.

        Args:
            current_key_metrics: Current key metrics from rotator.
                                 If provided, their last_used is taken into account.

        Returns:
            str: Least recently used healthy key
        """
        with self._lock:
            if not self._keys:
                raise ValueError("No keys available in rotation")

            own_metrics = self._key_metrics
            now = time.time()
            recovery_timeout = self.recovery_timeout
            available = self._key_available
            ext_get = current_key_metrics.get if current_key_metrics else None

            # Single pass: least recently used among available keys,
            # falling back to the least recently used key overall.
            best_key = best_any = None
            best_ts = best_any_ts = float('inf')
            for k in self._keys:
                own = own_metrics.get(k)
                ts = own.last_used if own is not None else 0.0
                ext = ext_get(k) if ext_get is not None else None
                if ext is not None and ext.last_used > ts:
                    ts = ext.last_used
                if ts < best_any_ts:
                    best_any, best_any_ts = k, ts
                if ts < best_ts and (ext_get is None or available(ext, now, recovery_timeout)):
                    best_key, best_ts = k, ts
            lru_key = best_key if best_key is not None else best_any

            # Mark as used in internal state only - external metrics are owned
            # (and updated) by the rotator itself.
            own = self._key_metrics.get(lru_key)
            if own is None:
                own = self._key_metrics[lru_key] = KeyMetrics(lru_key)
            own.last_used = time.time()

        return lru_key

    def update_keys(self, new_keys: List[str]) -> None:
        """Updates keys, adding metrics for new keys and removing stale ones."""
        with self._lock:
            self._keys = list(new_keys)
            new_set = set(new_keys)
            # Remove metrics for removed keys
            for key in list(self._key_metrics.keys()):
                if key not in new_set:
                    del self._key_metrics[key]
            # Add metrics for new keys
            for key in new_keys:
                if key not in self._key_metrics:
                    self._key_metrics[key] = KeyMetrics(key)