# 🏷️ Fuda

A universal Python library for working with unique IDs.

Generate an ID, read one back, or find out what's inside it. Fuda brings 39 formats
under a shared Python API, with typed values where the format has something useful
to expose, like a timestamp, a UUID, or a content digest.

- Generate individual IDs, batches, or a stream of IDs.
- Parse, validate, and inspect formats through the same set of functions.
- Configure generator classes once and reuse them across calls.
- Work from Python or the command line, with Rust handling the hot loops.

Fuda supports **Python 3.14+**, has **no required third-party Python runtime
dependencies**, and is licensed under **MIT**. It's still in early development,
so the API may change before a stable release.

## Installation

Install from PyPI in your virtual environment:

```sh
python -m pip install fuda
```

The Rust extension comes inside the wheel, so a normal install doesn't need a
Rust toolchain. Wheels target these platforms:

| Platform | Architectures |
| --- | --- |
| Windows | x86-64, ARM64 |
| macOS 11+ | Intel, Apple Silicon |
| Linux with glibc 2.28+ | x86-64, ARM64 |
| Linux with musl 1.2+, including Alpine | x86-64, ARM64 |

Fuda uses CPython's stable ABI, so the same wheel works across standard CPython
3.14+ versions. CI covers 3.14 and 3.15. Free-threaded Python and PyPy aren't
supported by these wheels.

The extension is required and always used. There are no backend settings or
environment variables to configure. If you want pip to require a prebuilt wheel,
use `python -m pip install --only-binary=fuda fuda`. Building from source, including
an editable checkout, needs Rust and a native compiler for your platform.

## A quick start

```python
import fuda

ids = fuda.ULIDGenerator()
event_id = ids.generate()
batch = ids.generate_many(100)

users = fuda.TypeIDGenerator('user')
user_id = users.generate()

print(str(event_id))
print(event_id.timestamp_ms)
print(str(user_id))

assert fuda.validate('ulid', str(event_id))
assert fuda.ULID.from_str(str(event_id)) == event_id
```

Every generator has `generate()`, `generate_many(count)`, and `iter_ids(count)`.
Choose the class directly and keep the instance around to retain its configuration
and state. There is no default format or generic generation factory.

Return types follow the data: UUID generators return `uuid.UUID`, CUID2 and NanoID
return strings, and formats such as ULID return small immutable value objects.
Snowflake and Sonyflake return integers. Call `str(value)` when you need text for
a URL, a JSON field, or a log message.

## Supported formats

Import generator and value classes from `fuda`. The lowercase format names are
used by the parsing helpers and CLI. Generators create IDs, codecs encode existing
values, and content formats identify supplied bytes.

### Generators

| Generator class | Format name | What you get |
| --- | --- | --- |
| `Cuid2Generator` | `cuid2` | Letter-led lowercase base36 string; 24 characters by default |
| `UUID1Generator` | `uuid1` | Time-based UUID |
| `UUID3Generator` | `uuid3` | Deterministic UUID from a namespace and name (MD5) |
| `UUID4Generator` | `uuid4` | Random UUID |
| `UUID5Generator` | `uuid5` | Deterministic UUID from a namespace and name (SHA-1) |
| `UUID6Generator` | `uuid6` | Reordered time-based UUID |
| `UUID7Generator` | `uuid7` | Millisecond timestamp and monotonic generation |
| `UUID8Generator` | `uuid8` | Custom payload fields, random by default |
| `ULIDGenerator` | `ulid` | 26-character timestamped ID; monotonic generation by default |
| `NanoIDGenerator` | `nanoid` | 21 URL-safe characters by default; configurable length and alphabet |
| `TypeIDGenerator` | `typeid` | A typed prefix and an encoded UUID; UUIDv7 by default |
| `XUIDGenerator` | `xuid` | KarpelesLab XUID: grouped base32 UUID with an optional prefix |
| `KSUIDGenerator` | `ksuid` | 27-character ID with a seconds timestamp and 128 random bits |
| `SnowflakeGenerator` | `snowflake` | Configurable timestamp, node, and sequence layout in a 63-bit integer |
| `ShortUUIDGenerator` | `shortuuid` | 22-character base57 encoding of a UUID; generates UUIDv4 by default |
| `XIDGenerator` | `xid` | 20-character ID containing time, machine, process, and counter fields |
| `ObjectIDGenerator` | `objectid` | MongoDB's 12-byte ObjectID, written as 24 hex characters |
| `TSIDGenerator` | `tsid` | 64-bit timestamped ID, written as 13 base32 characters |
| `SonyflakeGenerator` | `sonyflake` | 63-bit time, sequence, and node layout; Sonyflake v2 defaults |
| `PushIDGenerator` | `pushid` | Firebase's 20-character timestamped push key |
| `SCRU128Generator` | `scru128` | 25-character base36 ID with a timestamp, counters, and random data |
| `TimeflakeGenerator` | `timeflake` | 22-character base62 ID with millisecond time and 80 random bits |
| `NUIDGenerator` | `nuid` | NATS's 22-character base62 prefix and incrementing sequence |
| `SCRU64Generator` | `scru64` | 12-character base36 ID with 256 ms ticks and an assigned node |
| `TIDGenerator` | `tid` | AT Protocol's 13-character timestamp and clock ID |
| `UPIDGenerator` | `upid` | Timestamped 128-bit ID with an embedded four-character prefix |
| `SNOGenerator` | `sno` | 80-bit ID with time, partition, metadata, sequence, and a rollback bit |
| `HyperIDGenerator` | `hyperid` | UUIDv4 prefix followed by a decimal counter |
| `Flake128Generator` | `flake128` | Boundary Flake: timestamp, 48-bit node, and 16-bit sequence |

### Codecs and content identifiers

| Class | Format name | Input |
| --- | --- | --- |
| `Sqids` | `sqids` | A sequence of nonnegative integers, encoded with an optional blocklist |
| `Hashids` | `hashids` | A sequence of nonnegative integers, with salt and alphabet settings |
| `Proquint` | `proquint` | Bytes encoded as pronounceable groups of five letters |
| `UUID25` | `uuid25` | A UUID encoded as 25 base36 characters |
| `CIDv0` | `cidv0` | An already serialized DAG-PB block |
| `CIDv1` | `cidv1` | Block bytes, with a codec and hash algorithm |
| `Multihash` | `multihash` | Bytes hashed into a self-describing digest |
| `NI`, `NIH` | `ni`, `nih` | Bytes identified using named-information URI formats |
| `SWHID` | `swhid` | File contents or structured Software Heritage objects |

`fuda.formats()` returns the registry as `FormatInfo` objects, including each
format's name, description, kind, and whether it can carry a timestamp.

## Generating IDs

Create a generator for the format you want, then use its methods:

```python
import fuda

ids = fuda.UUID7Generator()
one = ids.generate()
batch = ids.generate_many(100)

for value in ids.iter_ids(5):
    print(value)
```

Classes preserve concrete return types, so your editor can tell that
`UUID7Generator.generate()` returns a UUID and `ULIDGenerator.generate_many()`
returns a list of ULIDs. Codecs and content identifiers use `encode()` and
`from_content()` because they need input to work with.

The format-specific convenience functions, such as `uuid7()` and `ulid()`, are
also available for one-off calls. The module-level `generator()`, `generate()`,
`generate_many()`, and `iter_ids()` helpers have been removed. Use the corresponding
methods on a generator instance instead.

For repeated use with custom settings, keep a generator around:

```python
import fuda

ids = fuda.NanoIDGenerator(length=16, alphabet='0123456789abcdef')
one = ids.generate()
batch = ids.generate_many(100)
stream = ids.iter_ids(5)

assert len(one) == 16
assert all(char in '0123456789abcdef' for char in one)
```

NanoID accepts 2–256 distinct alphabet characters, including Unicode, and samples
them without modulo bias.

`generate_many()` returns a list and accepts up to 1,000,000 IDs per call.
`iter_ids()` produces values as you request them; omit the count for an unbounded
iterator. Use iteration when you don't want the whole batch in memory.

### Names and fixed values

UUIDv3 and UUIDv5 derive an ID from a namespace and name:

```python
import fuda
from uuid import NAMESPACE_DNS

names = fuda.UUID5Generator(NAMESPACE_DNS, 'example.com')
assert names.generate() == names.generate()
```

A configured UUIDv3 or UUIDv5 generator returns the same ID on every call. Create
another instance with a different name when you want another ID. UUIDv8 can fix
some or all of its payload with `a`, `b`, and `c`; fully fixed payloads also produce
the same ID every time. `ShortUUIDGenerator` creates new UUIDv4 values; use
`shortuuid(existing_uuid)` or `UUID25.encode(existing_uuid)` to encode existing bits.

CUID2 lengths range from 2 to 32 characters. NanoID accepts a configurable length
and alphabet. Shorter IDs have less collision resistance, so choose a length for
the number of IDs you expect to create.

### Node-based formats

Snowflake, Sonyflake, SCRU64, and Flake128 need an assigned `node_id`. SNO needs
an assigned `partition`. These formats require a retained generator so their
sequence state survives between calls:

```python
import fuda

ids = fuda.SnowflakeGenerator(node_id=7)
value = ids.generate()
batch = ids.generate_many(5)

assert ids.inspect(value)['node_id'] == 7

compact = fuda.SCRU64Generator(node_id=7, node_bits=8)
partitioned = fuda.SNOGenerator(partition=7, metadata=3)
```

Give concurrent generators distinct assignments. Fuda doesn't coordinate node
leases or persist generator state across restarts. Only reuse an assignment once
the previous generator's clock range has passed. Generators with assigned nodes
or partitions refuse inherited use after fork; construct a new one with a
distinct assignment in the child.

Time ordering has a few format-specific details:

- UUIDv7 and default ULID generation are monotonic within one generator. This
  doesn't establish a global order across machines.
- SCRU128 and SCRU64 tolerate up to 10 seconds of clock rollback by default;
  larger rollbacks raise. Counter overflow advances their logical time.
- Snowflake, Sonyflake, and Flake128 refuse rollback and raise on sequence
  exhaustion. Sonyflake defaults to 256 IDs per 10 ms tick per node.
- SNO handles a safe rollback by toggling a bit, so IDs can sort backwards.
  Unsafe repeated rollback and sequence exhaustion raise.
- Timeflake doesn't guarantee order within a millisecond. UPID timestamps have
  256 ms resolution. TID's custom `clock` returns Unix microseconds.

## Parsing, validation, and inspection

```python
import fuda

value = fuda.ULIDGenerator().generate()
text = str(value)
parsed = fuda.ULID.from_str(text)

assert fuda.parse('ulid', text) == parsed
assert fuda.ULID.from_bytes(parsed.bytes) == parsed
assert fuda.validate('ulid', text)
assert not fuda.validate('ulid', 'not-an-id')

print(int(parsed))
print(fuda.inspect('ulid', text))
print(fuda.detect(text))
```

`parse()` raises on invalid input. `validate()` returns a boolean for a known
format; an unknown format name raises `ValueError`. Both take text as input.
Use `inspect()` for a dictionary of available fields, including canonical text
and timestamps where applicable. For a custom Snowflake or Sonyflake layout,
use the generator's `inspect()` method to interpret its fields correctly.

`detect()` returns every matching format name. Several formats share alphabets
and lengths, so it can return multiple matches. Keep the format alongside stored
IDs when you need to parse them reliably.

Validation checks structure. It doesn't establish who created an ID, whether it
was generated randomly, or whether someone is allowed to access the resource.
Timestamped and counter-based formats can expose time or sequence information.
Use a dedicated token generator such as `secrets.token_urlsafe()` for secrets.

## Encoding existing values

```python
import fuda

sqids = fuda.Sqids(min_length=12)
encoded = sqids.encode([1, 2, 3])
assert sqids.decode(encoded) == [1, 2, 3]

hashids = fuda.Hashids(salt='example namespace', min_length=12)
encoded = hashids.encode([42, 100])
assert hashids.decode(encoded) == [42, 100]
assert hashids.decode_hex(hashids.encode_hex('0000abcd')) == '0000abcd'

spoken = fuda.Proquint.encode(bytes.fromhex('7f000001'))
assert spoken == 'lusab-babad'
assert fuda.Proquint.decode(spoken) == bytes.fromhex('7f000001')

original = fuda.UUID4Generator().generate()
assert fuda.UUID25.decode(fuda.UUID25.encode(original)) == original
assert fuda.decode_shortuuid(fuda.shortuuid(original)) == original
```

Sqids and Hashids accept integers from `0` through `2**63 - 1`. Keep the same
alphabet, salt, minimum length, and blocklist settings wherever you encode or
decode. Generic `parse()`, `validate()`, and `inspect()` use the default codec
settings; use your codec instance for custom settings. Sqids also offers
`decode(value, canonical=True)` to require the exact spelling for its settings.

These codecs are reversible and add no randomness or encryption. A Hashids salt
is a configuration value, not an encryption key. Proquint requires nonempty bytes
with an even length. UUID conversions preserve bits; reinterpreting a ULID or UPID
as a `UUID` doesn't turn it into an RFC UUID version.

## Identifying content

```python
import fuda

data = b'hello'
cid = fuda.CIDv1.from_content(data)

assert cid.verify(data)
assert not cid.verify(b'something else')
assert fuda.CIDv1.from_str(cid.to_base('base58btc')) == cid

digest = fuda.Multihash.from_content(data)
name = fuda.NI.from_content(data, authority='example.com')
human_name = name.to_nih()

assert digest.verify(data)
assert human_name.same_content(name)
assert human_name.verify(data)
```

CIDv1 defaults to the `raw` codec and SHA-256, with lowercase base32 text. It also
reads and writes supported base16, base36, base58btc, and base64 variants. Multihash
defaults to multibase-prefixed base58btc text.

Pass already serialized block bytes for other codecs. CIDv0 expects a DAG-PB
block. Fuda hashes the supplied bytes; it doesn't chunk files, build an IPFS DAG,
or fetch content from the network.

CIDv1 and Multihash support identity, SHA-2, SHA-3, and BLAKE2b-256 hashes. Unknown
numeric hash codes can survive parsing, but unsupported algorithms can't verify
content. Empty non-identity digests are parseable but verification raises.
Truncated digests have less collision resistance than full digests.

NI and NIH support registered SHA-2, SHA-3, and BLAKE2 algorithms. KangarooTwelve
names can be parsed, but hashing them isn't supported. NI authority and query
strings must already be percent-encoded where needed; fragments are rejected.
Those locator hints don't change content identity or trigger network requests.

For Software Heritage objects:

```python
import fuda

file_id = fuda.SWHID.from_content(b'hello\n')
directory_id = fuda.SWHID.from_directory([
    fuda.DirectoryEntry(b'hello.txt', file_id),
])
qualified = file_id.with_context(
    origin='https://example.com/repository',
    path=b'/hello.txt',
    lines=(1, 1),
)

assert file_id.verify(b'hello\n')
assert qualified.core == file_id
assert fuda.SWHID.from_str(str(qualified)) == qualified
```

All five core SWHID object types are supported: content, directory, revision,
release, and snapshot. Structured constructors include `from_directory()`,
`from_revision()`, `from_release()`, and `from_snapshot()`. Use `from_object()`
for an already serialized object body; it adds the type and length header.
Author, committer, and tagger headers are supplied as exact Git bytes.

## Command line

The `fuda` command and `python -m fuda` use the same interface:

```sh
python -m fuda formats
python -m fuda generate cuid2 -n 5
python -m fuda generate typeid --prefix user --json -n 3
python -m fuda generate snowflake --node-id 7 -n 5
python -m fuda inspect ulid 01ARZ3NDEKTSV4RRFFQ69G5FAV
python -m fuda validate ulid 01ARZ3NDEKTSV4RRFFQ69G5FAV
python -m fuda encode sqids 1 2 3 --min-length 12
python -m fuda decode proquint lusab-babad
python -m fuda content cidv1 --text hello
python -m fuda content ni --text hello --authority example.com
```

Generation prints one ID per line; `--json` produces an array of strings. For
content commands, `--file path` reads a file instead of `--text`. The whole file
is read into memory. Validation exits with `0` for valid input and `1` for invalid
input; argument and configuration errors exit with `2`. Run a command with
`--help` for its options.

## Performance

Reusable generators keep configuration and state between calls. The Rust
extension speeds up shared encoding, parsing, and codec loops. NanoID uses cached
alphabet tables with OS randomness on every call.

For a rough reference, a development run on Windows 11 with CPython 3.14.8 x64
measured these mean times on October 9, 2026. The earlier build only used Rust for
CUID2; the updated build also accelerates shared operations:

| Workload | Earlier build | Shared acceleration | Speedup |
| --- | ---: | ---: | ---: |
| ULID, generate and format | 5.16 µs | 3.03 µs | 1.70× |
| KSUID, generate and format | 5.68 µs | 3.15 µs | 1.80× |
| XUID, generate and format | 9.14 µs | 5.13 µs | 1.78× |
| Sqids, encode three integers | 50.5 µs | 9.13 µs | 5.53× |
| Hashids, encode three integers | 22.1 µs | 2.30 µs | 9.60× |
| Proquint, encode four bytes | 1.55 µs | 0.389 µs | 3.98× |
| CIDv0, hash and format | 12.8 µs | 4.08 µs | 3.14× |
| CIDv1, hash and format | 15.2 µs | 8.52 µs | 1.78× |
| NIH, hash and format | 24.9 µs | 10.1 µs | 2.46× |

Across the full suite, 23 of 39 workloads improved by more than 10%. The remaining
16 changed by less than 3.2%, including a few small slowdowns. These runs used
pyperf with three worker processes, three measured values per process, one warmup, and a 50 ms
minimum sample time. Codecs used rotating inputs and generators used real OS
entropy. Some runs reported timing instability. These are local measurements;
hardware, Python version, and batch size matter.

To measure your own setup, install the development extra and run:

```sh
python tools/benchmark.py -p 3 -n 5 -w 1 --min-time 0.1 -o ../fuda-benchmark.json
```

The main suite covers all 39 formats: generator output, codec output, and content
hashing. It retains generator state and uses final encoded strings. Sonyflake uses
a larger sequence field to avoid exhausting its default 256-ID tick in tight loops;
that layout is recorded in the benchmark metadata. `--focus` filters benchmark names.

`tools/benchmark_cuid2.py` compares CUID2 generation with `cuid2`, `idika`, and `anyid`.
It needs `idika==0.3.1` and `anyid==0.5.0` in the same virtual environment in
addition to the development dependencies. It compares final strings and labels
the limited `anyid` import used to work around its Windows package import issue.

### Native execution

Fuda stays mostly Python. Its public classes, generator state, and process handling
live there. Rust handles the loops that benefit from it:

- Fixed-width radix encoding and decoding, shared by formats such as ULID, KSUID,
  TypeID, ShortUUID, XID, TSID, SCRU128, and UUID25.
- Multibase encoding and decoding for CID and Multihash, plus XUID's base32 text.
- Sqids, Hashids, Proquint, and NIH check digits.
- CUID2 generation, including optional parallel batches.

UUID handling, hexadecimal formatting, and content hashing keep using Python's
standard library. Those operations already have native implementations. The
accelerators preserve the format rules, including leading zero bytes, padding
checks, custom alphabets, and Unicode Hashids salts.

`Cuid2Generator(parallel=True)` can spread batch generation across native workers.
After POSIX fork, a child with an inherited active worker pool uses serial native
batches. Other accelerators use immutable settings and don't start worker pools.

## Development

To work on Fuda itself, install stable Rust and a native compiler first. On Windows,
use Visual Studio Build Tools with the C++ workload; on macOS, use the Xcode command
line tools. Linux needs a C compiler and linker. Then create and activate a virtual
environment in the checkout and install the development tools:

```sh
python -m venv .venv
# Activate .venv using your shell's activation command before continuing.
python -m pip install -e '.[dev]'

python -m ruff check .
python tools/style.py --check
python -m mypy
python -m pytest
cargo fmt --check
cargo clippy --release -- -D warnings
cargo test --release

python -m build
python -m twine check --strict dist/*
```

`tools/style.py` applies the project's import ordering and spacing conventions.
The test suite includes reference vectors, round trips, property tests, and
regressions for invalid input, clock changes, and process state.

The source is grouped by purpose:

- `src/fuda/identifiers/` contains generators and their value types.
- `src/fuda/codecs/` contains reversible encodings of existing values.
- `src/fuda/content/` contains content identifiers and hashing helpers.
- `src/fuda/_core/` contains shared state, encoding, and extension loading.
- `rust/` contains the native hot loops; `src/fuda/_native.pyi` describes their
  Python signatures.

The top-level package keeps the public imports together, so callers can use
`from fuda import ULIDGenerator` without knowing the source layout.

CI builds wheels from the source distribution and tests them outside the checkout.
It covers Python 3.14–3.15 on Linux, Windows, and macOS, with x86-64 and ARM64 runners
and separate Linux musl builds. The release check requires all eight platform
wheels, the extension, typing files, codec data, and licenses. PyPI releases reuse
those tested artifacts.

## License

[MIT](LICENSE). The distribution also includes attribution and licenses for the
[Sqids](src/fuda/LICENSE.sqids), [Hashids](src/fuda/LICENSE.hashids), and
[data-encoding](src/fuda/LICENSE.data-encoding) code and data.
