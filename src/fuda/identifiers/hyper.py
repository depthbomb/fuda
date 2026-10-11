from typing import Self
from binascii import Error
from uuid import UUID, uuid4
from base64 import b64decode, b64encode
from fuda._core.encoding import integer
from dataclasses import field, dataclass
from fuda._core.state import ProcessGenerator

def _prefix(value: UUID, url_safe: bool) -> str:
    alphabet = b'-_' if url_safe else None
    return b64encode(value.bytes, altchars=alphabet).decode('ascii').rstrip('=') + ('-' if url_safe else '/')

@dataclass(frozen=True, slots=True)
class HyperID:
    uuid: UUID
    counter: int
    url_safe: bool = field(default=False, compare=False)
    fixed_length: bool = field(default=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.uuid, UUID) or self.uuid.version != 4:
            raise ValueError('HyperID requires a version 4 UUID')
        integer(self.counter, 'counter', 0, (1 << 31) - 1)
        if not isinstance(self.url_safe, bool) or not isinstance(self.fixed_length, bool):
            raise TypeError('url_safe and fixed_length must be booleans')

    def __str__(self) -> str:
        suffix = f'{self.counter:010d}' if self.fixed_length else str(self.counter)

        return _prefix(self.uuid, self.url_safe) + suffix

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        if not 24 <= len(value) <= 33 or not value.isascii() or value[22] not in '/-':
            raise ValueError('invalid HyperID prefix, separator or length')
        url_safe = value[22] == '-'
        counter = value[23:]
        if not counter.isdecimal() or (len(counter) != 10 and counter != str(int(counter))):
            raise ValueError('invalid HyperID decimal counter')
        try:
            data = b64decode(value[:22] + '==', altchars=b'-_' if url_safe else None, validate=True)
        except Error:
            raise ValueError('invalid HyperID UUID encoding') from None
        result = cls(UUID(bytes=data), int(counter), url_safe, len(counter) == 10)
        if str(result) != value:
            raise ValueError('noncanonical HyperID encoding')

        return result

class HyperIDGenerator(ProcessGenerator[str]):
    """A random UUID prefix with a cheap decimal counter, refreshed on rollover."""

    def __init__(
        self,
        *,
        url_safe: bool = False,
        fixed_length: bool = False,
        start: int = 0,
        max_count: int = (1 << 31) - 1,
    ) -> None:
        if not isinstance(url_safe, bool) or not isinstance(fixed_length, bool):
            raise TypeError('url_safe and fixed_length must be booleans')
        integer(max_count, 'max_count', 1, (1 << 31) - 1)
        integer(start, 'start', 0, max_count - 1)
        super().__init__()
        self.url_safe, self.fixed_length, self.max_count = url_safe, fixed_length, max_count
        self._start = start
        self._reset_process()

    def _reset_process(self) -> None:
        self._prefix = _prefix(uuid4(), self.url_safe)
        self._counter = self._start

    def generate(self) -> str:
        self._check_process()
        with self._lock:
            if self._counter == self.max_count:
                self._prefix = _prefix(uuid4(), self.url_safe)
                self._counter = 0
            counter, prefix = self._counter, self._prefix
            self._counter += 1

        return prefix + (f'{counter:010d}' if self.fixed_length else str(counter))
