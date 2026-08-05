from __future__ import annotations

import json
import re
from pathlib import Path

__all__: list[str] = []


ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
ROUTER_PATH = CLARA_ROOT / "skills" / "clara" / "SKILL.md"
CATALOG_PATH = (
    CLARA_ROOT / "skills" / "clara" / "references" / "workflow-catalog.md"
)


def _read_text(path: Path) -> str:
    """Return UTF-8 text for one Clara contract file."""

    return path.read_text(encoding="utf-8")


def _frontmatter_name(path: Path) -> str:
    """Return the mechanically declared bare skill name."""

    match = re.search(r"(?m)^name: ([a-z0-9-]+)$", _read_text(path))
    assert match is not None
    return match.group(1)


def test_clara_router_frontmatter_triggers_for_explicit_invocation() -> None:
    router = _read_text(ROUTER_PATH)

    frontmatter = router.split("---", maxsplit=2)[1]

    assert "whenever Clara is explicitly invoked" in frontmatter
    assert "including through @clara" in frontmatter
    assert "capability gap" in frontmatter
    assert "out of scope" in frontmatter


def test_clara_router_defines_supported_gap_and_unrelated_outcomes() -> None:
    router = _read_text(ROUTER_PATH)

    required_contracts = (
        "Supported professional work",
        "Professional capability gap",
        "Unrelated work",
        "Do not fall back to general-assistant behavior inside Clara",
        "Clara workflow: clara:<specialist-skill>",
    )

    assert all(contract in router for contract in required_contracts)
    assert "Clara exposes six distinct conversation workflows" not in router


def test_clara_workflow_catalog_covers_every_current_specialist_name() -> None:
    skill_paths = sorted((CLARA_ROOT / "skills").glob("*/SKILL.md"))
    declared_names = {_frontmatter_name(path) for path in skill_paths}
    directory_names = {path.parent.name for path in skill_paths}
    catalog = _read_text(CATALOG_PATH)
    catalogued_names = set(
        re.findall(r"^- `([a-z0-9-]+)`:", catalog, flags=re.MULTILINE)
    )

    # Exact set equality is deterministic because directory/frontmatter/catalog
    # identity is mechanically verifiable; semantic route selection stays model-led.
    assert declared_names == directory_names
    assert catalogued_names == declared_names - {"clara"}
    assert all(":" not in name for name in declared_names)


def test_clara_router_uses_model_led_selection_and_public_namespace() -> None:
    router = _read_text(ROUTER_PATH)
    normalized_router = " ".join(router.split())

    assert "Use model-led judgment" in normalized_router
    assert (
        "Do not build or use a deterministic keyword classifier"
        in normalized_router
    )
    assert "fully qualified form `clara:<skill-name>`" in normalized_router
    assert "Clara workflow: <specialist-skill>" not in normalized_router


def test_clara_trigger_fixtures_cover_explicit_scope_boundaries() -> None:
    fixtures = json.loads(
        (CLARA_ROOT / "evals" / "trigger_fixtures.json").read_text(
            encoding="utf-8"
        )
    )

    trigger_ids = {case["id"] for case in fixtures["should_trigger"]}
    non_trigger_ids = {case["id"] for case in fixtures["should_not_trigger"]}

    assert "clara-explicit-unrelated" in trigger_ids
    assert "clara-professional-capability-gap" in trigger_ids
    assert "generic-pizza" in non_trigger_ids
