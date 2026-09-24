"""Shared test fixtures."""

import asyncio
import time
from unittest.mock import patch

import pytest


class VirtualClock:
    """
    Makes time.sleep / asyncio.sleep instant while advancing time.time() and
    time.monotonic() by the requested amount - rate-limit windows, token buckets,
    circuit breaker timeouts and deadlines behave exactly as in real time.
    """

    def __init__(self):
        self.offset = 0.0
        self.sleeps: list[float] = []
        self._real_time = time.time
        self._real_monotonic = time.monotonic
        self._real_async_sleep = asyncio.sleep

    def advance(self, seconds: float) -> None:
        self.offset += max(0.0, seconds)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)

    async def async_sleep(self, seconds: float, *args, **kwargs):
        self.sleeps.append(seconds)
        self.advance(seconds)
        await self._real_async_sleep(0)

    def time(self) -> float:
        return self._real_time() + self.offset

    def monotonic(self) -> float:
        return self._real_monotonic() + self.offset


@pytest.fixture
def virtual_clock():
    clock = VirtualClock()
    with patch("time.sleep", clock.sleep), patch("time.time", clock.time), \
            patch("time.monotonic", clock.monotonic), patch("asyncio.sleep", clock.async_sleep):
        yield clock
