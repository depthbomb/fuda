"""Hashids 1.x codec. Adapted from hashids-python; see LICENSE.hashids.

Hashids disguises integer sequences. It does not encrypt them or add entropy.
"""

from math import ceil
from functools import lru_cache
from collections.abc import Iterable
from fuda._core.encoding import integer
from fuda._core.extension import native

HASHIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'

def _shuffle(text: str, salt: str) -> str:
    if not salt:
        return text
    chars = list(text)
    index = total = 0
    for position in range(len(chars) - 1, 0, -1):
        code = ord(salt[index])
        total += code
        other = (code + index + total) % position
        chars[position], chars[other] = chars[other], chars[position]
        index = (index + 1) % len(salt)
    return ''.join(chars)

class Hashids:
    """Encode nonnegative 63-bit integers using a reusable configuration."""

    def __init__(self, *, salt: str = '', min_length: int = 0, alphabet: str = HASHIDS_ALPHABET) -> None:
        if not isinstance(salt, str):
            raise TypeError('salt must be a string')
        if not isinstance(alphabet, str):
            raise TypeError('alphabet must be a string')
        if not alphabet.isascii() or any(not 33 <= ord(char) <= 126 for char in alphabet):
            raise ValueError('alphabet must contain printable ASCII without spaces')
        alphabet = ''.join(dict.fromkeys(alphabet))
        if len(alphabet) < 16:
            raise ValueError('alphabet requires at least 16 unique characters')
        self._salt = salt
        self._min_length = integer(min_length, 'min_length', 0, 255)
        separators = ''.join(char for char in 'cfhistuCFHISTU' if char in alphabet)
        alphabet = ''.join(char for char in alphabet if char not in separators)
        separators = _shuffle(separators, salt)
        missing = ceil(len(alphabet) / 3.5) - len(separators)
        if missing > 0:
            separators += alphabet[:missing]
            alphabet = alphabet[missing:]
        alphabet = _shuffle(alphabet, salt)
        count = ceil(len(alphabet) / 12)
        self._guards, self._alphabet = alphabet[:count], alphabet[count:]
        self._separators = separators
        # Later shuffles only read this prefix. The setup above needs the full
        # salt because it starts with a larger alphabet.
        self._salt = salt[: len(self._alphabet)]
        self._init_native()

    def _init_native(self) -> None:
        self._native_codec = native.HashidsCodec(
            self._alphabet, self._separators, self._guards, list(map(ord, self._salt)), self._min_length
        )

    def __getstate__(self) -> dict[str, object]:
        # Save the settings and rebuild the native cache when loading.
        state = self.__dict__.copy()
        state.pop('_native_codec')
        return state

    def __setstate__(self, state: dict[str, object]) -> None:
        self.__dict__.update(state)
        self._init_native()

    def encode(self, numbers: Iterable[int]) -> str:
        values = [integer(value, 'number', 0, (1 << 63) - 1) for value in numbers]
        return self._native_codec.encode(values)

    def decode(self, value: str) -> list[int]:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        return self._native_codec.decode(value)

    def encode_hex(self, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError('hex value must be a string')
        if any(char not in '0123456789abcdefABCDEF' for char in value):
            raise ValueError('invalid hex value')
        return self.encode(int('1' + value[offset : offset + 12], 16) for offset in range(0, len(value), 12))

    def decode_hex(self, value: str) -> str:
        chunks = [format(number, 'x') for number in self.decode(value)]
        if any(not chunk.startswith('1') or not 2 <= len(chunk) <= 13 for chunk in chunks):
            raise ValueError('identifier does not contain Hashids hex data')
        decoded = ''.join(chunk[1:] for chunk in chunks)
        if self.encode_hex(decoded) != value:
            raise ValueError('noncanonical Hashids hex data')
        return decoded

@lru_cache(maxsize=1)
def default_hashids() -> Hashids:
    return Hashids()
