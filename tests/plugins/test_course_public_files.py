"""Verify single-copy course publication and byte-preserving historical URLs."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from modules.course_files import CourseFiles
from scripts.course_materials.public_files import deduplicate, resolve_public_file

ROOT = Path(__file__).resolve().parents[2]


def publication_case(root: Path, generated: Path, content: bytes) -> str:
    """Publish the same attachment for two products, languages and filenames."""
    digest = hashlib.sha256(content).hexdigest()
    for product, filename in (("vera", "input.txt"), ("lucia", "practice.txt")):
        manifest = root / f"plugins/{product}/assets/courses/example/course.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": f"files/{filename}",
                            "sha256": digest,
                            "languages": ["it", "en"],
                        }
                    ]
                }
            )
        )
        for language in ("it", "en"):
            folder = generated / product / "example" / language
            (folder / "files").mkdir(parents=True)
            (folder / f"files/{filename}").write_bytes(content)
            (folder / "course.html").write_text(f'<a href="files/{filename}">Input</a>')
    return digest


def test_course_publication_keeps_one_copy_across_products_and_filenames(tmp_path):
    generated = tmp_path / "generated"
    content = b"fictional input\n" * 400
    digest = publication_case(tmp_path, generated, content)

    deduplicate(generated, tmp_path / "previous", tmp_path)

    stored = list(generated.glob("*/_files/*/*.txt"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == content
    assert (
        resolve_public_file(generated, "vera/example/it/files/input.txt") == stored[0]
    )
    assert (
        resolve_public_file(generated, f"vera/_files/{digest}/input.txt") == stored[0]
    )
    assert (
        resolve_public_file(generated, f"lucia/_files/{digest}/practice.txt")
        == stored[0]
    )
    page = (generated / "vera/example/it/course.html").read_text()
    assert (
        "/static/shared/courses/" + stored[0].relative_to(generated).as_posix() in page
    )


def test_course_rebuild_retains_old_pins_after_attachment_changes(tmp_path):
    previous = tmp_path / "previous"
    old_content = b"original lesson input"
    old_digest = publication_case(tmp_path, previous, old_content)
    deduplicate(previous, tmp_path / "empty", tmp_path)
    generated = tmp_path / "generated"
    new_content = b"revised lesson input"
    new_digest = publication_case(tmp_path, generated, new_content)

    deduplicate(generated, previous, tmp_path)

    assert (
        resolve_public_file(generated, "vera/example/it/files/input.txt").read_bytes()
        == old_content
    )
    assert (
        resolve_public_file(
            generated, f"vera/_files/{old_digest}/input.txt"
        ).read_bytes()
        == old_content
    )
    assert (
        resolve_public_file(
            generated, f"vera/_files/{new_digest}/input.txt"
        ).read_bytes()
        == new_content
    )
    assert new_digest in (generated / "vera/example/it/course.html").read_text()


def test_course_publication_rejects_corrupted_historical_hash_without_replacing_it(
    tmp_path,
):
    previous = tmp_path / "previous"
    generated = tmp_path / "generated"
    digest = publication_case(tmp_path, generated, b"original input")
    historical = previous / f"vera/_files/{digest}/input.txt"
    historical.parent.mkdir(parents=True)
    historical.write_bytes(b"altered historical bytes")

    with pytest.raises(ValueError, match="Immutable course file changed"):
        deduplicate(generated, previous, tmp_path)

    assert historical.read_bytes() == b"altered historical bytes"


def test_course_publication_rebuild_is_byte_identical(tmp_path):
    previous = tmp_path / "previous"
    generated = tmp_path / "generated"
    publication_case(tmp_path, previous, b"fictional input")
    deduplicate(previous, tmp_path / "empty", tmp_path)
    publication_case(tmp_path, generated, b"fictional input")

    deduplicate(generated, previous, tmp_path)

    expected = {
        p.relative_to(previous): p.read_bytes()
        for p in previous.rglob("*")
        if p.is_file()
    }
    actual = {
        p.relative_to(generated): p.read_bytes()
        for p in generated.rglob("*")
        if p.is_file()
    }
    assert actual == expected


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_course_old_and_new_urls_serve_identical_bytes_and_http_metadata(
    tmp_path, method
):
    generated = tmp_path / "generated"
    content = b"fictional lesson input"
    digest = publication_case(tmp_path, generated, content)
    deduplicate(generated, tmp_path / "empty", tmp_path)
    app = Starlette(routes=[Mount("/static/shared/courses", CourseFiles(generated))])
    client = TestClient(app)

    old = client.request(
        method, "/static/shared/courses/vera/example/it/files/input.txt"
    )
    new = client.request(
        method, f"/static/shared/courses/lucia/_files/{digest}/practice.txt"
    )

    assert old.status_code == new.status_code == 200
    assert old.headers["etag"] == new.headers["etag"]
    assert (
        old.headers["content-length"]
        == new.headers["content-length"]
        == str(len(content))
    )
    assert old.content == new.content == (content if method == "GET" else b"")


def test_course_unknown_urls_stay_missing_and_ranges_work(tmp_path):
    generated = tmp_path / "generated"
    publication_case(tmp_path, generated, b"fictional lesson input")
    deduplicate(generated, tmp_path / "empty", tmp_path)
    client = TestClient(Starlette(routes=[Mount("/courses", CourseFiles(generated))]))

    response = client.get(
        "/courses/vera/example/it/files/input.txt", headers={"Range": "bytes=0-8"}
    )

    assert response.status_code == 206
    assert response.content == b"fictional"
    assert client.get("/courses/missing.txt").status_code == 404


def test_public_courses_have_no_duplicate_files_at_or_above_four_kib():
    groups = defaultdict(list)
    for path in (ROOT / "static/shared/courses").rglob("*"):
        if path.is_file() and path.stat().st_size >= 4096:
            groups[hashlib.sha256(path.read_bytes()).hexdigest()].append(path)

    duplicates = [paths for paths in groups.values() if len(paths) > 1]

    assert duplicates == []


def test_every_published_course_alias_targets_its_exact_hash_without_chains():
    directory = ROOT / "static/shared/courses"
    aliases = json.loads((directory / "file-aliases.json").read_bytes())["aliases"]

    for original, target in aliases.items():
        assert target not in aliases, (original, target)
        assert not (directory / original).exists(), original
        assert (
            hashlib.sha256((directory / target).read_bytes()).hexdigest()
            == Path(target).parent.name
        )
