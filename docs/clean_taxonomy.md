Clean Taxonomy
==============

Script: `python scripts/clean_taxonomy.py`

Purpose
- Run taxonomy cleaner on the taxonomy file to normalize/fix issues, with a backup.

What it does
- Invokes `modules.add_attributes.taxonomy_cleaner.clean_taxonomy_file` on `TAXONOMY_PATH`, creating a backup and returning a report of cleaned categories.
- Prints a JSON summary of how many categories were cleaned.

Usage
```bash
python scripts/clean_taxonomy.py
```

Output
- JSON to stdout: `{"cleaned": <count>, "categories": [...]}`.
- Backs up the taxonomy file before writing fixes.

Notes
- Run from repo root with `PYTHONPATH=$PWD` if needed.***
