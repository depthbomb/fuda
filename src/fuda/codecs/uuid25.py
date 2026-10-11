from uuid import UUID
from typing import Self
from fuda._core.encoding import BASE36
from fuda.identifiers.types import BinaryID

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
