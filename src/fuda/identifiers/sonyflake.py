from time import time_ns
from collections.abc import Callable
from fuda._core.encoding import integer
from fuda._core.state import ProcessGenerator

SONYFLAKE_EPOCH = 1_735_689_600_000

class SonyflakeGenerator(ProcessGenerator[int]):
    """Sonyflake v2 layout with an assigned node. Clock values are milliseconds.

    The default epoch is 2025-01-01. Set epoch=1409529600000 for v1's epoch.
    Sequence exhaustion raises instead of sleeping; retry after the next tick.
    """

    def __init__(
        self,
        node_id: int,
        *,
        epoch: int = SONYFLAKE_EPOCH,
        time_unit_ms: int = 10,
        node_bits: int = 16,
        sequence_bits: int = 8,
        clock: Callable[[], int] | None = None,
    ) -> None:
        integer(epoch, 'epoch', 0, (1 << 63) - 1)
        integer(time_unit_ms, 'time_unit_ms', 1, (1 << 63) - 1)
        integer(node_bits, 'node_bits', 1, 30)
        integer(sequence_bits, 'sequence_bits', 1, 30)
        if node_bits + sequence_bits > 31:
            raise ValueError('Sonyflake requires at least 32 timestamp bits')
        integer(node_id, 'node_id', 0, (1 << node_bits) - 1)
        super().__init__()
        self.node_id, self.node_bits, self.sequence_bits = node_id, node_bits, sequence_bits
        self.epoch, self.time_unit_ms = epoch, time_unit_ms
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._last_tick = -1
        self._sequence = 0

    def _reset_process(self) -> None:
        raise RuntimeError('construct a SonyflakeGenerator with a distinct node_id after fork')

    def generate(self) -> int:
        self._check_process()
        with self._lock:
            now = integer(self._clock(), 'timestamp', self.epoch, (1 << 63) - 1)
            tick = now // self.time_unit_ms - self.epoch // self.time_unit_ms
            if tick < self._last_tick:
                raise RuntimeError('clock moved backwards; Sonyflake generation refused')
            sequence = self._sequence + 1 if tick == self._last_tick else 0
            if sequence >= 1 << self.sequence_bits:
                raise OverflowError('Sonyflake sequence exhausted; retry after the next tick')
            shift = self.node_bits + self.sequence_bits
            if tick >= 1 << (63 - shift):
                raise OverflowError('Sonyflake timestamp exhausted')
            self._last_tick, self._sequence = tick, sequence

        return (tick << shift) | (sequence << self.node_bits) | self.node_id

    def inspect(self, value: int) -> dict[str, int]:
        integer(value, 'value', 0, (1 << 63) - 1)
        tick = value >> (self.node_bits + self.sequence_bits)

        return {
            'timestamp_ms': (tick + self.epoch // self.time_unit_ms) * self.time_unit_ms,
            'node_id': value & ((1 << self.node_bits) - 1),
            'sequence': (value >> self.node_bits) & ((1 << self.sequence_bits) - 1),
        }
