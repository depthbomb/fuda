# 🏷️ Fuda

A Python library for generating, parsing, and inspecting IDs.

Fuda supports 39 formats, from UUIDs and ULIDs to content identifiers like CID.
Generate one ID or a batch, parse an ID from text, or read its timestamp and other
fields. You can use it from Python or the command line.

Requires **CPython 3.14+**. Fuda includes a Rust extension and has no required
third-party Python runtime dependencies.

## Installation

Install in your virtual environment:

```sh
python -m pip install fuda
```

Wheels include the Rust extension for these platforms:

| Platform | Architectures |
| --- | --- |
| Windows | x86-64, ARM64 |
| macOS 11+ | Intel, Apple Silicon |
| Linux with glibc 2.28+ | x86-64, ARM64 |
| Linux with musl 1.2+, including Alpine | x86-64, ARM64 |

The same wheel works on standard CPython 3.14 and newer. Free-threaded Python and
PyPy aren't supported.

To require a prebuilt wheel, use `python -m pip install --only-binary=fuda fuda`.
Building from source, including an editable checkout, needs Rust and a native
compiler for your platform.

## Quick start

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
Keep the instance around to reuse its configuration and state.

UUID generators return `uuid.UUID`, CUID2 and NanoID return strings, and formats
such as ULID return immutable value objects.
Snowflake and Sonyflake return integers.

## Supported formats

Import these classes from `fuda`. Use the lowercase format names with the parsing
helpers and CLI.

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

`fuda.formats()` lists each format's name, description, kind, and timestamp support.

## Generating IDs

For one-off calls, use functions such as `fuda.uuid7()` or `fuda.ulid()`.
For custom settings, create a generator:

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

A UUIDv3 or UUIDv5 generator returns the same ID on every call. Use a different
name to get a different ID. UUIDv8 accepts fixed payload fields `a`, `b`, and `c`;
setting all three also produces the same ID every time.

CUID2 accepts lengths from 2 to 32 characters. Shorter IDs have less collision
resistance, so choose a length for the number of IDs you expect to create.

### Node-based formats

Snowflake, Sonyflake, SCRU64, and Flake128 need an assigned `node_id`. SNO needs
an assigned `partition`. Keep the generator instance so its sequence state
survives between calls:

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
its last timestamp has passed. Generators with assigned nodes or partitions
refuse inherited use after fork; construct a new one with a distinct assignment
in the child.

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

Validation checks an ID's structure. IDs can expose timestamps or counters;
use `secrets.token_urlsafe()` for authentication tokens and other secrets.

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
decode. `parse()`, `validate()`, and `inspect()` use the default codec settings;
use your codec instance for custom settings. Sqids also offers
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

Rust handles shared encoding, parsing, codecs, and CUID2 generation. Generator
state lives in Python, and content hashing uses the standard library.

`Cuid2Generator(parallel=True)` spreads batch generation across native workers.
After POSIX fork, a child with an inherited active worker pool uses serial batches.

To benchmark your setup, install the development extra and run:

```sh
python tools/benchmark.py -p 3 -n 5 -w 1 --min-time 0.1 -o ../fuda-benchmark.json
```

The suite covers all 39 formats, including final string conversion. It reuses
generators and uses OS randomness. Sonyflake uses a larger sequence field to avoid
exhausting its default 256-ID tick; the layout is recorded in the results.
Use `--focus` to filter benchmark names.

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
checks for invalid input, clock changes, and process state.

CI builds wheels from the source distribution and tests them outside the checkout.
It covers Python 3.14 and 3.15 on Linux, Windows, and macOS, including x86-64,
ARM64, and Linux musl.

## License

[MIT](LICENSE). The distribution also includes attribution and licenses for the
[Sqids](src/fuda/LICENSE.sqids), [Hashids](src/fuda/LICENSE.hashids), and
[data-encoding](src/fuda/LICENSE.data-encoding) code and data.
