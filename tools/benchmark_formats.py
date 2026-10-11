"""Compare final encoded strings with independent reference implementations.

Optional benchmark dependencies: sqids, timeflake, scru128 and multiformats.
Run in the project virtual environment with pyperf's -o option to save samples.
"""

from pyperf import Runner
from importlib.metadata import version
from sqids import Sqids as ReferenceSqids
from timeflake import random as reference_timeflake
from multiformats import multihash, CID as ReferenceCID
from scru128 import Scru128Generator as ReferenceSCRU128
from fuda import Sqids, cidv1, SCRU128Generator, TimeflakeGenerator

runner = Runner()
for name in ('fuda', 'sqids', 'timeflake', 'scru128', 'multiformats'):
    runner.metadata[name + '_version'] = version(name)
runner.metadata['result_policy'] = 'final strings, including encoding; retained generator or codec state'
runner.metadata['entropy_policy'] = 'production default randomness and system clocks'
sqids = Sqids()
reference_sqids = ReferenceSqids()
scru128 = SCRU128Generator()
reference_scru128 = ReferenceSCRU128()
timeflake = TimeflakeGenerator()
content = b'Fuda content identifier benchmark.' * 32
runner.bench_func('sqids/fuda/three-integers', lambda: sqids.encode([1, 2, 3]))
runner.bench_func('sqids/reference/three-integers', lambda: reference_sqids.encode([1, 2, 3]))
runner.bench_func('timeflake/fuda/string', lambda: str(timeflake.generate()))
runner.bench_func('timeflake/reference/string', lambda: str(reference_timeflake()))
runner.bench_func('scru128/fuda/string', lambda: str(scru128.generate()))
runner.bench_func('scru128/reference/string', lambda: str(reference_scru128.generate()))
runner.bench_func('cidv1/fuda/sha256-base32', lambda: str(cidv1(content)))
runner.bench_func(
    'cidv1/reference/sha256-base32',
    lambda: str(ReferenceCID('base32', 1, 'raw', multihash.digest(content, 'sha2-256'))),
)
