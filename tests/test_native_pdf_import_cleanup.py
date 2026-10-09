from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_import_cleanup_preserves_native_swig_registry_between_pdf_operations():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from tests import conftest
item = SimpleNamespace(nodeid='native-pdf-runtime-regression')
conftest.pytest_runtest_setup(item)
import pymupdf
registry = sys.modules['swig_runtime_data4']
conftest.pytest_runtest_teardown(item)
assert sys.modules['swig_runtime_data4'] is registry
with pymupdf.open() as document:
    document.new_page()
    content = document.tobytes()
with pymupdf.open(stream=content, filetype='pdf') as reopened:
    assert reopened.page_count == 1
""",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
