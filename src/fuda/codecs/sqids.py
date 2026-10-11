"""Sqids encoding, following https://github.com/sqids/sqids-spec.

The bundled default blocklist and algorithm are covered by LICENSE.sqids.
Sqids obscures numbers; it does not encrypt them or create uniqueness.
"""

from json import loads
from functools import lru_cache
from collections.abc import Iterable
from importlib.resources import files
from fuda._core.encoding import integer
from fuda._core.extension import native

SQIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

@lru_cache(maxsize=1)
def _default_blocklist() -> frozenset[str]:
    return frozenset(loads(files('fuda.codecs').joinpath('sqids-blocklist.json').read_text(encoding='utf-8')))

def _shuffle(alphabet: str) -> str:
    chars = list(alphabet)
    size = len(chars)
    for index in range(size - 1):
        other = size - 1 - index
        target = (index * other + ord(chars[index]) + ord(chars[other])) % size
        chars[index], chars[target] = chars[target], chars[index]

    return ''.join(chars)

class Sqids:
    """Reversible sequences of integers in 0..2**63-1, with stable defaults.

    Persist alphabet, min_length and blocklist with your application settings.
    decode() accepts alternate encodings; canonical=True requires encode()'s
    exact output for this configuration.
    """

    def __init__(
        self,
        *,
        alphabet: str = SQIDS_ALPHABET,
        min_length: int = 0,
        blocklist: Iterable[str] | None = None,
    ) -> None:
        if not isinstance(alphabet, str):
            raise TypeError('alphabet must be a string')
        if not alphabet.isascii() or len(alphabet) < 3 or len(set(alphabet)) != len(alphabet):
            raise ValueError('alphabet must contain at least three unique ASCII characters')
        integer(min_length, 'min_length', 0, 255)
        words = _default_blocklist() if blocklist is None else blocklist
        if isinstance(words, str):
            raise TypeError('blocklist must be an iterable of words')
        alphabet_chars = set(alphabet.lower())
        exact, ends, anywhere = set(), set(), set()
        for word in words:
            if not isinstance(word, str):
                raise TypeError('blocklist words must be strings')
            word = word.lower()
            if len(word) < 3 or not set(word) <= alphabet_chars:
                continue
            if len(word) == 3:
                exact.add(word)
            elif any(char in '0123456789' for char in word):
                ends.add(word)
            else:
                anywhere.add(word)
        self._alphabet = _shuffle(alphabet)
        self._min_length = min_length
        self._exact = frozenset(exact)
        self._ends = tuple(sorted(ends))
        self._anywhere = tuple(sorted(anywhere))
        self._init_native()

    def _init_native(self) -> None:
        self._native_codec = native.SqidsCodec(
            self._alphabet, self._min_length, list(self._exact), list(self._ends), list(self._anywhere)
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
        values = tuple(numbers)
        for value in values:
            integer(value, 'number', 0, (1 << 63) - 1)
        return self._native_codec.encode(values)

    def decode(self, value: str, *, canonical: bool = False) -> list[int]:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        return self._native_codec.decode(value, bool(canonical))

@lru_cache(maxsize=1)
def default_sqids() -> Sqids:
    return Sqids()
