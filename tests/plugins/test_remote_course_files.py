"""Verify download boundaries, immutable assets and real slimmed packages."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request
from zipfile import ZipFile

import pytest

from scripts.course_materials.remote_files import (
    externalize_course_files,
    publish_remote_files,
)
from tests.plugins.test_prepared_courses import isolated  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
import courseware.library as runtime


class Response(io.BytesIO):
    def __init__(self, content: bytes, url: str, length: str | None = None):
        super().__init__(content)
        self.url = url
        self.headers = {} if length is None else {"Content-Length": length}

    def geturl(self):
        return self.url


@pytest.fixture
def remote_case(isolated):
    root, manifest, _ = isolated
    course = json.loads(manifest.read_bytes())
    remote = {}
    bodies = {}
    for asset in course["files"]:
        source = manifest.parent / asset["path"]
        url_path = f"_files/{asset['sha256']}/{source.name}"
        url = f"https://mparanza.com/static/shared/courses/vera/{url_path}"
        bodies[url] = source.read_bytes()
        remote[f"variance-analysis/{asset['path']}"] = {
            "url_path": url_path,
            "sha256": asset["sha256"],
        }
        source.unlink()
    (root / "assets/courses/remote.json").write_text(
        json.dumps(
            {
                "schema": "mparanza.course_files_remote.v1",
                "base": "https://mparanza.com/static/shared/courses/vera/",
                "files": remote,
            }
        )
    )
    return root, course, bodies


def test_remote_load_validates_catalogue_without_network(remote_case, monkeypatch):
    root, _, _ = remote_case

    def forbidden(*args, **kwargs):
        pytest.fail("load must not access the network")

    monkeypatch.setattr(runtime, "urlopen", forbidden)
    course = runtime.CourseLibrary(root, {"variance-analysis"}).load(
        "variance-analysis", "it"
    )
    assert course["workflow"] == "variance-analysis"


def test_render_downloads_only_selected_language_and_preserves_original_hashes(
    remote_case, tmp_path, monkeypatch
):
    root, course, bodies = remote_case
    fetched = []

    def open_file(url, *, timeout):
        assert timeout == 30
        fetched.append(url)
        return Response(bodies[url], url)

    monkeypatch.setattr(runtime, "urlopen", open_file)
    destination = tmp_path / "lesson"
    result = runtime.CourseLibrary(root, {"variance-analysis"}).render(
        "variance-analysis", "it", destination
    )
    expected = [a for a in course["files"] if "it" in a["languages"]]
    assert len(fetched) == len(expected)
    assert all(
        hashlib.sha256((destination / a["path"]).read_bytes()).hexdigest()
        == a["sha256"]
        for a in expected
    )
    assert not any(
        (destination / a["path"]).exists()
        for a in course["files"]
        if "it" not in a["languages"]
    )
    assert Path(result["course"]).is_file()
    assert not list(destination.glob(".course-download-*"))


@pytest.mark.parametrize(
    "failure", ["wrong_hash", "declared_size", "stream_size", "foreign_response"]
)
def test_rejected_download_exposes_no_partial_lesson(
    remote_case, tmp_path, monkeypatch, failure
):
    root, _, bodies = remote_case

    def open_file(url, *, timeout):
        if failure == "wrong_hash":
            return Response(b"changed", url)
        if failure == "declared_size":
            return Response(bodies[url], url, str(runtime._MAX_ATTACHMENT_BYTES + 1))
        if failure == "stream_size":
            return Response(bodies[url], url)
        return Response(bodies[url], "https://foreign.example/file")

    if failure == "stream_size":
        monkeypatch.setattr(runtime, "_MAX_ATTACHMENT_BYTES", 1)
    monkeypatch.setattr(runtime, "urlopen", open_file)
    destination = tmp_path / "lesson"
    with pytest.raises(runtime.CourseError):
        runtime.CourseLibrary(root, {"variance-analysis"}).render(
            "variance-analysis", "it", destination
        )
    assert list(destination.iterdir()) == []


def test_network_failure_is_actionable_and_same_folder_can_be_retried(
    remote_case, tmp_path, monkeypatch
):
    root, _, bodies = remote_case

    def blocked(*args, **kwargs):
        raise URLError("network egress blocked")

    monkeypatch.setattr(runtime, "urlopen", blocked)
    library = runtime.CourseLibrary(root, {"variance-analysis"})
    destination = tmp_path / "lesson"
    with pytest.raises(runtime.CourseError, match="Settings → Capabilities"):
        library.render("variance-analysis", "it", destination)
    monkeypatch.setattr(
        runtime, "urlopen", lambda url, **kwargs: Response(bodies[url], url)
    )
    result = library.render("variance-analysis", "it", destination)
    assert Path(result["course"]).is_file()


@pytest.mark.parametrize(
    "url",
    [
        "http://mparanza.com/static/shared/courses/file",
        "https://foreign.example/file",
        "https://mparanza.com@foreign.example/file",
    ],
)
def test_redirect_policy_rejects_foreign_or_insecure_destination(url):
    request = Request("https://mparanza.com/static/shared/courses/vera/file")
    with pytest.raises(runtime.CourseError):
        runtime._CourseRedirects().redirect_request(
            request, None, 302, "Found", {}, url
        )


@pytest.mark.parametrize(
    "path",
    [
        "https://foreign.example/a.md",
        "//foreign.example/a.md",
        "../a.md",
        "%2e%2e/a.md",
        "_files/code.py",
    ],
)
def test_remote_manifest_cannot_authorize_foreign_paths_or_code(remote_case, path):
    root, _, _ = remote_case
    manifest = root / "assets/courses/remote.json"
    data = json.loads(manifest.read_bytes())
    next(iter(data["files"].values()))["url_path"] = path
    manifest.write_text(json.dumps(data))
    with pytest.raises(runtime.CourseError):
        runtime.CourseLibrary(root, {"variance-analysis"}).load(
            "variance-analysis", "it"
        )


def public_case(tmp_path):
    content = b"fictional lesson data"
    digest = hashlib.sha256(content).hexdigest()
    asset = {
        "path": "files/input.txt",
        "sha256": digest,
        "languages": ["en"],
        "role": "source",
    }
    course = json.dumps(
        {"schema": "mparanza.teaching_kit.v2", "files": [asset]}
    ).encode()
    index = json.dumps(
        {"product": "vera", "courses": {"sample": {"path": "sample/course.json"}}}
    ).encode()
    assets = tmp_path / "plugins/vera/assets/courses"
    (assets / "sample").mkdir(parents=True)
    (assets / "index.json").write_bytes(index)
    (assets / "sample/course.json").write_bytes(course)
    public = tmp_path / "static/shared/courses/vera/sample/en/files/input.txt"
    public.parent.mkdir(parents=True)
    public.write_bytes(content)
    immutable = tmp_path / f"static/shared/courses/vera/_files/{digest}/input.txt"
    immutable.parent.mkdir(parents=True)
    immutable.write_bytes(content)
    entries = {
        "assets/courses/index.json": index,
        "assets/courses/sample/course.json": course,
        "assets/courses/sample/files/input.txt": content,
    }
    return entries, public, immutable


def test_externalization_preserves_metadata_and_rejects_changed_public_file(tmp_path):
    entries, public, _ = public_case(tmp_path)
    before = dict(entries)
    externalize_course_files(entries, "vera", root=tmp_path)
    assert entries["assets/courses/index.json"] == before["assets/courses/index.json"]
    assert (
        entries["assets/courses/sample/course.json"]
        == before["assets/courses/sample/course.json"]
    )
    assert "assets/courses/sample/files/input.txt" not in entries
    # Reapplication is required when projecting an already slimmed native package.
    externalize_course_files(entries, "vera", root=tmp_path)
    public.write_bytes(b"changed website material")
    with pytest.raises(ValueError, match="byte-identical"):
        externalize_course_files(entries, "vera", root=tmp_path)


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("surface", ["plugin", "chatgpt-upload", "claude-plugin"])
def test_actual_packages_contain_only_course_metadata_and_complete_remote_maps(
    product, surface
):
    archive = ROOT / f"plugin_packages/{product}/{product}-{surface}.zip"
    prefix = f"{product}-codex-plugin/plugins/{product}/" if surface == "plugin" else ""
    with ZipFile(archive) as zipped:
        assets = prefix + "assets/courses/"
        names = {
            name
            for name in zipped.namelist()
            if name.startswith(assets) and not name.endswith("/")
        }
        assert all(
            name in {assets + "index.json", assets + "remote.json"}
            or name.endswith("/course.json")
            for name in names
        )
        index = json.loads(zipped.read(assets + "index.json"))
        if product in {"vera", "lucia"}:
            canonical = json.loads(
                (ROOT / f"plugins/{product}/assets/courses/index.json").read_bytes()
            )
            assert set(index["courses"]) == set(canonical["courses"])
        remote = json.loads(zipped.read(assets + "remote.json"))
        keys = set()
        for workflow, entry in index["courses"].items():
            course = json.loads(zipped.read(assets + entry["path"]))
            for asset in course["files"]:
                key = f"{workflow}/{asset['path']}"
                keys.add(key)
                record = remote["files"][key]
                public = ROOT / "static/shared/courses" / product / record["url_path"]
                assert (
                    hashlib.sha256(public.read_bytes()).hexdigest()
                    == record["sha256"]
                    == asset["sha256"]
                )
        assert set(remote["files"]) == keys
        if surface == "claude-plugin":
            manifest = json.loads(zipped.read(prefix + ".claude-plugin/plugin.json"))
            assert manifest["privacyPolicyUrl"] == "https://mparanza.com/privacy"


def test_new_material_retains_previous_immutable_attachment(tmp_path, monkeypatch):
    from scripts.course_materials import remote_files

    _, public, old = public_case(tmp_path)
    monkeypatch.setattr(remote_files, "PRODUCTS", frozenset({"vera"}))
    before = old.read_bytes()
    course_path = tmp_path / "plugins/vera/assets/courses/sample/course.json"
    course = json.loads(course_path.read_bytes())
    public.write_bytes(b"revised fictional lesson data")
    course["files"][0]["sha256"] = hashlib.sha256(public.read_bytes()).hexdigest()
    course_path.write_text(json.dumps(course))

    publish_remote_files(tmp_path)

    new = (
        tmp_path
        / "static/shared/courses/vera"
        / remote_files.immutable_path(course["files"][0])
    )
    assert old.read_bytes() == before
    assert new.read_bytes() == public.read_bytes()
    assert new != old


def test_immutable_attachment_cannot_be_overwritten(tmp_path, monkeypatch):
    from scripts.course_materials import remote_files

    _, _, immutable = public_case(tmp_path)
    monkeypatch.setattr(remote_files, "PRODUCTS", frozenset({"vera"}))
    immutable.write_bytes(b"unexpected alteration")

    with pytest.raises(ValueError, match="Immutable course file changed"):
        publish_remote_files(tmp_path)

    assert immutable.read_bytes() == b"unexpected alteration"


def write_publication_policy(root, *, withdrawn=(), language_downloads=()):
    directory = root / "scripts/course_materials"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "publication_policy.json").write_text(
        json.dumps(
            {
                "withdrawn_lessons": list(withdrawn),
                "existing_language_downloads": list(language_downloads),
            }
        )
    )


def test_language_downloads_keep_exact_hash_and_never_recreate_removed_files(
    tmp_path, monkeypatch
):
    from scripts.course_materials import remote_files

    entries, public, immutable = public_case(tmp_path)
    original_hash = hashlib.sha256(public.read_bytes()).hexdigest()
    immutable.unlink()
    write_publication_policy(tmp_path, language_downloads=("vera",))
    monkeypatch.setattr(remote_files, "PRODUCTS", frozenset({"vera"}))

    assert publish_remote_files(tmp_path, check=True) == 1
    externalize_course_files(entries, "vera", root=tmp_path)
    externalize_course_files(entries, "vera", root=tmp_path)
    publish_remote_files(tmp_path)

    remote = json.loads(entries["assets/courses/remote.json"])
    assert remote["files"]["sample/files/input.txt"] == {
        "url_path": "sample/en/files/input.txt",
        "sha256": original_hash,
    }
    assert not immutable.exists()
    assert hashlib.sha256(public.read_bytes()).hexdigest() == original_hash


def test_language_downloads_reject_altered_or_missing_existing_material(tmp_path):
    entries, public, immutable = public_case(tmp_path)
    immutable.unlink()
    write_publication_policy(tmp_path, language_downloads=("vera",))
    public.write_bytes(b"different material")

    with pytest.raises(ValueError, match="byte-identical"):
        externalize_course_files(entries, "vera", root=tmp_path)


def test_explicit_withdrawal_removes_only_lesson_and_never_regenerates_it(
    tmp_path, monkeypatch
):
    from scripts.course_materials import remote_files

    entries, public, immutable = public_case(tmp_path)
    public.unlink()
    immutable.unlink()
    entries["skills/sample/SKILL.md"] = b"professional workflow remains available"
    write_publication_policy(tmp_path, withdrawn=("vera/sample",))
    monkeypatch.setattr(remote_files, "PRODUCTS", frozenset({"vera"}))

    assert publish_remote_files(tmp_path) == 0
    externalize_course_files(entries, "vera", root=tmp_path)

    assert json.loads(entries["assets/courses/index.json"])["courses"] == {}
    assert json.loads(entries["assets/courses/remote.json"])["files"] == {}
    assert not any(name.startswith("assets/courses/sample/") for name in entries)
    assert (
        entries["skills/sample/SKILL.md"] == b"professional workflow remains available"
    )
    assert not public.exists()
    assert not immutable.exists()
