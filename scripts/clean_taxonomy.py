from __future__ import annotations

import json
from pathlib import Path

from modules.add_attributes.taxonomy_cleaner import clean_taxonomy_file
from modules.add_attributes.attribute_taxonomy import TAXONOMY_PATH


def main() -> None:
    report = clean_taxonomy_file(TAXONOMY_PATH, backup=True)
    print(json.dumps({"cleaned": len(report), "categories": report}, indent=2))


if __name__ == "__main__":
    main()

