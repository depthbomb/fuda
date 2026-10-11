from os import urandom
from time import time_ns
from uuid import UUID, uuid4
from functools import lru_cache
from collections.abc import Callable
from fuda._core.extension import native
from fuda.identifiers.types import ULID, KSUID
from fuda._core.state import Generator, ProcessGenerator
from fuda._core.encoding import _radix, decode, encode, integer, SHORTUUID

NANOID_ALPHABET = '_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'

@lru_cache(maxsize=128)
def _nanoid_layout(alphabet: str) -> tuple[bytes, bytes]:
    if not isinstance(alphabet, str):
        raise TypeError('alphabet must be a string')
    if not 2 <= len(alphabet) <= 256 or len(set(alphabet)) != len(alphabet):
        raise ValueError('alphabet must contain between 2 and 256 distinct characters')
    if any(0xD800 <= ord(character) <= 0xDFFF for character in alphabet):
        raise ValueError('alphabet cannot contain Unicode surrogates')
    mask = (1 << (len(alphabet) - 1).bit_length()) - 1
    excluded = bytes(value for value in range(256) if value & mask >= len(alphabet))
    if alphabet.isascii():
        table = bytes(ord(alphabet[value & mask]) if value & mask < len(alphabet) else 0 for value in range(256))
    else:
        table = bytes(value & mask for value in range(256))

    return table, excluded

def _nanoid(length: int, alphabet: str, table: bytes, excluded: bytes) -> str:
    # Every accepted byte maps equally often to each symbol. Deletion happens
    # before translation, so non-power-of-two alphabets retain rejection sampling.
    step = length if not excluded else max(16, min(4096, length * 256 // (256 - len(excluded)) + 8))
    parts = []
    remaining = length
    ascii_alphabet = alphabet.isascii()
    while remaining:
        data = urandom(step).translate(table, excluded)
        if len(data) > remaining:
            data = data[:remaining]
        parts.append(data.decode('ascii') if ascii_alphabet else ''.join(alphabet[index] for index in data))
        remaining -= len(data)

    return ''.join(parts)

def nanoid(length: int = 21, *, alphabet: str = NANOID_ALPHABET) -> str:
    integer(length, 'length', 1, 1_000_000)
    table, excluded = _nanoid_layout(alphabet)

    return _nanoid(length, alphabet, table, excluded)

class NanoIDGenerator(Generator[str]):
    """Reusable NanoID configuration with unbiased OS randomness on every call."""

    def __init__(self, length: int = 21, *, alphabet: str = NANOID_ALPHABET) -> None:
        self._length = integer(length, 'length', 1, 1_000_000)
        self._table, self._excluded = _nanoid_layout(alphabet)
        self._alphabet = alphabet
        self._native_random = native.RandomAlphabet(alphabet)

    def generate(self) -> str:
        return _nanoid(self._length, self._alphabet, self._table, self._excluded)

    def _generate_many(self, count: int, parallel: bool) -> list[str]:
        return self._native_random.generate_many(count, self._length, parallel)

class ULIDGenerator(ProcessGenerator[ULID]):
    def __init__(self, *, monotonic: bool = True, clock: Callable[[], int] | None = None) -> None:
        if not isinstance(monotonic, bool):
            raise TypeError('monotonic must be a boolean')
        super().__init__()
        self.monotonic = monotonic
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._last_ms = -1
        self._random = 0

    def _reset_process(self) -> None:
        self._last_ms = -1
        self._random = 0

    def generate(self) -> ULID:
        self._check_process()
        with self._lock:
            now = integer(self._clock(), 'timestamp', 0, (1 << 48) - 1)
            if self.monotonic and now <= self._last_ms:
                now = self._last_ms
                self._random += 1
                if self._random >= 1 << 80:
                    raise OverflowError('ULID randomness exhausted in this millisecond')
            else:
                self._random = int.from_bytes(urandom(10), 'big')
            self._last_ms = now
            result = (now << 80) | self._random

        return ULID(result)

class KSUIDGenerator(Generator[KSUID]):
    """Generate KSUIDs using the current time or a fixed Unix timestamp in seconds."""

    def __init__(self, *, timestamp: int | None = None) -> None:
        if timestamp is not None:
            integer(timestamp, 'timestamp', 1_400_000_000, 1_400_000_000 + (1 << 32) - 1)
        self._timestamp = timestamp

    def generate(self) -> KSUID:
        return ksuid(timestamp=self._timestamp)

    def _generate_many(self, count: int, parallel: bool) -> list[KSUID]:
        values = native.random_u128_many(count, (1 << 128) - 1, parallel=parallel)
        results = []
        for random in values:
            timestamp = time_ns() // 1_000_000_000 if self._timestamp is None else self._timestamp
            integer(timestamp, 'timestamp', 1_400_000_000, 1_400_000_000 + (1 << 32) - 1)
            results.append(KSUID(((timestamp - 1_400_000_000) << 128) | random))

        return results

class ShortUUIDGenerator(Generator[str]):
    """Generate random UUIDv4 values encoded in ShortUUID's base57 alphabet."""

    def generate(self) -> str:
        return shortuuid()

    def _generate_many(self, count: int, parallel: bool) -> list[str]:
        mask = ((1 << 128) - 1) ^ ((15 << 76) | (3 << 62))
        values = native.random_u128_many(count, mask, (4 << 76) | (2 << 62), parallel)

        return _radix(SHORTUUID).encode_u128_many(values, 22, parallel)

def ksuid(*, timestamp: int | None = None) -> KSUID:
    timestamp = time_ns() // 1_000_000_000 if timestamp is None else timestamp
    integer(timestamp, 'timestamp', 1_400_000_000, 1_400_000_000 + (1 << 32) - 1)

    return KSUID(((timestamp - 1_400_000_000) << 128) | int.from_bytes(urandom(16), 'big'))

def shortuuid(value: UUID | None = None) -> str:
    if value is not None and not isinstance(value, UUID):
        raise TypeError('value must be a UUID')

    return encode((value if value is not None else uuid4()).int, SHORTUUID, 22)

def decode_shortuuid(value: str) -> UUID:
    return UUID(int=decode(value, SHORTUUID, 22, 128))
