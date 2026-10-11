from json import loads
from os import getpid
from pathlib import Path
from copy import copy, deepcopy
from pickle import dumps
from sys import executable
from subprocess import run
from pytest import mark, raises
from hypothesis import given, strategies as st
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from fuda import (
    TID, PushID, SCRU64, SCRU128, Timeflake, CIDv1, Sqids, Proquint,
    TIDGenerator, PushIDGenerator, SCRU64Generator, SCRU128Generator,
    SonyflakeGenerator, TimeflakeGenerator, NUIDGenerator,
    cidv1, formats, inspect, parse, validate,
)
from fuda.identifiers.sonyflake import SONYFLAKE_EPOCH
from fuda.identifiers.extended_types import SCRU64_LIMIT

FIXTURES = loads((Path(__file__).parent / 'fixtures/additional-reference.json').read_text(encoding='utf-8'))
BINARY = [PushID, SCRU128, SCRU64, Timeflake, TID]

@mark.parametrize('fixture', FIXTURES['binary'])
def test_reference_binary_encodings(fixture):
    value = parse(fixture['format'], fixture['encoded'])
    assert int(value) == int(fixture['integer'])
    expected = fixture['encoded'].zfill(22) if fixture['format'] == 'timeflake' else fixture['encoded']
    assert str(value) == expected
    assert type(value).from_bytes(value.bytes) == value

@mark.parametrize('kind', BINARY)
@given(number=st.integers(min_value=0, max_value=2**128 - 1))
def test_binary_roundtrips(kind, number):
    limit = SCRU64_LIMIT if kind == SCRU64 else 2**kind._bits
    value = kind(number % limit)
    assert kind.from_str(str(value)) == value
    assert kind.from_bytes(value.bytes) == value

@mark.parametrize('kind', BINARY)
def test_binary_invalid_shapes_and_types(kind):
    value = kind(123)
    for malformed in ('', str(value)[1:], str(value) + '0', ' ' + str(value), 'é' * kind._width):
        with raises(ValueError):
            kind.from_str(malformed)
    for number in (-1, 2**128):
        with raises(ValueError):
            kind(number)
    for number in (True, 1.5, '1'):
        with raises(TypeError):
            kind(number)
    with raises(TypeError):
        kind.from_bytes(bytearray(value.bytes))
    with raises(ValueError):
        kind.from_bytes(value.bytes[:-1])
    with raises(TypeError):
        kind.from_str(None)

def test_reserved_and_overflow_encodings():
    assert int(SCRU128.from_str('f5lxx1zz5pnorynqglhzmsp33')) == 2**128 - 1
    assert int(SCRU64.from_str('zzzzzzzzzzzz')) == 36**12 - 1
    assert SCRU64.from_str('ZZZZZZZZZZZZ') == SCRU64(36**12 - 1)
    assert SCRU128.from_str(str(SCRU128(123456789)).upper()) == SCRU128(123456789)
    with raises(ValueError):
        SCRU128.from_str('z' * 25)
    with raises(ValueError):
        Timeflake.from_str('z' * 22)
    with raises(ValueError):
        SCRU64(36**12)
    with raises(ValueError):
        TID.from_str('k222222222222')
    with raises(ValueError):
        TID.from_str('3JZFCIJPJ2Z2A')
    assert str(TID(0)) == '2222222222222'
    assert str(TID(2**63 - 1)) == 'bzzzzzzzzzzzz'
    assert str(TID(2**64 - 1)) == 'jzzzzzzzzzzzz'
    assert TID.from_str('3jzfcijpj2z2a').clock_id == 6

def test_pushid_layout_and_increment(monkeypatch):
    monkeypatch.setattr('fuda.identifiers.ordered.randbits', lambda bits: 0)
    clock = [1]
    source = PushIDGenerator(clock=lambda: clock[0])
    first = source.generate()
    assert str(first) == '-------0------------'
    assert first.timestamp_ms == 1 and first.randomness == 0
    assert str(source.generate()) == '-------0-----------0'
    clock[0] = 0
    assert source.generate().randomness == 2
    source._random = 2**72 - 1
    with raises(OverflowError):
        source.generate()
    clock[0] = 2
    assert source.generate().timestamp_ms == 2

def test_timeflake_fields():
    source = TimeflakeGenerator(clock=lambda: 1_700_000_000_123)
    values = source.generate_many(100)
    assert len(set(values)) == 100
    assert all(value.timestamp_ms == 1_700_000_000_123 for value in values)
    assert len({value.randomness for value in values}) == 100

def test_scru128_reference_spec_vector():
    value = SCRU128.from_bytes(bytes([1, 127, 239, 57, 194, 100, 27, 165, 106, 148, 131, 24, 136, 65, 224, 90]))
    assert str(value) == '0372ijojuxuhjsfkeryi2mrtm'
    assert int(value) == 1993501768880490086615869617690763354

def test_scru128_counters_and_rollback(monkeypatch):
    monkeypatch.setattr('fuda.identifiers.scru.randbits', lambda bits: 7)
    clock = [20000]
    source = SCRU128Generator(clock=lambda: clock[0])
    first, second = source.generate_many(2)
    assert (first.timestamp_ms, first.counter_hi, first.counter_lo, first.entropy) == (20000, 7, 7, 7)
    assert second.counter_lo == 8
    source._lo = 2**24 - 1
    carried = source.generate()
    assert (carried.counter_hi, carried.counter_lo) == (8, 0)
    source._hi, source._lo = 2**24 - 1, 2**24 - 1
    overflowed = source.generate()
    assert (overflowed.timestamp_ms, overflowed.counter_hi, overflowed.counter_lo) == (20001, 0, 7)
    assert source.generate() > overflowed
    clock[0] = 9999
    with raises(RuntimeError, match='rollback'):
        source.generate()
    clock[0] = 21001
    assert source.generate().counter_hi == 7
    clock[0] = 2**48 - 2
    source.generate()
    source._hi, source._lo = 2**24 - 1, 2**24 - 1
    with raises(OverflowError):
        source.generate()

def test_scru64_layout_counter_and_rollback(monkeypatch):
    monkeypatch.setattr('fuda.identifiers.scru.randbits', lambda bits: 0)
    clock = [25_600]
    source = SCRU64Generator(5, node_bits=21, clock=lambda: clock[0])
    values = source.generate_many(9)
    assert int(values[0]) == 1_677_721_640
    assert str(values[0]) == '000000rqveaw'
    assert values[0].timestamp_ms == 25_600
    assert values[-1].timestamp_ms == 25_856
    assert values == sorted(values)
    clock[0] = 0
    with raises(ValueError):
        source.generate()
    clock[0] = 1_000
    with raises(RuntimeError, match='rollback'):
        source.generate()
    clock[0] = 30_000
    assert source.generate() > values[-1]
    clock[0] = ((SCRU64_LIMIT - 1) >> 24) << 8
    with raises(OverflowError):
        source.generate()

def test_sonyflake_v2_layout_and_policies():
    clock = [SONYFLAKE_EPOCH + 1000]
    source = SonyflakeGenerator(42, clock=lambda: clock[0])
    first, second = source.generate_many(2)
    assert first == 1_677_721_642
    assert second == 1_677_787_178
    assert source.inspect(second) == {'timestamp_ms': clock[0], 'node_id': 42, 'sequence': 1}
    source._sequence = 255
    with raises(OverflowError):
        source.generate()
    clock[0] -= 10
    with raises(RuntimeError):
        source.generate()
    clock[0] += 20
    assert source.generate() > second
    clock[0] = SONYFLAKE_EPOCH + (2**39 * 10)
    with raises(OverflowError):
        source.generate()
    custom = SonyflakeGenerator(3, epoch=1003, time_unit_ms=10, node_bits=2, sequence_bits=3, clock=lambda: 1010)
    assert custom.generate() == 35
    assert custom.inspect(35) == {'timestamp_ms': 1010, 'node_id': 3, 'sequence': 0}

def test_tid_monotonic_microseconds():
    clock = [123456789]
    source = TIDGenerator(1023, clock=lambda: clock[0])
    first, second = source.generate_many(2)
    assert first.timestamp_us == 123456789
    assert second.timestamp_us == first.timestamp_us + 1
    assert first.clock_id == second.clock_id == 1023
    clock[0] = 10
    assert source.generate().timestamp_us == first.timestamp_us + 2
    assert inspect('tid', str(first))['timestamp_us'] == 123456789
    clock[0] = 2**53 - 1
    assert source.generate().timestamp_us == 2**53 - 1
    with raises(OverflowError):
        source.generate()

def test_nuid_sequence_and_rollover(monkeypatch):
    source = NUIDGenerator()
    source._prefix, source._sequence, source._increment = 'abcdefghijkl', 0, 33
    assert source.generate() == 'abcdefghijkl000000000X'
    assert source.generate() == 'abcdefghijkl0000000014'
    source._sequence = 62**10 - 1
    module = import_module('fuda.identifiers.nuid')
    monkeypatch.setattr(module, 'nanoid', lambda *args, **kwargs: 'newprefix123')
    monkeypatch.setattr(module, 'randbelow', lambda maximum: 0)
    assert source.generate() == 'newprefix1230000000000'
    assert source._increment == 33
    assert validate('nuid', source.generate())
    assert not validate('nuid', '_' * 22)

@mark.parametrize('factory', [PushIDGenerator, SCRU128Generator, NUIDGenerator, TIDGenerator, lambda: SCRU64Generator(1)])
def test_new_generators_thread_safety(factory):
    source = factory()
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: source.generate(), range(2000)))
    assert len(set(values)) == 2000

@mark.parametrize('factory', [PushIDGenerator, SCRU128Generator, NUIDGenerator, TIDGenerator])
def test_new_generators_process_change(factory):
    source = factory()
    before = source.generate()
    source._lock.acquire()
    source._pid = -1
    after = source.generate()
    assert before != after
    assert source._pid == getpid()

@mark.parametrize('factory', [lambda: SonyflakeGenerator(1), lambda: SCRU64Generator(1), lambda: TIDGenerator(1)])
def test_new_assigned_generators_refuse_fork(factory):
    source = factory()
    source._pid = -1
    for _ in range(2):
        with raises(RuntimeError, match='distinct'):
            source.generate()

@mark.parametrize('factory', [PushIDGenerator, SCRU128Generator, TimeflakeGenerator, NUIDGenerator, TIDGenerator,
                             lambda: SonyflakeGenerator(1), lambda: SCRU64Generator(1)])
def test_new_generators_cannot_copy_state(factory):
    for operation in (copy, deepcopy, dumps):
        with raises(TypeError):
            operation(factory())

@mark.parametrize('factory,options', [
    (SCRU64Generator, {'node_id': -1}), (SCRU64Generator, {'node_id': 256}),
    (SCRU64Generator, {'node_id': 0, 'node_bits': 0}),
    (SCRU64Generator, {'node_id': 0, 'node_bits': 24}),
    (SCRU64Generator, {'node_id': 0, 'max_rollback_ms': -1}),
    (SCRU128Generator, {'max_rollback_ms': -1}),
    (SonyflakeGenerator, {'node_id': 65536}),
    (SonyflakeGenerator, {'node_id': 0, 'node_bits': 30, 'sequence_bits': 2}),
    (SonyflakeGenerator, {'node_id': 0, 'time_unit_ms': 0}),
    (SonyflakeGenerator, {'node_id': 0, 'epoch': -1}),
    (TIDGenerator, {'clock_id': 1024}),
])
def test_invalid_new_generator_configuration(factory, options):
    with raises(ValueError):
        factory(**options)

@mark.parametrize('factory', [PushIDGenerator, SCRU128Generator, TimeflakeGenerator, TIDGenerator])
def test_invalid_clock_values(factory):
    with raises(TypeError):
        factory(clock=lambda: True).generate()
    with raises(ValueError):
        factory(clock=lambda: -1).generate()

@mark.parametrize('fixture', FIXTURES['sqids'])
def test_sqids_reference(fixture):
    codec = Sqids(**fixture['options'])
    assert codec.encode(fixture['numbers']) == fixture['encoded']
    assert codec.decode(fixture['encoded'], canonical=True) == fixture['numbers']

@given(numbers=st.lists(st.integers(min_value=0, max_value=2**63 - 1), max_size=15),
       min_length=st.integers(min_value=0, max_value=255))
def test_sqids_roundtrip(numbers, min_length):
    codec = Sqids(min_length=min_length)
    result = codec.encode(numbers)
    assert codec.decode(result, canonical=True) == numbers
    if numbers:
        assert len(result) >= min_length

def test_sqids_known_vector_and_blocklist():
    assert Sqids().encode([1, 2, 3]) == '86Rf07'
    assert Sqids(blocklist=['86Rf07']).encode([1, 2, 3]) == 'se8ojk'
    assert Sqids().decode('86Rf07') == [1, 2, 3]
    assert inspect('sqids', '86Rf07')['numbers'] == [1, 2, 3]
    assert not validate('sqids', 'se8ojk')
    assert Sqids().decode('se8ojk') == [1, 2, 3]
    with raises(ValueError):
        Sqids().decode('se8ojk', canonical=True)
    assert Sqids().encode([]) == ''
    assert Sqids().decode('') == []
    assert not validate('sqids', '')

def test_sqids_blocklist_rules_and_exhaustion():
    assert Sqids().encode([4572721]) == 'JExTR'
    assert Sqids(blocklist=[]).encode([4572721]) == 'aho1e'
    assert Sqids(blocklist=['ArUO']).encode([100000]) == 'QyG4'
    assert Sqids(blocklist=['JSwXFaosAN', 'OCjV9JK64o', 'rBHf', '79SM', '7tE6']).encode([1000000, 2000000]) == '1aYeB7bRUt'
    assert Sqids(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', blocklist=['sxnzkl']).encode([1, 2, 3]) == 'IBSHOZ'
    assert Sqids(blocklist=['bM']).encode([0]) == 'bM'
    with raises(ValueError, match='prevents encoding'):
        Sqids(alphabet='abc', min_length=3, blocklist=['cab', 'abc', 'bca']).encode([0])

@mark.parametrize('options', [{'alphabet': 'ab'}, {'alphabet': 'aab'}, {'alphabet': 'äbc'}, {'min_length': 256}, {'min_length': -1}])
def test_sqids_bad_config(options):
    with raises(ValueError):
        Sqids(**options)

def test_sqids_invalid_inputs():
    with raises(TypeError):
        Sqids(blocklist='abc')
    with raises(TypeError):
        Sqids(blocklist=[None])
    for bad in (True, '1', 1.2):
        with raises(TypeError):
            Sqids().encode([bad])
    for bad in (-1, 2**63):
        with raises(ValueError):
            Sqids().encode([bad])
    with raises(ValueError):
        Sqids().decode('not-a-sqid')
    with raises(ValueError):
        Sqids().decode('a' + 'b' * 200)
    with raises(TypeError):
        Sqids().decode(None)

@mark.parametrize('raw,encoded', [
    ('0000', 'babab'), ('ffff', 'zuzuz'), ('7f000001', 'lusab-babad'),
    ('3f54dcc1', 'gutih-tugad'), ('00000000', 'babab-babab'),
])
def test_proquint_vectors(raw, encoded):
    assert Proquint.encode(bytes.fromhex(raw)) == encoded
    assert Proquint.decode(encoded).hex() == raw
    assert validate('proquint', encoded)
    assert inspect('proquint', encoded)['hex'] == raw

@given(data=st.binary(min_size=1, max_size=50))
def test_proquint_roundtrip(data):
    data += b'\0' * (len(data) % 2)
    assert Proquint.decode(Proquint.encode(data)) == data

@mark.parametrize('value', ['', 'baba', 'babab-', '-babab', 'Babab', 'baaab', 'bbbbb', 'babab--babab', 'bábab'])
def test_proquint_invalid(value):
    assert not validate('proquint', value)
    with raises(ValueError):
        Proquint.decode(value)

def test_proquint_invalid_data():
    with raises(ValueError):
        Proquint.encode(b'')
    with raises(ValueError):
        Proquint.encode(b'a')
    with raises(TypeError):
        Proquint.encode('ab')
    with raises(TypeError):
        Proquint.decode(b'babab')

@mark.parametrize('fixture', FIXTURES['cidv1'])
def test_cidv1_reference_multibase_and_hashes(fixture):
    content = bytes.fromhex(fixture['content'])
    value = cidv1(content, codec=fixture['codec'], hash_name=fixture['hash'])
    for base, encoded in fixture['encodings'].items():
        assert value.to_base(base) == encoded
        assert CIDv1.from_str(encoded) == value
        assert parse('cidv1', encoded) == value
    assert CIDv1.from_bytes(value.bytes) == value
    assert value.verify(content)
    assert not value.verify(content + b'!')

@given(content=st.binary(max_size=512))
def test_cidv1_roundtrip(content):
    value = cidv1(content)
    assert CIDv1.from_str(str(value)) == value
    assert CIDv1.from_bytes(value.bytes) == value
    assert value.verify(content)

def test_cidv1_fields_extensions_and_truncation():
    value = cidv1(b'hello')
    assert str(value) == 'bafkreibm6jg3ux5qumhcn2b3flc3tyu6dmlb4xa7u5bf44yegnrjhc4yeq'
    fields = inspect('cidv1', str(value))
    assert fields['codec'] == 0x55 and fields['hash_code'] == 0x12
    assert fields['codec_name'] == 'raw' and fields['hash_name'] == 'sha2-256'
    opaque = CIDv1(2**40, 2**41, b'abc')
    assert CIDv1.from_str(str(opaque)) == opaque
    assert opaque.codec_name is None and opaque.hash_name is None
    with raises(ValueError, match='not supported'):
        opaque.verify(b'abc')
    short = CIDv1(value.codec, value.hash_code, value.digest[:16])
    assert short.verify(b'hello')
    assert not short.verify(b'HELLO')
    for name in ('sha3-224', 'sha3-384', 'sha3-512', 'blake2b-256'):
        assert cidv1(b'hello', hash_name=name).verify(b'hello')

@mark.parametrize('value', [
    b'', b'\x00', b'\x02\x55\x12\x20', b'\x81\x00\x55\x00\x00',
    b'\x01\xd5\x00\x00\x00', b'\x01\x55\x80\x00\x00',
    b'\x01\x55\x00\x80\x00', b'\x01\x55\x12\x20hello',
    b'\x01\x55\x00\x00trailing', b'\x01' + b'\x80' * 9 + b'\0',
    b'\x01\x55\x12\x21' + b'a' * 33,
])
def test_cidv1_rejects_malformed_binary(value):
    with raises(ValueError):
        CIDv1.from_bytes(value)

@mark.parametrize('value', ['', 'b', 'z', 'QmYwAPJzv5CZsnAzt8auVZRnGmc2gRwDbKMGiWKKKhJJTs',
                                 'bafkqaaa=', 'Bafkqaaa', 'f0155000', 'z0', '🔥', 'mAVUAAA==='])
def test_cidv1_rejects_malformed_text(value):
    assert not validate('cidv1', value)

def test_cidv1_validation_errors():
    with raises(TypeError):
        cidv1('hello')
    with raises(TypeError):
        CIDv1(True, 0, b'')
    with raises(TypeError):
        CIDv1(0, 0, bytearray())
    with raises(TypeError):
        CIDv1.from_bytes(None)
    with raises(TypeError):
        CIDv1.from_str(None)
    with raises(ValueError):
        cidv1(b'', codec='unknown')
    with raises(ValueError):
        cidv1(b'', hash_name='unknown')
    with raises(ValueError):
        cidv1(b'').to_base('unknown')

def test_registry_has_all_39_formats():
    assert len(formats()) == 39
    assert {item.name for item in formats() if item.kind == 'codec'} == {'sqids', 'proquint', 'hashids', 'uuid25'}
    assert {item.name for item in formats() if item.kind == 'content'} == {'cidv0', 'cidv1', 'multihash', 'ni', 'nih', 'swhid'}

@mark.parametrize('arguments,expected', [
    (['encode', 'sqids', '1', '2', '3'], '86Rf07'),
    (['decode', 'sqids', '86Rf07'], '[1, 2, 3]'),
    (['encode', 'proquint', '7f000001'], 'lusab-babad'),
    (['decode', 'proquint', 'lusab-babad'], '7f000001'),
    (['cidv1', '--text', 'hello'], 'bafkreibm6jg3ux5qumhcn2b3flc3tyu6dmlb4xa7u5bf44yegnrjhc4yeq'),
])
def test_new_cli_commands(arguments, expected):
    result = run([executable, '-m', 'fuda', *arguments], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected

def test_cid_cli_file(tmp_path):
    content = tmp_path / 'content.bin'
    content.write_bytes(bytes(range(256)))
    result = run([executable, '-m', 'fuda', 'cidv1', '--file', str(content)], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == str(cidv1(content.read_bytes()))
    result = run([executable, '-m', 'fuda', 'cidv1', '--file', str(content) + '.missing'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'Traceback' not in result.stderr
