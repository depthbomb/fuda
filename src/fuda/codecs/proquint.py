"""Pronounceable encoding of 16-bit words: https://arxiv.org/html/0901.4016."""

from collections.abc import Iterable
from fuda._core.extension import native
from fuda._core.batch import text_items, batch_items

class Proquint:
    """Encode bytes as hyphen-separated CVCVC words; no new entropy is added."""

    @staticmethod
    def encode(value: bytes) -> str:
        if not isinstance(value, bytes):
            raise TypeError('value must be bytes')
        return native.proquint_encode(value)

    @staticmethod
    def decode(value: str) -> bytes:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        return native.proquint_decode(value)

    @staticmethod
    def encode_many(values: Iterable[bytes], *, parallel: bool = False) -> list[str]:
        items = batch_items(values, parallel)
        if any(not isinstance(value, bytes) for value in items):
            raise TypeError('value must be bytes')

        return native.proquint_encode_many(items, parallel)

    @staticmethod
    def decode_many(values: Iterable[str], *, parallel: bool = False) -> list[bytes]:
        return native.proquint_decode_many(text_items(values, parallel), parallel)
