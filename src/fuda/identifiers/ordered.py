from time import time_ns
from secrets import randbits
from os import getpid, urandom
from collections.abc import Callable
from fuda._core.encoding import integer
from fuda._core.extension import native
from fuda._core.state import Generator, ProcessGenerator
from fuda.identifiers.extended_types import TID, PushID, Timeflake

class PushIDGenerator(ProcessGenerator[PushID]):
    """Monotonic Firebase push keys. The clock returns Unix milliseconds."""

    def __init__(self, *, clock: Callable[[], int] | None = None) -> None:
        super().__init__()
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._reset_process()

    def _reset_process(self) -> None:
        self._last_ms = -1
        self._random = 0

    def generate(self) -> PushID:
        self._check_process()
        with self._lock:
            now = max(integer(self._clock(), 'timestamp', 0, (1 << 48) - 1), self._last_ms)
            random = self._random + 1 if now == self._last_ms else randbits(72)
            if random >= 1 << 72:
                raise OverflowError('Push ID randomness exhausted; retry after the next millisecond')
            self._last_ms, self._random = now, random

        return PushID((now << 72) | random)

class TimeflakeGenerator(Generator[Timeflake]):
    """Independent 80-bit randomness per ID; no ordering within a millisecond."""

    def __init__(self, *, clock: Callable[[], int] | None = None) -> None:
        self._clock = clock or (lambda: time_ns() // 1_000_000)

    def generate(self) -> Timeflake:
        now = integer(self._clock(), 'timestamp', 0, (1 << 48) - 1)

        return Timeflake((now << 80) | int.from_bytes(urandom(10), 'big'))

    def _generate_many(self, count: int, parallel: bool) -> list[Timeflake]:
        values = native.random_u128_many(count, (1 << 80) - 1, parallel=parallel)
        results = []
        for random in values:
            now = integer(self._clock(), 'timestamp', 0, (1 << 48) - 1)
            results.append(Timeflake((now << 80) | random))

        return results

class TIDGenerator(ProcessGenerator[TID]):
    """Monotonic AT Protocol TIDs. The clock returns Unix microseconds."""

    def __init__(self, clock_id: int | None = None, *, clock: Callable[[], int] | None = None) -> None:
        if clock_id is not None:
            integer(clock_id, 'clock_id', 0, 1023)
        super().__init__()
        self._configured_clock = clock_id
        self._clock = clock or (lambda: time_ns() // 1000)
        self._reset_process()

    def _reset_process(self) -> None:
        if self._pid != getpid() and self._configured_clock is not None:
            raise RuntimeError('construct a TIDGenerator with a distinct clock_id after fork')
        self.clock_id = randbits(10) if self._configured_clock is None else self._configured_clock
        self._last_us = -1

    def generate(self) -> TID:
        self._check_process()
        with self._lock:
            now = max(integer(self._clock(), 'timestamp', 0, (1 << 53) - 1), self._last_us + 1)
            if now >= 1 << 53:
                raise OverflowError('TID timestamp exhausted')
            self._last_us = now

        return TID((now << 10) | self.clock_id)
