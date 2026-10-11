import fuda
from json import loads
from copy import copy, deepcopy
from pickle import dumps
from sys import executable
from subprocess import run
from itertools import islice
from uuid import UUID, NAMESPACE_DNS, uuid3, uuid5
from pytest import mark, raises
from fuda.cli import _GENERATORS

GENERATORS = [
    ('cuid2', fuda.Cuid2Generator, {}),
    ('flake128', fuda.Flake128Generator, {'node_id': 7}),
    ('hyperid', fuda.HyperIDGenerator, {}),
    ('ksuid', fuda.KSUIDGenerator, {}),
    ('nanoid', fuda.NanoIDGenerator, {}),
    ('nuid', fuda.NUIDGenerator, {}),
    ('objectid', fuda.ObjectIDGenerator, {}),
    ('pushid', fuda.PushIDGenerator, {}),
    ('scru64', fuda.SCRU64Generator, {'node_id': 7}),
    ('scru128', fuda.SCRU128Generator, {}),
    ('shortuuid', fuda.ShortUUIDGenerator, {}),
    ('sno', fuda.SNOGenerator, {'partition': 7}),
    ('snowflake', fuda.SnowflakeGenerator, {'node_id': 7}),
    ('sonyflake', fuda.SonyflakeGenerator, {'node_id': 7}),
    ('tid', fuda.TIDGenerator, {}),
    ('timeflake', fuda.TimeflakeGenerator, {}),
    ('tsid', fuda.TSIDGenerator, {}),
    ('typeid', fuda.TypeIDGenerator, {'prefix': 'user'}),
    ('ulid', fuda.ULIDGenerator, {}),
    ('upid', fuda.UPIDGenerator, {'prefix': 'user'}),
    ('uuid1', fuda.UUID1Generator, {}),
    ('uuid3', fuda.UUID3Generator, {'namespace': NAMESPACE_DNS, 'name': 'example.com'}),
    ('uuid4', fuda.UUID4Generator, {}),
    ('uuid5', fuda.UUID5Generator, {'namespace': NAMESPACE_DNS, 'name': 'example.com'}),
    ('uuid6', fuda.UUID6Generator, {}),
    ('uuid7', fuda.UUID7Generator, {}),
    ('uuid8', fuda.UUID8Generator, {}),
    ('xid', fuda.XIDGenerator, {}),
    ('xuid', fuda.XUIDGenerator, {'prefix': 'user'}),
]

def test_every_generatable_format_has_a_public_class_and_cli_entry():
    registered = {item.name for item in fuda.formats() if item.kind == 'generator'}
    assert registered == set(_GENERATORS) == {name for name, _, _ in GENERATORS}
    assert len(registered) == 29
    for name, cls, _ in GENERATORS:
        assert cls.__name__ in fuda.__all__
        assert _GENERATORS[name] is cls

@mark.parametrize('name,cls,options', GENERATORS)
def test_generator_interface(name, cls, options):
    source = cls(**options)
    values = [source.generate(), *source.generate_many(2), *source.iter_ids(2)]
    assert all(fuda.validate(name, str(value)) for value in values)
    assert source.generate_many(0) == []
    assert list(source.iter_ids(0)) == []
    assert len(list(islice(source.iter_ids(), 3))) == 3

@mark.parametrize('name,cls,options', GENERATORS)
def test_generator_count_errors(name, cls, options):
    source = cls(**options)
    for count in (-1, True, 1.5, '2'):
        with raises((TypeError, ValueError)):
            source.generate_many(count)
        with raises((TypeError, ValueError)):
            list(source.iter_ids(count))
    with raises(ValueError):
        source.generate_many(1_000_001)

@mark.parametrize('name,cls,options', GENERATORS)
def test_generators_cannot_duplicate_state(name, cls, options):
    source = cls(**options)
    for clone in (copy, deepcopy, dumps):
        with raises(TypeError):
            clone(source)

@mark.parametrize('cls,reference', [(fuda.UUID3Generator, uuid3), (fuda.UUID5Generator, uuid5)])
def test_named_uuid_generators(cls, reference):
    expected = reference(NAMESPACE_DNS, 'example.com')
    source = cls(NAMESPACE_DNS, 'example.com')
    assert source.generate_many(3) == [expected] * 3
    assert cls(NAMESPACE_DNS, 'another.example.com').generate() != expected
    with raises(TypeError, match='namespace'):
        cls('not-a-uuid', 'example.com')
    with raises(TypeError, match='name'):
        cls(NAMESPACE_DNS, b'example.com')

@mark.parametrize('cls,version', [(fuda.UUID1Generator, 1), (fuda.UUID6Generator, 6)])
def test_uuid_node_configuration(cls, version):
    value = cls(node=0x010203040506, clock_seq=123).generate()
    assert value.version == version
    assert value.node == 0x010203040506 and value.clock_seq == 123
    for options in ({'node': -1}, {'node': 1 << 48}, {'clock_seq': 1 << 14}, {'node': True}):
        with raises((TypeError, ValueError)):
            cls(**options)

def test_uuid8_payload_configuration():
    source = fuda.UUID8Generator(a=0x2489e9ad2ee2, b=0xe00, c=0x0ec932d5f69181c0)
    assert source.generate() == UUID('2489e9ad-2ee2-8e00-8ec9-32d5f69181c0')
    assert len(set(fuda.UUID8Generator(a=123).generate_many(20))) == 20
    for options in ({'a': 1 << 48}, {'b': 1 << 12}, {'c': 1 << 62}, {'a': True}):
        with raises((TypeError, ValueError)):
            fuda.UUID8Generator(**options)

def test_ksuid_fixed_time_and_shortuuid_randomness():
    values = fuda.KSUIDGenerator(timestamp=1_400_000_000).generate_many(20)
    assert len(set(values)) == 20
    assert all(value.timestamp == 1_400_000_000 for value in values)
    with raises(ValueError):
        fuda.KSUIDGenerator(timestamp=1_399_999_999)
    uuids = [fuda.decode_shortuuid(value) for value in fuda.ShortUUIDGenerator().generate_many(20)]
    assert len(set(uuids)) == 20 and all(value.version == 4 for value in uuids)

@mark.parametrize('cls', [fuda.TypeIDGenerator, fuda.XUIDGenerator])
def test_prefixed_generators_own_uuid7_state(cls, monkeypatch):
    monkeypatch.setattr('fuda.identifiers.uuids.urandom', lambda count: bytes(count))
    first = cls('user', clock=lambda: 123)
    second = cls('user', clock=lambda: 123)
    values = first.generate_many(3)
    assert all(value.prefix == 'user' and value.uuid.version == 7 for value in values)
    assert values[0].uuid.int < values[1].uuid.int < values[2].uuid.int
    assert second.generate() == values[0]
    assert first.generate().uuid.int == values[-1].uuid.int + 1

@mark.parametrize('cls', [fuda.SnowflakeGenerator, fuda.SonyflakeGenerator, fuda.SCRU64Generator, fuda.Flake128Generator, fuda.SNOGenerator])
def test_node_assignments_are_required_at_construction(cls):
    with raises(TypeError):
        cls()

@mark.parametrize('cls,options', [(fuda.TypeIDGenerator, {'prefix': 'Bad'}), (fuda.XUIDGenerator, {'prefix': 'too-long'}),
                                 (fuda.NanoIDGenerator, {'length': 0}), (fuda.Cuid2Generator, {'parallel': 1})])
def test_bad_configuration_fails_before_generation(cls, options):
    with raises((TypeError, ValueError)):
        cls(**options)

@mark.parametrize('name,cls,options', GENERATORS)
def test_cli_generator_classes(name, cls, options):
    args = [executable, '-m', 'fuda', 'generate', name, '-n', '2', '--json']
    for key, value in options.items():
        args.extend(['--' + key.replace('_', '-'), str(value)])
    result = run(args, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    values = loads(result.stdout)
    assert len(values) == 2 and all(fuda.validate(name, value) for value in values)

def test_cli_validation():
    result = run([executable, '-m', 'fuda', 'validate', 'cuid2', 'INVALID'], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout.strip() == 'false'
