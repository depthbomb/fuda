from typing import Self
from fuda.identifiers.types import BinaryID
from fuda._core.encoding import BASE36, BASE62, integer

PUSH_ALPHABET = '-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'
TID_ALPHABET = '234567abcdefghijklmnopqrstuvwxyz'
SCRU64_LIMIT = 36**12

class PushID(BinaryID):
    """Firebase's 20-character, 120-bit push key."""

    __slots__ = ()
    _bits = 120
    _width = 20
    _alphabet = PUSH_ALPHABET
    _case = 'sensitive'

    @property
    def timestamp_ms(self) -> int:
        return self.value >> 72

    @property
    def randomness(self) -> int:
        return self.value & ((1 << 72) - 1)

class SCRU128(BinaryID):
    __slots__ = ()
    _width = 25
    _alphabet = BASE36
    _case = 'lower'

    @property
    def timestamp_ms(self) -> int:
        return self.value >> 80

    @property
    def counter_hi(self) -> int:
        return (self.value >> 56) & 0xFFFFFF

    @property
    def counter_lo(self) -> int:
        return (self.value >> 32) & 0xFFFFFF

    @property
    def entropy(self) -> int:
        return self.value & 0xFFFFFFFF

class SCRU64(BinaryID):
    __slots__ = ()
    _bits = 64
    _width = 12
    _alphabet = BASE36
    _case = 'lower'

    def __post_init__(self) -> None:
        integer(self.value, 'value', 0, SCRU64_LIMIT - 1)

    @property
    def timestamp_ms(self) -> int:
        return (self.value >> 24) << 8

class Timeflake(BinaryID):
    __slots__ = ()
    _width = 22
    _alphabet = BASE62
    _case = 'sensitive'

    @classmethod
    def from_str(cls, value: str) -> Self:
        # The reference encoder emits a single zero for the all-zero value.
        if value == '0':
            return cls(0)

        return super().from_str(value)

    @property
    def timestamp_ms(self) -> int:
        return self.value >> 80

    @property
    def randomness(self) -> int:
        return self.value & ((1 << 80) - 1)

class TID(BinaryID):
    """AT Protocol TID; parsing follows the published 64-bit syntax.

    New IDs use 63 bits, reserving the top bit as required by the generator spec.
    """

    __slots__ = ()
    _bits = 64
    _width = 13
    _alphabet = TID_ALPHABET
    _case = 'sensitive'

    @property
    def timestamp_us(self) -> int:
        return self.value >> 10

    @property
    def timestamp_ms(self) -> int:
        return self.timestamp_us // 1000

    @property
    def clock_id(self) -> int:
        return self.value & 1023
