"""Python codec oracles retained for native differential tests only.

These are the pre-acceleration implementations, already checked against the
upstream vectors. Keeping them here lets us compare algorithms without shipping
a second runtime implementation in the package.
"""
from math import ceil
from json import loads
from binascii import Error
from functools import lru_cache
from collections.abc import Iterable
from importlib.resources import files
from base64 import b32decode, b32encode, b64decode, b64encode
from fuda._core.encoding import integer

HASHIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'

def _hashids_shuffle(text: str, salt: str) -> str:
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

def _parts(text: str, delimiters: str) -> list[str]:
    for char in delimiters:
        text = text.replace(char, '\x00')
    return text.split('\x00')

class ReferenceHashids:
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
        separators = _hashids_shuffle(separators, salt)
        missing = ceil(len(alphabet) / 3.5) - len(separators)
        if missing > 0:
            separators += alphabet[:missing]
            alphabet = alphabet[missing:]
        alphabet = _hashids_shuffle(alphabet, salt)
        count = ceil(len(alphabet) / 12)
        self._guards, self._alphabet = alphabet[:count], alphabet[count:]
        self._separators = separators
        # Runtime shuffles only consume this prefix. Keep the full salt for the
        # constructor's earlier shuffles, which use a larger alphabet.
        self._salt = salt[: len(self._alphabet)]
        self._first_alphabets: dict[str, str] = {}

    def _first_alphabet(self, lottery: str) -> str:
        # There is at most one cached permutation per lottery character.
        cached = self._first_alphabets.get(lottery)
        if cached is None:
            cached = _hashids_shuffle(self._alphabet, (lottery + self._salt + self._alphabet)[: len(self._alphabet)])
            self._first_alphabets[lottery] = cached

        return cached

    def encode(self, numbers: Iterable[int]) -> str:
        values = [integer(value, 'number', 0, (1 << 63) - 1) for value in numbers]
        if not values:
            return ''
        alphabet = self._alphabet
        total = sum(value % (index + 100) for index, value in enumerate(values))
        lottery = alphabet[total % len(alphabet)]
        encoded = lottery
        for index, value in enumerate(values):
            alphabet = (
                self._first_alphabet(lottery)
                if index == 0
                else _hashids_shuffle(alphabet, (lottery + self._salt + alphabet)[: len(alphabet)])
            )
            quotient, digits = value, ''
            while True:
                quotient, remainder = divmod(quotient, len(alphabet))
                digits = alphabet[remainder] + digits
                if not quotient:
                    break
            encoded += digits
            if index + 1 < len(values):
                encoded += self._separators[(value % (ord(digits[0]) + index)) % len(self._separators)]
        if len(encoded) < self._min_length:
            encoded = self._guards[(total + ord(encoded[0])) % len(self._guards)] + encoded
            if len(encoded) < self._min_length:
                encoded += self._guards[(total + ord(encoded[2])) % len(self._guards)]
        while len(encoded) < self._min_length:
            alphabet = _hashids_shuffle(alphabet, alphabet)
            half = len(alphabet) // 2
            encoded = alphabet[half:] + encoded + alphabet[:half]
            excess = len(encoded) - self._min_length
            if excess > 0:
                encoded = encoded[excess // 2 : excess // 2 + self._min_length]
        return encoded

    def decode(self, value: str) -> list[int]:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if not value:
            return []
        parts = _parts(value, self._guards)
        body = parts[1] if len(parts) in (2, 3) else parts[0]
        if not body:
            raise ValueError('invalid Hashids encoding')
        lottery, alphabet = body[0], self._alphabet
        if lottery not in alphabet:
            raise ValueError('invalid Hashids lottery character')
        result = []
        for index, part in enumerate(_parts(body[1:], self._separators)):
            if not part:
                raise ValueError('empty Hashids number')
            alphabet = (
                self._first_alphabet(lottery)
                if index == 0
                else _hashids_shuffle(alphabet, (lottery + self._salt + alphabet)[: len(alphabet)])
            )
            number = 0
            for char in part:
                number = number * len(alphabet) + alphabet.index(char)
                if number >= 1 << 63:
                    raise ValueError('Hashids number exceeds 63 bits')
            result.append(number)
        if self.encode(result) != value:
            raise ValueError('invalid or noncanonical Hashids encoding')
        return result

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


SQIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

@lru_cache(maxsize=1)
def _default_blocklist() -> frozenset[str]:
    return frozenset(loads(files('fuda.codecs').joinpath('sqids-blocklist.json').read_text(encoding='utf-8')))

def _sqids_shuffle(alphabet: str) -> str:
    chars = list(alphabet)
    size = len(chars)
    for index in range(size - 1):
        other = size - 1 - index
        target = (index * other + ord(chars[index]) + ord(chars[other])) % size
        chars[index], chars[target] = chars[target], chars[index]

    return ''.join(chars)

def _encode_number(value: int, alphabet: str) -> str:
    digits = []
    while True:
        value, digit = divmod(value, len(alphabet))
        digits.append(alphabet[digit])
        if not value:
            return ''.join(reversed(digits))

class ReferenceSqids:
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
        self._alphabet = _sqids_shuffle(alphabet)
        self._chars = frozenset(alphabet)
        self._min_length = min_length
        self._exact = frozenset(exact)
        self._ends = tuple(sorted(ends))
        self._anywhere = tuple(sorted(anywhere))

    def encode(self, numbers: Iterable[int]) -> str:
        values = tuple(numbers)
        for value in values:
            integer(value, 'number', 0, (1 << 63) - 1)
        if not values:
            return ''
        size = len(self._alphabet)
        offset = (len(values) + sum(ord(self._alphabet[value % size]) + i for i, value in enumerate(values))) % size
        for increment in range(size + 1):
            start = (offset + increment) % size
            alphabet = self._alphabet[start:] + self._alphabet[:start]
            parts = [alphabet[0]]
            alphabet = alphabet[::-1]
            for index, value in enumerate(values):
                parts.append(_encode_number(value, alphabet[1:]))
                if index < len(values) - 1:
                    parts.append(alphabet[0])
                    alphabet = _sqids_shuffle(alphabet)
            result = ''.join(parts)
            if len(result) < self._min_length:
                result += alphabet[0]
                while len(result) < self._min_length:
                    alphabet = _sqids_shuffle(alphabet)
                    result += alphabet[: self._min_length - len(result)]
            lowered = result.lower()
            blocked = lowered in self._exact or lowered.startswith(self._ends) or lowered.endswith(self._ends)
            if not blocked and not any(word in lowered for word in self._anywhere):
                return result

        raise ValueError('blocklist prevents encoding these numbers with this alphabet')

    def decode(self, value: str, *, canonical: bool = False) -> list[int]:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if not set(value) <= self._chars:
            raise ValueError('identifier contains characters outside the Sqids alphabet')
        if not value:
            return []
        offset = self._alphabet.index(value[0])
        alphabet = (self._alphabet[offset:] + self._alphabet[:offset])[::-1]
        remaining = value[1:]
        numbers = []
        while remaining:
            chunk, separator, remaining = remaining.partition(alphabet[0])
            if not chunk:
                break
            number = 0
            digits = {char: index for index, char in enumerate(alphabet[1:])}
            for char in chunk:
                number = number * (len(alphabet) - 1) + digits[char]
                if number >= 1 << 63:
                    raise ValueError('decoded number exceeds 2**63-1')
            numbers.append(number)
            if separator:
                alphabet = _sqids_shuffle(alphabet)
        if canonical and self.encode(numbers) != value:
            raise ValueError('noncanonical Sqids identifier for this configuration')

        return numbers


_BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_BASE36 = '0123456789abcdefghijklmnopqrstuvwxyz'
BASE_PREFIXES = {
    'base32': 'b',
    'base32upper': 'B',
    'base58btc': 'z',
    'base16': 'f',
    'base16upper': 'F',
    'base36': 'k',
    'base36upper': 'K',
    'base64': 'm',
    'base64pad': 'M',
    'base64url': 'u',
    'base64urlpad': 'U',
}

def _base_encode(data: bytes, alphabet: str) -> str:
    zeros = len(data) - len(data.lstrip(b'\0'))
    number = int.from_bytes(data, 'big')
    digits = []
    while number:
        number, digit = divmod(number, len(alphabet))
        digits.append(alphabet[digit])

    return alphabet[0] * zeros + ''.join(reversed(digits))

def _base_decode(value: str, alphabet: str) -> bytes:
    zeros = len(value) - len(value.lstrip(alphabet[0]))
    number = 0
    for char in value:
        if char not in alphabet:
            raise ValueError('invalid multibase digit')
        number = number * len(alphabet) + alphabet.index(char)

    return b'\0' * zeros + number.to_bytes((number.bit_length() + 7) // 8, 'big')

def multibase_encode(data: bytes, prefix: str) -> str:
    if prefix in ('b', 'B'):
        encoded = b32encode(data).decode('ascii').rstrip('=')
        encoded = encoded.lower() if prefix == 'b' else encoded
    elif prefix in ('f', 'F'):
        encoded = data.hex()
        encoded = encoded.upper() if prefix == 'F' else encoded
    elif prefix in ('z', 'k', 'K'):
        alphabet = _BASE58 if prefix == 'z' else _BASE36
        encoded = _base_encode(data, alphabet)
        encoded = encoded.upper() if prefix == 'K' else encoded
    elif prefix in ('m', 'M', 'u', 'U'):
        encoded = b64encode(data, altchars=b'-_' if prefix in ('u', 'U') else None).decode('ascii')
        if prefix in ('m', 'u'):
            encoded = encoded.rstrip('=')
    else:
        raise ValueError('unsupported multibase encoding')

    return prefix + encoded

def multibase_decode(value: str) -> bytes:
    if not value or not value.isascii():
        raise ValueError('expected an ASCII multibase string')
    prefix, payload = value[0], value[1:]
    try:
        if prefix in ('b', 'B'):
            data = b32decode(payload.upper() + '=' * (-len(payload) % 8))
        elif prefix in ('f', 'F'):
            data = bytes.fromhex(payload)
        elif prefix in ('z', 'k', 'K'):
            data = _base_decode(payload, _BASE58 if prefix == 'z' else _BASE36.upper() if prefix == 'K' else _BASE36)
        elif prefix in ('m', 'M', 'u', 'U'):
            padded = payload + '=' * (-len(payload) % 4) if prefix in ('m', 'u') else payload
            data = b64decode(padded, altchars=b'-_' if prefix in ('u', 'U') else None, validate=True)
        else:
            raise ValueError('unsupported multibase prefix')
    except (Error, ValueError) as error:
        raise ValueError(f'invalid multibase: {error}') from None
    if multibase_encode(data, prefix) != value:
        raise ValueError('noncanonical multibase spelling or padding')

    return data

_CONSONANTS = 'bdfghjklmnprstvz'
_VOWELS = 'aiou'

class ReferenceProquint:
    """Encode bytes as hyphen-separated CVCVC words; no new entropy is added."""

    @staticmethod
    def encode(value: bytes) -> str:
        if not isinstance(value, bytes):
            raise TypeError('value must be bytes')
        if not value or len(value) % 2:
            raise ValueError('Proquint requires a nonempty, even number of bytes')
        words = []
        for offset in range(0, len(value), 2):
            number = (value[offset] << 8) | value[offset + 1]
            words.append(
                _CONSONANTS[number >> 12]
                + _VOWELS[(number >> 10) & 3]
                + _CONSONANTS[(number >> 6) & 15]
                + _VOWELS[(number >> 4) & 3]
                + _CONSONANTS[number & 15]
            )

        return '-'.join(words)

    @staticmethod
    def decode(value: str) -> bytes:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        words = value.split('-')
        decoded = bytearray()
        for word in words:
            if len(word) != 5:
                raise ValueError('each Proquint word must contain five lowercase letters')
            number = 0
            for char, alphabet in zip(word, (_CONSONANTS, _VOWELS, _CONSONANTS, _VOWELS, _CONSONANTS), strict=True):
                if char not in alphabet:
                    raise ValueError('invalid Proquint consonant or vowel')
                number = number * len(alphabet) + alphabet.index(char)
            decoded.extend(number.to_bytes(2, 'big'))

        return bytes(decoded)
