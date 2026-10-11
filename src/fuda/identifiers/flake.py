from typing import Self
from time import time_ns
from collections.abc import Callable
from fuda.identifiers.types import BinaryID
from fuda._core.state import ProcessGenerator
from fuda._core.encoding import BASE62, decode, encode, integer

class Flake128(BinaryID):
    """Boundary Flake's binary layout, represented as 32 lowercase hex digits."""

    __slots__ = ()
    _width = 32
    _alphabet = '0123456789abcdef'
    _case = 'lower'

    def __str__(self) -> str:
        return f'{self.value:032x}'

    @property
    def timestamp_ms(self) -> int:
        return self.value >> 64

    @property
    def node_id(self) -> int:
        return (self.value >> 16) & ((1 << 48) - 1)

    @property
    def sequence(self) -> int:
        return self.value & 65535

    def to_base62(self) -> str:
        return encode(self.value, BASE62, 22).lstrip('0') or '0'

    @classmethod
    def from_base62(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if not 1 <= len(value) <= 22 or (len(value) > 1 and value[0] == '0'):
            raise ValueError('invalid Flake base62 length or leading zeros')

        return cls(decode(value, BASE62, len(value), 128))

class Flake128Generator(ProcessGenerator[Flake128]):
    """Explicit 48-bit node; refuses rollback and 16-bit sequence exhaustion.

    Clocks return Unix milliseconds. Persist node leases externally; generator
    state is not durable across restarts.
    """

    def __init__(self, node_id: int, *, clock: Callable[[], int] | None = None) -> None:
        integer(node_id, 'node_id', 0, (1 << 48) - 1)
        super().__init__()
        self.node_id = node_id
        self._node = node_id << 16
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._last_ms = -1
        self._sequence = 0

    def _reset_process(self) -> None:
        raise RuntimeError('construct a Flake128Generator with a distinct node_id after fork')

    def generate(self) -> Flake128:
        self._check_process()
        with self._lock:
            now = integer(self._clock(), 'timestamp', 0, (1 << 64) - 1)
            if now < self._last_ms:
                raise RuntimeError('clock moved backwards; Flake generation refused')
            sequence = self._sequence + 1 if now == self._last_ms else 0
            if sequence > 65535:
                raise OverflowError('Flake sequence exhausted; retry after the next millisecond')
            self._last_ms, self._sequence = now, sequence

        return Flake128((now << 64) | self._node | sequence)
