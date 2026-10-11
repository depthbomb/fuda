from io import BytesIO
from zipfile import ZipFile
from tarfile import TarInfo, open as open_tar
from pytest import fixture, mark, raises
from check_distributions import PACKAGE_FILES, PLATFORMS, check_distributions

VERSION = '0.1.0'


def make_wheel(directory, platform, *, omit=None, metadata=None, pure=False):
    path = directory / f'fuda-{VERSION}-cp314-abi3-{platform}.whl'
    extension = 'fuda/_native.pyd' if platform.startswith('win') else 'fuda/_native.abi3.so'
    with ZipFile(path, 'w') as archive:
        for name in PACKAGE_FILES | {extension}:
            if name != omit:
                archive.writestr(name, '')
        archive.writestr(
            f'fuda-{VERSION}.dist-info/METADATA',
            metadata or f'Name: fuda\nVersion: {VERSION}\nRequires-Python: >=3.14\n',
        )
        archive.writestr(
            f'fuda-{VERSION}.dist-info/WHEEL',
            f'Root-Is-Purelib: {str(pure).lower()}\n'
            + ''.join(f'Tag: cp314-abi3-{tag}\n' for tag in platform.split('.')),
        )
    return path


def make_sdist(directory, *, omit=None, extra=()):
    names = {
        'Cargo.toml', 'Cargo.lock', 'setup.py', 'pyproject.toml', 'MANIFEST.in',
        'rust/lib.rs', 'rust/encoding.rs', 'rust/hashids.rs', 'rust/sqids.rs',
        'tests/reference_codecs.py', 'tools/check_distributions.py',
        *('src/' + name for name in PACKAGE_FILES), *extra,
    }
    with open_tar(directory / f'fuda-{VERSION}.tar.gz', 'w:gz') as archive:
        for name in names - {omit}:
            archive.addfile(TarInfo(f'fuda-{VERSION}/{name}'), BytesIO())


@fixture
def distributions(tmp_path):
    # These tiny archives exercise the release gate, not the platform toolchains.
    for platform in PLATFORMS.values():
        make_wheel(tmp_path, platform)
    make_sdist(tmp_path)
    return tmp_path


def test_complete_release_set(distributions):
    assert check_distributions(distributions, VERSION) == set(PLATFORMS)


def test_repaired_linux_wheel_can_have_multiple_tags(distributions):
    (distributions / f'fuda-{VERSION}-cp314-abi3-manylinux_2_28_x86_64.whl').unlink()
    make_wheel(distributions, 'manylinux_2_28_x86_64.manylinux_2_34_x86_64')
    assert check_distributions(distributions, VERSION) == set(PLATFORMS)


def test_missing_platform_blocks_release(distributions):
    (distributions / f'fuda-{VERSION}-cp314-abi3-win_arm64.whl').unlink()
    with raises(ValueError, match='missing wheel platforms: windows-arm64'):
        check_distributions(distributions, VERSION)


@mark.parametrize('filename', ['fuda-0.1.0-py3-none-any.whl', 'fuda-0.1.0-cp314-cp314-win_amd64.whl'])
def test_incorrect_abi_blocks_release(distributions, filename):
    (distributions / filename).touch()
    with raises(ValueError, match='unexpected wheel name or ABI'):
        check_distributions(distributions, VERSION)


def test_duplicate_platform_blocks_release(distributions):
    make_wheel(distributions, 'manylinux_2_28_x86_64.manylinux_2_34_x86_64')
    with raises(ValueError, match='duplicate wheel platform'):
        check_distributions(distributions, VERSION)


@mark.parametrize('omit', ['fuda/_native.pyd', 'fuda/codecs/sqids-blocklist.json', 'fuda/identifiers/upid.py'])
def test_incomplete_wheel_blocks_release(distributions, omit):
    make_wheel(distributions, 'win_amd64', omit=omit)
    with raises(ValueError, match='missing:|exactly one native extension'):
        check_distributions(distributions, VERSION)


def test_inconsistent_metadata_blocks_release(distributions):
    make_wheel(distributions, 'win_amd64', metadata='Name: fuda\nVersion: 0.2.0\nRequires-Python: >=3.14\n')
    with raises(ValueError, match='inconsistent package metadata'):
        check_distributions(distributions, VERSION)


def test_pure_wheel_metadata_blocks_release(distributions):
    make_wheel(distributions, 'win_amd64', pure=True)
    with raises(ValueError, match='inconsistent wheel tags'):
        check_distributions(distributions, VERSION)


def test_source_distribution_needs_rust_sources(distributions):
    make_sdist(distributions, omit='rust/encoding.rs')
    with raises(ValueError, match='source distribution is missing:.*rust/encoding.rs'):
        check_distributions(distributions, VERSION)


def test_source_distribution_must_not_include_local_extension(distributions):
    make_sdist(distributions, extra={'src/fuda/_native.pyd'})
    with raises(ValueError, match='compiled artifacts'):
        check_distributions(distributions, VERSION)


def test_missing_source_distribution_blocks_release(distributions):
    (distributions / f'fuda-{VERSION}.tar.gz').unlink()
    with raises(ValueError, match='exactly one matching source distribution'):
        check_distributions(distributions, VERSION)
