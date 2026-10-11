"""Ruff formatting with Fuda's single blank line and import ordering conventions."""

from re import sub
from pathlib import Path
from subprocess import run
from sys import argv, executable
from ast import parse, Import, unparse, ImportFrom

root = Path(__file__).resolve().parents[1]
paths = [root / 'setup.py', *sorted((root / 'src').rglob('*.py')), *sorted((root / 'tools').glob('*.py'))]
if '--check' not in argv:
    run([executable, '-m', 'ruff', 'check', '--fix', *map(str, paths)], check=True)
changed = []
for path in paths:
    source = path.read_text(encoding='utf-8')
    formatted = run(
        [executable, '-m', 'ruff', 'format', '--stdin-filename', str(path), '-'],
        input=source,
        text=True,
        encoding='utf-8',
        capture_output=True,
        check=True,
    ).stdout
    lines = formatted.splitlines(keepends=True)
    imports = [node for node in parse(formatted).body if isinstance(node, (Import, ImportFrom))]
    replacements = []
    for node in imports:
        node.names.sort(key=lambda alias: (len(unparse(alias)), unparse(alias)))
        text = unparse(node)
        key = (0 if isinstance(node, ImportFrom) and node.module == '__future__' else 1, len(text), text)
        replacements.append((key, text))
    if imports:
        insertion = imports[0].lineno - 1
        for node in reversed(imports):
            del lines[node.lineno - 1 : node.end_lineno]
        lines[insertion:insertion] = [text + '\n' for _, text in sorted(replacements)]
    expected = sub(r'\n{3,}', '\n\n', ''.join(lines))
    if expected != source:
        changed.append(str(path.relative_to(root)))
        if '--check' not in argv:
            path.write_text(expected, encoding='utf-8', newline='\n')
if changed and '--check' in argv:
    raise SystemExit('Formatting needed: ' + ', '.join(changed))

print(f'Checked {len(paths)} Python files')
