from uuid import UUID
from dataclasses import dataclass
from typing import Self, ClassVar
from builtins import bytes as Bytes
from fuda._core.encoding import BASE62, decode, encode, integer, BASE32HEX, CROCKFORD

@dataclass(frozen=True, slots=True, order=True)
class BinaryID:
    value: int
    _bits: ClassVar[int] = 128
    _width: ClassVar[int] = 26
    _alphabet: ClassVar[str] = CROCKFORD
    _shift: ClassVar[int] = 0
    _case: ClassVar[str] = 'upper'

    def __post_init__(self) -> None:
        integer(self.value, 'value', 0, (1 << self._bits) - 1)

    def __str__(self) -> str:
        return encode(self.value << self._shift, self._alphabet, self._width)

    def __int__(self) -> int:
        return self.value

    @property
    def bytes(self) -> bytes:
        return self.value.to_bytes(self._bits // 8, 'big')

    @classmethod
    def from_bytes(cls, value: Bytes) -> Self:
        if not isinstance(value, bytes):
            raise TypeError('value must be bytes')
        if len(value) != cls._bits // 8:
            raise ValueError(f'value must contain {cls._bits // 8} bytes')

        return cls(int.from_bytes(value, 'big'))

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if not value.isascii():
            raise ValueError('identifier must contain ASCII characters')
        if cls._case == 'upper':
            value = value.upper()
        elif cls._case == 'lower':
            value = value.lower()
        decoded = decode(value, cls._alphabet, cls._width, cls._bits + cls._shift)
        if decoded & ((1 << cls._shift) - 1):
            raise ValueError('nonzero base32 padding bits')

        return cls(decoded >> cls._shift)

class ULID(BinaryID):
    __slots__ = ()

    @property
    def timestamp_ms(self) -> int:
        return self.value >> 80

    @property
    def randomness(self) -> int:
        return self.value & ((1 << 80) - 1)

    def to_uuid(self) -> UUID:
        """Reinterpret the same 128 bits; this does not create a UUIDv7."""
        return UUID(int=self.value)

    @classmethod
    def from_uuid(cls, value: UUID) -> Self:
        if not isinstance(value, UUID):
            raise TypeError('value must be a UUID')

        return cls(value.int)

class KSUID(BinaryID):
    __slots__ = ()
    _bits = 160
    _width = 27
    _alphabet = BASE62
    _case = 'sensitive'

    @property
    def timestamp(self) -> int:
        return (self.value >> 128) + 1_400_000_000

    @property
    def timestamp_ms(self) -> int:
        return self.timestamp * 1000

    @property
    def payload(self) -> bytes:
        return self.bytes[4:]

class XID(BinaryID):
    __slots__ = ()
    _bits = 96
    _width = 20
    _alphabet = BASE32HEX
    _shift = 4
    _case = 'lower'

    @property
    def timestamp(self) -> int:
        return self.value >> 64

    @property
    def timestamp_ms(self) -> int:
        return self.timestamp * 1000

    @property
    def machine_id(self) -> bytes:
        return self.bytes[4:7]

    @property
    def process_id(self) -> int:
        return int.from_bytes(self.bytes[7:9], 'big')

    @property
    def counter(self) -> int:
        return self.value & 0xFFFFFF

class ObjectID(BinaryID):
    __slots__ = ()
    _bits = 96
    _width = 24
    _alphabet = '0123456789abcdef'
    _case = 'lower'

    @property
    def timestamp(self) -> int:
        return self.value >> 64

    @property
    def timestamp_ms(self) -> int:
        return self.timestamp * 1000

class TSID(BinaryID):
    __slots__ = ()
    _bits = 64
    _width = 13

    @property
    def timestamp_ms(self) -> int:
        return (self.value >> 22) + 1_577_836_800_000

    @property
    def random_part(self) -> int:
        return self.value & ((1 << 22) - 1)
