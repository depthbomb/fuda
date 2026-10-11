"""Repeatable audit benchmarks: final values, OS entropy, and retained state."""

from re import search
from pyperf import Runner
from itertools import cycle
from fuda import cidv1, parse, nanoid, multihash, UUID7Generator, NanoIDGenerator
from fuda import XID, ULID, UPID, SWHID, UUID25, Hashids, SCRU128, ObjectID, Timeflake, Cuid2Generator

def forward_options(command, arguments):
    if arguments.focus:
        command.extend(['--focus', arguments.focus])

runner = Runner(add_cmdline_args=forward_options)
runner.argparser.add_argument('--focus', default='')
args = runner.parse_args()
runner.metadata['scope'] = 'final strings, parsers, production generators, rotating codec inputs and snapshot aliases'

def benchmark(name, function, *, inner_loops=1):
    if not args.focus or search(args.focus, name):
        runner.bench_func(name, function, inner_loops=inner_loops)

number = 0x01933455778899AABBCCDDEEFF112233
for cls in (ULID, XID, UUID25, ObjectID, UPID, SCRU128, Timeflake):
    value = cls(number % 2**cls._bits)
    text = str(value)
    benchmark(f'encode/{cls.__name__}', lambda value=value: str(value))
    benchmark(f'parse/{cls.__name__}', lambda cls=cls, text=text: cls.from_str(text))

codec = Hashids(salt='benchmark')
numbers = cycle([[i, i + 1, 1000 + i] for i in range(256)])
benchmark('hashids/rotating-three', lambda: codec.encode(next(numbers)))
benchmark('nanoid/default', nanoid)
benchmark('nanoid/unicode', lambda: nanoid(alphabet='abcdefαβγδ🙂🚀'))
nanoid_source = NanoIDGenerator()
benchmark('nanoid/batch100', lambda: nanoid_source.generate_many(100), inner_loops=100)
parallel_cuids = Cuid2Generator()
benchmark('cuid2/batch1000', lambda: parallel_cuids.generate_many(1000, parallel=True), inner_loops=1000)
uuid7 = UUID7Generator()
benchmark('uuid7/string', lambda: str(uuid7.generate()))
source = Cuid2Generator()
benchmark('cuid2/scalar', source.generate)
for count in (10, 100, 1000):
    branches = {str(i).encode(): str(i + 1).encode() for i in range(count)}
    branches[str(count).encode()] = None
    benchmark(f'swhid/alias-chain{count}', lambda branches=branches: SWHID.from_snapshot(branches))
content = b'Fuda performance and correctness audit.' * 32
cid = cidv1(content)
mh = multihash(content)
benchmark('cidv1/parse', lambda: parse('cidv1', str(cid)))
benchmark('multihash/parse', lambda: parse('multihash', str(mh)))
