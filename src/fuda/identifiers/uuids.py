from os import urandom
from time import time_ns
from collections.abc import Callable
from fuda._core.encoding import integer
from uuid import UUID, uuid1, uuid3, uuid4, uuid5
from fuda._core.state import Generator, ProcessGenerator

__all__ = [
    'UUID1Generator',
    'UUID3Generator',
    'UUID4Generator',
    'UUID5Generator',
    'UUID6Generator',
    'UUID7Generator',
    'UUID8Generator',
    'uuid1',
    'uuid3',
    'uuid4',
    'uuid5',
    'uuid6',
    'uuid7',
    'uuid8',
]

def _node_options(node: int | None, clock_seq: int | None) -> None:
    if node is not None:
        integer(node, 'node', 0, (1 << 48) - 1)
    if clock_seq is not None:
        integer(clock_seq, 'clock_seq', 0, (1 << 14) - 1)

def _name_options(namespace: UUID, name: str) -> None:
    if not isinstance(namespace, UUID):
        raise TypeError('namespace must be a UUID')
    if not isinstance(name, str):
        raise TypeError('name must be a string')

class UUID1Generator(Generator[UUID]):
    """Generate time-based UUIDs with optional node and clock sequence settings."""

    def __init__(self, *, node: int | None = None, clock_seq: int | None = None) -> None:
        _node_options(node, clock_seq)
        self._node, self._clock_seq = node, clock_seq

    def generate(self) -> UUID:
        return uuid1(node=self._node, clock_seq=self._clock_seq)

class UUID3Generator(Generator[UUID]):
    """Return the deterministic MD5 UUID for a configured namespace and name."""

    def __init__(self, namespace: UUID, name: str) -> None:
        _name_options(namespace, name)
        self._value = uuid3(namespace, name)

    def generate(self) -> UUID:
        return self._value

class UUID4Generator(Generator[UUID]):
    """Generate random UUIDs using operating-system entropy."""

    def generate(self) -> UUID:
        return uuid4()

class UUID5Generator(Generator[UUID]):
    """Return the deterministic SHA-1 UUID for a configured namespace and name."""

    def __init__(self, namespace: UUID, name: str) -> None:
        _name_options(namespace, name)
        self._value = uuid5(namespace, name)

    def generate(self) -> UUID:
        return self._value

class UUID6Generator(Generator[UUID]):
    """Generate reordered time-based UUIDs with optional node settings."""

    def __init__(self, *, node: int | None = None, clock_seq: int | None = None) -> None:
        _node_options(node, clock_seq)
        self._node, self._clock_seq = node, clock_seq

    def generate(self) -> UUID:
        return uuid6(node=self._node, clock_seq=self._clock_seq)

class UUID8Generator(Generator[UUID]):
    """Generate UUIDv8 values, filling unspecified payload fields with randomness."""

    def __init__(self, *, a: int | None = None, b: int | None = None, c: int | None = None) -> None:
        for name, value, bits in (('a', a, 48), ('b', b, 12), ('c', c, 62)):
            if value is not None:
                integer(value, name, 0, (1 << bits) - 1)
        self._a, self._b, self._c = a, b, c

    def generate(self) -> UUID:
        return uuid8(self._a, self._b, self._c)

class UUID7Generator(ProcessGenerator[UUID]):
    """Monotonic within one generator, using logical time during clock rollback."""

    def __init__(self, *, clock: Callable[[], int] | None = None) -> None:
        super().__init__()
        self._clock = clock or (lambda: time_ns() // 1_000_000)
        self._last_ms = -1
        self._random = 0

    def _reset_process(self) -> None:
        self._last_ms = -1
        self._random = 0

    def generate(self) -> UUID:
        self._check_process()
        with self._lock:
            now = integer(self._clock(), 'timestamp', 0, (1 << 48) - 1)
            if now <= self._last_ms:
                now = self._last_ms
                random = self._random + 1
                if random >= 1 << 74:
                    now += 1
                    if now >= 1 << 48:
                        raise OverflowError('UUIDv7 timestamp exhausted')
                    random = int.from_bytes(urandom(10), 'big') & ((1 << 74) - 1)
            else:
                random = int.from_bytes(urandom(10), 'big') & ((1 << 74) - 1)
            self._last_ms, self._random = now, random
            value = (now << 80) | (7 << 76) | ((random >> 62) << 64) | (2 << 62) | (random & ((1 << 62) - 1))

        return UUID(int=value)

_uuid7_generator = UUID7Generator()

def uuid7() -> UUID:
    return _uuid7_generator.generate()

def uuid6(node: int | None = None, clock_seq: int | None = None) -> UUID:
    original = uuid1(node=node, clock_seq=clock_seq)
    timestamp = original.time
    value = ((timestamp >> 12) << 80) | (6 << 76) | ((timestamp & 0xFFF) << 64) | (original.int & ((1 << 64) - 1))

    return UUID(int=value)

def uuid8(a: int | None = None, b: int | None = None, c: int | None = None) -> UUID:
    random = int.from_bytes(urandom(16), 'big')
    first = random >> 80 if a is None else integer(a, 'a', 0, (1 << 48) - 1)
    middle = (random >> 64) & 0xFFF if b is None else integer(b, 'b', 0, (1 << 12) - 1)
    last = random & ((1 << 62) - 1) if c is None else integer(c, 'c', 0, (1 << 62) - 1)

    return UUID(int=(first << 80) | (8 << 76) | (middle << 64) | (2 << 62) | last)
