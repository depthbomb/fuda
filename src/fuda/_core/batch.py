from itertools import islice
from collections.abc import Iterable
from fuda._core.encoding import batch_count

def check_parallel(parallel: bool) -> None:
    if not isinstance(parallel, bool):
        raise TypeError('parallel must be a boolean')

def batch_items[T](values: Iterable[T], parallel: bool) -> list[T]:
    check_parallel(parallel)
    if isinstance(values, (list, tuple)):
        batch_count(len(values))
        return list(values)
    result = list(islice(values, 1_000_001))
    batch_count(len(result))

    return result

def text_items(values: Iterable[str], parallel: bool) -> list[str]:
    result = batch_items(values, parallel)
    if any(not isinstance(value, str) for value in result):
        raise TypeError('identifier must be a string')

    return result
