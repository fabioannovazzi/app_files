#!/usr/bin/env bash
set -euo pipefail

# Install runtime and development dependencies
pip install -r requirements.txt
pip install -r dev-requirements.txt
