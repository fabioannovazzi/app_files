"""All product builders reject host-repaired metadata before replacing releases."""

from __future__ import annotations

import builtins
import importlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts.validate_plugin_skills import (
    main,
    validate_skill_archive,
    validate_skill_entries,
    validate_skill_frontmatter,
)

VALID_SKILL = b'---\nname: future-workflow\ndescription: "Review evidence: prepare a draft."\n---\nBody\n'
INVALID_SKILL = b"---\nname: future-workflow\ndescription: Review evidence: prepare a draft.\n---\nBody\n"


@pytest.mark.parametrize(
    "description",
    [
        '"Review evidence: prepare a draft."',
        "'Review evidence: prepare a draft.'",
        "Simple description",
        "|\n  Review evidence: prepare a draft.\n  Keep sources.",
        '"> €100: vérification, perché, Prüfung"',
    ],
)
def test_valid_yaml_scalar_forms_are_accepted_without_modification(description):
    content = f"---\nname: sample\ndescription: {description}\n---\nBody".encode()

    result = validate_skill_frontmatter(content, path="skills/sample/SKILL.md")

    assert result is None


@pytest.mark.parametrize(
    "content",
    [
        INVALID_SKILL,
        b"---\nname: sample\ndescription: Prepare a company: assess customers.\n---",
        b"---\nname: sample\ndescription: null\n---",
        b"---\nname: sample\ndescription: true\n---",
        b"---\nname: sample\ndescription: [one, two]\n---",
        b"---\nname: sample\ndescription: {key: value}\n---",
        b"---\nname: sample\ndescription: ' '\n---",
        b"---\nname: ''\ndescription: Valid\n---",
        b"---\nname: sample\n---",
        b"---\nname: sample\nname: second\ndescription: Valid\n---",
        b"---\nname: sample\ndescription: Valid\nextra: {key: one, key: two}\n---",
        b"---\n1: numeric key\nname: sample\ndescription: Valid\n---",
        b"---\n- list\n---",
        b"---\nname: sample\ndescription: Unterminated",
        b"No frontmatter",
        b"\xef\xbb\xbf" + VALID_SKILL,
        b"\xff" + VALID_SKILL,
    ],
)
def test_malformed_or_ambiguous_metadata_reports_the_exact_skill(content):
    with pytest.raises(ValueError, match="Invalid skill metadata in nested/SKILL.md"):
        validate_skill_frontmatter(content, path="nested/SKILL.md")


def test_missing_parser_blocks_build_instead_of_skipping_validation(monkeypatch):
    original_import = builtins.__import__

    def missing_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("missing build dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_yaml)

    with pytest.raises(RuntimeError, match="requirements-plugin-build.txt"):
        validate_skill_frontmatter(VALID_SKILL, path="SKILL.md")


def test_duplicate_archive_member_is_rejected(tmp_path):
    archive = tmp_path / "duplicate.zip"
    with ZipFile(archive, "w") as handle:
        handle.writestr("SKILL.md", VALID_SKILL)
        with pytest.warns(UserWarning, match="Duplicate name"):
            handle.writestr("SKILL.md", VALID_SKILL)

    with pytest.raises(ValueError, match="Duplicate ZIP member"):
        validate_skill_archive(archive)


def test_embedded_and_new_skill_names_cannot_escape_validation():
    entries = {
        "README.md": b"not skill metadata",
        "modules/new/skills/new/SKILL.md": INVALID_SKILL,
    }

    with pytest.raises(ValueError, match="modules/new/skills/new/SKILL.md"):
        validate_skill_entries(entries)


@pytest.mark.parametrize("valid", [False, True])
def test_source_command_reports_invalid_skills(tmp_path, valid):
    path = tmp_path / "SKILL.md"
    path.write_bytes(VALID_SKILL if valid else INVALID_SKILL)

    result = main([str(path)])

    assert result == (0 if valid else 1)


def builder_case(tmp_path, monkeypatch, product, host):
    """Replace assembly inputs only; exercise each real build/check boundary."""
    output, public = tmp_path / "release.zip", tmp_path / "public.zip"
    metadata, directory = tmp_path / "release.json", tmp_path / "unpacked"
    codex = importlib.import_module("scripts.build_codex_plugin_zip")
    target = next(
        p
        for p in [*codex.load_packages(), *codex.load_bundles()]
        if p.target_name == product
    )
    prefix = (
        f"{target.package_root}/plugins/{product}/"
        if host == "codex"
        else f"{product}/" if host == "antigravity" else ""
    )
    entries = {
        prefix
        + ".codex-plugin/plugin.json": json.dumps(
            {"name": product, "version": "0.1.999"}
        ).encode(),
        prefix + "skills/future-workflow/SKILL.md": INVALID_SKILL,
        prefix + "mcp_config.json": b'{"mcpServers":{}}',
    }
    if host == "cowork":
        builder = importlib.import_module("scripts.build_claude_plugin_zip")
        _, packages = builder.load_configuration()
        target = replace(
            next(p for p in packages if p.plugin == product),
            output_directory=directory,
            output_zip=output,
            public_zip=public,
        )
        monkeypatch.setattr(builder, "claude_package_entries", lambda _: entries)
        build = lambda: builder.build_package(target)
        check = lambda: builder.verify_package(target)
    elif host == "antigravity":
        builder = importlib.import_module("build_antigravity_plugin")
        monkeypatch.setattr(builder, "package_entries", lambda _: entries)
        build = lambda: builder.build_package(output, metadata, product=product)
        check = lambda: builder.verify_package(output, metadata, product=product)
    else:
        target = replace(target, output_zip=output)
        monkeypatch.setattr(codex, "validate_plugin_source", lambda _: [])
        monkeypatch.setattr(codex, "expected_zip_entries", lambda _: entries)
        monkeypatch.setattr(codex, "chatgpt_upload_entries", lambda _: entries)
        if host == "codex":
            build = lambda: codex.build_package(target)
            check = lambda: codex.verify_package(target)
        else:
            build = lambda: codex.build_chatgpt_upload(target, output)
            check = lambda: codex.verify_chatgpt_upload(target, output)
    return build, check, entries, (output, public, metadata, directory)


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("host", ["codex", "chatgpt", "cowork", "antigravity"])
def test_invalid_candidate_cannot_replace_any_existing_artifact(
    tmp_path, monkeypatch, product, host
):
    build, _, _, (output, public, metadata, directory) = builder_case(
        tmp_path, monkeypatch, product, host
    )
    output.write_bytes(b"previous ZIP")
    public.write_bytes(b"previous public ZIP")
    metadata.write_bytes(b"previous metadata")
    directory.mkdir()
    (directory / "marker").write_bytes(b"previous directory")

    with pytest.raises(ValueError, match="Invalid skill metadata.*future-workflow"):
        build()

    assert output.read_bytes() == b"previous ZIP"
    assert public.read_bytes() == b"previous public ZIP"
    assert metadata.read_bytes() == b"previous metadata"
    assert (directory / "marker").read_bytes() == b"previous directory"


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("host", ["codex", "chatgpt", "cowork", "antigravity"])
def test_check_rejects_invalid_metadata_even_when_archive_matches_source(
    tmp_path, monkeypatch, product, host
):
    _, check, entries, (output, public, metadata, directory) = builder_case(
        tmp_path, monkeypatch, product, host
    )
    for archive in (output, public):
        with ZipFile(archive, "w") as handle:
            for name, content in entries.items():
                handle.writestr(name, content)
    for name, content in entries.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    metadata.write_text(
        json.dumps({"name": product, "version": "0.1.999"}, indent=2) + "\n"
    )

    if host == "antigravity":
        with pytest.raises(ValueError, match="Invalid skill metadata"):
            check()
    else:
        assert any("Invalid skill metadata" in error for error in check())


def test_all_source_skills_have_valid_metadata():
    assert main([]) == 0


def test_cowork_publishes_the_checked_bytes_without_a_second_serialization(
    tmp_path, monkeypatch
):
    builder = importlib.import_module("scripts.build_claude_plugin_zip")
    _, packages = builder.load_configuration()
    output, public = tmp_path / "release.zip", tmp_path / "public.zip"
    package = replace(
        next(p for p in packages if p.plugin == "clara"),
        output_directory=tmp_path / "unpacked",
        output_zip=output,
        public_zip=public,
    )
    skill_path = "skills/mparanza-future-workflow/SKILL.md"
    entries = {
        ".claude-plugin/plugin.json": b'{"name":"clara","version":"0.1.999"}',
        skill_path: VALID_SKILL.replace(b"name: future", b"name: mparanza-future"),
    }
    monkeypatch.setattr(builder, "claude_package_entries", lambda _: entries)
    original_writer = builder._write_zip
    candidates = []

    def unstable_writer(path, content):
        # A second serialization would introduce an unverified last-minute edit.
        content = {**content, skill_path: INVALID_SKILL} if candidates else content
        original_writer(path, content)
        candidates.append(path.read_bytes())

    monkeypatch.setattr(builder, "_write_zip", unstable_writer)

    builder.build_package(package)

    assert output.read_bytes() == candidates[0]
    assert public.read_bytes() == candidates[0]
    assert (package.output_directory / skill_path).read_bytes() == entries[skill_path]


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize(
    "filename",
    [
        "{p}-plugin.zip",
        "{p}-chatgpt-upload.zip",
        "{p}-claude-plugin.zip",
        "antigravity",
    ],
)
def test_all_shipped_product_skills_are_parseable(product, filename):
    archive = ROOT / (
        f"static/shared/{product}/downloads/{product}-antigravity-plugin.zip"
        if filename == "antigravity"
        else f"plugin_packages/{product}/{filename.format(p=product)}"
    )

    result = validate_skill_archive(archive)

    assert result is None
