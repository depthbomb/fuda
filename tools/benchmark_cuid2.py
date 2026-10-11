"""Run with pyperf options, including -o PATH, to save reproducible raw samples.

Benchmark dependencies (idika, anyid) are intentionally optional. Install them
in the development virtual environment. Batches return ordinary list[str].
"""

from re import search
from cuid2 import Cuid
from sys import modules
from pathlib import Path
from pyperf import Runner
from types import ModuleType
from fuda import Cuid2Generator
from idika import with_cuid, n_with_cuid
from importlib.metadata import version, distribution
from importlib.util import module_from_spec, spec_from_file_location

def anyid_generator() -> type:
    # anyid's package root crashes on Windows through XID's os.uname call.
    # Load its unchanged CUID2 subpackage only and label that restriction.
    path = Path(distribution('anyid').locate_file('anyid'))
    package = ModuleType('_benchmark_anyid')
    package.__path__ = [str(path)]
    modules[package.__name__] = package
    spec = spec_from_file_location('_benchmark_anyid.cuid2', path / 'cuid2/__init__.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('cannot load anyid CUID2')
    module = module_from_spec(spec)
    modules[spec.name] = module
    spec.loader.exec_module(module)

    return module.Cuid2Generator

def forward_options(command, arguments):
    if arguments.focus:
        command.extend(['--focus', arguments.focus])

runner = Runner(add_cmdline_args=forward_options)
runner.argparser.add_argument('--focus', default='', help='Only benchmark names matching this regular expression')
arguments = runner.parse_args()

def benchmark(name, function, *, inner_loops=1):
    if not arguments.focus or search(arguments.focus, name):
        runner.bench_func(name, function, inner_loops=inner_loops)

runner.metadata['fuda_version'] = version('fuda')
runner.metadata['cuid2_version'] = version('cuid2')
runner.metadata['idika_version'] = version('idika')
runner.metadata['anyid_version'] = version('anyid')
runner.metadata['anyid_scope'] = 'unchanged CUID2 subpackage only; package root fails on Windows'
runner.metadata['entropy_policy'] = 'default secure production generators; no seeded RNGs'
AnyidGenerator = anyid_generator()
for length in (10, 24, 32):
    native = Cuid2Generator(length)
    parallel = Cuid2Generator(length)
    original = Cuid(length=length)
    anyid = AnyidGenerator(length=length)
    benchmark(f'cuid2/{length}', original.generate)
    benchmark(f'anyid/{length}', anyid.generate)
    benchmark(f'idika/{length}', lambda length=length: with_cuid(length).result)
    benchmark(f'fuda-native/{length}', native.generate)
    for count in (100, 1000):
        benchmark(
            f'idika/{length}/batch-{count}',
            lambda count=count, length=length: [value.result for value in n_with_cuid(count, length).result],
            inner_loops=count,
        )
        benchmark(
            f'fuda-serial/{length}/batch-{count}',
            lambda native=native, count=count: native.generate_many(count),
            inner_loops=count,
        )
        benchmark(
            f'fuda-parallel/{length}/batch-{count}',
            lambda parallel=parallel, count=count: parallel.generate_many(count, parallel=True),
            inner_loops=count,
        )
