from hashlib import sha3_512
from pytest import mark, raises
from cuid2 import utils as reference
from fuda import Cuid2Generator, is_cuid2
from fuda._core.extension import native as _native
from fuda._core.encoding import base36
from hypothesis import given, strategies as st

@given(st.integers(0, (1 << 512) - 1))
def test_base36(number):
    expected = reference.base36_encode(number)
    assert base36(number) == expected

@given(st.text(alphabet=st.characters(exclude_categories=('Cs',)), max_size=500))
def test_native_hash_matches_reference(data):
    expected = base36(int.from_bytes(sha3_512(data.encode()).digest(), 'big'))
    assert _native.hash_base36(data) == expected
    assert _native.hash_base36(data)[1:] == reference.create_hash(data)

@mark.parametrize('length', [2, 10, 24, 32])
@mark.parametrize('parallel', [False, True])
def test_batch(parallel, length):
    generator = Cuid2Generator(length)
    values = generator.generate_many(300, parallel=parallel)
    assert all(is_cuid2(value, length=length) for value in values)
    if length >= 10:
        assert len(set(values)) == len(values)
    assert generator.generate_many(0) == []
    assert len(list(generator.iter_ids(4))) == 4

@mark.parametrize('length', [0, 1, 33, 98, -1, True, 2.5, '24'])
def test_lengths(length):
    with raises((ValueError, TypeError)):
        Cuid2Generator(length)
    with raises((ValueError, TypeError, OverflowError)):
        _native.cuid2(length, 'host', 1)

def test_batch_and_counter_limits():
    generator = Cuid2Generator()
    for count in (-1, 1_000_001, True):
        with raises((ValueError, TypeError)):
            generator.generate_many(count)
    generator._counter = (1 << 64) - 1
    with raises(OverflowError):
        generator.generate()

def test_exact_length_retry(monkeypatch):
    generator = Cuid2Generator(24)
    results = iter(['short', 'a' * 24])
    monkeypatch.setattr('fuda.identifiers.cuid.native.cuid2', lambda *args: next(results))
    assert generator.generate() == 'a' * 24
    monkeypatch.setattr('fuda.identifiers.cuid.native.cuid2', lambda *args: 'short')
    with raises(RuntimeError, match='exact-length'):
        generator.generate()

def test_batch_retries_short_native_results(monkeypatch):
    monkeypatch.setattr('fuda.identifiers.cuid.native.cuid2_many', lambda *args: ['short', 'a' * 24])
    monkeypatch.setattr('fuda.identifiers.cuid.native.cuid2', lambda *args: 'b' * 24)
    assert Cuid2Generator().generate_many(2) == ['b' * 24, 'a' * 24]
