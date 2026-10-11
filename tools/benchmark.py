"""Measure all 39 formats using configured generators, codecs and content values.

Run in the development virtual environment with pyperf's -o option to save results.
No optional reference packages are needed. --focus selects benchmark names by regex.
"""

import fuda
from re import search
from pyperf import Runner
from itertools import cycle
from uuid import UUID, NAMESPACE_DNS
from importlib.metadata import version

def forward_options(command, arguments):
    if arguments.focus:
        command.extend(['--focus', arguments.focus])

runner = Runner(add_cmdline_args=forward_options)
runner.argparser.add_argument('--focus', default='')
args = runner.parse_args()
runner.metadata['fuda_version'] = version('fuda')
runner.metadata['result_policy'] = 'final strings; retained generators/codecs; content includes hashing and encoding'
runner.metadata['entropy_policy'] = 'production OS randomness; UUID3/5 repeat their configured deterministic names'

def benchmark(name, function):
    if not args.focus or search(args.focus, name):
        runner.bench_func(name, function)

sources = [
    ('cuid2', fuda.Cuid2Generator()),
    ('flake128', fuda.Flake128Generator(node_id=1)),
    ('hyperid', fuda.HyperIDGenerator()),
    ('ksuid', fuda.KSUIDGenerator()),
    ('nanoid', fuda.NanoIDGenerator()),
    ('nuid', fuda.NUIDGenerator()),
    ('objectid', fuda.ObjectIDGenerator()),
    ('pushid', fuda.PushIDGenerator()),
    ('scru64', fuda.SCRU64Generator(node_id=1)),
    ('scru128', fuda.SCRU128Generator()),
    ('shortuuid', fuda.ShortUUIDGenerator()),
    ('sno', fuda.SNOGenerator(partition=1)),
    ('snowflake', fuda.SnowflakeGenerator(node_id=1)),
    # Leave capacity for tight benchmark loops while retaining at least 32 time bits.
    ('sonyflake', fuda.SonyflakeGenerator(node_id=1, node_bits=8, sequence_bits=20)),
    ('tid', fuda.TIDGenerator()),
    ('timeflake', fuda.TimeflakeGenerator()),
    ('tsid', fuda.TSIDGenerator()),
    ('typeid', fuda.TypeIDGenerator('item')),
    ('ulid', fuda.ULIDGenerator()),
    ('upid', fuda.UPIDGenerator('item')),
    ('uuid1', fuda.UUID1Generator()),
    ('uuid3', fuda.UUID3Generator(NAMESPACE_DNS, 'example.com')),
    ('uuid4', fuda.UUID4Generator()),
    ('uuid5', fuda.UUID5Generator(NAMESPACE_DNS, 'example.com')),
    ('uuid6', fuda.UUID6Generator()),
    ('uuid7', fuda.UUID7Generator()),
    ('uuid8', fuda.UUID8Generator()),
    ('xid', fuda.XIDGenerator()),
    ('xuid', fuda.XUIDGenerator('item')),
]
runner.metadata['sonyflake_layout'] = 'node_bits=8, sequence_bits=20; avoids benchmark sequence exhaustion'
for name, source in sources:
    benchmark(name + '/generate-string', lambda source=source: str(source.generate()))

sqids, hashids = fuda.Sqids(), fuda.Hashids()
numbers = cycle([[i, i + 1, 1000 + i] for i in range(256)])
uuid = UUID('00112233-4455-6677-8899-aabbccddeeff')
benchmark('sqids/encode', lambda: sqids.encode(next(numbers)))
benchmark('hashids/encode', lambda: hashids.encode(next(numbers)))
benchmark('uuid25/encode', lambda: fuda.UUID25.encode(uuid))
benchmark('proquint/encode', lambda: fuda.Proquint.encode(b'\x7f\x00\x00\x01'))

data = b'Fuda content identifier benchmark.' * 32
block = b'\x0a\x05hello'
benchmark('cidv0/content-string', lambda: str(fuda.CIDv0.from_content(block)))
benchmark('cidv1/content-string', lambda: str(fuda.CIDv1.from_content(data)))
benchmark('multihash/content-string', lambda: str(fuda.Multihash.from_content(data)))
benchmark('ni/content-string', lambda: str(fuda.NI.from_content(data)))
benchmark('nih/content-string', lambda: str(fuda.NIH.from_content(data)))
benchmark('swhid/content-string', lambda: str(fuda.SWHID.from_content(data)))
