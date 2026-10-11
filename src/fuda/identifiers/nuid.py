from secrets import randbelow
from fuda._core.state import ProcessGenerator
from fuda._core.encoding import BASE62, encode
from fuda.identifiers.random_ids import nanoid

_MAX_SEQUENCE = 62**10

class NUIDGenerator(ProcessGenerator[str]):
    """NATS NUID: 12 random base62 characters and a 10-character sequence.

    OS randomness seeds the prefix and sequence. Subsequent IDs expose a
    predictable increment, so these are not secret tokens.
    """

    def __init__(self) -> None:
        super().__init__()
        self._reset_process()

    def _reset_process(self) -> None:
        self._prefix = nanoid(12, alphabet=BASE62)
        self._sequence = randbelow(_MAX_SEQUENCE)
        self._increment = 33 + randbelow(300)

    def generate(self) -> str:
        self._check_process()
        with self._lock:
            self._sequence += self._increment
            if self._sequence >= _MAX_SEQUENCE:
                self._reset_process()
            prefix, sequence = self._prefix, self._sequence

        return prefix + encode(sequence, BASE62, 10)
