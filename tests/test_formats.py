from json import loads
from pathlib import Path
from uuid import UUID, NAMESPACE_DNS
from pytest import mark, raises
from hypothesis import given, strategies as st
from fuda import (
    ULID, KSUID, XID, TSID, ObjectID, TypeID, XUID, uuid3, uuid5, uuid6, uuid8,
    typeid, xuid, ksuid, nanoid, shortuuid, decode_shortuuid, parse, validate, detect, inspect,
)

fixtures = Path(__file__).parent / 'fixtures'

@mark.parametrize('case', loads((fixtures / 'valid-typeid.json').read_text(encoding='utf-8')))
def test_official_typeid_valid(case):
    value = TypeID.from_str(case['typeid'])
    assert value.prefix == case['prefix']
    assert value.uuid == UUID(case['uuid'])
    assert str(value) == case['typeid']

@mark.parametrize('case', loads((fixtures / 'invalid-typeid.json').read_text(encoding='utf-8')))
def test_official_typeid_invalid(case):
    with raises(ValueError):
        TypeID.from_str(case['typeid'])

@mark.parametrize('cls,bits', [(ULID, 128), (KSUID, 160), (XID, 96), (ObjectID, 96), (TSID, 64)])
@given(data=st.data())
def test_binary_roundtrip(cls, bits, data):
    integer = data.draw(st.integers(0, (1 << bits) - 1))
    value = cls(integer)
    assert cls.from_str(str(value)) == value
    assert cls.from_bytes(value.bytes) == value
    assert int(value) == integer

@given(st.integers(0, (1 << 128) - 1))
def test_uuid_codecs(value):
    uuid = UUID(int=value)
    assert decode_shortuuid(shortuuid(uuid)) == uuid
    assert TypeID.from_str(str(typeid('a__b', value=uuid))).uuid == uuid
    assert XUID.from_str(str(xuid('item', value=uuid))).uuid == uuid
    assert ULID.from_uuid(uuid).to_uuid() == uuid

def test_known_vectors():
    assert str(xuid('shell', value=UUID('3f1b4d37-34d9-46c6-b546-a57c5f736d22'))) == 'shell-h4nu2n-zu3f-dmnn-kguv-6f643nei'
    assert str(xuid('null', value=UUID(int=0))) == 'null-aaaaaa-aaaa-aaaa-aaaa-aaaaaaaa'
    assert str(xuid(value=UUID(int=0))) == 'aaaaaa-aaaa-aaaa-aaaa-aaaaaaaa'
    assert str(ULID((1 << 128) - 1)) == '7ZZZZZZZZZZZZZZZZZZZZZZZZZ'
    assert str(TSID((1 << 64) - 1)) == 'FZZZZZZZZZZZZ'
    assert ULID.from_str('01ARZ3NDEKTSV4RRFFQ69G5FAV').timestamp_ms == 1469922850259
    assert str(uuid3(NAMESPACE_DNS, 'www.example.com')) == '5df41881-3aed-3515-88a7-2f4a814cf09e'
    assert str(uuid5(NAMESPACE_DNS, 'www.example.com')) == '2ed6657d-e927-568b-95e1-2665a8aea6a2'
    assert str(uuid8(0x2489e9ad2ee2, 0xe00, 0x0ec932d5f69181c0)) == '2489e9ad-2ee2-8e00-8ec9-32d5f69181c0'

def test_uuid6_reorders_reference(monkeypatch):
    monkeypatch.setattr('fuda.identifiers.uuids.uuid1', lambda **_: UUID('c232ab00-9414-11ec-b3c8-9f6bdeced846'))
    assert str(uuid6()) == '1ec9414c-232a-6b00-b3c8-9f6bdeced846'

@mark.parametrize('cls,value', [
    (ULID, '8' + '0' * 25), (ULID, 'I' * 26), (XID, '0' * 19 + '1'),
    (KSUID, 'z' * 27), (TSID, 'G' + '0' * 12), (ObjectID, 'g' * 24),
    (TypeID, 'User_' + '0' * 26), (XUID, 'aaaaaa-aaaa-aaaa-aaaa-aaaaaaab'),
    (XUID, 'ſaaaaa-aaaa-aaaa-aaaa-aaaaaaaa'),
])
def test_reject_noncanonical_bits(cls, value):
    with raises(ValueError):
        cls.from_str(value)

def test_metadata_and_shape_ambiguity():
    value = str(ULID(0))
    assert {'ulid', 'nanoid', 'typeid'} <= set(detect(value))
    assert inspect('ulid', value)['timestamp_ms'] == 0
    assert not validate('cuid2', 'A123')
    assert not validate('cuid2', 'a123\n')
    assert not validate('ulid', 1)
    with raises(ValueError):
        validate('bogus', 'anything')
    assert parse('shortuuid', shortuuid(UUID(int=0))) == UUID(int=0)

def test_custom_nanoid_and_ksuid():
    for alphabet in ('abc', '札番号', '0123456789abcdef'):
        value = nanoid(79, alphabet=alphabet)
        assert len(value) == 79
        assert set(value) <= set(alphabet)
    for alphabet in ('', 'a', 'aaa', '\ud800a'):
        with raises(ValueError):
            nanoid(alphabet=alphabet)
    assert ksuid(timestamp=1_400_000_000).timestamp == 1_400_000_000

@mark.parametrize('case', loads((fixtures / 'xuid-reference.json').read_text(encoding='utf-8')))
def test_go_xuid_reference(case):
    if 'key' in case:
        result = XUID.from_key(case['key'], case.get('prefix'))
    else:
        result = XUID.from_uuid(UUID(case['uuid']), case['prefix'])
    assert str(result) == case['xuid'].rstrip('\x00')
    assert result.uuid == UUID(case['uuid'])
