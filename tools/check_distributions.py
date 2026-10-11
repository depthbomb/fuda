"""Check the complete release set before any of it reaches PyPI."""

from pathlib import Path
from re import fullmatch
from tomllib import loads
from zipfile import ZipFile
from argparse import ArgumentParser
from email.parser import BytesParser
from tarfile import open as open_tar

PLATFORMS = {
    'windows-x64': r'win_amd64',
    'windows-arm64': r'win_arm64',
    'macos-intel': r'macosx_11_0_x86_64',
    'macos-arm64': r'macosx_11_0_arm64',
    'linux-x64': r'manylinux_2_28_x86_64',
    'linux-arm64': r'manylinux_2_28_aarch64',
    'alpine-x64': r'musllinux_1_2_x86_64',
    'alpine-arm64': r'musllinux_1_2_aarch64',
}
PACKAGE_FILES = {
    'fuda/__init__.py',
    'fuda/api.py',
    'fuda/cli.py',
    'fuda/__main__.py',
    'fuda/_core/__init__.py',
    'fuda/_core/batch.py',
    'fuda/_core/extension.py',
    'fuda/_core/encoding.py',
    'fuda/_core/state.py',
    'fuda/identifiers/__init__.py',
    'fuda/identifiers/cuid.py',
    'fuda/identifiers/uuids.py',
    'fuda/identifiers/random_ids.py',
    'fuda/identifiers/types.py',
    'fuda/identifiers/extended_types.py',
    'fuda/identifiers/prefixed.py',
    'fuda/identifiers/stateful.py',
    'fuda/identifiers/ordered.py',
    'fuda/identifiers/nuid.py',
    'fuda/identifiers/scru.py',
    'fuda/identifiers/sonyflake.py',
    'fuda/identifiers/sno.py',
    'fuda/identifiers/upid.py',
    'fuda/identifiers/hyper.py',
    'fuda/identifiers/flake.py',
    'fuda/codecs/__init__.py',
    'fuda/codecs/hashids.py',
    'fuda/codecs/sqids.py',
    'fuda/codecs/proquint.py',
    'fuda/codecs/uuid25.py',
    'fuda/codecs/sqids-blocklist.json',
    'fuda/content/__init__.py',
    'fuda/content/cid.py',
    'fuda/content/multihash.py',
    'fuda/content/ni.py',
    'fuda/content/swhid.py',
    'fuda/content/_multiformats.py',
    'fuda/py.typed',
    'fuda/_native.pyi',
    'fuda/LICENSE.sqids',
    'fuda/LICENSE.hashids',
    'fuda/LICENSE.data-encoding',
}

def check_distributions(directory: Path, version: str) -> set[str]:
    found: set[str] = set()
    wheels = sorted(directory.glob('*.whl'))
    for path in wheels:
        parts = path.stem.split('-')
        if len(parts) != 5 or parts[:4] != ['fuda', version, 'cp314', 'abi3']:
            raise ValueError(f'unexpected wheel name or ABI: {path.name}')
        # A repaired Linux wheel can advertise several compatible platform tags.
        tags = parts[4].split('.')
        matches = {name for name, pattern in PLATFORMS.items() if any(fullmatch(pattern, tag) for tag in tags)}
        if len(matches) != 1 or found & matches:
            raise ValueError(f'unknown or duplicate wheel platform: {path.name}')
        found.update(matches)
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = PACKAGE_FILES - names
            if missing:
                raise ValueError(f'{path.name} is missing: {", ".join(sorted(missing))}')
            binaries = [name for name in names if name.startswith('fuda/_native.') and name.endswith(('.so', '.pyd'))]
            if len(binaries) != 1:
                raise ValueError(f'{path.name} must contain exactly one native extension')
            metadata = BytesParser().parsebytes(archive.read(f'fuda-{version}.dist-info/METADATA'))
            if metadata['Name'] != 'fuda' or metadata['Version'] != version or metadata['Requires-Python'] != '>=3.14':
                raise ValueError(f'{path.name} has inconsistent package metadata')
            wheel = BytesParser().parsebytes(archive.read(f'fuda-{version}.dist-info/WHEEL'))
            if wheel['Root-Is-Purelib'] != 'false' or set(wheel.get_all('Tag', [])) != {
                f'cp314-abi3-{tag}' for tag in tags
            }:
                raise ValueError(f'{path.name} has inconsistent wheel tags')
    if found != PLATFORMS.keys():
        raise ValueError(f'missing wheel platforms: {", ".join(sorted(PLATFORMS.keys() - found))}')
    sources = sorted(directory.glob('*.tar.gz'))
    if len(sources) != 1 or sources[0].name != f'fuda-{version}.tar.gz':
        raise ValueError('expected exactly one matching source distribution')
    with open_tar(sources[0]) as archive:
        names = set(archive.getnames())
        required = {
            'Cargo.toml',
            'Cargo.lock',
            'setup.py',
            'pyproject.toml',
            'MANIFEST.in',
            'rust/lib.rs',
            'rust/batch.rs',
            'rust/cuid.rs',
            'rust/encoding.rs',
            'rust/hashids.rs',
            'rust/random.rs',
            'rust/sqids.rs',
            'tests/reference_codecs.py',
            'tools/check_distributions.py',
            *('src/' + name for name in PACKAGE_FILES),
        }
        missing = {f'fuda-{version}/{name}' for name in required} - names
        if missing:
            raise ValueError(f'source distribution is missing: {", ".join(sorted(missing))}')
        if any(name.endswith(('.pyd', '.so', '.pyc')) for name in names):
            raise ValueError('source distribution contains compiled artifacts')
    return found

def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    project = loads(Path('pyproject.toml').read_text(encoding='utf-8'))['project']
    try:
        platforms = check_distributions(args.directory, project['version'])
    except (ValueError, KeyError) as error:
        parser.exit(1, str(error) + '\n')
    print(f'Checked {len(platforms)} native wheels and the source distribution')

if __name__ == '__main__':
    main()
