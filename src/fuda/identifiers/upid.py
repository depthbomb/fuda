from uuid import UUID
from os import urandom
from typing import Self
from time import time_ns
from collections.abc import Callable
from fuda._core.state import Generator
from fuda._core.extension import native
from fuda.identifiers.types import BinaryID
from fuda._core.encoding import decode, encode, integer

_ALPHABET = '234567abcdefghijklmnopqrstuvwxyz'

class UPID(BinaryID):
    """128 bits containing a 40-bit time, 64 random bits, prefix and version."""

    __slots__ = ()

    @property
    def timestamp_ms(self) -> int:
        return (self.value >> 88) << 8

    @property
    def randomness(self) -> int:
        return (self.value >> 24) & ((1 << 64) - 1)

    @property
    def prefix(self) -> str:
        return encode((self.value >> 4) & 0xFFFFF, _ALPHABET, 4)

    @property
    def version(self) -> int:
        return self.value & 15

    def __str__(self) -> str:
        random = self.randomness
        return (
            self.prefix
            + '_'
            + encode(self.value >> 88, _ALPHABET, 8)
            + encode(random >> 4, _ALPHABET, 12)
            + _ALPHABET[random & 15]
            + _ALPHABET[self.version]
        )

    def to_uuid(self) -> UUID:
        """Reinterpret the storage bits; this does not produce an RFC UUID version."""
        return UUID(int=self.value)

    @classmethod
    def from_uuid(cls, value: UUID) -> Self:
        if not isinstance(value, UUID):
            raise TypeError('value must be a UUID')

        return cls(value.int)

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if len(value) != 27 or value[4] != '_' or not value.isascii():
            raise ValueError('UPID requires four prefix characters, an underscore and 22 characters')
        prefix = decode(value[:4], _ALPHABET, 4, 20)
        timestamp = decode(value[5:13], _ALPHABET, 8, 40)
        random = (decode(value[13:25], _ALPHABET, 12, 60) << 4) | decode(value[25], _ALPHABET, 1, 4)
        version = decode(value[26], _ALPHABET, 1, 4)

        return cls((timestamp << 88) | (random << 24) | (prefix << 4) | version)

class UPIDGenerator(Generator[UPID]):
    """The clock returns Unix milliseconds. Short prefixes are padded with z."""

    def __init__(self, prefix: str = 'item', *, clock: Callable[[], int] | None = None) -> None:
        if not isinstance(prefix, str):
            raise TypeError('prefix must be a string')
        if not 1 <= len(prefix) <= 4 or any(char not in _ALPHABET for char in prefix):
            raise ValueError('prefix must contain 1..4 lowercase UPID alphabet characters')
        self.prefix = prefix.ljust(4, 'z')
        self._suffix = (decode(self.prefix, _ALPHABET, 4, 20) << 4) | 6
        self._clock = clock or (lambda: time_ns() // 1_000_000)

    def generate(self) -> UPID:
        timestamp = integer(self._clock(), 'timestamp', 0, (1 << 48) - 1) >> 8

        return UPID((timestamp << 88) | (int.from_bytes(urandom(8), 'big') << 24) | self._suffix)

    def _generate_many(self, count: int, parallel: bool) -> list[UPID]:
        values = native.random_u128_many(count, (1 << 64) - 1, parallel=parallel)
        results = []
        for random in values:
            timestamp = integer(self._clock(), 'timestamp', 0, (1 << 48) - 1) >> 8
            results.append(UPID((timestamp << 88) | (random << 24) | self._suffix))

        return results
