"""Serve exact public fixture bytes to extracted-package course CLI tests."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["installed_course_command"]

_MOCK_PUBLIC_DOWNLOADS = """
import io, runpy, sys
from pathlib import Path
from urllib.parse import urlsplit, unquote
root, repository = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(root / 'scripts'))
sys.path.insert(0, str(root / 'vendor/modules'))
import courseware.library as library
class PublicFile(io.BytesIO):
    headers = {}
    def __init__(self, url):
        parsed = urlsplit(url)
        path = repository / unquote(parsed.path).lstrip('/')
        assert parsed.hostname == 'mparanza.com'
        assert path.resolve().is_relative_to((repository / 'static/shared/courses').resolve())
        super().__init__(path.read_bytes())
        self.url = url
    def geturl(self):
        return self.url
library.urlopen = lambda url, **kwargs: PublicFile(url)
sys.argv = [str(root / 'scripts/local_courses.py'), *sys.argv[3:]]
runpy.run_path(sys.argv[0], run_name='__main__')
"""


def installed_course_command(root: Path, repository: Path, *args: object) -> list[str]:
    """Mock only public data transport; execute the actual installed CLI unchanged."""
    return [
        sys.executable,
        "-c",
        _MOCK_PUBLIC_DOWNLOADS,
        str(root),
        str(repository),
        *map(str, args),
    ]
