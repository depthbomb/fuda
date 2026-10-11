from fuda._core.encoding import integer
from fuda._core.extension import native

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

def varint(value: int) -> bytes:
    integer(value, 'varint', 0, (1 << 63) - 1)
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)

    return bytes(output)

def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    number = 0
    for index in range(9):
        if offset >= len(data):
            raise ValueError('truncated multiformats varint')
        byte = data[offset]
        offset += 1
        number |= (byte & 127) << (index * 7)
        if byte < 128:
            if index and byte == 0:
                raise ValueError('nonminimal multiformats varint')
            return number, offset

    raise ValueError('multiformats varint exceeds 63 bits')

def multibase_encode(data: bytes, prefix: str) -> str:
    return native.multibase_encode(data, prefix)

def multibase_decode(value: str) -> bytes:
    return native.multibase_decode(value)
