"""Fuda: generation, parsing and inspection for common identifier formats."""

from fuda.api import upid, hyperid
from fuda.codecs.sqids import Sqids
from fuda.codecs.uuid25 import UUID25
from fuda._core.state import Generator
from fuda.codecs.hashids import Hashids
from fuda.codecs.proquint import Proquint
from fuda.content.cid import CIDv0, cidv0
from fuda.content.cid import CIDv1, cidv1
from fuda.content.ni import NI, ni, NIH, nih
from fuda.identifiers.nuid import NUIDGenerator
from fuda.identifiers.sno import SNO, SNOGenerator
from fuda.identifiers.upid import UPID, UPIDGenerator
from fuda.content.multihash import Multihash, multihash
from fuda.identifiers.random_ids import NanoIDGenerator
from fuda.identifiers.sonyflake import SonyflakeGenerator
from fuda.api import tid, nuid, pushid, scru128, timeflake
from fuda.identifiers.cuid import is_cuid2, Cuid2Generator
from fuda.content.swhid import SWHID, swhid, DirectoryEntry
from fuda.identifiers.hyper import HyperID, HyperIDGenerator
from fuda.identifiers.flake import Flake128, Flake128Generator
from fuda.identifiers.scru import SCRU64Generator, SCRU128Generator
from fuda.identifiers.types import XID, TSID, ULID, KSUID, ObjectID
from fuda.identifiers.extended_types import TID, PushID, SCRU64, SCRU128, Timeflake
from fuda.identifiers.ordered import TIDGenerator, PushIDGenerator, TimeflakeGenerator
from fuda.api import xid, tsid, ulid, cuid2, parse, detect, formats, inspect, objectid, validate
from fuda.identifiers.prefixed import XUID, xuid, TypeID, typeid, XUIDGenerator, TypeIDGenerator
from fuda.identifiers.stateful import XIDGenerator, TSIDGenerator, ObjectIDGenerator, SnowflakeGenerator
from fuda.identifiers.random_ids import ksuid, nanoid, shortuuid, ULIDGenerator, KSUIDGenerator, decode_shortuuid, ShortUUIDGenerator
from fuda.identifiers.uuids import uuid1, uuid3, uuid4, uuid5, uuid6, uuid7, uuid8, UUID1Generator, UUID3Generator, UUID4Generator, UUID5Generator, UUID6Generator, UUID7Generator, UUID8Generator

__version__ = '0.1.0'
__all__ = [
    'UUID1Generator',
    'UUID3Generator',
    'UUID4Generator',
    'UUID5Generator',
    'UUID6Generator',
    'UUID8Generator',
    'KSUIDGenerator',
    'ShortUUIDGenerator',
    'TypeIDGenerator',
    'XUIDGenerator',
    'NanoIDGenerator',
    'NI',
    'NIH',
    'ni',
    'nih',
    'CIDv0',
    'cidv0',
    'Hashids',
    'UUID25',
    'UPID',
    'UPIDGenerator',
    'SNO',
    'SNOGenerator',
    'HyperID',
    'HyperIDGenerator',
    'Flake128',
    'Flake128Generator',
    'Multihash',
    'multihash',
    'SWHID',
    'DirectoryEntry',
    'swhid',
    'upid',
    'hyperid',
    'TID',
    'PushID',
    'SCRU64',
    'SCRU128',
    'Timeflake',
    'CIDv1',
    'Sqids',
    'Proquint',
    'TIDGenerator',
    'NUIDGenerator',
    'PushIDGenerator',
    'SCRU64Generator',
    'SCRU128Generator',
    'TimeflakeGenerator',
    'SonyflakeGenerator',
    'cidv1',
    'tid',
    'nuid',
    'pushid',
    'scru128',
    'timeflake',
    'Generator',
    'Cuid2Generator',
    'ULIDGenerator',
    'UUID7Generator',
    'ObjectIDGenerator',
    'XIDGenerator',
    'TSIDGenerator',
    'SnowflakeGenerator',
    'ULID',
    'KSUID',
    'XID',
    'TSID',
    'ObjectID',
    'TypeID',
    'XUID',
    'cuid2',
    'is_cuid2',
    'ulid',
    'xid',
    'objectid',
    'tsid',
    'nanoid',
    'ksuid',
    'shortuuid',
    'decode_shortuuid',
    'uuid1',
    'uuid3',
    'uuid4',
    'uuid5',
    'uuid6',
    'uuid7',
    'uuid8',
    'typeid',
    'xuid',
    'formats',
    'parse',
    'validate',
    'inspect',
    'detect',
]
