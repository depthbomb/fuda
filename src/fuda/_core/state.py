from os import getpid
from threading import Lock
from typing import Generic, TypeVar
from collections.abc import Iterator
from fuda._core.encoding import batch_count

T = TypeVar('T', covariant=True)

class Generator(Generic[T]):  # noqa: UP046 - preserve covariance for specialized output types.
    """Common batch and bounded-memory iteration behavior."""

    def generate(self) -> T:
        raise NotImplementedError

    def generate_many(self, count: int) -> list[T]:
        batch_count(count)

        return [self.generate() for _ in range(count)]

    def iter_ids(self, count: int | None = None) -> Iterator[T]:
        if count is not None:
            if not isinstance(count, int) or isinstance(count, bool):
                raise TypeError('count must be an integer')
            if count < 0:
                raise ValueError('count must not be negative')
        index = 0
        while count is None or index < count:
            yield self.generate()
            index += 1

    def __copy__(self) -> None:
        raise TypeError('generators cannot be copied; construct an independent generator')

    def __deepcopy__(self, memo: object) -> None:
        raise TypeError('generators cannot be copied; construct an independent generator')

    def __reduce__(self) -> str:
        raise TypeError('generators cannot be pickled; construct one in the child process')

class ProcessGenerator[T](Generator[T]):
    def __init__(self) -> None:
        self._pid = getpid()
        self._lock = Lock()

    def _check_process(self) -> None:
        pid = getpid()
        if self._pid != pid:
            # The inherited lock may have belonged to a vanished thread.
            self._lock = Lock()
            self._reset_process()
            self._pid = pid

    def _reset_process(self) -> None:
        raise NotImplementedError
