from copy import copy, deepcopy
from os import environ
from pickle import dumps, loads
from subprocess import run
from sys import executable
from pytest import mark, raises
from hypothesis import given, strategies as st
from fuda import Sqids, Hashids, Proquint
from fuda._core.extension import native as _native
from fuda._core.encoding import BASE36, BASE62, CROCKFORD

from reference_codecs import (
    BASE_PREFIXES, ReferenceHashids, ReferenceSqids, ReferenceProquint,
    multibase_encode, multibase_decode,
)


@mark.parametrize('alphabet', [BASE36, BASE62, CROCKFORD, '01', ''.join(map(chr, range(128)))])
@given(st.integers(0, 2**256 - 1), st.integers(0, 160))
def test_radix_matches_python_at_width_boundaries(alphabet, value, width):
    codec = _native.RadixCodec(alphabet)
    if value >= len(alphabet)**width:
        with raises(ValueError):
            codec.encode_bytes(value.to_bytes(32, 'big'), width)
        if value < 2**128:
            with raises(ValueError):
                codec.encode_u128(value, width)
        return
    remainder, expected = value, ''
    for _ in range(width):
        remainder, digit = divmod(remainder, len(alphabet))
        expected = alphabet[digit] + expected
    assert codec.encode_bytes(value.to_bytes(32, 'big'), width) == expected
    assert int.from_bytes(codec.decode_bytes(expected, width, 256), 'big') == value
    if value < 2**128:
        assert codec.encode_u128(value, width) == expected
        assert codec.decode_u128(expected, width, 128) == value
    if value:
        with raises(ValueError):
            codec.decode_bytes(expected, width, value.bit_length() - 1)

@mark.parametrize('alphabet', ['', 'a', 'aba', 'abcé', 'ab🙂'])
def test_native_rejects_invalid_radix_configuration(alphabet):
    with raises(ValueError):
        _native.RadixCodec(alphabet)

def test_native_radix_rejects_malformed_and_oversized_values():
    codec = _native.RadixCodec(BASE36)
    for text in (' ', '-', '+', '_', 'é', 'Z', '\0'):
        with raises(ValueError):
            codec.decode_u128(text, len(text), 128)
        with raises(ValueError):
            codec.decode_bytes(text, len(text), 160)
    with raises(ValueError):
        codec.decode_u128('z' * 25, 25, 128)
    with raises(ValueError):
        codec.encode_u128(0, 1_000_001)
    with raises(ValueError):
        codec.decode_u128('', 0, 129)
    assert codec.encode_u128(0, 0) == ''
    assert codec.encode_bytes(b'', 0) == ''
    assert codec.decode_u128('', 0, 0) == 0

@given(st.binary(max_size=512))
def test_multibase_matches_python_in_every_supported_base(data):
    for prefix in BASE_PREFIXES.values():
        expected = multibase_encode(data, prefix)
        assert _native.multibase_encode(data, prefix) == expected
        assert _native.multibase_decode(expected) == multibase_decode(expected) == data

@mark.parametrize('data', [b'', b'\0', b'\0' * 32, b'\0\0\1', bytes(range(256))])
def test_multibase_preserves_leading_zero_bytes(data):
    for prefix in 'bBfFzkKmMuU':
        assert _native.multibase_decode(_native.multibase_encode(data, prefix)) == data

@given(st.text(alphabet='bBfFzkKmMuU=+/-_0123456789abcdefABCDEF\n\0🙂', max_size=70))
def test_multibase_invalid_inputs_match_python(text):
    try:
        expected = multibase_decode(text)
    except ValueError:
        with raises(ValueError):
            _native.multibase_decode(text)
    else:
        assert _native.multibase_decode(text) == expected

@mark.parametrize('text', ['bmy======', 'bMY', 'Bmz', 'f0a ', 'f0A', 'F0a', 'mZg==', 'MZg', 'uZh', 'UZg===', 'z0', 'kA', 'Ka'])
def test_multibase_rejects_noncanonical_spelling(text):
    with raises(ValueError):
        _native.multibase_decode(text)

@given(st.binary(min_size=1, max_size=200))
def test_proquint_matches_python(data):
    data += b'\0' if len(data) % 2 else b''
    expected = ReferenceProquint.encode(data)
    assert Proquint.encode(data) == expected
    assert Proquint.decode(expected) == ReferenceProquint.decode(expected) == data

@mark.parametrize('text', ['', '-', 'Babab', 'bAbab', 'ba-bab', 'babab-', 'aaaaa', '🙂abc'])
def test_native_proquint_rejects_bad_words(text):
    with raises(ValueError):
        _native.proquint_decode(text)

@mark.parametrize('alphabet', ['abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890', '0123456789abcdef', ''.join(map(chr, range(33, 127)))])
@given(st.lists(st.integers(0, 2**63 - 1), max_size=20), st.text(max_size=100), st.integers(0, 255))
def test_hashids_matches_python_with_custom_settings(alphabet, values, salt, min_length):
    native = Hashids(alphabet=alphabet, salt=salt, min_length=min_length)
    python = ReferenceHashids(alphabet=alphabet, salt=salt, min_length=min_length)
    encoded = python.encode(values)
    assert native.encode(values) == encoded
    assert native.decode(encoded) == python.decode(encoded) == values

@mark.parametrize('salt', ['\ud800', '\udfff🙂日本語', '🚀' * 200])
def test_hashids_python_codepoints_are_preserved(salt):
    native = Hashids(salt=salt, min_length=30)
    python = ReferenceHashids(salt=salt, min_length=30)
    assert native.encode([42, 0, 2**63 - 1]) == python.encode([42, 0, 2**63 - 1])

@given(st.lists(st.integers(0, 2**63 - 1), max_size=15), st.integers(0, 255), st.permutations('abc0123'))
def test_sqids_matches_python_with_small_alphabets(values, min_length, letters):
    options = dict(alphabet=''.join(letters), min_length=min_length, blocklist=['abc', 'abc0', 'aaaa'])
    native, python = Sqids(**options), ReferenceSqids(**options)
    try:
        encoded = python.encode(values)
    except ValueError:
        with raises(ValueError):
            native.encode(values)
    else:
        assert native.encode(values) == encoded
        assert native.decode(encoded, canonical=True) == python.decode(encoded, canonical=True) == values

@mark.parametrize('alphabet', ['abc', '\0\1\2', ''.join(map(chr, range(128)))])
def test_sqids_control_characters_and_smallest_alphabet(alphabet):
    options = dict(alphabet=alphabet, min_length=255, blocklist=[])
    native, python = Sqids(**options), ReferenceSqids(**options)
    values = [0, 1, 2**63 - 1]
    assert native.encode(values) == python.encode(values)
    assert native.decode(native.encode(values), canonical=True) == values

@mark.parametrize('kind', ['sqids', 'hashids'])
@given(st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!\0é', max_size=70))
def test_native_codec_malformed_inputs_match_python(kind, text):
    native = Sqids() if kind == 'sqids' else Hashids()
    python = ReferenceSqids() if kind == 'sqids' else ReferenceHashids()
    for options in ([{}, {'canonical': True}] if kind == 'sqids' else [{}]):
        try:
            expected = python.decode(text, **options)
        except ValueError:
            with raises(ValueError):
                native.decode(text, **options)
        else:
            assert native.decode(text, **options) == expected

@mark.parametrize('kind', ['sqids', 'hashids'])
def test_accelerated_codecs_can_be_copied_and_pickled(kind):
    codec = Sqids(min_length=30) if kind == 'sqids' else Hashids(min_length=30)
    for duplicate in (copy(codec), deepcopy(codec), loads(dumps(codec))):
        encoded = codec.encode([1, 0, 2**63 - 1])
        assert duplicate.encode([1, 0, 2**63 - 1]) == encoded
        assert duplicate.decode(encoded) == [1, 0, 2**63 - 1]
@given(st.binary(max_size=512))
def test_nih_check_digit_matches_python(data):
    digits = list(reversed(data.hex()))
    total = sum(sum(divmod(int(char, 16) * (2 if index % 2 == 0 else 1), 16)) for index, char in enumerate(digits))
    assert _native.hex_checkdigit(data.hex()) == format(-total % 16, 'x')

@mark.parametrize('value', ['python', 'native', 'auto', 'invalid'])
def test_legacy_environment_variables_do_not_select_an_implementation(value):
    code = "from fuda import Cuid2Generator, Hashids; from fuda._core.extension import native; assert len(Cuid2Generator().generate()) == 24; assert Hashids().decode(Hashids().encode([1])) == [1]"
    result = run([executable, '-c', code], env={**environ, 'FUDA_BACKEND': value, 'FUDA_PURE_PYTHON': '1'}, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr

def test_missing_native_extension_has_an_actionable_error():
    code = """
import sys
from importlib.abc import MetaPathFinder
class MissingExtension(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'fuda._native':
            raise ModuleNotFoundError('simulated missing extension')
sys.meta_path.insert(0, MissingExtension())
import fuda
"""
    result = run([executable, '-c', code], capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert 'Fuda requires its compiled Rust extension' in result.stderr
    assert '--only-binary=fuda' in result.stderr
    assert 'simulated missing extension' in result.stderr

def test_native_codec_configuration_is_checked():
    for alphabet, separators, guards in [('', 'a', 'b'), ('abc', '', 'd'), ('abc', 'd', ''), ('abc', 'a', 'd'), ('aé', 'b', 'c')]:
        with raises(ValueError):
            _native.HashidsCodec(alphabet, separators, guards, [], 0)
    for alphabet in ('', 'a', 'aa', 'aab', 'ab🙂'):
        with raises(ValueError):
            _native.SqidsCodec(alphabet, 0, [], [], [])
