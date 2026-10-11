from uuid import UUID
from typing import Any
from typing import Literal
from functools import lru_cache
from dataclasses import dataclass
from fuda.content.ni import NI, NIH
from fuda.content.swhid import SWHID
from fuda.identifiers.sno import SNO
from fuda.codecs.uuid25 import UUID25
from fuda._core.encoding import BASE62
from fuda._core.encoding import integer
from fuda.codecs.proquint import Proquint
from fuda.content.cid import CIDv0, CIDv1
from fuda.codecs.sqids import default_sqids
from fuda.identifiers.flake import Flake128
from fuda.content.multihash import Multihash
from fuda.codecs.hashids import default_hashids
from fuda.identifiers.nuid import NUIDGenerator
from fuda.identifiers.prefixed import XUID, TypeID
from fuda.identifiers.scru import SCRU128Generator
from fuda.identifiers.upid import UPID, UPIDGenerator
from fuda.identifiers.random_ids import _nanoid_layout
from fuda.identifiers.cuid import is_cuid2, Cuid2Generator
from fuda.identifiers.hyper import HyperID, HyperIDGenerator
from fuda.identifiers.types import XID, TSID, ULID, KSUID, BinaryID, ObjectID
from fuda.identifiers.extended_types import TID, PushID, SCRU64, SCRU128, Timeflake
from fuda.identifiers.stateful import XIDGenerator, TSIDGenerator, ObjectIDGenerator
from fuda.identifiers.ordered import TIDGenerator, PushIDGenerator, TimeflakeGenerator
from fuda.identifiers.random_ids import shortuuid, ULIDGenerator, NANOID_ALPHABET, decode_shortuuid

type Identifier = str | int | UUID | BinaryID | TypeID | XUID | CIDv0 | CIDv1 | Multihash | NI | NIH | SWHID | HyperID

@dataclass(frozen=True, slots=True)
class FormatInfo:
    name: str
    timestamp: bool
    description: str
    kind: Literal['generator', 'codec', 'content'] = 'generator'

_FORMATS = (
    FormatInfo('cuid2', False, 'Opaque letter-led base36 string; default 24 characters'),
    *(FormatInfo(f'uuid{v}', v in (1, 6, 7), f'RFC 9562 UUID version {v}') for v in (1, 3, 4, 5, 6, 7, 8)),
    FormatInfo('ulid', True, '128 bits, millisecond time and 80 random bits'),
    FormatInfo('nanoid', False, 'Custom alphabet; default 21 URL-safe characters'),
    FormatInfo('typeid', True, 'Typed prefix and a UUID, UUIDv7 by default'),
    FormatInfo('xuid', True, 'KarpelesLab grouped base32 UUID with optional prefix'),
    FormatInfo('ksuid', True, '160 bits, seconds since May 2014 and 128 random bits'),
    FormatInfo('snowflake', True, 'Configurable 63-bit timestamp/node/sequence layout'),
    FormatInfo('shortuuid', False, 'Fixed 22-character base57 UUID codec'),
    FormatInfo('xid', True, '96 bits: seconds, machine, process and counter'),
    FormatInfo('objectid', True, 'MongoDB 12-byte ObjectID'),
    FormatInfo('tsid', True, '64 bits: milliseconds since 2020, node and counter'),
    FormatInfo('sonyflake', True, 'Configurable 63-bit Sonyflake v2 time/sequence/node layout'),
    FormatInfo('pushid', True, 'Firebase 120-bit push key: milliseconds and 72 random bits'),
    FormatInfo('scru128', True, '128 bits: milliseconds, two 24-bit counters and 32 random bits'),
    FormatInfo('timeflake', True, '128 bits: milliseconds and 80 random bits, encoded in base62'),
    FormatInfo('nuid', False, 'NATS 22-character base62 prefix and incrementing sequence'),
    FormatInfo('scru64', True, '12 base36 characters: 256 ms ticks, assigned node and counter'),
    FormatInfo('tid', True, 'AT Protocol 63-bit microsecond timestamp and clock ID'),
    FormatInfo('sqids', False, 'Reversible integer sequences; default configuration for parsing', 'codec'),
    FormatInfo('proquint', False, 'Pronounceable encoding of 16-bit words', 'codec'),
    FormatInfo('upid', True, '128 bits: 256 ms time, random data, prefix and version'),
    FormatInfo('sno', True, '80 bits: 4 ms ticks, rollback toggle, metadata, partition and sequence'),
    FormatInfo('hyperid', False, 'UUIDv4 prefix with a decimal counter'),
    FormatInfo('flake128', True, 'Boundary Flake: milliseconds, 48-bit node and 16-bit sequence'),
    FormatInfo('uuid25', False, '25-character base36 UUID encoding', 'codec'),
    FormatInfo('hashids', False, 'Reversible integer sequences; default configuration for parsing', 'codec'),
    FormatInfo('cidv0', False, 'DAG-PB block with a SHA-256 multihash', 'content'),
    FormatInfo('multihash', False, 'Self-describing digest, with multibase-prefixed text', 'content'),
    FormatInfo('ni', False, 'RFC 6920 named information URI', 'content'),
    FormatInfo('nih', False, 'RFC 6920 human-readable name and check digit', 'content'),
    FormatInfo('swhid', False, 'Software Heritage core and qualified object identifiers', 'content'),
    FormatInfo('cidv1', False, 'Content identifier: multicodec and multihash', 'content'),
)
_NAMES = frozenset(item.name for item in _FORMATS)
_BINARY_TYPES: dict[str, type[BinaryID]] = {
    'upid': UPID,
    'sno': SNO,
    'flake128': Flake128,
    'uuid25': UUID25,
    'ulid': ULID,
    'ksuid': KSUID,
    'xid': XID,
    'objectid': ObjectID,
    'tsid': TSID,
    'pushid': PushID,
    'scru128': SCRU128,
    'scru64': SCRU64,
    'timeflake': Timeflake,
    'tid': TID,
}
_ulids = ULIDGenerator()
_xids = XIDGenerator()
_objects = ObjectIDGenerator()
_tsids = TSIDGenerator()
_pushids = PushIDGenerator()
_scru128s = SCRU128Generator()
_timeflakes = TimeflakeGenerator()
_nuids = NUIDGenerator()
_tids = TIDGenerator()

@lru_cache(maxsize=128)
def _upids(prefix: str) -> UPIDGenerator:
    return UPIDGenerator(prefix)

@lru_cache(maxsize=4)
def _hyperids(url_safe: bool, fixed_length: bool) -> HyperIDGenerator:
    return HyperIDGenerator(url_safe=url_safe, fixed_length=fixed_length)

def upid(prefix: str = 'item') -> UPID:
    return _upids(prefix).generate()

def hyperid(*, url_safe: bool = False, fixed_length: bool = False) -> str:
    if not isinstance(url_safe, bool) or not isinstance(fixed_length, bool):
        raise TypeError('url_safe and fixed_length must be booleans')
    return _hyperids(url_safe, fixed_length).generate()

@lru_cache(maxsize=31)
def _cuids(length: int) -> Cuid2Generator:
    return Cuid2Generator(length)

def _format(name: str) -> str:
    if name not in _NAMES:
        raise ValueError(f'unknown format {name!r}; choose from {", ".join(sorted(_NAMES))}')

    return name

def formats() -> tuple[FormatInfo, ...]:
    return _FORMATS

def cuid2(length: int = 24) -> str:
    integer(length, 'length', 2, 32)

    return _cuids(length).generate()

def ulid() -> ULID:
    return _ulids.generate()

def xid() -> XID:
    return _xids.generate()

def objectid() -> ObjectID:
    return _objects.generate()

def tsid() -> TSID:
    return _tsids.generate()

def pushid() -> PushID:
    return _pushids.generate()

def scru128() -> SCRU128:
    return _scru128s.generate()

def timeflake() -> Timeflake:
    return _timeflakes.generate()

def nuid() -> str:
    return _nuids.generate()

def tid() -> TID:
    return _tids.generate()

def parse(format: str, value: str, *, alphabet: str = NANOID_ALPHABET) -> Identifier:
    name = _format(format)
    if not isinstance(value, str):
        raise TypeError('identifier must be a string')
    if name.startswith('uuid') and name != 'uuid25':
        result = UUID(value)
        if result.version != int(name[-1]):
            raise ValueError(f'expected {name}')
        return result
    if name == 'shortuuid':
        return decode_shortuuid(value)
    if name == 'typeid':
        return TypeID.from_str(value)
    if name == 'xuid':
        return XUID.from_str(value)
    if name in _BINARY_TYPES:
        return _BINARY_TYPES[name].from_str(value)
    if name in ('snowflake', 'sonyflake'):
        if not value.isascii() or not value.isdecimal():
            raise ValueError(f'{name} must be an unsigned decimal integer')
        return integer(int(value), 'value', 0, (1 << 63) - 1)
    if name == 'hyperid':
        return HyperID.from_str(value)
    if name == 'cidv0':
        return CIDv0.from_str(value)
    if name == 'multihash':
        return Multihash.from_str(value)
    if name == 'ni':
        return NI.from_str(value)
    if name == 'nih':
        return NIH.from_str(value)
    if name == 'swhid':
        return SWHID.from_str(value)
    if name == 'hashids' and value:
        default_hashids().decode(value)
        return value
    if name == 'cidv1':
        return CIDv1.from_str(value)
    if name == 'proquint':
        Proquint.decode(value)
        return value
    if name == 'sqids' and value:
        default_sqids().decode(value, canonical=True)
        return value
    if name == 'nuid' and len(value) == 22 and all(char in BASE62 for char in value):
        return value
    if name == 'cuid2' and is_cuid2(value):
        return value
    if name == 'nanoid':
        _nanoid_layout(alphabet)
        if value and all(character in alphabet for character in value):
            return value

    raise ValueError(f'invalid {name} identifier')

def validate(format: str, value: object, *, alphabet: str = NANOID_ALPHABET) -> bool:
    _format(format)
    if not isinstance(value, str):
        return False
    try:
        parse(format, value, alphabet=alphabet)
    except (ValueError, TypeError):
        return False

    return True

def detect(value: str) -> tuple[str, ...]:
    """Return all matching shapes. Identifiers do not carry reliable format tags."""
    return tuple(name for name in sorted(_NAMES) if validate(name, value))

def inspect(format: str, value: str) -> dict[str, Any]:
    parsed = parse(format, value)
    result: dict[str, Any] = {'format': format, 'canonical': str(parsed)}
    if format == 'shortuuid' and isinstance(parsed, UUID):
        result['canonical'] = shortuuid(parsed)
    if isinstance(parsed, BinaryID):
        result.update(integer=int(parsed), hex=parsed.bytes.hex())
        if isinstance(
            parsed, (ULID, KSUID, XID, ObjectID, TSID, PushID, SCRU128, SCRU64, Timeflake, TID, UPID, SNO, Flake128)
        ):
            result['timestamp_ms'] = parsed.timestamp_ms
        if isinstance(parsed, TID):
            result.update(timestamp_us=parsed.timestamp_us, clock_id=parsed.clock_id)
        if isinstance(parsed, SCRU128):
            result.update(counter_hi=parsed.counter_hi, counter_lo=parsed.counter_lo, entropy=parsed.entropy)
    if isinstance(parsed, UPID):
        result.update(prefix=parsed.prefix, version=parsed.version, randomness=parsed.randomness)
    if isinstance(parsed, SNO):
        result.update(
            partition=parsed.partition, metadata=parsed.metadata, sequence=parsed.sequence, tick_tock=parsed.tick_tock
        )
    if isinstance(parsed, Flake128):
        result.update(node_id=parsed.node_id, sequence=parsed.sequence, base62=parsed.to_base62())
    if isinstance(parsed, UUID25):
        result['uuid'] = str(parsed.to_uuid())
    if isinstance(parsed, HyperID):
        result.update(
            uuid=str(parsed.uuid), counter=parsed.counter, url_safe=parsed.url_safe, fixed_length=parsed.fixed_length
        )
    if isinstance(parsed, CIDv0):
        result.update(
            version=0,
            codec=0x70,
            codec_name='dag-pb',
            hash_code=0x12,
            hash_name='sha2-256',
            digest=parsed.digest.hex(),
            hex=parsed.bytes.hex(),
        )
    if isinstance(parsed, Multihash):
        result.update(
            hash_code=parsed.hash_code, hash_name=parsed.hash_name, digest=parsed.digest.hex(), hex=parsed.bytes.hex()
        )
    if isinstance(parsed, (NI, NIH)):
        result.update(algorithm=parsed.algorithm, digest=parsed.digest.hex())
        if isinstance(parsed, NI):
            result.update(authority=parsed.authority, query=parsed.query)
    if isinstance(parsed, SWHID):
        result.update(
            object_type=parsed.object_type,
            digest=parsed.digest.hex(),
            core=str(parsed.core),
            origin=parsed.origin,
            visit=str(parsed.visit) if parsed.visit else None,
            anchor=str(parsed.anchor) if parsed.anchor else None,
            path_hex=parsed.path.hex() if parsed.path is not None else None,
            lines=parsed.lines,
        )
    if format == 'hashids':
        result['numbers'] = default_hashids().decode(value)
    if isinstance(parsed, CIDv1):
        result.update(
            version=1,
            codec=parsed.codec,
            codec_name=parsed.codec_name,
            hash_code=parsed.hash_code,
            hash_name=parsed.hash_name,
            digest=parsed.digest.hex(),
            hex=parsed.bytes.hex(),
        )
    if isinstance(parsed, int):
        result['integer'] = parsed
    if format == 'sqids':
        result['numbers'] = default_sqids().decode(value)
    if format == 'proquint':
        decoded = Proquint.decode(value)
        result.update(hex=decoded.hex(), integer=int.from_bytes(decoded, 'big'), bits=len(decoded) * 8)
    if isinstance(parsed, (TypeID, XUID)):
        result.update(prefix=parsed.prefix, uuid=str(parsed.uuid))
        parsed = parsed.uuid
    if isinstance(parsed, UUID):
        result.update(uuid_version=parsed.version, hex=parsed.hex, integer=parsed.int)
        if parsed.version == 7:
            result['timestamp_ms'] = parsed.int >> 80
        elif parsed.version in (1, 6):
            ticks = parsed.time if parsed.version == 1 else ((parsed.int >> 80) << 12) | ((parsed.int >> 64) & 0xFFF)
            result['timestamp_ms'] = (ticks - 0x01B21DD213814000) // 10_000

    return result
