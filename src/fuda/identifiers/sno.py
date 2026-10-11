from time import time_ns
from collections.abc import Callable
from fuda._core.encoding import integer
from fuda.identifiers.types import BinaryID
from fuda._core.state import ProcessGenerator

SNO_EPOCH = 1_262_304_000_000

class SNO(BinaryID):
    __slots__ = ()
    _bits = 80
    _width = 16
    _alphabet = '23456789abcdefghijklmnopqrstuvwx'
    _case = 'sensitive'

    @property
    def timestamp_ms(self) -> int:
        return (self.value >> 41) * 4 + SNO_EPOCH

    @property
    def tick_tock(self) -> int:
        return (self.value >> 40) & 1

    @property
    def metadata(self) -> int:
        return (self.value >> 32) & 255

    @property
    def partition(self) -> int:
        return (self.value >> 16) & 65535

    @property
    def sequence(self) -> int:
        return self.value & 65535

class SNOGenerator(ProcessGenerator[SNO]):
    """Assigned partitions, 4 ms ticks, and one application metadata byte.

    A safe clock rollback toggles a bit. A repeated unsafe rollback or an
    exhausted sequence raises rather than blocking. IDs may sort backwards
    after a rollback. The clock returns Unix milliseconds.
    """

    def __init__(
        self,
        partition: int,
        *,
        metadata: int = 0,
        sequence_min: int = 0,
        sequence_max: int = 65535,
        clock: Callable[[], int] | None = None,
    ) -> None:
        integer(partition, 'partition', 0, 65535)
        integer(metadata, 'metadata', 0, 255)
        integer(sequence_min, 'sequence_min', 0, 65535)
        integer(sequence_max, 'sequence_max', sequence_min, 65535)
        super().__init__()
        self.partition, self.metadata = partition, metadata
        self.sequence_min, self.sequence_max = sequence_min, sequence_max
        self._payload = (metadata << 32) | (partition << 16)
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._last_tick = -1
        self._safe_tick = -1
        self._toggle = 0
        self._sequence = sequence_min

    def _reset_process(self) -> None:
        raise RuntimeError('construct a SNOGenerator with a distinct partition after fork')

    def generate(self) -> SNO:
        self._check_process()
        with self._lock:
            now = integer(self._clock(), 'timestamp', SNO_EPOCH, SNO_EPOCH + ((1 << 39) - 1) * 4 + 3)
            tick = (now - SNO_EPOCH) // 4
            toggle, safe = self._toggle, self._safe_tick
            if tick == self._last_tick:
                sequence = self._sequence + 1
            else:
                sequence = self.sequence_min
                if tick < self._last_tick:
                    if tick <= safe:
                        raise RuntimeError('unsafe repeated SNO clock rollback; retry after the safe timestamp')
                    safe, toggle = self._last_tick, toggle ^ 1
            if sequence > self.sequence_max:
                raise OverflowError('SNO sequence exhausted; retry after the next tick')
            self._last_tick, self._safe_tick, self._toggle, self._sequence = tick, safe, toggle, sequence

        return SNO((tick << 41) | (toggle << 40) | self._payload | sequence)
