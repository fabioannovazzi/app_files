from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "plugins" / "clara" / "skills" / "html-deck"
SCRIPTS = SKILL_ROOT / "scripts"
REVISION_MAP_SCHEMA = "clara.html_deck_revision_map.v1"


def run_script(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = "/tmp/html-deck-revision-test-pycache"
    return subprocess.run(
        [sys.executable, str(path), *args],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def slide_source(
    *,
    opening_text: str = "Evidence and implication.",
    summary_text: str = "Approve the governed next step.",
    logo_text: str = "Clara",
    decision_id: str = "decision",
) -> str:
    return f"""
    <section class="slide is-active" id="opening" data-slide-title="Opening claim"
      data-chapter="opening" aria-hidden="false">
      <div class="slide-frame">
        <h1>Opening claim</h1>
        <p data-component-id="opening-copy">{opening_text}</p>
      </div>
      <aside class="speaker-notes">Explain the context.</aside>
    </section>
    <section class="slide" id="{decision_id}" data-slide-title="Decision"
      data-chapter="decision" aria-hidden="true">
      <div class="slide-frame">
        <h2>Decision</h2>
        <p data-component-id="summary">{summary_text}</p>
        <span data-component-id="brand-mark" data-revision-protected="true"
          data-revision-protection-reason="Brand identity">{logo_text}</span>
      </div>
      <aside class="speaker-notes">Name the owner.</aside>
    </section>
    """


def create_work(path: Path, slides: str) -> Path:
    path.mkdir()
    metadata = {
        "schema_version": "clara.html_deck_work.v1",
        "title": "Decision Brief",
    }
    (path / "deck.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (path / "slides.html").write_text(slides, encoding="utf-8")
    (path / "custom.css").write_text("", encoding="utf-8")
    slide_ids = [
        "opening",
        "decision-v2" if 'id="decision-v2"' in slides else "decision",
    ]
    ledger = {
        "schema_version": "clara.html_deck_ledger.v1",
        "sources": [],
        "slides": [
            {
                "slide_id": slide_id,
                "basis_status": "speaker-judgement",
                "basis_note": "Fixture judgement.",
                "claims": [],
            }
            for slide_id in slide_ids
        ],
    }
    (path / "content-ledger.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def inspect(path: Path) -> dict[str, Any]:
    result = run_script(SCRIPTS / "inspect_html_deck.py", str(path))
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def revision_map(
    inventory: dict[str, Any],
    *,
    edit_targets: list[dict[str, Any]],
    untouched_slides: list[str],
    protected_slides: list[str] | None = None,
    protected_components: list[dict[str, str]] | None = None,
    slide_changes: dict[str, Any] | None = None,
    global_edits: list[str] | None = None,
) -> dict[str, Any]:
    normalized_targets = []
    for target in edit_targets:
        normalized_target = dict(target)
        normalized_target.setdefault("reason", "Apply the requested revision.")
        normalized_targets.append(normalized_target)
    return {
        "schema_version": REVISION_MAP_SCHEMA,
        "baseline_fingerprint": inventory["deck"]["normalized_dom_fingerprint"],
        "edit_targets": normalized_targets,
        "global_edits": global_edits or [],
        "untouched_slides": untouched_slides,
        "protected_slides": protected_slides or [],
        "protected_components": protected_components or [],
        "slide_changes": slide_changes or {"add": [], "remove": [], "rename": []},
    }


def write_map(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def comparison_codes(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {item["code"] for item in json.loads(result.stdout)["issues"]}


def test_inspector_reports_deterministic_components_and_protection(
    tmp_path: Path,
) -> None:
    work = create_work(tmp_path / "work", slide_source())

    first = inspect(work)
    second = inspect(work)

    assert first == second
    assert first["schema_version"] == "clara.html_deck_inventory.v1"
    assert first["deck"]["slide_count"] == 2
    decision = first["deck"]["slides"][1]
    components = {
        component["component_id"]: component
        for component in decision["components"]
        if component["component_id"]
    }
    assert components["brand-mark"]["protection"] == {
        "declared_by": "data-revision-protected",
        "protected": True,
        "reason": "Brand identity",
    }
    assert len(decision["normalized_dom_fingerprint"]) == 64


def test_inspector_accepts_clara_standalone_html(tmp_path: Path) -> None:
    standalone = tmp_path / "index.html"
    standalone.write_text(
        "<!doctype html><html><head><title>Decision Brief</title></head><body>"
        '<main class="deck-stage" data-clara-deck-mode="stage">'
        f"{slide_source()}</main></body></html>",
        encoding="utf-8",
    )

    report = inspect(standalone)

    assert report["input"]["kind"] == "standalone_html"
    assert report["deck"]["title"] == "Decision Brief"


def standalone_source(*, runtime: str = "window.deckRuntime = 1;") -> str:
    return (
        "<!doctype html><html><head><title>Decision Brief</title>"
        "<style>.slide { color: #111; }</style></head><body>"
        '<main class="deck-stage" data-clara-deck-mode="stage">'
        f"{slide_source()}</main><script>{runtime}</script></body></html>"
    )


def test_comparator_rejects_undeclared_standalone_runtime_change(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.html"
    after = tmp_path / "after.html"
    before.write_text(standalone_source(), encoding="utf-8")
    after.write_text(
        standalone_source(runtime="window.deckRuntime = 2;"),
        encoding="utf-8",
    )
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening", "decision"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "document.unplanned_global_change" in comparison_codes(result)


def test_inspector_rejects_unaddressable_protected_component(tmp_path: Path) -> None:
    slides = slide_source().replace(
        'data-component-id="brand-mark" data-revision-protected="true"',
        'data-revision-protected="true"',
    )
    work = create_work(tmp_path / "work", slides)

    result = run_script(SCRIPTS / "inspect_html_deck.py", str(work))

    assert result.returncode == 1
    assert "components.protected_id_required" in comparison_codes(result)


def test_revision_map_requires_complete_non_conflicting_classification(
    tmp_path: Path,
) -> None:
    work = create_work(tmp_path / "work", slide_source())
    inventory = inspect(work)
    payload = revision_map(
        inventory,
        edit_targets=[],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "validate_revision_map.py",
        str(work),
        str(map_path),
    )

    assert result.returncode == 1
    assert "map.slide_unclassified" in comparison_codes(result)


def test_revision_map_accepts_component_target_and_inline_protection(
    tmp_path: Path,
) -> None:
    work = create_work(tmp_path / "work", slide_source())
    inventory = inspect(work)
    payload = revision_map(
        inventory,
        edit_targets=[
            {
                "slide_id": "decision",
                "scope": "components",
                "component_ids": ["summary"],
                "reason": "Update the recommendation",
            }
        ],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "validate_revision_map.py",
        str(work),
        str(map_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["result"] == "pass"


def test_revision_map_requires_edit_target_reason(tmp_path: Path) -> None:
    work = create_work(tmp_path / "work", slide_source())
    inventory = inspect(work)
    payload = revision_map(
        inventory,
        edit_targets=[
            {
                "slide_id": "decision",
                "scope": "components",
                "component_ids": ["summary"],
            }
        ],
        untouched_slides=["opening"],
    )
    payload["edit_targets"][0]["reason"] = ""
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "validate_revision_map.py",
        str(work),
        str(map_path),
    )

    assert result.returncode == 1
    assert "map.target_reason_required" in comparison_codes(result)


def test_comparator_allows_only_the_targeted_component_change(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(
        tmp_path / "after",
        slide_source(summary_text="Approve the pilot with a named owner."),
    )
    payload = revision_map(
        inspect(before),
        edit_targets=[
            {
                "slide_id": "decision",
                "scope": "components",
                "component_ids": ["summary"],
            }
        ],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["planned_changes"] == [
        {
            "component_changes": [{"changed": True, "component_id": "summary"}],
            "scope": "components",
            "slide_id": "decision",
        }
    ]


def test_comparator_rejects_change_outside_component_target(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(
        tmp_path / "after",
        slide_source(
            opening_text="Evidence and implication.",
            summary_text="Approve the pilot.",
        ).replace("<h2>Decision</h2>", "<h2>Different decision</h2>"),
    )
    payload = revision_map(
        inspect(before),
        edit_targets=[
            {
                "slide_id": "decision",
                "scope": "components",
                "component_ids": ["summary"],
            }
        ],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "components.unplanned_change" in comparison_codes(result)


def test_comparator_rejects_protected_change_inside_slide_target(
    tmp_path: Path,
) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source(logo_text="Changed brand"))
    payload = revision_map(
        inspect(before),
        edit_targets=[{"slide_id": "decision", "scope": "slide", "component_ids": []}],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "components.protected_changed" in comparison_codes(result)


def test_comparator_rejects_protected_component_relocation(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    relocated = (
        slide_source()
        .replace(
            '<span data-component-id="brand-mark"',
            '<div><span data-component-id="brand-mark"',
        )
        .replace("Clara</span>", "Clara</span></div>")
    )
    after = create_work(tmp_path / "after", relocated)
    payload = revision_map(
        inspect(before),
        edit_targets=[{"slide_id": "decision", "scope": "slide", "component_ids": []}],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "components.protected_moved" in comparison_codes(result)


def test_revision_map_rejects_removing_slide_with_protected_component(
    tmp_path: Path,
) -> None:
    before = create_work(tmp_path / "before", slide_source())
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening"],
        slide_changes={"add": [], "remove": ["decision"], "rename": []},
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "validate_revision_map.py",
        str(before),
        str(map_path),
    )

    assert result.returncode == 1
    assert "map.protected_component_removal" in comparison_codes(result)


def test_comparator_rejects_unplanned_slide_id_change(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source(decision_id="decision-v2"))
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening", "decision"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    codes = comparison_codes(result)
    assert "slides.unplanned_removal_or_id_change" in codes
    assert "slides.unplanned_addition_or_id_change" in codes


def test_comparator_accepts_declared_id_only_rename(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source(decision_id="decision-v2"))
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening"],
        slide_changes={
            "add": [],
            "remove": [],
            "rename": [{"from": "decision", "to": "decision-v2"}],
        },
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_comparator_rejects_ledger_change_hidden_inside_rename(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source(decision_id="decision-v2"))
    ledger_path = after / "content-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["slides"][1]["basis_note"] = "Changed during the ID rename."
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening"],
        slide_changes={
            "add": [],
            "remove": [],
            "rename": [{"from": "decision", "to": "decision-v2"}],
        },
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "provenance.rename_changed_ledger" in comparison_codes(result)


def test_comparator_rejects_undeclared_custom_css_change(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source())
    (after / "custom.css").write_text(".slide { color: red; }\n", encoding="utf-8")
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening", "decision"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "document.unplanned_global_change" in comparison_codes(result)


def test_comparator_rejects_undeclared_metadata_change(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source())
    metadata_path = after / "deck.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["title"] = "Changed title"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening", "decision"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "document.unplanned_global_change" in comparison_codes(result)


def test_comparator_accepts_declared_custom_css_change(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source())
    (after / "custom.css").write_text(".slide { color: red; }\n", encoding="utf-8")
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening", "decision"],
        global_edits=["custom-css"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_comparator_rejects_declared_component_noop(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(tmp_path / "after", slide_source())
    payload = revision_map(
        inspect(before),
        edit_targets=[
            {
                "slide_id": "decision",
                "scope": "components",
                "component_ids": ["summary"],
            }
        ],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "targets.no_change" in comparison_codes(result)


def test_comparator_rejects_untargeted_slide_ledger_change(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    after = create_work(
        tmp_path / "after",
        slide_source(summary_text="Approve the pilot with a named owner."),
    )
    ledger_path = after / "content-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["slides"][0]["basis_note"] = "Changed evidence basis."
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload = revision_map(
        inspect(before),
        edit_targets=[
            {
                "slide_id": "decision",
                "scope": "components",
                "component_ids": ["summary"],
            }
        ],
        untouched_slides=["opening"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 1
    assert "provenance.unplanned_slide_change" in comparison_codes(result)


def test_normalized_dom_ignores_formatting_only_whitespace(tmp_path: Path) -> None:
    before = create_work(tmp_path / "before", slide_source())
    compact = slide_source().replace("\n", " ").replace("      ", " ")
    after = create_work(tmp_path / "after", compact)
    payload = revision_map(
        inspect(before),
        edit_targets=[],
        untouched_slides=["opening", "decision"],
    )
    map_path = write_map(tmp_path / "revision-map.json", payload)

    result = run_script(
        SCRIPTS / "compare_html_deck_revision.py",
        str(before),
        str(after),
        "--revision-map",
        str(map_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
