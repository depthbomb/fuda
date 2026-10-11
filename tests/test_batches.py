import fuda
from uuid import UUID
from itertools import repeat
from pytest import mark, raises
from concurrent.futures import ThreadPoolExecutor
from hypothesis import given, strategies as st
from fuda._core.extension import native

@mark.parametrize('parallel', [False, True])
@mark.parametrize('name,source', [
    ('cuid2', fuda.Cuid2Generator()),
    ('nanoid', fuda.NanoIDGenerator()),
    ('uuid4', fuda.UUID4Generator()),
    ('uuid8', fuda.UUID8Generator()),
    ('ksuid', fuda.KSUIDGenerator(timestamp=1_500_000_000)),
    ('shortuuid', fuda.ShortUUIDGenerator()),
    ('timeflake', fuda.TimeflakeGenerator(clock=lambda: 123)),
    ('upid', fuda.UPIDGenerator('user', clock=lambda: 512)),
])
def test_random_batches_return_valid_distinct_values(name, source, parallel):
    values = source.generate_many(1024, parallel=parallel)
    assert len(values) == len(set(values)) == 1024
    assert all(fuda.validate(name, str(value)) for value in values)
    if name == 'ksuid':
        assert all(value.timestamp == 1_500_000_000 for value in values)
    elif name == 'shortuuid':
        assert all(fuda.decode_shortuuid(value).version == 4 for value in values)

@mark.parametrize('parallel', [False, True])
@given(st.integers(2, 256), st.integers(1, 100))
def test_native_nanoid_batch_alphabets(parallel, radix, length):
    alphabet = ''.join(chr(0x400 + index) for index in range(radix))
    values = fuda.NanoIDGenerator(length, alphabet=alphabet).generate_many(300, parallel=parallel)
    assert len(values) == 300
    assert all(len(value) == length and set(value) <= set(alphabet) for value in values)

@mark.parametrize('parallel', [False, True])
@mark.parametrize('a', [None, 0x123456789abc])
@mark.parametrize('b', [None, 0xdef])
@mark.parametrize('c', [None, (1 << 62) - 1])
def test_uuid8_batches_preserve_fixed_payload_fields(parallel, a, b, c):
    values = fuda.UUID8Generator(a=a, b=b, c=c).generate_many(300, parallel=parallel)
    for value in values:
        assert value.version == 8 and value.variant == 'specified in RFC 4122'
        for expected, actual in ((a, value.int >> 80), (b, (value.int >> 64) & 0xfff), (c, value.int & ((1 << 62) - 1))):
            if expected is not None:
                assert actual == expected
    if None not in (a, b, c):
        assert len(set(values)) == 1

@mark.parametrize('parallel', [False, True])
@mark.parametrize('factory', [fuda.TimeflakeGenerator, fuda.UPIDGenerator])
def test_batch_calls_custom_clock_once_per_id(factory, parallel):
    timestamps = iter([512, 256, 768, 1024])
    source = factory(clock=lambda: next(timestamps))
    assert source.generate_many(0, parallel=parallel) == []
    assert [value.timestamp_ms for value in source.generate_many(3, parallel=parallel)] == [512, 256, 768]
    assert source.generate().timestamp_ms == 1024

@mark.parametrize('parallel', [False, True])
@mark.parametrize('codec,values', [
    (fuda.Hashids(salt='🚀\ud800', min_length=24), [[index, 0, (1 << 63) - 1] for index in range(1024)]),
    (fuda.Sqids(min_length=24, blocklist=['abc', '1234']), [[index, 0, (1 << 63) - 1] for index in range(1024)]),
    (fuda.Proquint, [index.to_bytes(4, 'big') for index in range(1024)]),
    (fuda.UUID25, [UUID(int=index) for index in range(1024)]),
])
def test_codec_batches_match_single_calls_in_order(codec, values, parallel):
    encoded = codec.encode_many(iter(values), parallel=parallel)
    assert encoded == [codec.encode(value) for value in values]
    assert codec.decode_many(iter(encoded), parallel=parallel) == values
    assert codec.encode_many([], parallel=parallel) == []
    assert codec.decode_many([], parallel=parallel) == []

@mark.parametrize('parallel', [False, True])
def test_uuid25_batch_decoding_accepts_uppercase(parallel):
    values = [UUID(int=(1 << 128) - 1), UUID(int=0)]
    texts = [fuda.UUID25.encode(value).upper() for value in values]
    assert fuda.UUID25.decode_many(texts, parallel=parallel) == values

@mark.parametrize('parallel', [False, True])
def test_sqids_batch_canonical_validation(parallel):
    codec = fuda.Sqids(min_length=24)
    values = [[index] for index in range(1024)]
    encoded = codec.encode_many(values, parallel=parallel)
    assert codec.decode_many(encoded, canonical=True, parallel=parallel) == values
    with raises(ValueError):
        codec.decode_many([fuda.Sqids().encode([1])] * 1024, canonical=True, parallel=parallel)

@mark.parametrize('parallel', [False, True])
@mark.parametrize('codec,bad', [
    (fuda.Hashids(), [True]), (fuda.Hashids(), [-1]), (fuda.Hashids(), [1 << 63]),
    (fuda.Sqids(), [True]), (fuda.Sqids(), [-1]), (fuda.Sqids(), [1 << 63]),
    (fuda.Proquint, b''), (fuda.Proquint, b'a'), (fuda.Proquint, bytearray(b'ab')),
    (fuda.UUID25, 1),
])
def test_codec_batch_encoding_rejects_invalid_inputs(codec, bad, parallel):
    with raises((TypeError, ValueError)):
        codec.encode_many([bad] * 1024, parallel=parallel)

@mark.parametrize('parallel', [False, True])
@mark.parametrize('codec', [fuda.Hashids(), fuda.Sqids(), fuda.Proquint, fuda.UUID25])
def test_codec_batch_errors_and_limits(codec, parallel):
    with raises(ValueError):
        codec.decode_many(['invalid!'] * 1024, parallel=parallel)
    with raises(TypeError):
        codec.decode_many([None], parallel=parallel)
    with raises(ValueError):
        codec.decode_many(repeat(''), parallel=parallel)
    for method in (codec.encode_many, codec.decode_many):
        with raises(TypeError, match='parallel'):
            method([], parallel=1)

@mark.parametrize('parallel', [False, True])
def test_native_batch_boundaries(parallel):
    assert native.random_u128_many(0, (1 << 128) - 1, parallel=parallel) == []
    with raises(ValueError, match='batch count'):
        native.random_u128_many(1_000_001, 1, parallel=parallel)
    with raises(ValueError, match='batch count'):
        native.RandomAlphabet('abc').generate_many(1_000_001, 1, parallel)
    with raises(OverflowError):
        native.cuid2_many(2, 24, 'test', (1 << 64) - 1, parallel)

@mark.parametrize('alphabet', ['\0\1\2', 'αβ🙂🚀', ''.join(map(chr, range(256)))])
def test_native_nanoid_batches_support_multibyte_and_control_characters(alphabet):
    values = fuda.NanoIDGenerator(33, alphabet=alphabet).generate_many(1024, parallel=True)
    assert all(len(value) == 33 and set(value) <= set(alphabet) for value in values)

def test_concurrent_batches_share_generators_and_codecs():
    source = fuda.Cuid2Generator()
    codec = fuda.Hashids(salt='concurrent workers')
    rows = [[index] for index in range(1024)]
    def generate(_):
        encoded = codec.encode_many(rows, parallel=True)
        assert codec.decode_many(encoded, parallel=True) == rows
        return source.generate_many(1024, parallel=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(generate, range(8)))
    values = [value for batch in batches for value in batch]
    assert len(values) == len(set(values)) == 8192
