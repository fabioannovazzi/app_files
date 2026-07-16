Generate Taxonomy Branch
========================

Script: `python scripts/generate_taxonomy_branch.py`

Purpose
- Use the LLM-driven taxonomy generator to scaffold new category branches.

What it does
- Takes one or more category names and optional industry context, runs the taxonomy generator via an LLM wrapper (headless), and produces branch YAML/JSON files (see script for output handling).

Key options
- Positional: `categories` (one or more category names).
- `--industry`: industry context.
- `--industry-description`: expanded industry description.
- `--prompt-file` / `--output-dir` (if present in script; check `--help` for full list).

Usage
```bash
PYTHONPATH=$PWD python scripts/generate_taxonomy_branch.py concealer highlighter \
  --industry "Cosmetics in US"
```

Notes
- Runs headless (legacy UI silenced; deprecated/optional). Review
  generated branches before merging into the taxonomy.***
