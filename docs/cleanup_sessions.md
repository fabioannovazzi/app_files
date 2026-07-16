Cleanup Sessions
================

Script: `python scripts/cleanup_sessions.py`

Purpose
- Remove old persisted FastAPI session artifacts.

What it does
- Scans persisted session files and deletes those older than the retention window.
- Supports a dry-run to preview deletions.

Usage
```bash
python scripts/cleanup_sessions.py --retention-hours 72 --dry-run
```
- `--retention-hours`: Delete session files older than this many hours (default: 72).
- `--dry-run`: Show which files would be removed without deleting them.

Output
- Prints a summary: scanned count and removed count.

Notes
- Run from the repo root with `PYTHONPATH=$PWD` if needed.***
