"""Pronounceable encoding of 16-bit words: https://arxiv.org/html/0901.4016."""

from fuda._core.extension import native

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
