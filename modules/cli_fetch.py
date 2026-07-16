#!/usr/bin/env python3
"""
Minimal CLI to fetch plain-text from any legal URL using the layered extractor.

Example
-------
$ python cli_fetch.py https://iga.in.gov/laws/2023/ic/titles/24#24-2-3-2
IC 24-2-3-2  Definitions  …
"""


import sys
import logging

# The extract_page orchestrator lives in modules.validation.core.
from modules.validation.core import extract_page

def main() -> None:
    if len(sys.argv) not in (2, 3):
        logging.info("usage: cli_fetch.py <url> [--debug]")
        sys.exit(1)

    url    = sys.argv[1]
    debug  = "--debug" in sys.argv
    text   = extract_page(url, debug=debug, min_len=200)

    if text:
        print(text)
    else:
        logging.info("✘ failed to extract text  (see logs/extractor-failures.log)")
        sys.exit(2)

if __name__ == "__main__":
    main()
