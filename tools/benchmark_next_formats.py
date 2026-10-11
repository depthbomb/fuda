"""Benchmarks for the next format group, including final string conversion.

Optional reference dependencies: upid==0.3.1, uuid25==0.1.4, hashids==1.3.1,
multiformats==0.3.1.post4. Use pyperf's -o PATH to keep raw samples.
"""

from re import search
from uuid import UUID
from pyperf import Runner
from importlib.metadata import version
from upid import upid as reference_upid
from uuid25 import Uuid25 as ReferenceUUID25
from hashids import Hashids as ReferenceHashids
from multiformats import CID as ReferenceCID, multihash as reference_multihash
from fuda import ni, cidv0, swhid, UUID25, Hashids, SNOGenerator, UPIDGenerator, HyperIDGenerator, Flake128Generator

def forward_options(command, arguments):
    if arguments.focus:
        command.extend(['--focus', arguments.focus])

runner = Runner(add_cmdline_args=forward_options)
runner.argparser.add_argument('--focus', default='', help='Only run benchmark names matching this regular expression')
arguments = runner.parse_args()

def benchmark(name, function):
    if not arguments.focus or search(arguments.focus, name):
        runner.bench_func(name, function)

runner.metadata['result_policy'] = 'final strings, including encoding; reusable generators and codecs'
runner.metadata['entropy_policy'] = 'production default randomness and clocks'
for package in ('fuda', 'upid', 'uuid25', 'hashids', 'multiformats'):
    runner.metadata[package + '_version'] = version(package)
upid = UPIDGenerator('user')
hyperid = HyperIDGenerator()
sno = SNOGenerator(1)
flake = Flake128Generator(1)
hashids = Hashids(salt='benchmark')
reference_hashids = ReferenceHashids(salt='benchmark')
uuid = UUID('00112233-4455-4677-8899-aabbccddeeff')
content = b'Fuda content identifier benchmark.' * 32
benchmark('upid/fuda/string', lambda: str(upid.generate()))
benchmark('upid/reference/string', lambda: str(reference_upid('user')))
benchmark('uuid25/fuda/encode', lambda: UUID25.encode(uuid))
benchmark('uuid25/reference/encode', lambda: str(ReferenceUUID25.from_uuid(uuid)))
benchmark('hashids/fuda/three-integers', lambda: hashids.encode([1, 2, 3]))
benchmark('hashids/reference/three-integers', lambda: reference_hashids.encode(1, 2, 3))
benchmark('cidv0/fuda/sha256-base58', lambda: str(cidv0(content)))
benchmark(
    'cidv0/reference/sha256-base58',
    lambda: str(ReferenceCID('base58btc', 0, 'dag-pb', reference_multihash.digest(content, 'sha2-256'))),
)
benchmark('hyperid/fuda/string', hyperid.generate)
benchmark('sno/fuda/string', lambda: str(sno.generate()))
benchmark('flake128/fuda/string', lambda: str(flake.generate()))
benchmark('ni/fuda/sha256', lambda: str(ni(content)))
benchmark('swhid/fuda/content', lambda: str(swhid(content)))
