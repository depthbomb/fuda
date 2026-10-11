from __future__ import annotations
from typing import Self
from hmac import compare_digest
from dataclasses import dataclass
from builtins import bytes as Bytes
from fuda._core.encoding import integer
from fuda.content.multihash import _HASHES, _digest, Multihash, _HASH_CODES
from fuda.content._multiformats import varint, read_varint, BASE_PREFIXES, multibase_decode, multibase_encode

_CODECS = {'raw': 0x55, 'dag-pb': 0x70, 'dag-cbor': 0x71, 'dag-json': 0x129, 'json': 0x200, 'cbor': 0x51}

@dataclass(frozen=True, slots=True)
class CIDv1:
    """CIDv1 of an encoded content block, with canonical lowercase base32 text.

    from_content hashes the supplied bytes directly. It does not chunk files or
    serialize DAG objects. Unknown codec and hash codes are preserved on parse.
    """

    codec: int
    hash_code: int
    digest: bytes

    def __post_init__(self) -> None:
        integer(self.codec, 'codec', 0, (1 << 63) - 1)
        integer(self.hash_code, 'hash_code', 0, (1 << 63) - 1)
        if not isinstance(self.digest, bytes):
            raise TypeError('digest must be bytes')
        # Multihashes permit truncation, but cannot exceed a fixed hash's output.
        if self.hash_code in _HASH_CODES:
            size = _HASH_CODES[self.hash_code][2]
            if size and len(self.digest) > size:
                raise ValueError('digest exceeds the hash algorithm output size')

    def __str__(self) -> str:
        return self.to_base('base32')

    @property
    def bytes(self) -> bytes:
        return b'\x01' + varint(self.codec) + varint(self.hash_code) + varint(len(self.digest)) + self.digest

    @property
    def codec_name(self) -> str | None:
        return next((name for name, code in _CODECS.items() if code == self.codec), None)

    @property
    def hash_name(self) -> str | None:
        info = _HASH_CODES.get(self.hash_code)

        return info[0] if info is not None else None

    def to_base(self, base: str = 'base32') -> str:
        if base not in BASE_PREFIXES:
            raise ValueError(f'unsupported multibase {base!r}; choose from {", ".join(BASE_PREFIXES)}')

        return multibase_encode(self.bytes, BASE_PREFIXES[base])

    @property
    def multihash(self) -> Multihash:
        return Multihash(self.hash_code, self.digest)

    def to_v0(self) -> CIDv0:
        if self.codec != 0x70 or self.hash_code != 0x12:
            raise ValueError('CIDv0 requires dag-pb and SHA-256')
        return CIDv0(self.digest)

    def verify(self, content: Bytes) -> bool:
        if self.hash_code != 0 and not self.digest:
            raise ValueError('cannot verify content against an empty digest')
        digest = _digest(content, self.hash_code)
        if self.hash_code != 0:
            digest = digest[: len(self.digest)]

        return compare_digest(digest, self.digest)

    @classmethod
    def from_bytes(cls, value: Bytes) -> Self:
        if not isinstance(value, bytes):
            raise TypeError('value must be bytes')
        version, offset = read_varint(value, 0)
        if version != 1:
            raise ValueError('expected CID version 1')
        codec, offset = read_varint(value, offset)
        hash_code, offset = read_varint(value, offset)
        length, offset = read_varint(value, offset)
        if length != len(value) - offset:
            raise ValueError('multihash digest length does not match the CID bytes')

        return cls(codec, hash_code, value[offset:])

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')

        return cls.from_bytes(multibase_decode(value))

    @classmethod
    def from_content(cls, content: Bytes, *, codec: str | int = 'raw', hash_name: str = 'sha2-256') -> Self:
        if isinstance(codec, str):
            if codec not in _CODECS:
                raise ValueError(f'unknown codec {codec!r}; pass its numeric multicodec code')
            code = _CODECS[codec]
        else:
            code = integer(codec, 'codec', 0, (1 << 63) - 1)
        if hash_name not in _HASHES:
            raise ValueError(f'unsupported hash {hash_name!r}')
        hash_code = _HASHES[hash_name][0]

        return cls(code, hash_code, _digest(content, hash_code))

def cidv1(content: bytes, *, codec: str | int = 'raw', hash_name: str = 'sha2-256') -> CIDv1:
    return CIDv1.from_content(content, codec=codec, hash_name=hash_name)

@dataclass(frozen=True, slots=True)
class CIDv0:
    """CIDv0 for an already serialized DAG-PB block, without file import/chunking."""

    digest: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.digest, bytes):
            raise TypeError('digest must be bytes')
        if len(self.digest) != 32:
            raise ValueError('CIDv0 requires a 32-byte SHA-256 digest')

    @property
    def bytes(self) -> bytes:
        return b'\x12\x20' + self.digest

    @property
    def multihash(self) -> Multihash:
        return Multihash(0x12, self.digest)

    def __str__(self) -> str:
        return multibase_encode(self.bytes, 'z')[1:]

    def to_v1(self) -> CIDv1:
        return CIDv1(0x70, 0x12, self.digest)

    def verify(self, content: Bytes) -> bool:
        return self.multihash.verify(content)

    @classmethod
    def from_bytes(cls, value: Bytes) -> Self:
        if not isinstance(value, bytes):
            raise TypeError('value must be bytes')
        if len(value) != 34 or value[:2] != b'\x12\x20':
            raise ValueError('invalid CIDv0 multihash')
        return cls(value[2:])

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if len(value) != 46 or not value.startswith('Qm'):
            raise ValueError('CIDv0 must be an unprefixed base58btc SHA-256 multihash')
        return cls.from_bytes(multibase_decode('z' + value))

    @classmethod
    def from_content(cls, content: Bytes) -> Self:
        return cls(_digest(content, 0x12))

def cidv0(content: bytes) -> CIDv0:
    return CIDv0.from_content(content)
