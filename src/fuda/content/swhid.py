"""Software Heritage core and qualified persistent identifiers (SWHID v1).

Object serializers follow the published Git/SWH formats. Input bytes retain
their exact spelling; callers supply complete Git author/date header values.
"""

from __future__ import annotations
from typing import Self
from hashlib import sha1
from hmac import compare_digest
from re import search, fullmatch
from fuda._core.encoding import integer
from dataclasses import replace, dataclass
from collections.abc import Mapping, Iterable
from urllib.parse import unquote, quote_from_bytes, unquote_to_bytes

_TYPES = {'cnt': 'blob', 'dir': 'tree', 'rev': 'commit', 'rel': 'tag', 'snp': 'snapshot'}
_LONG_TYPES = {'cnt': 'content', 'dir': 'directory', 'rev': 'revision', 'rel': 'release', 'snp': 'snapshot'}

def _bytes(value: bytes, name: str) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError(f'{name} must be bytes')
    return value

def _target(value: SWHID, allowed: tuple[str, ...]) -> bytes:
    if not isinstance(value, SWHID):
        raise TypeError('target must be a SWHID')
    if value.object_type not in allowed:
        raise ValueError(f'target must have one of these object types: {allowed}')
    return value.digest

def _manifest(headers: Iterable[tuple[bytes, bytes]], message: bytes | None) -> bytes:
    output = []
    for key, value in headers:
        _bytes(key, 'header name')
        _bytes(value, 'header value')
        if not key or any(char <= 32 or char >= 127 for char in key):
            raise ValueError('header names must be printable ASCII without spaces')
        output.append(key + b' ' + value.replace(b'\n', b'\n ') + b'\n')
    if message is not None:
        output.append(b'\n' + _bytes(message, 'message'))
    return b''.join(output)

@dataclass(frozen=True, slots=True)
class DirectoryEntry:
    name: bytes
    target: SWHID
    mode: int = 0o100644

    def __post_init__(self) -> None:
        _bytes(self.name, 'entry name')
        if not self.name or b'/' in self.name or b'\x00' in self.name:
            raise ValueError('directory entry names must be nonempty and contain neither slash nor NUL')
        integer(self.mode, 'mode', 0, 0o177777)
        allowed = {0o100644: ('cnt',), 0o100755: ('cnt',), 0o120000: ('cnt',), 0o40000: ('dir',), 0o160000: ('rev',)}
        if self.mode not in allowed:
            raise ValueError('unsupported Git directory entry mode')
        _target(self.target, allowed[self.mode])

@dataclass(frozen=True, slots=True)
class SWHID:
    object_type: str
    digest: bytes
    origin: str | None = None
    visit: SWHID | None = None
    anchor: SWHID | None = None
    path: bytes | None = None
    lines: tuple[int, int | None] | None = None

    def __post_init__(self) -> None:
        if self.object_type not in _TYPES:
            raise ValueError('SWHID object_type must be cnt, dir, rev, rel, or snp')
        if len(_bytes(self.digest, 'digest')) != 20:
            raise ValueError('SWHID requires a 20-byte SHA-1 digest')
        if self.origin is not None:
            if not isinstance(self.origin, str):
                raise TypeError('origin must be a string')
            if not self.origin or any(ord(char) <= 32 for char in self.origin):
                raise ValueError('origin must be a nonempty URI without whitespace')
        for value, allowed in ((self.visit, ('snp',)), (self.anchor, ('dir', 'rev', 'rel', 'snp'))):
            if value is not None:
                _target(value, allowed)
                if value != value.core:
                    raise ValueError('visit and anchor must be core SWHIDs without qualifiers')
        if self.path is not None:
            _bytes(self.path, 'path')
            if not self.path.startswith(b'/'):
                raise ValueError('qualified SWHID paths must be absolute')
        if self.lines is not None:
            if not isinstance(self.lines, tuple) or len(self.lines) != 2:
                raise TypeError('lines must be a (start, end_or_None) tuple')
            start, end = self.lines
            integer(start, 'start line', 1, (1 << 63) - 1)
            if end is not None:
                integer(end, 'end line', start, (1 << 63) - 1)

    @property
    def core(self) -> SWHID:
        return SWHID(self.object_type, self.digest)

    def with_context(
        self,
        *,
        origin: str | None = None,
        visit: SWHID | None = None,
        anchor: SWHID | None = None,
        path: bytes | None = None,
        lines: tuple[int, int | None] | None = None,
    ) -> Self:
        """Return a copy with the supplied context, replacing existing qualifiers."""
        return replace(self, origin=origin, visit=visit, anchor=anchor, path=path, lines=lines)

    def __str__(self) -> str:
        result = f'swh:1:{self.object_type}:{self.digest.hex()}'
        if self.origin is not None:
            result += ';origin=' + self.origin.replace('%', '%25').replace(';', '%3B')
        if self.visit is not None:
            result += ';visit=' + str(self.visit)
        if self.anchor is not None:
            result += ';anchor=' + str(self.anchor)
        if self.path is not None:
            result += ';path=' + quote_from_bytes(self.path, safe='/')
        if self.lines is not None:
            result += ';lines=' + '-'.join(str(value) for value in self.lines if value is not None)
        return result

    @classmethod
    def from_str(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError('identifier must be a string')
        core, *raw = value.split(';')
        match = fullmatch(r'swh:1:(cnt|dir|rev|rel|snp):([0-9a-f]{40})', core)
        if match is None:
            raise ValueError('invalid core SWHID')
        qualifiers = {}
        for item in raw:
            name, separator, content = item.partition('=')
            if not separator or name not in ('origin', 'visit', 'anchor', 'path', 'lines') or name in qualifiers:
                raise ValueError('unknown, missing or duplicate SWHID qualifier')
            if search(r'%(?![0-9A-Fa-f]{2})', content):
                raise ValueError('invalid percent escape in SWHID qualifier')
            qualifiers[name] = content
        origin = unquote(qualifiers['origin'], errors='strict') if 'origin' in qualifiers else None
        visit = cls.from_str(qualifiers['visit']) if 'visit' in qualifiers else None
        anchor = cls.from_str(qualifiers['anchor']) if 'anchor' in qualifiers else None
        path = unquote_to_bytes(qualifiers['path']) if 'path' in qualifiers else None
        lines = None
        if 'lines' in qualifiers:
            line_match = fullmatch(r'([0-9]+)(?:-([0-9]+))?', qualifiers['lines'])
            if line_match is None:
                raise ValueError('invalid SWHID line range')
            start, end = line_match.groups()
            lines = (int(start), int(end) if end is not None else None)
        return cls(match[1], bytes.fromhex(match[2]), origin, visit, anchor, path, lines)

    @classmethod
    def from_object(cls, body: bytes, *, object_type: str) -> Self:
        """Hash a serialized object body, adding the Git/SWH header exactly once."""
        _bytes(body, 'body')
        if object_type not in _TYPES:
            raise ValueError('unknown SWHID object type')
        header = f'{_TYPES[object_type]} {len(body)}\x00'.encode('ascii')
        return cls(object_type, sha1(header + body, usedforsecurity=False).digest())

    @classmethod
    def from_content(cls, content: bytes) -> Self:
        return cls.from_object(content, object_type='cnt')

    def verify(self, body: bytes) -> bool:
        """Verify content bytes or an already serialized non-content object body."""
        return compare_digest(self.digest, self.from_object(body, object_type=self.object_type).digest)

    @classmethod
    def from_directory(cls, entries: Iterable[DirectoryEntry]) -> Self:
        values = list(entries)
        if any(not isinstance(entry, DirectoryEntry) for entry in values):
            raise TypeError('entries must contain DirectoryEntry objects')
        if len({entry.name for entry in values}) != len(values):
            raise ValueError('directory entry names must be unique')
        values.sort(key=lambda entry: entry.name + (b'/' if entry.mode == 0o40000 else b''))
        body = b''.join(
            format(entry.mode, 'o').encode('ascii') + b' ' + entry.name + b'\x00' + entry.target.digest
            for entry in values
        )
        return cls.from_object(body, object_type='dir')

    @classmethod
    def from_revision(
        cls,
        directory: SWHID,
        *,
        parents: Iterable[SWHID] = (),
        author: bytes | None = None,
        committer: bytes | None = None,
        message: bytes | None = None,
        extra_headers: Iterable[tuple[bytes, bytes]] = (),
    ) -> Self:
        """Author/committer are complete Git header values, including dates if used."""
        headers = [(b'tree', _target(directory, ('dir',)).hex().encode('ascii'))]
        headers.extend((b'parent', _target(parent, ('rev',)).hex().encode('ascii')) for parent in parents)
        if author is not None:
            headers.append((b'author', author))
        if committer is not None:
            headers.append((b'committer', committer))
        headers.extend(extra_headers)
        return cls.from_object(_manifest(headers, message), object_type='rev')

    @classmethod
    def from_release(
        cls, target: SWHID, *, name: bytes, tagger: bytes | None = None, message: bytes | None = None
    ) -> Self:
        digest = _target(target, tuple(_TYPES))
        kind = 'refs' if target.object_type == 'snp' else _TYPES[target.object_type]
        headers = [(b'object', digest.hex().encode('ascii')), (b'type', kind.encode('ascii')), (b'tag', name)]
        if tagger is not None:
            headers.append((b'tagger', tagger))
        return cls.from_object(_manifest(headers, message), object_type='rel')

    @classmethod
    def from_snapshot(cls, branches: Mapping[bytes, SWHID | bytes | None]) -> Self:
        """Map branch names to core objects, alias names (bytes), or dangling None."""
        output = []
        for name in branches:
            _bytes(name, 'branch name')
            if b'\x00' in name:
                raise ValueError('branch name cannot contain NUL')
        resolved: set[bytes] = set()
        for name, target in sorted(branches.items()):
            if target is None:
                kind, digest = 'dangling', b''
            elif isinstance(target, bytes):
                if name not in resolved:
                    seen = {name}
                    current: SWHID | bytes | None = target
                    while isinstance(current, bytes) and current not in resolved:
                        if current in seen or current not in branches:
                            raise ValueError('snapshot alias is unresolved or cyclic')
                        seen.add(current)
                        current = branches[current]
                    resolved.update(seen)
                kind, digest = 'alias', target
            else:
                digest = _target(target, tuple(_TYPES))
                kind = _LONG_TYPES[target.object_type]
            output.append(
                kind.encode('ascii') + b' ' + name + b'\x00' + str(len(digest)).encode('ascii') + b':' + digest
            )
        return cls.from_object(b''.join(output), object_type='snp')

def swhid(content: bytes) -> SWHID:
    return SWHID.from_content(content)
