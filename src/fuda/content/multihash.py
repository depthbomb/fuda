"""Standalone multihashes, represented as multibase-prefixed base58btc text."""

from typing import Self
from hmac import compare_digest
from hashlib import new, blake2b
from dataclasses import dataclass
from builtins import bytes as Bytes
from fuda._core.encoding import integer
from fuda.content._multiformats import varint, read_varint, BASE_PREFIXES, multibase_decode, multibase_encode

_HASHES = {
    'identity': (0x00, '', 0),
    'sha2-256': (0x12, 'sha256', 32),
    'sha2-512': (0x13, 'sha512', 64),
    'sha3-512': (0x14, 'sha3_512', 64),
    'sha3-384': (0x15, 'sha3_384', 48),
    'sha3-256': (0x16, 'sha3_256', 32),
    'sha3-224': (0x17, 'sha3_224', 28),
    'blake2b-256': (0xB220, 'blake2b', 32),
}
_HASH_CODES = {code: (name, algorithm, size) for name, (code, algorithm, size) in _HASHES.items()}

def _digest(data: bytes, code: int) -> bytes:
    if not isinstance(data, bytes):
        raise TypeError('content must be bytes')
    if code not in _HASH_CODES:
        raise ValueError('hash algorithm is not supported for content verification')
    _, algorithm, size = _HASH_CODES[code]
    if code == 0:
        return data
    if algorithm == 'blake2b':
        return blake2b(data, digest_size=size).digest()
    return new(algorithm, data).digest()

@dataclass(frozen=True, slots=True)
class Multihash:
    hash_code: int
    digest: bytes

    def __post_init__(self) -> None:
        integer(self.hash_code, 'hash_code', 0, (1 << 63) - 1)
        if not isinstance(self.digest, bytes):
            raise TypeError('digest must be bytes')
        info = _HASH_CODES.get(self.hash_code)
        if info is not None and info[2] and len(self.digest) > info[2]:
            raise ValueError('digest exceeds the hash algorithm output size')

    @property
    def bytes(self) -> bytes:
        return varint(self.hash_code) + varint(len(self.digest)) + self.digest

    @property
    def hash_name(self) -> str | None:
        info = _HASH_CODES.get(self.hash_code)
        return info[0] if info is not None else None

    def __str__(self) -> str:
        return self.to_base()

    def to_base(self, base: str = 'base58btc') -> str:
        if base not in BASE_PREFIXES:
            raise ValueError(f'unsupported multibase {base!r}')
        return multibase_encode(self.bytes, BASE_PREFIXES[base])

    def verify(self, content: Bytes) -> bool:
        if self.hash_code != 0 and not self.digest:
            raise ValueError('cannot verify content against an empty digest')
        digest = _digest(content, self.hash_code)
        return compare_digest(digest if self.hash_code == 0 else digest[: len(self.digest)], self.digest)

    @classmethod
    def from_bytes(cls, value: Bytes) -> Self:
        if not isinstance(value, bytes):
            raise TypeError('value must be bytes')
        code, offset = read_varint(value, 0)
        length, offset = read_varint(value, offset)
        if length != len(value) - offset:
            raise ValueError('multihash digest length does not match the bytes')
        return cls(code, value[offset:])

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        return cls.from_bytes(multibase_decode(value))

    @classmethod
    def from_content(cls, content: Bytes, *, hash_name: str = 'sha2-256', digest_size: int | None = None) -> Self:
        if hash_name not in _HASHES:
            raise ValueError(f'unsupported hash {hash_name!r}')
        code = _HASHES[hash_name][0]
        digest = _digest(content, code)
        if digest_size is not None:
            integer(digest_size, 'digest_size', 0 if code == 0 else 1, len(digest))
            if code == 0 and digest_size != len(digest):
                raise ValueError('identity hashes cannot truncate content')
            digest = digest[:digest_size]
        return cls(code, digest)

def multihash(content: bytes, *, hash_name: str = 'sha2-256', digest_size: int | None = None) -> Multihash:
    return Multihash.from_content(content, hash_name=hash_name, digest_size=digest_size)
