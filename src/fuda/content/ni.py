"""RFC 6920 NI and NIH names. Parsing and verification never access the network."""

from __future__ import annotations
from typing import Self
from hmac import compare_digest
from re import search, fullmatch
from urllib.parse import urlsplit
from builtins import bytes as Bytes
from fuda._core.encoding import integer
from fuda._core.extension import native
from dataclasses import field, dataclass
from hashlib import new, blake2b, blake2s
from base64 import urlsafe_b64decode, urlsafe_b64encode

# IANA Named Information registry, including algorithms without binary suite IDs.
_SUITES: dict[str, tuple[int | None, str, int]] = {
    'sha-256': (1, 'sha256', 32),
    'sha-256-128': (2, 'sha256', 16),
    'sha-256-120': (3, 'sha256', 15),
    'sha-256-96': (4, 'sha256', 12),
    'sha-256-64': (5, 'sha256', 8),
    'sha-256-32': (6, 'sha256', 4),
    'sha-384': (7, 'sha384', 48),
    'sha-512': (8, 'sha512', 64),
    'sha3-224': (9, 'sha3_224', 28),
    'sha3-256': (10, 'sha3_256', 32),
    'sha3-384': (11, 'sha3_384', 48),
    'sha3-512': (12, 'sha3_512', 64),
    'blake2s-256': (None, 'blake2s', 32),
    'blake2b-256': (None, 'blake2b', 32),
    'blake2b-512': (None, 'blake2b', 64),
    'k12-256': (None, '', 32),
    'k12-512': (None, '', 64),
}
_NUMERIC = {code: name for name, (code, _, _) in _SUITES.items() if code is not None}

def _hash(content: bytes, algorithm: str) -> bytes:
    if not isinstance(content, bytes):
        raise TypeError('content must be bytes')
    if algorithm not in _SUITES:
        raise ValueError('unknown NI hash algorithm')
    _, name, size = _SUITES[algorithm]
    if not name:
        raise ValueError('KangarooTwelve names can be parsed, but hashing requires an external implementation')
    if name == 'blake2b':
        return blake2b(content, digest_size=size).digest()
    if name == 'blake2s':
        return blake2s(content, digest_size=size).digest()
    return new(name, content).digest()[:size]

def _uri_component(value: str, pattern: str) -> None:
    if not isinstance(value, str):
        raise TypeError('URI components must be strings')
    if not value:
        return
    if fullmatch(pattern, value) is None or search(r'%(?![0-9A-Fa-f]{2})', value):
        raise ValueError('invalid URI component; percent-encode reserved and non-ASCII characters')

def _checkdigit(value: str) -> str:
    return native.hex_checkdigit(value)

@dataclass(frozen=True, slots=True)
class _Name:
    algorithm: str
    digest: bytes

    def __post_init__(self) -> None:
        if self.algorithm not in _SUITES:
            raise ValueError('unknown NI hash algorithm')
        if not isinstance(self.digest, bytes):
            raise TypeError('digest must be bytes')
        if len(self.digest) != _SUITES[self.algorithm][2]:
            raise ValueError('digest length does not match the NI algorithm')

    @property
    def bytes(self) -> bytes:
        """RFC 6920 binary name, without the authority or query."""
        code = _SUITES[self.algorithm][0]
        if code is None:
            raise ValueError('algorithm has no registered binary suite ID')
        return bytes([code]) + self.digest

    @classmethod
    def from_bytes(cls, value: Bytes) -> Self:
        if not isinstance(value, bytes):
            raise TypeError('value must be bytes')
        if not value or value[0] & 63 not in _NUMERIC:
            raise ValueError('unknown binary NI suite ID')
        # RFC 6920 requires ignoring the two reserved bits on receipt.
        return cls(_NUMERIC[value[0] & 63], value[1:])

    def verify(self, content: Bytes) -> bool:
        return compare_digest(self.digest, _hash(content, self.algorithm))

    def same_content(self, other: object) -> bool:
        return isinstance(other, _Name) and self.algorithm == other.algorithm and self.digest == other.digest

@dataclass(frozen=True, slots=True)
class NI(_Name):
    """An NI URI. Locator hints are excluded from equality and hashing."""

    authority: str = field(default='', compare=False)
    query: str = field(default='', compare=False)

    def __post_init__(self) -> None:
        _Name.__post_init__(self)
        _uri_component(
            self.authority,
            r"(?:[A-Za-z0-9._~!$&'()*+,;=:%-]*@)?"
            r"(?:\[[A-Za-z0-9:._~!$&'()*+,;=%-]+\]|[A-Za-z0-9._~!$&'()*+,;=%-]*)"
            r'(?::[0-9]*)?',
        )
        _uri_component(self.query, r"[A-Za-z0-9._~!$&'()*+,;=:@%/?-]*")
        if self.authority:
            urlsplit('ni://' + self.authority + '/')

    def __str__(self) -> str:
        digest = urlsafe_b64encode(self.digest).decode('ascii').rstrip('=')
        result = f'ni://{self.authority}/{self.algorithm};{digest}'
        if self.query:
            result += '?' + self.query
        return result

    def to_nih(self) -> NIH:
        return NIH(self.algorithm, self.digest)

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if (
            not value[:5].lower() == 'ni://'
            or '#' in value
            or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
        ):
            raise ValueError('expected an absolute NI URI')
        parts = urlsplit(value)
        algorithm, separator, encoded = parts.path[1:].partition(';')
        if not separator or fullmatch(r'[A-Za-z0-9_-]+', encoded) is None:
            raise ValueError('invalid NI digest')
        digest = urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
        if urlsafe_b64encode(digest).decode('ascii').rstrip('=') != encoded:
            raise ValueError('noncanonical NI base64url digest')
        return cls(algorithm, digest, parts.netloc, parts.query)

    @classmethod
    def from_content(cls, content: Bytes, *, algorithm: str = 'sha-256', authority: str = '', query: str = '') -> Self:
        return cls(algorithm, _hash(content, algorithm), authority, query)

@dataclass(frozen=True, slots=True)
class NIH(_Name):
    """Human-readable NI name, canonically grouped with a Luhn mod-16 digit."""

    def __str__(self) -> str:
        return self.to_str()

    def to_str(self, *, group_size: int = 4, checkdigit: bool = True, numeric_algorithm: bool = False) -> str:
        integer(group_size, 'group_size', 0, 128)
        if not isinstance(checkdigit, bool) or not isinstance(numeric_algorithm, bool):
            raise TypeError('checkdigit and numeric_algorithm must be bools')
        code = _SUITES[self.algorithm][0]
        if numeric_algorithm and code is None:
            raise ValueError('algorithm has no registered numeric suite ID')
        algorithm = str(code) if numeric_algorithm else self.algorithm
        digest = self.digest.hex()
        grouped = (
            '-'.join(digest[offset : offset + group_size] for offset in range(0, len(digest), group_size))
            if group_size
            else digest
        )
        return f'nih:{algorithm};{grouped}' + (';' + _checkdigit(digest) if checkdigit else '')

    def to_ni(self, *, authority: str = '', query: str = '') -> NI:
        return NI(self.algorithm, self.digest, authority, query)

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        match = fullmatch(r'(?i:nih):([a-z0-9-]+);([0-9a-f-]+)(?:;([0-9a-f]))?', value)
        if match is None:
            raise ValueError('invalid NIH URI')
        algorithm, grouped, check = match.groups()
        if algorithm.isdecimal():
            algorithm = _NUMERIC.get(int(algorithm), '')
        digest = grouped.replace('-', '')
        if check is not None and check != _checkdigit(digest):
            raise ValueError('invalid NIH check digit')
        return cls(algorithm, bytes.fromhex(digest))

    @classmethod
    def from_content(cls, content: Bytes, *, algorithm: str = 'sha-256') -> Self:
        return cls(algorithm, _hash(content, algorithm))

def ni(content: bytes, *, algorithm: str = 'sha-256', authority: str = '', query: str = '') -> NI:
    return NI.from_content(content, algorithm=algorithm, authority=authority, query=query)

def nih(content: bytes, *, algorithm: str = 'sha-256') -> NIH:
    return NIH.from_content(content, algorithm=algorithm)
