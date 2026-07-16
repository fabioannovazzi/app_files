#!/usr/bin/env python3
from pathlib import Path
repo = Path('.').resolve()
tests = repo/'tests'
out = repo/'.codex_tests_done.txt'
paths = []
if tests.exists():
    for p in tests.rglob('test_*.py'):
        try:
            s = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        if 'def test_' in s or 'pytest.mark.parametrize' in s or 'assert ' in s:
            paths.append(p.relative_to(repo).as_posix())
out.write_text('\n'.join(sorted(set(paths))) + '\n', encoding='utf-8')
print(f'Wrote {len(set(paths))} entries to {out}')

