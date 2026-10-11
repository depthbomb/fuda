from re import compile
from functools import lru_cache
from typing import TYPE_CHECKING
from fuda._core.extension import native

if TYPE_CHECKING:
    from fuda._native import RadixCodec

BASE36 = '0123456789abcdefghijklmnopqrstuvwxyz'
BASE62 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
BASE32HEX = '0123456789abcdefghijklmnopqrstuv'
SHORTUUID = '23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_PAIRS = tuple(a + b for a in BASE36 for b in BASE36)
_HEX = compile('[0-9a-f]*')

@lru_cache(maxsize=32)
def _radix(alphabet: str) -> 'RadixCodec':
    return native.RadixCodec(alphabet)

def integer(value: int, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f'{name} must be an integer')
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')

    return value

def base36(value: int) -> str:
    if value < 0:
        raise ValueError('Cannot encode negative integers.')
    if value == 0:
        return '0'
    parts = []
    while value >= 1296:
        value, remainder = divmod(value, 1296)
        parts.append(_PAIRS[remainder])
    parts.append(BASE36[value] if value < 36 else _PAIRS[value])

    return ''.join(reversed(parts))

def encode(value: int, alphabet: str, width: int) -> str:
    if value < 0:
        raise ValueError('cannot encode a negative integer')
    if width == 0 and value == 0:
        return ''
    if alphabet == '0123456789abcdef':
        # Python already formats hex in C, so a Rust call doesn't help here.
        encoded = format(value, 'x')
        if len(encoded) > width:
            raise ValueError('integer exceeds the encoding width')
        return encoded.rjust(width, '0')
    codec = _radix(alphabet)
    # Most IDs fit in u128. KSUID needs the wider bytes path.
    if value.bit_length() <= 128:
        return codec.encode_u128(value, width)
    return codec.encode_bytes(value.to_bytes((value.bit_length() + 7) // 8, 'big'), width)

def decode(text: str, alphabet: str, width: int, bits: int) -> int:
    if not isinstance(text, str):
        raise TypeError('identifier must be a string')
    if len(text) != width:
        raise ValueError(f'identifier must contain {width} characters')
    if alphabet == '0123456789abcdef':
        if _HEX.fullmatch(text) is None:
            raise ValueError('identifier contains a character outside its alphabet')
        result = int(text, 16) if text else 0
        if result >= 1 << bits:
            raise ValueError('identifier exceeds its binary width')
        return result
    codec = _radix(alphabet)
    if bits <= 128:
        return codec.decode_u128(text, width, bits)
    return int.from_bytes(codec.decode_bytes(text, width, bits), 'big')

def batch_count(count: int) -> int:
    return integer(count, 'count', 0, 1_000_000)
