from os import urandom
from time import time_ns
from hashlib import sha3_512
from secrets import randbelow
from fuda._core.extension import native
from fuda._core.state import ProcessGenerator
from fuda._core.encoding import BASE36, base36, integer

class Cuid2Generator(ProcessGenerator[str]):
    """Strict CUID2 generation with OS entropy and a process-local fingerprint."""

    def __init__(self, length: int = 24) -> None:
        integer(length, 'length', 2, 32)
        super().__init__()
        self.length = length
        self._reset_process()

    def _reset_process(self) -> None:
        self._counter = randbelow(476_782_367)
        fingerprint = sha3_512(urandom(64) + str(time_ns()).encode()).digest()
        self._fingerprint = base36(int.from_bytes(fingerprint, 'big'))[1:33]

    def _reserve(self, count: int) -> int:
        self._check_process()
        with self._lock:
            start = self._counter + 1
            if start + count > 1 << 64:
                raise OverflowError('CUID2 counter exhausted')
            self._counter += count

        return start

    def generate(self) -> str:
        size = self.length
        for _ in range(8):
            counter = self._reserve(1)
            result = native.cuid2(size, self._fingerprint, counter)
            if len(result) == size:
                return result

        raise RuntimeError('could not produce an exact-length CUID2')

    def _generate_many(self, count: int, parallel: bool) -> list[str]:
        start = self._reserve(count)
        results = native.cuid2_many(count, self.length, self._fingerprint, start, parallel)
        for index, result in enumerate(results):
            if len(result) != self.length:
                results[index] = self.generate()

        return results

def is_cuid2(value: object, *, length: int | None = None) -> bool:
    if length is not None:
        integer(length, 'length', 2, 32)
    if not isinstance(value, str) or not 2 <= len(value) <= 32:
        return False

    return (
        (length is None or len(value) == length)
        and 'a' <= value[0] <= 'z'
        and all(character in BASE36 for character in value[1:])
    )
