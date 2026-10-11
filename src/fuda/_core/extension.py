import sys

__all__ = ['native']

try:
    from fuda import _native as native
except ImportError as error:
    raise ImportError(
        'Fuda requires its compiled Rust extension. Reinstall a wheel for your Python version and platform '
        'with python -m pip install --force-reinstall --only-binary=fuda fuda. '
        'Building Fuda from source requires Rust and a native compiler.'
    ) from error

if sys.platform != 'win32':
    from os import register_at_fork

    # A child must not reuse a worker pool inherited from another process.
    register_at_fork(after_in_child=native._after_fork)
