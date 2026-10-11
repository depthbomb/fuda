"""Compare batch operations with repeated single calls using the same inputs."""

import fuda
from re import search
from uuid import UUID
from pyperf import Runner

def forward_options(command, arguments):
    command.extend(['--size', str(arguments.size), '--focus', arguments.focus])
    if arguments.serial_calls:
        command.append('--serial-calls')
    if arguments.parallel:
        command.append('--parallel')

runner = Runner(add_cmdline_args=forward_options)
runner.argparser.add_argument('--size', type=int, default=1000)
runner.argparser.add_argument('--focus', default='')
runner.argparser.add_argument('--serial-calls', action='store_true')
runner.argparser.add_argument('--parallel', action='store_true')
args = runner.parse_args()
runner.metadata['batch_size'] = args.size
runner.metadata['entropy_policy'] = 'production OS randomness; retained generators and codecs'

def benchmark(name, single, batch):
    if args.focus and not search(args.focus, name):
        return
    operation = (lambda: [single(index) for index in range(args.size)]) if args.serial_calls else batch
    runner.bench_func(name, operation, inner_loops=args.size)

for name, source in [
    ('cuid2', fuda.Cuid2Generator()),
    ('nanoid', fuda.NanoIDGenerator()),
    ('uuid4', fuda.UUID4Generator()),
    ('uuid8', fuda.UUID8Generator()),
    ('ksuid', fuda.KSUIDGenerator()),
    ('shortuuid', fuda.ShortUUIDGenerator()),
    ('timeflake', fuda.TimeflakeGenerator()),
    ('upid', fuda.UPIDGenerator()),
]:
    benchmark(
        name + '/generate',
        lambda index, source=source: source.generate(),
        lambda source=source: source.generate_many(args.size, parallel=args.parallel),
    )

numbers = [[index, index + 1, index + 1000] for index in range(args.size)]
uuids = [UUID(int=index) for index in range(args.size)]
data = [index.to_bytes(4, 'big') for index in range(args.size)]
for name, codec, values in [
    ('hashids', fuda.Hashids(), numbers),
    ('sqids', fuda.Sqids(), numbers),
    ('proquint', fuda.Proquint, data),
    ('uuid25', fuda.UUID25, uuids),
]:
    benchmark(
        name + '/encode',
        lambda index, codec=codec, values=values: codec.encode(values[index]),
        lambda codec=codec, values=values: codec.encode_many(values, parallel=args.parallel),
    )
    encoded = [codec.encode(value) for value in values]
    benchmark(
        name + '/decode',
        lambda index, codec=codec, encoded=encoded: codec.decode(encoded[index]),
        lambda codec=codec, encoded=encoded: codec.decode_many(encoded, parallel=args.parallel),
    )
