from uuid import UUID
from typing import Self
from collections.abc import Iterable
from fuda.identifiers.types import BinaryID
from fuda._core.encoding import BASE36, _radix
from fuda._core.batch import text_items, batch_items

class UUID25(BinaryID):
    """Case-insensitive base36 representation of the same 128 UUID bits."""

    __slots__ = ()
    _width = 25
    _alphabet = BASE36
    _case = 'lower'

    def to_uuid(self) -> UUID:
        return UUID(int=self.value)

    @classmethod
    def from_uuid(cls, value: UUID) -> Self:
        if not isinstance(value, UUID):
            raise TypeError('value must be a UUID')

        return cls(value.int)

    @staticmethod
    def encode(value: UUID) -> str:
        return str(UUID25.from_uuid(value))

    @staticmethod
    def decode(value: str) -> UUID:
        return UUID25.from_str(value).to_uuid()

    @staticmethod
    def encode_many(values: Iterable[UUID], *, parallel: bool = False) -> list[str]:
        items = batch_items(values, parallel)
        if any(not isinstance(value, UUID) for value in items):
            raise TypeError('value must be a UUID')

        return _radix(BASE36).encode_u128_many([value.int for value in items], 25, parallel)

    @staticmethod
    def decode_many(values: Iterable[str], *, parallel: bool = False) -> list[UUID]:
        items = text_items(values, parallel)
        if any(not value.isascii() for value in items):
            raise ValueError('identifier must contain ASCII characters')
        decoded = _radix(BASE36).decode_u128_many([value.lower() for value in items], 25, 128, parallel)

        return [UUID(int=value) for value in decoded]
