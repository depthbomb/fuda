from typing import Self
from uuid import UUID, uuid5
from dataclasses import dataclass
from collections.abc import Callable
from fuda._core.state import Generator
from fuda._core.extension import native
from fuda.identifiers.uuids import uuid7, UUID7Generator
from fuda._core.encoding import decode, encode, CROCKFORD

_TYPE_ALPHABET = CROCKFORD.lower()
_XUID_NAMESPACE = UUID('d16b6139-8989-467f-a240-441df6734f45')

def _type_prefix(prefix: str) -> str:
    if not isinstance(prefix, str):
        raise TypeError('prefix must be a string')
    if len(prefix) > 63 or any(c not in 'abcdefghijklmnopqrstuvwxyz_' for c in prefix):
        raise ValueError('TypeID prefix must contain at most 63 lowercase ASCII letters or underscores')
    if prefix and (prefix.startswith('_') or prefix.endswith('_')):
        raise ValueError('TypeID prefix must start and end with a letter')

    return prefix

def _xuid_prefix(prefix: str) -> str:
    if not isinstance(prefix, str):
        raise TypeError('prefix must be a string')
    if len(prefix) > 5 or (prefix and (not prefix.isascii() or not prefix.isalnum())):
        raise ValueError('XUID prefix must contain at most 5 ASCII letters or digits')

    return prefix.lower()

@dataclass(frozen=True, slots=True)
class TypeID:
    prefix: str
    uuid: UUID

    def __post_init__(self) -> None:
        _type_prefix(self.prefix)
        if not isinstance(self.uuid, UUID):
            raise TypeError('uuid must be a UUID')

    def __str__(self) -> str:
        suffix = encode(self.uuid.int, _TYPE_ALPHABET, 26)

        return f'{self.prefix}_{suffix}' if self.prefix else suffix

    @property
    def bytes(self) -> bytes:
        return self.uuid.bytes

    @classmethod
    def from_uuid(cls, value: UUID, prefix: str = '') -> Self:
        return cls(prefix, value)

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        prefix, separator, suffix = value.rpartition('_')
        if not separator:
            prefix, suffix = '', value
        elif not prefix:
            raise ValueError('an empty TypeID prefix must omit the separator')
        _type_prefix(prefix)

        return cls(prefix, UUID(int=decode(suffix, _TYPE_ALPHABET, 26, 128)))

@dataclass(frozen=True, slots=True)
class XUID:
    prefix: str
    uuid: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, 'prefix', _xuid_prefix(self.prefix))
        if not isinstance(self.uuid, UUID):
            raise TypeError('uuid must be a UUID')

    def __str__(self) -> str:
        raw = native.multibase_encode(self.uuid.bytes, 'b')[1:]
        body = f'{raw[:6]}-{raw[6:10]}-{raw[10:14]}-{raw[14:18]}-{raw[18:]}'

        return f'{self.prefix}-{body}' if self.prefix else body

    @property
    def bytes(self) -> bytes:
        return self.uuid.bytes

    @classmethod
    def from_uuid(cls, value: UUID, prefix: str = '') -> Self:
        return cls(prefix, value)

    @classmethod
    def from_key(cls, key: str, prefix: str | None = None) -> Self:
        if not isinstance(key, str):
            raise TypeError('key must be a string')
        if prefix is None:
            return cls('utref', uuid5(_XUID_NAMESPACE, key))
        _xuid_prefix(prefix)

        return cls(prefix, uuid5(uuid5(_XUID_NAMESPACE, prefix), key))

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        parts = value.split('-')
        if not value.isascii():
            raise ValueError('XUID must contain ASCII characters')
        prefix = ''
        if len(parts) == 6:
            prefix, parts = parts[0], parts[1:]
            if not prefix:
                raise ValueError('an empty XUID prefix must omit its separator')
        if len(parts) != 5 or list(map(len, parts)) != [6, 4, 4, 4, 8]:
            try:
                return cls('', UUID(value))
            except ValueError:
                raise ValueError('invalid XUID or UUID') from None
        _xuid_prefix(prefix)
        raw = ''.join(parts).upper()
        if any(letter not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567' for letter in raw):
            raise ValueError('invalid XUID base32 alphabet')
        data = native.multibase_decode('B' + raw)

        return cls(prefix, UUID(bytes=data))

class TypeIDGenerator(Generator[TypeID]):
    """Generate prefixed TypeIDs with an independent monotonic UUIDv7 source."""

    def __init__(self, prefix: str = '', *, clock: Callable[[], int] | None = None) -> None:
        self._prefix = _type_prefix(prefix)
        self._uuids = UUID7Generator(clock=clock)

    def generate(self) -> TypeID:
        return TypeID(self._prefix, self._uuids.generate())

class XUIDGenerator(Generator[XUID]):
    """Generate grouped XUIDs with an independent monotonic UUIDv7 source."""

    def __init__(self, prefix: str = '', *, clock: Callable[[], int] | None = None) -> None:
        self._prefix = _xuid_prefix(prefix)
        self._uuids = UUID7Generator(clock=clock)

    def generate(self) -> XUID:
        return XUID(self._prefix, self._uuids.generate())

def typeid(prefix: str = '', *, value: UUID | None = None) -> TypeID:
    _type_prefix(prefix)

    return TypeID(prefix, value if value is not None else uuid7())

def xuid(prefix: str = '', *, value: UUID | None = None) -> XUID:
    _xuid_prefix(prefix)

    return XUID(prefix, value if value is not None else uuid7())
