from time import time_ns
from secrets import randbits
from collections.abc import Callable
from fuda._core.encoding import integer
from fuda._core.state import ProcessGenerator
from fuda.identifiers.extended_types import SCRU64, SCRU128, SCRU64_LIMIT

class SCRU128Generator(ProcessGenerator[SCRU128]):
    """SCRU128 v2.1.1 with bounded rollback tolerance and monotonic counters.

    Clocks return Unix milliseconds. Rollbacks exceeding max_rollback_ms raise
    RuntimeError without resetting state. Counter overflow advances logical time.
    """

    def __init__(self, *, clock: Callable[[], int] | None = None, max_rollback_ms: int = 10_000) -> None:
        integer(max_rollback_ms, 'max_rollback_ms', 0, (1 << 48) - 1)
        super().__init__()
        self.max_rollback_ms = max_rollback_ms
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._reset_process()

    def _reset_process(self) -> None:
        self._last_ms = 0
        self._hi_renewed = -1000
        self._hi = 0
        self._lo = 0

    def generate(self) -> SCRU128:
        self._check_process()
        with self._lock:
            now = integer(self._clock(), 'timestamp', 1, (1 << 48) - 2)
            if now + self.max_rollback_ms < self._last_ms:
                raise RuntimeError('clock rollback exceeds max_rollback_ms')
            hi, renewed = self._hi, self._hi_renewed
            if now > self._last_ms:
                lo = randbits(24)
            else:
                now = self._last_ms
                lo = self._lo + 1
                if lo >= 1 << 24:
                    lo = 0
                    hi += 1
                    if hi >= 1 << 24:
                        now += 1
                        hi, lo, renewed = 0, randbits(24), now
            if now >= (1 << 48) - 1:
                raise OverflowError('SCRU128 timestamp exhausted')
            if now - renewed >= 1000:
                hi, renewed = randbits(24), now
            entropy = randbits(32)
            self._last_ms, self._hi, self._lo, self._hi_renewed = now, hi, lo, renewed

        return SCRU128((now << 80) | (hi << 56) | (lo << 32) | entropy)

class SCRU64Generator(ProcessGenerator[SCRU64]):
    """SCRU64 v1 with an assigned node, 256 ms ticks and a monotonic counter.

    All nodes sharing a node_bits setting need distinct node IDs. Counter
    overflow advances logical time. Large clock rollbacks raise RuntimeError.
    """

    def __init__(
        self,
        node_id: int,
        *,
        node_bits: int = 8,
        clock: Callable[[], int] | None = None,
        max_rollback_ms: int = 10_000,
    ) -> None:
        integer(node_bits, 'node_bits', 1, 23)
        integer(node_id, 'node_id', 0, (1 << node_bits) - 1)
        integer(max_rollback_ms, 'max_rollback_ms', 0, (1 << 63) - 1)
        super().__init__()
        self.node_id, self.node_bits = node_id, node_bits
        self.max_rollback_ms = max_rollback_ms
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._last_tick = 0
        self._counter = 0

    def _reset_process(self) -> None:
        raise RuntimeError('construct a SCRU64Generator with a distinct node_id after fork')

    def generate(self) -> SCRU64:
        self._check_process()
        with self._lock:
            now_ms = integer(self._clock(), 'timestamp', 256, (1 << 63) - 1)
            if now_ms + self.max_rollback_ms < self._last_tick << 8:
                raise RuntimeError('clock rollback exceeds max_rollback_ms')
            tick = now_ms >> 8
            bits = 24 - self.node_bits
            if tick > self._last_tick:
                counter = randbits(bits - 1)
            else:
                tick, counter = self._last_tick, self._counter + 1
                if counter >= 1 << bits:
                    tick, counter = tick + 1, randbits(bits - 1)
            if tick >= (SCRU64_LIMIT - 1) >> 24:
                raise OverflowError('SCRU64 timestamp exhausted')
            self._last_tick, self._counter = tick, counter

        return SCRU64((tick << 24) | (self.node_id << bits) | counter)
