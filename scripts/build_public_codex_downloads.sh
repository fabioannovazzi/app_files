#!/bin/sh
set -eu

# The production restart calls npm without activating the API environment.
python=${MPARANZA_DEPLOY_PYTHON:-python3}
if [ -z "${MPARANZA_DEPLOY_PYTHON:-}" ] && [ -x /opt/mparanza_api_env/bin/python3 ]; then
    python=/opt/mparanza_api_env/bin/python3
fi
"$python" scripts/build_codex_plugin_zip.py vera clara lucia
exec make stage-product-downloads
