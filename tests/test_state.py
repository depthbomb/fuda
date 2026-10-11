from os import getpid
from pickle import dumps
from copy import copy, deepcopy
from pytest import mark, raises
from concurrent.futures import ThreadPoolExecutor
from fuda import ULIDGenerator, UUID7Generator, ObjectIDGenerator, XIDGenerator, TSIDGenerator, SnowflakeGenerator, Cuid2Generator
from fuda.identifiers.stateful import TSID_EPOCH

@mark.parametrize('factory', [ULIDGenerator, UUID7Generator])
def test_monotonic_clock_rollback(factory):
    clock = iter([100, 100, 99, 101])
    generator = factory(clock=lambda: next(clock))
    values = generator.generate_many(4)
    assert values == sorted(values)
    assert len(set(values)) == 4
    assert len({value.int >> 80 if hasattr(value, 'int') else value.timestamp_ms for value in values}) == 2

def test_counter_exhaustion():
    ulids = ULIDGenerator(clock=lambda: 100)
    ulids.generate()
    ulids._random = (1 << 80) - 1
    with raises(OverflowError):
        ulids.generate()
    uuids = UUID7Generator(clock=lambda: 100)
    uuids.generate()
    uuids._random = (1 << 74) - 1
    assert uuids.generate().int >> 80 == 101

@mark.parametrize('timestamp', [0, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF])
def test_objectid_unsigned_timestamp(timestamp):
    generator = ObjectIDGenerator(clock=lambda: timestamp)
    generator._counter = 0xFFFFFF
    first, second = generator.generate_many(2)
    assert first.timestamp == second.timestamp == timestamp
    assert first.bytes[-3:] == b'\xff' * 3
    assert second.bytes[-3:] == b'\x00' * 3
    assert first.bytes[4:9] == second.bytes[4:9]
    assert not hasattr(first, 'counter')

def test_xid_fields():
    generator = XIDGenerator(machine_id=b'abc', clock=lambda: 0x80000000)
    generator._counter = 0xFFFFFF
    value = generator.generate()
    assert value.counter == 0
    assert value.process_id == getpid() & 0xFFFF
    assert value.machine_id == b'abc'
    assert value.timestamp == 0x80000000

def test_snowflake_exhaustion_rollback_and_inspection():
    clock = [100]
    generator = SnowflakeGenerator(3, epoch=0, sequence_bits=2, clock=lambda: clock[0])
    values = generator.generate_many(4)
    assert generator.inspect(values[-1]) == {'timestamp_ms': 100, 'node_id': 3, 'sequence': 3}
    with raises(OverflowError):
        generator.generate()
    clock[0] = 99
    with raises(RuntimeError):
        generator.generate()
    clock[0] = 101
    assert generator.generate() > values[-1]

def test_tsid_logical_clock():
    generator = TSIDGenerator(1, node_bits=20, clock=lambda: TSID_EPOCH)
    generator.generate()
    generator._counter = 3
    result = generator.generate()
    assert result.timestamp_ms == TSID_EPOCH + 1
    assert result.random_part == 4

@mark.parametrize('factory', [ULIDGenerator, UUID7Generator, ObjectIDGenerator, XIDGenerator, TSIDGenerator, Cuid2Generator])
def test_thread_safety(factory):
    generator = factory()
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: generator.generate(), range(3000)))
    assert len(set(values)) == 3000

@mark.parametrize('factory', [ULIDGenerator, UUID7Generator, ObjectIDGenerator, XIDGenerator, TSIDGenerator, Cuid2Generator])
def test_process_change_reseeds_without_inherited_lock(factory, monkeypatch):
    generator = factory()
    before = generator.generate()
    generator._lock.acquire()
    generator._pid = -1
    after = generator.generate()
    assert before != after
    assert generator._pid == getpid()

@mark.parametrize('generator', [SnowflakeGenerator(1), TSIDGenerator(1)])
def test_explicit_nodes_refuse_fork(generator):
    generator._pid = -1
    for _ in range(2):
        with raises(RuntimeError, match='distinct node_id'):
            generator.generate()

def test_generators_cannot_duplicate_state():
    generator = Cuid2Generator()
    for operation in (copy, deepcopy, dumps):
        with raises(TypeError):
            operation(generator)

def test_real_fork():
    import os
    if not hasattr(os, 'fork'):
        import pytest
        pytest.skip('fork is not available on this platform')
    generator = ObjectIDGenerator()
    before = generator.generate()
    reader, writer = os.pipe()
    generator._lock.acquire()
    pid = os.fork()
    if pid == 0:
        os.close(reader)
        try:
            os.write(writer, generator.generate().bytes)
        finally:
            os._exit(0)
    generator._lock.release()
    os.close(writer)
    try:
        data = os.read(reader, 12)
        _, status = os.waitpid(pid, 0)
        assert status == 0
        assert data[4:9] != before.bytes[4:9]
    finally:
        os.close(reader)
