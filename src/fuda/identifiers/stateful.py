from time import time_ns
from hashlib import sha256
from os import getpid, urandom
from socket import gethostname
from collections.abc import Callable
from fuda._core.encoding import integer
from fuda._core.state import ProcessGenerator
from fuda.identifiers.types import XID, TSID, ObjectID

TWITTER_EPOCH = 1_288_834_974_657
DISCORD_EPOCH = 1_420_070_400_000
TSID_EPOCH = 1_577_836_800_000

class ObjectIDGenerator(ProcessGenerator[ObjectID]):
    def __init__(self, *, clock: Callable[[], int] | None = None) -> None:
        super().__init__()
        self._clock = clock or (lambda: time_ns() // 1_000_000_000)
        self._reset_process()

    def _reset_process(self) -> None:
        self._random = urandom(5)
        self._counter = int.from_bytes(urandom(3), 'big')

    def generate(self) -> ObjectID:
        self._check_process()
        with self._lock:
            timestamp = integer(self._clock(), 'timestamp', 0, (1 << 32) - 1)
            counter = self._counter
            self._counter = (counter + 1) & 0xFFFFFF
            data = timestamp.to_bytes(4, 'big') + self._random + counter.to_bytes(3, 'big')

        return ObjectID.from_bytes(data)

class XIDGenerator(ProcessGenerator[XID]):
    def __init__(self, *, machine_id: bytes | None = None, clock: Callable[[], int] | None = None) -> None:
        if machine_id is not None and (not isinstance(machine_id, bytes) or len(machine_id) != 3):
            raise ValueError('machine_id must contain exactly 3 bytes')
        super().__init__()
        self._machine_id = machine_id if machine_id is not None else sha256(gethostname().encode()).digest()[:3]
        self._clock = clock or (lambda: time_ns() // 1_000_000_000)
        self._reset_process()

    def _reset_process(self) -> None:
        self._counter = int.from_bytes(urandom(3), 'big')
        self._process_id = getpid() & 0xFFFF

    def generate(self) -> XID:
        self._check_process()
        with self._lock:
            timestamp = integer(self._clock(), 'timestamp', 0, (1 << 32) - 1)
            self._counter = (self._counter + 1) & 0xFFFFFF
            data = (
                timestamp.to_bytes(4, 'big')
                + self._machine_id
                + self._process_id.to_bytes(2, 'big')
                + self._counter.to_bytes(3, 'big')
            )

        return XID.from_bytes(data)

class SnowflakeGenerator(ProcessGenerator[int]):
    """63-bit Snowflake; node IDs must be assigned uniquely by the application."""

    def __init__(
        self,
        node_id: int,
        *,
        epoch: int = TWITTER_EPOCH,
        node_bits: int = 10,
        sequence_bits: int = 12,
        clock: Callable[[], int] | None = None,
    ) -> None:
        integer(node_bits, 'node_bits', 1, 22)
        integer(sequence_bits, 'sequence_bits', 1, 22)
        if node_bits + sequence_bits >= 63:
            raise ValueError('layout must leave timestamp bits')
        integer(node_id, 'node_id', 0, (1 << node_bits) - 1)
        integer(epoch, 'epoch', 0, (1 << 63) - 1)
        super().__init__()
        self.node_id = node_id
        self.epoch = epoch
        self.node_bits = node_bits
        self.sequence_bits = sequence_bits
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._last_ms = -1
        self._sequence = 0

    def _reset_process(self) -> None:
        raise RuntimeError('construct a SnowflakeGenerator with a distinct node_id after fork')

    def generate(self) -> int:
        self._check_process()
        with self._lock:
            now = integer(self._clock(), 'timestamp', self.epoch, (1 << 63) - 1)
            if now < self._last_ms:
                raise RuntimeError('clock moved backwards; Snowflake generation refused')
            sequence = self._sequence + 1 if now == self._last_ms else 0
            if sequence >= 1 << self.sequence_bits:
                raise OverflowError('Snowflake sequence exhausted; retry after the next millisecond')
            elapsed = now - self.epoch
            if elapsed >= 1 << (63 - self.node_bits - self.sequence_bits):
                raise OverflowError('Snowflake timestamp exhausted')
            self._sequence = sequence
            self._last_ms = now
            result = (
                (elapsed << (self.node_bits + self.sequence_bits)) | (self.node_id << self.sequence_bits) | sequence
            )

        return result

    def inspect(self, value: int) -> dict[str, int]:
        integer(value, 'value', 0, (1 << 63) - 1)

        return {
            'timestamp_ms': (value >> (self.node_bits + self.sequence_bits)) + self.epoch,
            'node_id': (value >> self.sequence_bits) & ((1 << self.node_bits) - 1),
            'sequence': value & ((1 << self.sequence_bits) - 1),
        }

class TSIDGenerator(ProcessGenerator[TSID]):
    """42-bit milliseconds since 2020 plus a 22-bit node/counter field."""

    def __init__(
        self, node_id: int | None = None, *, node_bits: int = 10, clock: Callable[[], int] | None = None
    ) -> None:
        integer(node_bits, 'node_bits', 0, 20)
        if node_id is not None:
            integer(node_id, 'node_id', 0, (1 << node_bits) - 1)
        super().__init__()
        self.node_bits = node_bits
        self._configured_node = node_id
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._reset_process()

    def _reset_process(self) -> None:
        if self._pid != getpid() and self._configured_node is not None:
            raise RuntimeError('construct a TSIDGenerator with a distinct node_id after fork')
        self.node_id = (
            self._configured_node
            if self._configured_node is not None
            else int.from_bytes(urandom(4), 'big') & ((1 << self.node_bits) - 1)
        )
        self._last_ms = -1
        self._counter = 0

    def generate(self) -> TSID:
        self._check_process()
        with self._lock:
            now = max(integer(self._clock(), 'timestamp', TSID_EPOCH, (1 << 63) - 1), self._last_ms)
            counter_bits = 22 - self.node_bits
            mask = (1 << counter_bits) - 1
            if now == self._last_ms:
                counter = self._counter + 1
                if counter > mask:
                    now += 1
                    counter = 0
            else:
                counter = int.from_bytes(urandom(4), 'big') & mask
            elapsed = now - TSID_EPOCH
            if elapsed >= 1 << 42:
                raise OverflowError('TSID timestamp exhausted')
            self._last_ms = now
            self._counter = counter
            result = (elapsed << 22) | (self.node_id << counter_bits) | counter

        return TSID(result)
