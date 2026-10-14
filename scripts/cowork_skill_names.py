"""Enforce owned Claude skill identities in generated, installable packages."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from posixpath import normpath, relpath
from zipfile import ZipFile

__all__ = ["project_skill_names", "validate_skill_names", "validate_skill_zip"]

PREFIX = "mparanza-"
# These checks enforce the documented host format and our owned namespace.
# They do not classify a skill's purpose or predict future provider policies.
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
FRONTMATTER_NAME = re.compile(r"(?m)^name:[ \t]*(['\"]?)([^\n'\"]+)\1[ \t]*$")
TEXT_SUFFIXES = {
    ".md",
    ".json",
    ".py",
    ".cjs",
    ".js",
    ".mjs",
    ".ps1",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
}
PATH_TOKEN = re.compile(
    r"(?<![a-zA-Z0-9_-])(?:\.{1,2}/|skills/|modules/)[^\s`\"'<>(),;]*"
)


def _name(path: str, data: bytes) -> str:
    text = data.decode("utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{path}: invalid skill frontmatter")
    frontmatter = text.split("\n---\n", 1)[0]
    names = FRONTMATTER_NAME.findall(frontmatter)
    if len(names) != 1:
        raise ValueError(f"{path}: expected exactly one skill name")
    name = names[0][1].strip()
    if not NAME.fullmatch(name) or len(name) > 64:
        raise ValueError(f"{path}: invalid skill name {name!r}")
    if "anthropic" in name or "claude" in name:
        raise ValueError(f"{path}: skill name contains a provider-reserved word")
    if PurePosixPath(path).parent.name != name:
        raise ValueError(f"{path}: skill name differs from its directory: {name}")
    return name


def _skills(entries: dict[str, bytes]) -> dict[str, str]:
    return {
        path: _name(path, data)
        for path, data in entries.items()
        if path.endswith("/SKILL.md")
    }


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _component_roots(entries: dict[str, bytes], path: str) -> tuple[str, ...]:
    parts = PurePosixPath(path).parts
    if parts[0] == "modules" and len(parts) > 2:
        return (f"modules/{parts[1]}/",)
    if parts[0] == "skills" and len(parts) > 2 and "components.json" in entries:
        components = json.loads(entries["components.json"])
        for component in components["plugins"]:
            role = components.get("workflow_roles", {}).get(component, {})
            if parts[1] == role.get("skill", component):
                return tuple(
                    f"modules/{name}/"
                    for name in [component, *role.get("internal_engines", [])]
                )
    return ()


def project_skill_names(entries: dict[str, bytes]) -> dict[str, bytes]:
    """Namespace owned skills; preserve workflow IDs and canonical provenance."""
    skills = _skills(entries)
    aliases = {
        name: name if name.startswith(PREFIX) else PREFIX + name
        for name in skills.values()
    }
    directories = {
        str(PurePosixPath(path).parent): str(
            PurePosixPath(path).parent.with_name(aliases[name])
        )
        for path, name in skills.items()
    }

    ordered = sorted(directories.items(), key=lambda item: -len(item[0]))

    def projected_path(path: str) -> str:
        for old, new in ordered:
            if path == old or path.startswith(old + "/"):
                return new + path[len(old) :]
        return path

    result: dict[str, bytes] = {}
    for path, data in entries.items():
        destination = projected_path(path)
        working_roots = _component_roots(entries, path)
        if destination in result:
            raise ValueError(f"Claude skill name projection collides: {destination}")
        provenance = (
            path.startswith("assets/courses/")
            or (
                path.startswith("skills/vera/references/localization/")
                and path.endswith(".json")
            )
            or (
                path.startswith("skills/mparanza-vera/references/localization/")
                and path.endswith(".json")
            )
        )
        if not provenance and PurePosixPath(path).suffix in TEXT_SUFFIXES:
            text = data.decode("utf-8")

            def rewrite(match: re.Match[str]) -> str:
                token = match.group(0)
                # Explicit plugin-root paths and paths relative to this file are
                # resolved independently; component directories are never renamed.
                target = normpath(str(PurePosixPath(path).parent / token))
                root_target = normpath(token)
                if projected_path(root_target) != root_target:
                    return projected_path(root_target)
                if projected_path(target) != target:
                    rewritten = relpath(
                        projected_path(target), str(PurePosixPath(destination).parent)
                    )
                    if rewritten != normpath(token):
                        return rewritten
                for working_root in working_roots:
                    component_target = working_root + token
                    if projected_path(component_target) != component_target:
                        return projected_path(component_target).removeprefix(
                            working_root
                        )
                return token

            text = PATH_TOKEN.sub(rewrite, text)
            # Path joins in bundled Python helpers are also executable paths.
            for old, new in aliases.items():
                if old == new:
                    continue
                text = re.sub(
                    r"(['\"])skills\1(\s*/\s*)(['\"])" + re.escape(old) + r"\3",
                    lambda m: f"{m[1]}skills{m[1]}{m[2]}{m[3]}{new}{m[3]}",
                    text,
                )
                # A bare backticked identifier can be a canonical CLI workflow
                # ID. Rename explicit skill invocations, never ambiguous prose.
                for product in ("vera", "clara", "lucia"):
                    text = text.replace(f"`{product}:{old}`", f"`{product}:{new}`")
                    text = text.replace(f"`/{product}:{old}`", f"`/{product}:{new}`")
                text = text.replace(f"`/{old}`", f"`/{new}`")
                if PurePosixPath(path).name == "workflow-catalog.md":
                    text = re.sub(
                        r"(?m)^- `" + re.escape(old) + r"`:", f"- `{new}`:", text
                    )
            if path in skills:
                header, body = text.split("\n---\n", 1)
                header = FRONTMATTER_NAME.sub(f"name: {aliases[skills[path]]}", header)
                text = header + "\n---\n" + body
            data = text.encode()
        result[destination] = data

    # Component and workflow IDs stay canonical; only wrapper paths get aliases.
    if "components.json" in result:
        components = json.loads(result["components.json"])
        roles = components.setdefault("workflow_roles", {})
        for component in components["plugins"]:
            role = roles.get(component, {})
            name = role.get("skill", component)
            if f"skills/{aliases.get(name, name)}/SKILL.md" in result:
                role["skill"] = aliases.get(name, name)
                roles[component] = role
        result["components.json"] = _json(components)
    index_path = "assets/courses/index.json"
    if index_path in result:
        index = json.loads(result[index_path])
        for record in index["courses"].values():
            manifest = "assets/courses/" + record["path"]
            course = json.loads(result[manifest])
            for source in course["sources"]:
                source["path"] = projected_path(source["path"])
                source["sha256"] = hashlib.sha256(result[source["path"]]).hexdigest()
            result[manifest] = _json(course)
            record["sha256"] = hashlib.sha256(result[manifest]).hexdigest()
        result[index_path] = _json(index)
    validate_skill_names(result)
    return result


def validate_skill_names(entries: dict[str, bytes]) -> None:
    """Reject unsafe identities and broken explicit skill links in final bytes."""
    skills = _skills(entries)
    for path, name in skills.items():
        if not name.startswith(PREFIX) or name == PREFIX.rstrip("-"):
            raise ValueError(f"{path}: skill name must start with {PREFIX}")
    # Name/folder alignment makes identities unique within each directory.
    # Shared component mirrors are not additional root-level public skills;
    # duplicate ZIP members are checked independently below.
    external_routers: set[str] = set()
    manifest_path = ".claude-plugin/plugin.json"
    if manifest_path in entries:
        product = json.loads(entries[manifest_path])["name"]
        # Shared methods can explicitly refer to another installed product's
        # router. Its files are outside this archive, not dangling owned links.
        external_routers = {
            PREFIX + name for name in ("vera", "clara", "lucia") if name != product
        }
    for path, data in entries.items():
        if PurePosixPath(path).suffix != ".md" or path.startswith("assets/courses/"):
            continue
        for token in PATH_TOKEN.findall(data.decode()):
            token = token.rstrip(".").split("#", 1)[0]
            if not token.endswith("/SKILL.md"):
                continue
            target_name = PurePosixPath(token).parent.name
            if token.startswith("skills/") and target_name in external_routers:
                continue
            canonical = {name.removeprefix(PREFIX) for name in skills.values()}
            if not target_name.startswith(PREFIX) and target_name not in canonical:
                continue
            relative = normpath(str(PurePosixPath(path).parent / token))
            components = [
                normpath(root + token) for root in _component_roots(entries, path)
            ]
            if (
                token not in entries
                and relative not in entries
                and not any(component in entries for component in components)
            ):
                raise ValueError(f"{path}: broken skill reference {token}")


def validate_skill_zip(path: Path | str) -> None:
    """Inspect the actual distributable, including duplicate ZIP members."""
    with ZipFile(str(path)) as archive:
        files = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(files) != len(set(files)):
            raise ValueError(f"{path}: duplicate ZIP member")
        validate_skill_names({name: archive.read(name) for name in files})
