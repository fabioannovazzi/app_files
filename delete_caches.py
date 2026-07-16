#!/usr/bin/env python3

"""
delete_caches.py – remove cached files/directories created by the project.

Run this script from the root of your repository.  It will delete the caches
listed below only if they exist, and it will log each action.
"""

from pathlib import Path
import shutil

def delete_file(path: Path) -> None:
    if path.exists() and path.is_file():
        print(f"Deleting file {path}")
        path.unlink()
    else:
        print(f"File {path} not found or already removed – skipping.")

def delete_dir(path: Path) -> None:
    if path.exists() and path.is_dir():
        print(f"Deleting directory {path}")
        shutil.rmtree(path)
    else:
        print(f"Directory {path} not found or already removed – skipping.")

def main() -> None:
    # Determine the project root (directory containing this script)
    root_dir = Path(__file__).resolve().parent

    # List of cache files relative to the project root
    cache_files = [
        root_dir / "product_attributes.json",
        root_dir / "alias_index.json",
        root_dir / "attribute_classifications.parquet",
        root_dir / "novelty_log.parquet",
        root_dir / "record.json",
        root_dir / "llm_calls_record.json",
        root_dir / "category_websites.json",
        root_dir / "merchant_brand_websites.json",
        root_dir / "src" / "description_cache.json",
    ]

    # List of cache directories relative to the project root
    cache_dirs = [
        root_dir / ".page_cache",
        root_dir / ".bank_extract_reports",
        root_dir / "caches",  # if you have already migrated caches here
    ]

    # Delete project-root caches
    for f in cache_files:
        delete_file(f)
    for d in cache_dirs:
        delete_dir(d)

    # Delete the Playwright/validation cache in the user’s home directory
    home_vr_cache = Path.home() / ".vr_cache"
    delete_dir(home_vr_cache)

if __name__ == "__main__":
    main()

