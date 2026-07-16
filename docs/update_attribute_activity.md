Update Attribute Activity
=========================

Script: `python scripts/update_attribute_activity.py`

Purpose
- Sync `attribute_activity.json` with new categories/attributes from `attribute_taxonomy.json`, marking new entries inactive by default.

What it does
- Loads `attribute_taxonomy.json` and `attribute_activity.json`.
- Adds any missing categories/attributes from the taxonomy into the activity file with `status: inactive`, preserves existing entries, and updates the version if present.

Usage
```bash
python scripts/update_attribute_activity.py
```

Output
- Writes an updated `attribute_activity.json` (sorted categories, new inactive attributes added).

Notes
- Run from repo root with `PYTHONPATH=$PWD` if needed.***
