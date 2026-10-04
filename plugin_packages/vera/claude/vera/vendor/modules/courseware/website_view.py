"""Copy the exact validated local teaching site, including its local assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def website_files(lesson: Path, execution: dict) -> dict[Path, tuple[str, str]]:
    """Bind authored outputs and passive assets to the complete native inventory."""
    records = [
        lesson / item["path"]
        for item in execution["native_records"]
        if Path(item["path"]).name == "site_validation.json"
    ]
    if len(records) != 1:
        raise ValueError("Website results need one native site validation record")
    validation = json.loads(records[0].read_text(encoding="utf-8"))
    inventory = validation.get("inventory", [])
    digest = hashlib.sha256(
        json.dumps(
            inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if (
        validation.get("status") != "ready"
        or validation.get("site_digest") != digest
        or not inventory
    ):
        raise ValueError("Website results need a current successful site inventory")
    site = records[0].parent / "work/site"
    outputs = {lesson / item["path"]: item["sha256"] for item in execution["outputs"]}
    allowed = {
        ".html",
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".woff",
        ".woff2",
        ".ttf",
        ".txt",
    }
    result = {}
    for item in inventory:
        relative = PurePosixPath(item["path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in item["path"]
            or relative.as_posix() != item["path"]
            or relative.suffix.lower() not in allowed
        ):
            raise ValueError("Website inventory contains an unsupported local path")
        source = site / relative
        # Reused styles/fonts/images are dependencies, never completion evidence.
        # Their exact bytes remain bound by the attested native inventory.
        output_required = relative.suffix.lower() == ".html"
        if (
            source in result
            or (output_required and outputs.get(source) != item["sha256"])
            or (source in outputs and outputs[source] != item["sha256"])
            or not source.is_file()
            or any(p.is_symlink() for p in (source, *source.parents))
            or source.stat().st_size != item["bytes"]
            or hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]
        ):
            raise ValueError(
                "Website results must include every exact validated site file"
            )
        result[source] = ("website/" + relative.as_posix(), item["sha256"])
    if site / "index.html" not in result:
        raise ValueError("Website results need the validated index page")
    if any(p.is_relative_to(site) and p not in result for p in outputs):
        raise ValueError("Website outputs contain an unvalidated site file")
    return result
