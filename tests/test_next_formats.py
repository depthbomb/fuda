from copy import copy, deepcopy
from importlib import import_module
from json import loads
from pathlib import Path
from uuid import UUID
from subprocess import run
from sys import executable
from concurrent.futures import ThreadPoolExecutor
from pytest import mark, raises
from hypothesis import given, strategies as st
from fuda import (
    UPID, SNO, UUID25, Flake128, HyperID, CIDv0, CIDv1, Multihash, NI, NIH, SWHID,
    UPIDGenerator, SNOGenerator, HyperIDGenerator, Flake128Generator,
    Hashids, DirectoryEntry, cidv0, multihash, ni, nih, swhid,
    parse, inspect, validate,
)
from fuda.identifiers.sno import SNO_EPOCH

FIXTURE = loads((Path(__file__).parent / 'fixtures' / 'next-reference.json').read_text())

@mark.parametrize('name,cls', [('upid', UPID), ('uuid25', UUID25), ('sno', SNO)])
def test_reference_binary_vectors(name, cls):
    for row in FIXTURE[name]:
        raw = bytes.fromhex(row['hex'])
        value = cls.from_bytes(raw)
        assert str(value) == row['text']
        assert cls.from_str(row['text']).bytes == raw
        if name == 'sno':
            assert (value.timestamp_ms, value.metadata, value.sequence) == (row['timestamp_ms'], row['metadata'], row['sequence'])

def test_reference_hashids_vectors():
    for row in FIXTURE['hashids']:
        codec = Hashids(salt=row['salt'], alphabet=row['alphabet'], min_length=row['min_length'])
        assert codec.encode(row['numbers']) == row['text']
        assert codec.decode(row['text']) == row['numbers']

def test_reference_content_vectors():
    for row in FIXTURE['content']:
        data = bytes.fromhex(row['hex'])
        assert str(cidv0(data)) == row['cidv0']
        assert multihash(data).bytes.hex() == row['multihash_hex']

def test_reference_hyperid_vectors(monkeypatch):
    for row in FIXTURE['hyperid']:
        uuid = UUID(row['uuid'])
        monkeypatch.setattr('fuda.identifiers.hyper.uuid4', lambda value=uuid: value)
        source = HyperIDGenerator(url_safe=row['url_safe'], fixed_length=row['fixed_length'], start=row['start'])
        assert source.generate_many(2) == row['ids']
        for count, value in enumerate(row['ids'], row['start']):
            assert HyperID.from_str(value) == HyperID(uuid, count)

def test_reference_swh_objects():
    for row in FIXTURE['swh']:
        data = bytes.fromhex(row['hex'])
        cnt = swhid(data)
        directory = SWHID.from_directory([DirectoryEntry(b'a', cnt), DirectoryEntry(b'b', cnt, 0o100755)])
        person = b'Reese <reese@example.com>'
        rev = SWHID.from_revision(directory, author=person, committer=person, message=data, extra_headers=((b'gpgsig', b'one\ntwo'),))
        rel = SWHID.from_release(rev, name=b'v1', tagger=person, message=data)
        snp = SWHID.from_snapshot({b'HEAD': b'refs/heads/master', b'refs/heads/master': rev, b'empty': None, b'tag': rel})
        for kind, value in [('cnt', cnt), ('dir', directory), ('rev', rev), ('rel', rel), ('snp', snp)]:
            assert str(value) == row[kind]
            assert SWHID.from_str(row[kind]) == value

@mark.parametrize('cls,bits', [(UPID, 128), (UUID25, 128), (SNO, 80), (Flake128, 128)])
@given(st.integers(min_value=0, max_value=2**128 - 1))
def test_binary_roundtrips(cls, bits, number):
    value = cls(number % 2**bits)
    assert cls.from_str(str(value)) == value
    assert cls.from_bytes(value.bytes) == value
    if cls is Flake128:
        assert cls.from_base62(value.to_base62()) == value
    if cls in (UPID, UUID25):
        assert cls.from_uuid(value.to_uuid()) == value

@mark.parametrize('cls', [UPID, UUID25, SNO, Flake128])
def test_binary_invalid(cls):
    valid = str(cls(0))
    for value in ('', valid[:-1], valid + '0', '\n' + valid, 'é' * len(valid)):
        with raises(ValueError):
            cls.from_str(value)
    for value in (-1, 2**128, True, 1.5):
        with raises((ValueError, TypeError)):
            cls(value)
    with raises(TypeError):
        cls.from_str(None)

def test_upid_time_entropy_prefix(monkeypatch):
    monkeypatch.setattr(import_module('fuda.identifiers.upid'), 'urandom', lambda size: b'\xff' * size)
    value = UPIDGenerator('usr', clock=lambda: 1700000000255).generate()
    assert value.prefix == 'usrz'
    assert value.version == 6
    assert value.randomness == 2**64 - 1
    assert value.timestamp_ms == (1700000000255 >> 8) << 8
    for prefix in ('', 'longer', 'A', '_', '01'):
        with raises(ValueError):
            UPIDGenerator(prefix)
    with raises(ValueError):
        UPID.from_str(str(value)[:-1] + 'z')

def test_sno_clock_and_exhaustion():
    now = [SNO_EPOCH + 400]
    source = SNOGenerator(42, metadata=7, sequence_min=5, sequence_max=6, clock=lambda: now[0])
    first, second = source.generate_many(2)
    assert (first.partition, first.metadata, first.sequence, second.sequence) == (42, 7, 5, 6)
    with raises(OverflowError):
        source.generate()
    now[0] -= 4
    rollback = source.generate()
    assert rollback.tick_tock == 1 and rollback.sequence == 5
    now[0] -= 4
    with raises(RuntimeError, match='rollback'):
        source.generate()
    now[0] += 16
    forward = source.generate()
    now[0] -= 4
    assert source.generate().tick_tock == 0
    assert forward > rollback

def test_flake_layout_and_overflow():
    now = [1700000000000]
    source = Flake128Generator(0x010203040506, clock=lambda: now[0])
    first = source.generate()
    assert first.bytes == now[0].to_bytes(8, 'big') + bytes.fromhex('0102030405060000')
    assert first.node_id == 0x010203040506 and first.timestamp_ms == now[0]
    source._sequence = 65535
    with raises(OverflowError):
        source.generate()
    now[0] -= 1
    with raises(RuntimeError):
        source.generate()
    now[0] += 2
    assert source.generate().sequence == 0
    for value in ('', '00', 'z' * 22, 'é'):
        with raises(ValueError):
            Flake128.from_base62(value)

@mark.parametrize('factory', [UPIDGenerator, HyperIDGenerator, lambda: SNOGenerator(3), lambda: Flake128Generator(3)])
def test_thread_safety_and_copy(factory):
    source = factory()
    with ThreadPoolExecutor(8) as pool:
        ids = list(pool.map(lambda _: str(source.generate()), range(2000)))
    assert len(set(ids)) == len(ids)
    for operation in (copy, deepcopy):
        with raises(TypeError):
            operation(source)

@mark.parametrize('factory', [lambda: SNOGenerator(1), lambda: Flake128Generator(1)])
def test_assigned_generators_fork_refusal(factory):
    source = factory()
    source._pid = -1
    with raises(RuntimeError, match='fork'):
        source.generate()

def test_hyper_rollover_and_fork():
    source = HyperIDGenerator(max_count=2)
    first, second, third = [HyperID.from_str(value) for value in source.generate_many(3)]
    assert first.uuid == second.uuid and first.counter == 0 and second.counter == 1
    assert third.uuid != first.uuid and third.counter == 0
    source._pid = -1
    child = HyperID.from_str(source.generate())
    assert child.uuid != third.uuid and child.counter == 0

@mark.parametrize('value', ['', 'A' * 22 + '/0', 'ABEiM0RVRneImaq7zN3u/w/00', 'ABEiM0RVRneImaq7zN3u/w/2147483648', 'ABEiM0RVRneImaq7zN3u/w/-1'])
def test_invalid_hyperids(value):
    assert not validate('hyperid', value)

@given(st.lists(st.integers(0, 2**63 - 1), max_size=8), st.integers(0, 255))
def test_hashids_roundtrips(values, length):
    codec = Hashids(salt='test salt', min_length=length)
    assert codec.decode(codec.encode(values)) == values

@given(st.text(alphabet='0123456789abcdefABCDEF', max_size=100))
def test_hashids_hex(value):
    codec = Hashids(salt='hex', min_length=30)
    assert codec.decode_hex(codec.encode_hex(value)) == value.lower()

def test_hashids_invalid():
    for options in ({'alphabet': 'short'}, {'alphabet': 'a' * 16}, {'alphabet': 'abcdefghijklmnop '}, {'min_length': -1}, {'salt': None}):
        with raises((ValueError, TypeError)):
            Hashids(**options)
    codec = Hashids()
    for values in ([-1], [True], [2**63], [1.0]):
        with raises((ValueError, TypeError)):
            codec.encode(values)
    for text in ('?', 'hello', 'jR '):
        with raises(ValueError):
            codec.decode(text)
    with raises(ValueError):
        codec.decode_hex(codec.encode([0]))

@mark.parametrize('name', ['identity', 'sha2-256', 'sha2-512', 'sha3-256', 'blake2b-256'])
@given(st.binary(max_size=200))
def test_multihash_roundtrips(name, data):
    value = multihash(data, hash_name=name)
    assert Multihash.from_bytes(value.bytes) == value
    for base in ('base58btc', 'base16', 'base32', 'base64url'):
        assert Multihash.from_str(value.to_base(base)) == value
    assert value.verify(data)
    assert not value.verify(data + b'!')

def test_cid_conversions_and_invalid():
    value = cidv0(b'block bytes')
    assert value.to_v1().to_v0() == value
    assert value.to_v1().multihash == value.multihash
    assert CIDv0.from_bytes(value.bytes) == value
    assert value.verify(b'block bytes') and not value.verify(b'other')
    for raw in (b'', b'\x12\x20', value.bytes + b'!', b'\x92\x00' + value.bytes[1:]):
        with raises(ValueError):
            CIDv0.from_bytes(raw)
        with raises(ValueError):
            Multihash.from_bytes(raw)
    with raises(ValueError):
        CIDv1.from_content(b'raw').to_v0()
    with raises(ValueError):
        CIDv1.from_content(b'x', codec='dag-pb', hash_name='sha3-256').to_v0()
    unknown = Multihash(123456, b'123')
    assert Multihash.from_str(str(unknown)) == unknown
    with raises(ValueError):
        unknown.verify(b'123')
    truncated = multihash(b'hello', digest_size=12)
    assert truncated.verify(b'hello') and not truncated.verify(b'bye')
    with raises(ValueError):
        multihash(b'hello', hash_name='identity', digest_size=3)

def test_rfc6920_vectors():
    expected = 'ni:///sha-256;f4OxZX_x_FO5LcGBSKHWXfwtSx-j1ncoSt3SABJtkGk'
    assert str(ni(b'Hello World!')) == expected
    names = [
        'nih:sha-256-120;5326-9057-e12f-e2b7-4ba0-7c89-2560-a2;f',
        'nih:3;532690-57e12f-e2b74b-a07c89-2560a2;f',
    ]
    assert NIH.from_str(names[0]) == NIH.from_str(names[1])
    assert NIH.from_str(names[0]).bytes.hex() == '0353269057e12fe2b74ba07c892560a2'
    assert str(NIH.from_str('nih:sha-256-32;53269057;b')) == 'nih:sha-256-32;5326-9057;b'

@mark.parametrize('algorithm', ['sha-256','sha-256-128','sha-256-120','sha-256-96','sha-256-64','sha-256-32','sha-384','sha-512','sha3-224','sha3-256','sha3-384','sha3-512','blake2b-256','blake2b-512','blake2s-256'])
def test_ni_nih_algorithms(algorithm):
    value = ni(b'data', algorithm=algorithm, authority='example.com:443', query='ct=text/plain&x=%E6%9C%AD')
    assert NI.from_str(str(value)) == value
    assert value.verify(b'data') and not value.verify(b'other')
    human = value.to_nih()
    assert NIH.from_str(str(human)) == human
    assert value.same_content(human) and human.to_ni() == value
    assert NI.from_content(b'data', algorithm=algorithm) == value
    if algorithm.startswith('blake'):
        with raises(ValueError):
            _ = value.bytes
    else:
        assert NI.from_bytes(value.bytes) == value
        assert NIH.from_bytes(human.bytes) == human
        assert NI.from_bytes(bytes([value.bytes[0] | 192]) + value.bytes[1:]) == value
        assert NIH.from_str(human.to_str(numeric_algorithm=True, group_size=0, checkdigit=False)) == human

def test_ni_parse_only_k12_and_malformed():
    value = NI('k12-256', bytes(32))
    assert NI.from_str(str(value)) == value
    with raises(ValueError, match='external'):
        value.verify(b'data')
    for text in ('ni:///sha-256;x', 'ni:///sha-256;AA==', 'ni:///unknown;AA', str(ni(b'x')) + '?a=%', str(ni(b'x')) + '\n'):
        assert not validate('ni', text)
    for text in ('nih:6;53269057;a', 'nih:6;FFFFFFFF', 'nih:0;53269057', 'nih:sha-256;00', 'nih:6;----;0'):
        assert not validate('nih', text)

def test_swh_empty_objects_context_and_sorting():
    assert str(swhid(b'')) == 'swh:1:cnt:e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'
    directory = SWHID.from_directory([])
    assert str(directory) == 'swh:1:dir:4b825dc642cb6eb9a060e54bf8d69288fbee4904'
    assert str(SWHID.from_snapshot({})) == 'swh:1:snp:1a8893e6a86f444e8be8e7bda6cb34fb1735a00e'
    content = swhid(b'hello')
    snapshot = SWHID.from_snapshot({b'master': content})
    qualified = content.with_context(origin='https://example.com/a%20b;x', visit=snapshot, anchor=directory, path=b'/a;\xff', lines=(1, 20))
    assert SWHID.from_str(str(qualified)) == qualified
    assert qualified.core == content and qualified.verify(b'hello')
    entries = [DirectoryEntry(b'a', directory, 0o40000), DirectoryEntry(b'a.c', content), DirectoryEntry(b'a0', content)]
    expected = b'100644 a.c\0' + content.digest + b'40000 a\0' + directory.digest + b'100644 a0\0' + content.digest
    assert SWHID.from_directory(reversed(entries)) == SWHID.from_object(expected, object_type='dir')

def test_swh_rejects_invalid_objects():
    content = swhid(b'')
    for name in (b'', b'/', b'a\0b'):
        with raises(ValueError):
            DirectoryEntry(name, content)
    with raises(ValueError):
        DirectoryEntry(b'a', content, 0o40000)
    with raises(ValueError):
        SWHID.from_directory([DirectoryEntry(b'a', content)] * 2)
    for branches in ({b'HEAD': b'missing'}, {b'HEAD': b'HEAD'}, {b'a': b'b', b'b': b'a'}):
        with raises(ValueError):
            SWHID.from_snapshot(branches)
    for options in ({'visit': content}, {'anchor': content}, {'path': b'relative'}, {'lines': (5, 2)}, {'lines': (0, None)}):
        with raises(ValueError):
            content.with_context(**options)
    for suffix in (';unknown=x', ';path=/%xx', ';lines=x', ';lines=1;lines=2'):
        assert not validate('swhid', str(content) + suffix)

def test_registry_parse_inspect():
    values = {'upid': UPIDGenerator().generate(), 'sno': SNOGenerator(1).generate(), 'flake128': Flake128Generator(1).generate(),
              'uuid25': UUID25(123), 'hyperid': HyperIDGenerator().generate(), 'hashids': Hashids().encode([1, 2]),
              'cidv0': cidv0(b'block'), 'multihash': multihash(b'x'), 'ni': ni(b'x'), 'nih': nih(b'x'), 'swhid': swhid(b'x')}
    for name, value in values.items():
        text = str(value)
        assert validate(name, text)
        assert str(parse(name, text)) == text
        assert inspect(name, text)['canonical'] == text
    assert inspect('hashids', values['hashids'])['numbers'] == [1, 2]
    assert inspect('sno', str(values['sno']))['partition'] == 1

@mark.parametrize('name', ['upid','sno','flake128','uuid25','hyperid','hashids','cidv0','multihash','ni','nih','swhid'])
@given(st.text(max_size=150))
def test_validate_never_leaks_parser_errors(name, text):
    assert isinstance(validate(name, text), bool)

@mark.parametrize('args,format', [
    (['generate','upid','--prefix','user'], 'upid'),
    (['generate','sno','--partition','4','--metadata','9'], 'sno'),
    (['generate','flake128','--node-id','3'], 'flake128'),
    (['generate','hyperid','--url-safe','--fixed-length'], 'hyperid'),
    (['encode','uuid25','00112233-4455-6677-8899-aabbccddeeff'], 'uuid25'),
    (['encode','hashids','1','2'], 'hashids'),
    *[(['content', name, '--text', 'hello'], name) for name in ('cidv0','cidv1','multihash','ni','nih','swhid')],
])
def test_cli_new_formats(args, format):
    result = run([executable, '-m', 'fuda', *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert validate(format, result.stdout.strip())

@mark.parametrize('args', [
    ['content', 'cidv0', '--text', 'hello', '--hash', 'sha2-512'],
    ['content', 'nih', '--text', 'hello', '--authority', 'example.com'],
    ['content', 'swhid', '--text', 'hello', '--base', 'base32'],
])
def test_cli_rejects_unused_content_options(args):
    result = run([executable, '-m', 'fuda', *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'not supported' in result.stderr
    assert not result.stdout
