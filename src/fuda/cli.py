from uuid import UUID
from json import dumps
from sys import stderr
from pathlib import Path
from dataclasses import asdict
from argparse import ArgumentParser
from fuda.content.ni import ni, nih
from collections.abc import Callable
from fuda.content.swhid import SWHID
from fuda.codecs.uuid25 import UUID25
from fuda.codecs.proquint import Proquint
from fuda.content.cid import cidv0, cidv1
from fuda.content.multihash import multihash
from fuda.codecs.sqids import Sqids, SQIDS_ALPHABET
from fuda.api import detect, formats, inspect, validate
from fuda.codecs.hashids import Hashids, HASHIDS_ALPHABET
from fuda import Generator, SNOGenerator, TIDGenerator, XIDGenerator, NUIDGenerator, TSIDGenerator, ULIDGenerator, UPIDGenerator, XUIDGenerator, Cuid2Generator, KSUIDGenerator, UUID1Generator, UUID3Generator, UUID4Generator, UUID5Generator, UUID6Generator, UUID7Generator, UUID8Generator, NanoIDGenerator, PushIDGenerator, SCRU64Generator, TypeIDGenerator, HyperIDGenerator, SCRU128Generator, Flake128Generator, ObjectIDGenerator, ShortUUIDGenerator, SnowflakeGenerator, SonyflakeGenerator, TimeflakeGenerator

_GENERATORS: dict[str, Callable[..., Generator[object]]] = {
    'cuid2': Cuid2Generator,
    'flake128': Flake128Generator,
    'hyperid': HyperIDGenerator,
    'ksuid': KSUIDGenerator,
    'nanoid': NanoIDGenerator,
    'nuid': NUIDGenerator,
    'objectid': ObjectIDGenerator,
    'pushid': PushIDGenerator,
    'scru64': SCRU64Generator,
    'scru128': SCRU128Generator,
    'shortuuid': ShortUUIDGenerator,
    'sno': SNOGenerator,
    'snowflake': SnowflakeGenerator,
    'sonyflake': SonyflakeGenerator,
    'tid': TIDGenerator,
    'timeflake': TimeflakeGenerator,
    'tsid': TSIDGenerator,
    'typeid': TypeIDGenerator,
    'ulid': ULIDGenerator,
    'upid': UPIDGenerator,
    'uuid1': UUID1Generator,
    'uuid3': UUID3Generator,
    'uuid4': UUID4Generator,
    'uuid5': UUID5Generator,
    'uuid6': UUID6Generator,
    'uuid7': UUID7Generator,
    'uuid8': UUID8Generator,
    'xid': XIDGenerator,
    'xuid': XUIDGenerator,
}

def main() -> None:
    parser = ArgumentParser(prog='fuda', description='Generate and inspect common identifier formats.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('formats')
    generate = commands.add_parser('generate')
    generate.add_argument('format', choices=tuple(_GENERATORS))
    generate.add_argument('-n', '--count', type=int, default=1)
    generate.add_argument('--length', type=int)
    generate.add_argument('--prefix')
    generate.add_argument('--namespace', type=UUID)
    generate.add_argument('--name')
    generate.add_argument('--node-id', type=int)
    generate.add_argument('--node-bits', type=int)
    generate.add_argument('--clock-id', type=int)
    generate.add_argument('--partition', type=int)
    generate.add_argument('--metadata', type=int)
    generate.add_argument('--url-safe', action='store_true', default=None)
    generate.add_argument('--fixed-length', action='store_true', default=None)
    generate.add_argument('--json', action='store_true')
    for command in ('validate', 'inspect'):
        item = commands.add_parser(command)
        item.add_argument('format')
        item.add_argument('value')
    commands.add_parser('detect').add_argument('value')
    encode = commands.add_parser('encode', help='Encode integers with Sqids, or hex bytes with Proquint')
    encode.add_argument('format', choices=('sqids', 'proquint', 'hashids', 'uuid25'))
    encode.add_argument('values', nargs='+')
    decode = commands.add_parser('decode')
    decode.add_argument('format', choices=('sqids', 'proquint', 'hashids', 'uuid25'))
    decode.add_argument('value')
    for codec in (encode, decode):
        codec.add_argument('--alphabet')
        codec.add_argument('--salt')
        codec.add_argument('--min-length', type=int)
        codec.add_argument('--no-blocklist', action='store_true', default=None)
    for command in ('cidv1', 'content'):
        content = commands.add_parser(command, help='Hash content or a serialized object body')
        if command == 'content':
            content.add_argument('format', choices=[item.name for item in formats() if item.kind == 'content'])
        source = content.add_mutually_exclusive_group(required=True)
        source.add_argument('--text', help='UTF-8 text')
        source.add_argument('--file', type=Path)
        content.add_argument('--codec')
        content.add_argument('--hash')
        content.add_argument('--base')
        content.add_argument('--object-type', choices=('cnt', 'dir', 'rev', 'rel', 'snp'))
        content.add_argument('--authority')
        content.add_argument('--query')
    args = parser.parse_args()
    try:
        if args.command == 'formats':
            print(dumps([asdict(item) for item in formats()], indent=2))
        elif args.command == 'validate':
            valid = validate(args.format, args.value)
            print('true' if valid else 'false')
            if not valid:
                raise SystemExit(1)
        elif args.command == 'inspect':
            print(dumps(inspect(args.format, args.value), indent=2))
        elif args.command == 'detect':
            print(dumps(detect(args.value)))
        elif args.command in ('cidv1', 'content'):
            name = 'cidv1' if args.command == 'cidv1' else args.format
            supported = {
                'cidv1': {'codec', 'hash', 'base'},
                'cidv0': set(),
                'multihash': {'hash', 'base'},
                'ni': {'hash', 'authority', 'query'},
                'nih': {'hash'},
                'swhid': {'object_type'},
            }
            for key in ('codec', 'hash', 'base', 'object_type', 'authority', 'query'):
                if getattr(args, key) is not None and key not in supported[name]:
                    raise ValueError(f'--{key.replace("_", "-")} is not supported for {name}')
            data = args.text.encode('utf-8') if args.text is not None else args.file.read_bytes()
            if name == 'cidv1':
                print(
                    cidv1(
                        data,
                        codec=args.codec if args.codec is not None else 'raw',
                        hash_name=args.hash if args.hash is not None else 'sha2-256',
                    ).to_base(args.base if args.base is not None else 'base32')
                )
            elif name == 'cidv0':
                print(cidv0(data))
            elif name == 'multihash':
                print(
                    multihash(data, hash_name=args.hash if args.hash is not None else 'sha2-256').to_base(
                        args.base if args.base is not None else 'base58btc'
                    )
                )
            elif name == 'ni':
                print(
                    ni(
                        data,
                        algorithm=args.hash if args.hash is not None else 'sha-256',
                        authority=args.authority or '',
                        query=args.query or '',
                    )
                )
            elif name == 'nih':
                print(nih(data, algorithm=args.hash if args.hash is not None else 'sha-256'))
            else:
                print(SWHID.from_object(data, object_type=args.object_type if args.object_type is not None else 'cnt'))
        elif args.command in ('encode', 'decode'):
            allowed = {
                'sqids': {'alphabet', 'min_length', 'no_blocklist'},
                'hashids': {'alphabet', 'salt', 'min_length'},
                'proquint': set(),
                'uuid25': set(),
            }
            for key in ('alphabet', 'salt', 'min_length', 'no_blocklist'):
                if getattr(args, key) is not None and key not in allowed[args.format]:
                    raise ValueError(f'--{key.replace("_", "-")} is not supported for {args.format}')
            if args.format == 'uuid25':
                if args.command == 'decode':
                    print(UUID25.decode(args.value))
                else:
                    if len(args.values) != 1:
                        raise ValueError('UUID25 encoding accepts one UUID')
                    print(UUID25.encode(UUID(args.values[0])))
            elif args.format == 'hashids':
                hashids = Hashids(
                    salt=args.salt if args.salt is not None else '',
                    min_length=args.min_length if args.min_length is not None else 0,
                    alphabet=args.alphabet if args.alphabet is not None else HASHIDS_ALPHABET,
                )
                if args.command == 'encode':
                    print(hashids.encode(int(value) for value in args.values))
                else:
                    print(dumps(hashids.decode(args.value)))
            elif args.format == 'sqids':
                sqids = Sqids(
                    alphabet=args.alphabet if args.alphabet is not None else SQIDS_ALPHABET,
                    min_length=args.min_length if args.min_length is not None else 0,
                    blocklist=() if args.no_blocklist else None,
                )
                if args.command == 'encode':
                    print(sqids.encode(int(value) for value in args.values))
                else:
                    print(dumps(sqids.decode(args.value)))
            elif args.command == 'decode':
                print(Proquint.decode(args.value).hex())
            else:
                if len(args.values) != 1:
                    raise ValueError('Proquint encoding accepts one hex string')
                print(Proquint.encode(bytes.fromhex(args.values[0])))
        else:
            options = {}
            if args.length is not None:
                options['length'] = args.length
            if args.prefix is not None:
                options['prefix'] = args.prefix
            if args.namespace is not None:
                options['namespace'] = args.namespace
            if args.name is not None:
                options['name'] = args.name
            if args.node_id is not None:
                options['node_id'] = args.node_id
            if args.node_bits is not None:
                options['node_bits'] = args.node_bits
            if args.clock_id is not None:
                options['clock_id'] = args.clock_id
            for key in ('partition', 'metadata', 'url_safe', 'fixed_length'):
                value = getattr(args, key)
                if value is not None:
                    options[key] = value
            values = _GENERATORS[args.format](**options).iter_ids(args.count)
            if args.json:
                if args.count > 1_000_000:
                    raise ValueError('JSON output is limited to 1000000 IDs; use line output')
                print(dumps([str(value) for value in values]))
            else:
                for value in values:
                    print(value)
    except (ValueError, TypeError, OverflowError, RuntimeError, OSError) as error:
        print(f'fuda: {error}', file=stderr)
        raise SystemExit(2) from None
