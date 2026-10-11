from importlib import import_module
from subprocess import run
from sys import executable
from os import name as os_name
from pytest import mark, raises
from fuda import CIDv1, Multihash, UUID7Generator, NI, SWHID, ULID
from fuda import nanoid, parse, multihash, NanoIDGenerator, UUID3Generator, ULIDGenerator
from fuda import SNOGenerator
from fuda import Hashids
from fuda.identifiers.sno import SNO_EPOCH
from hypothesis import given, strategies as st
from collections import Counter
from fuda._core.encoding import encode, decode

def test_uuid7_exhaustion_does_not_reset_counter(monkeypatch):
    module = import_module('fuda.identifiers.uuids')
    monkeypatch.setattr(module, 'urandom', lambda count: bytes(count))
    source = UUID7Generator(clock=lambda: (1 << 48) - 1)
    source.generate()
    source._random = (1 << 74) - 1
    before = source._last_ms, source._random
    for _ in range(3):
        with raises(OverflowError):
            source.generate()
        assert (source._last_ms, source._random) == before

def test_uuid7_entropy_failure_preserves_state(monkeypatch):
    module = import_module('fuda.identifiers.uuids')
    source = UUID7Generator(clock=lambda: 100)
    source.generate()
    source._random = (1 << 74) - 1
    def fail(count):
        raise OSError('entropy unavailable')
    monkeypatch.setattr(module, 'urandom', fail)
    with raises(OSError):
        source.generate()
    assert source._random == (1 << 74) - 1

@mark.parametrize('value', [Multihash(0x12, b''), CIDv1(0x55, 0x12, b'')])
def test_empty_hash_does_not_authenticate_arbitrary_content(value):
    assert type(value).from_bytes(value.bytes) == value
    with raises(ValueError, match='empty digest'):
        value.verify(b'arbitrary unrelated data')

def test_empty_identity_hash_is_meaningful():
    value = multihash(b'', hash_name='identity')
    assert value.verify(b'') and not value.verify(b'nonempty')

def test_empty_hash_generation_rejected():
    with raises(ValueError):
        multihash(b'data', digest_size=0)

@mark.parametrize('authority', ['user@@host', 'host:abc', 'host:80:90', 'a[b]c', 'host:1@other:bad'])
def test_ni_authority_grammar(authority):
    with raises(ValueError):
        NI.from_content(b'data', authority=authority)

def test_ni_fragment_is_not_part_of_rfc6920_grammar():
    valid = str(NI.from_content(b'data'))
    for suffix in ('#', '#part', '?ct=text/plain#part'):
        with raises(ValueError):
            NI.from_str(valid + suffix)

@mark.parametrize('authority', ['', 'example.com', 'user:pass@example.com:443', '[2001:db8::1]:443', '[v1.a:b]', 'host:'])
def test_ni_valid_authorities(authority):
    value = NI.from_content(b'data', authority=authority)
    assert NI.from_str(str(value)) == value

def test_nanoid_parser_uses_generator_alphabet_rules():
    for alphabet in ('a', 'aab', 'ab\ud800'):
        with raises(ValueError):
            parse('nanoid', 'a', alphabet=alphabet)

@mark.parametrize('factory', [lambda: UUID3Generator(), lambda: ULIDGenerator(typo=1), lambda: NanoIDGenerator(typo=1)])
def test_configuration_errors_are_caught_before_generation(factory):
    with raises(TypeError):
        factory()

def test_nanoid_checks_configuration_without_emitting():
    with raises(ValueError):
        NanoIDGenerator(length=0)

def test_ulid_from_uuid_wrong_type():
    with raises(TypeError):
        ULID.from_uuid('not a UUID')

def test_snapshot_alias_dag_and_cycle():
    branches = {str(i).encode(): str(i + 1).encode() for i in range(2000)}
    branches[b'2000'] = None
    branches[b'shared'] = b'1000'
    assert SWHID.from_snapshot(branches) == SWHID.from_snapshot(dict(reversed(list(branches.items()))))
    branches[b'2000'] = b'50'
    with raises(ValueError, match='cyclic'):
        SWHID.from_snapshot(branches)

def test_snapshot_alias_validation_has_linear_lookup_cost():
    class CountedBranches(dict):
        lookups = 0
        def __getitem__(self, key):
            self.lookups += 1
            return super().__getitem__(key)
    branches = CountedBranches({str(i).encode(): str(i + 1).encode() for i in range(1000)})
    branches[b'1000'] = None
    SWHID.from_snapshot(branches)
    assert branches.lookups <= 2 * len(branches)

@mark.skipif(os_name == 'nt', reason='requires POSIX fork and the native extension')
def test_native_parallel_generation_after_fork():
    # Use a child interpreter and alarm so a deadlock cannot hang pytest.
    code = '''
import os, signal
from fuda import Cuid2Generator, is_cuid2
from fuda import _native
source = Cuid2Generator(parallel=True)
source.generate_many(100)
pid = os.fork()
if pid == 0:
    signal.alarm(10)
    try:
        ids = source.generate_many(100)
        ids += Cuid2Generator(parallel=True).generate_many(100)
        ids += _native.cuid2_many(100, 24, 'fork test', 1, True)
        assert len(set(ids)) == 300 and all(is_cuid2(value) for value in ids)
        os._exit(0)
    except BaseException:
        os._exit(1)
_, status = os.waitpid(pid, 0)
assert status == 0, status
'''
    result = run([executable, '-c', code], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr

def test_native_after_fork_hook_preserves_generation():
    result = run([executable, '-c', '''
from fuda import _native, is_cuid2
_native.cuid2_many(100, 24, 'test', 1, True)
_native._after_fork()
_native._after_fork()
ids = _native.cuid2_many(100, 24, 'test', 101, True)
assert len(set(ids)) == 100 and all(is_cuid2(value) for value in ids)
'''], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr

@given(st.lists(st.integers(0, 50), max_size=200))
def test_sno_arbitrary_clock_traces_do_not_reuse_ids(ticks):
    now = [SNO_EPOCH]
    source = SNOGenerator(1, sequence_max=3, clock=lambda: now[0])
    seen = set()
    for tick in ticks:
        now[0] = SNO_EPOCH + tick * 4
        try:
            value = source.generate()
        except (RuntimeError, OverflowError):
            continue
        assert value not in seen
        seen.add(value)

@given(st.integers(1, 256), st.integers(1, 200))
def test_nanoid_alphabets_and_exact_length(radix, length):
    if radix < 2:
        return
    alphabet = ''.join(chr(0x400 + index) for index in range(radix))
    result = nanoid(length, alphabet=alphabet)
    assert len(result) == length and set(result) <= set(alphabet)

@mark.parametrize('radix', [2, 3, 16, 31, 32, 36, 62, 63, 64, 95, 128, 255, 256])
@mark.parametrize('unicode', [False, True])
def test_nanoid_rejection_sampling_is_unbiased(monkeypatch, radix, unicode):
    if not unicode and radix > 128:
        return
    alphabet = ''.join(chr((1024 if unicode else 0) + index) for index in range(radix))
    position = 0
    def entropy(count):
        nonlocal position
        data = bytes((position + index) % 256 for index in range(count))
        position += count
        return data
    monkeypatch.setattr(import_module('fuda.identifiers.random_ids'), 'urandom', entropy)
    repeats = 256 // (1 << (radix - 1).bit_length())
    value = nanoid(radix * repeats, alphabet=alphabet)
    assert Counter(value) == {letter: repeats for letter in alphabet}

@mark.parametrize('alphabet', ['0123456789abcdef', '0123456789abcdefghijklmnopqrstuvwxyz', '0123456789ABCDEFGHJKMNPQRSTVWXYZ', '234567abcdefghijklmnopqrstuvwxyz', '-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'])
@given(st.integers(0, 2**160 - 1), st.integers(1, 40))
def test_optimized_encoding_matches_independent_division(alphabet, number, width):
    number %= len(alphabet)**width
    value, expected = number, ''
    for _ in range(width):
        value, digit = divmod(value, len(alphabet))
        expected = alphabet[digit] + expected
    assert encode(number, alphabet, width) == expected
    assert decode(expected, alphabet, width, 256) == number
    with raises(ValueError):
        encode(len(alphabet)**width, alphabet, width)

@mark.parametrize('value', ['+001', '-001', ' 001', '0_01', '０001', '\n001'])
def test_fast_numeric_parsers_do_not_inherit_int_leniency(value):
    with raises(ValueError):
        decode(value, '0123456789abcdef', 4, 16)

def test_hashids_long_salt_is_bounded_after_configuration():
    # With the default alphabet, all constructor and runtime shuffles consume
    # fewer than 100 salt characters; preserve the relevant prefix exactly.
    prefix = ''.join(chr(0x400 + index) for index in range(100))
    short = Hashids(salt=prefix, min_length=100)
    long = Hashids(salt=prefix + 'unused' * 100_000, min_length=100)
    assert len(long._salt) <= len(long._alphabet)
    for numbers in ([0], [1, 2, 3], [2**63 - 1] * 10):
        value = short.encode(numbers)
        assert long.encode(numbers) == value
        assert long.decode(value) == numbers

@mark.parametrize('args', [
    ['encode', 'uuid25', '00112233-4455-6677-8899-aabbccddeeff', '--salt', 'ignored'],
    ['encode', 'proquint', '0000', '--min-length', '12'],
    ['encode', 'hashids', '1', '--no-blocklist'],
    ['encode', 'sqids', '1', '--salt', 'ignored'],
    ['encode', 'hashids', '1', '--alphabet', ''],
])
def test_cli_rejects_ignored_codec_options(args):
    result = run([executable, '-m', 'fuda', *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert not result.stdout
