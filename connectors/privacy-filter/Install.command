#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if command -v python3.12 >/dev/null 2>&1; then
  python3.12 install.py --setup
elif command -v python3 >/dev/null 2>&1; then
  python3 install.py --setup
else
  echo "Install Python 3.12, then run this installer again."
fi
read -r -p "Press Enter to close / Premi Invio per chiudere. "
