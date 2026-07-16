from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "plugins" / "clara" / "skills" / "html-deck"
COMPOSER_PATH = SKILL_ROOT / "scripts" / "compose_html_deck.py"
REGISTRY_PATH = SKILL_ROOT / "assets" / "layout-library" / "registry.json"


def load_composer() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_html_deck_composer", COMPOSER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cover_slide(*, slide_id: str = "opening") -> dict[str, object]:
    title = "Choose the governed path"
    return {
        "id": slide_id,
        "layout_id": "editorial-cover",
        "title": title,
        "chapter": "opening",
        "chapter_label": "Opening",
        "tone": "dark",
        "notes": "Frame the decision and the consequence of delay.",
        "source_refs": ["source-01"],
        "claim_refs": ["claim-01"],
        "slots": {
            "eyebrow": "Leadership discussion",
            "title": title,
            "subtitle": "A concise evidence-led promise for the room.",
            "author": "Advisory team",
            "source_note": "Internal evidence synthesis.",
        },
    }


def metric_slide(*, slide_id: str = "decision-gap") -> dict[str, object]:
    title = "The operating gap is now visible"
    return {
        "id": slide_id,
        "layout_id": "metric-contrast",
        "title": title,
        "chapter": "evidence",
        "chapter_label": "Evidence",
        "notes": "Reveal actual, comparison basis, and implication in order.",
        "source_refs": ["source-02"],
        "claim_refs": ["claim-02"],
        "slots": {
            "eyebrow": "Observed difference",
            "title": title,
            "metrics": [
                {
                    "label": "Observed",
                    "value": "72",
                    "detail": "Actual measure in the stated period.",
                    "tone": "neutral",
                    "_fragment": 1,
                },
                {
                    "label": "Decision gap",
                    "value": "24",
                    "detail": "Difference against the agreed baseline.",
                    "tone": "accent",
                    "_fragment": 2,
                },
            ],
            "source_note": "Values shown on a consistent basis.",
        },
    }


def deck_plan(
    *slides: dict[str, object], allow_bespoke_html: bool = False
) -> dict[str, object]:
    return {
        "schema_version": "clara.html_deck_plan.v1",
        "allow_bespoke_html": allow_bespoke_html,
        "slides": list(slides),
    }


def test_layout_registry_exposes_complete_advisory_contracts() -> None:
    composer = load_composer()

    registry = composer.load_registry(REGISTRY_PATH)

    layouts = registry["layouts"]
    assert len(layouts) == 15
    assert "visual-takeaway" in layouts
    assert layouts["visual-takeaway"]["slots"]["visual"]["renderer"] == "data_visual"
    assert all(layout["narrative_role"] for layout in layouts.values())
    assert all(
        layout["density_budget"]["max_total_words"] > 0 for layout in layouts.values()
    )
    assert all(
        layout["typography_budget"]["body_min_px"] >= 18 for layout in layouts.values()
    )


def test_compose_deck_renders_registered_layouts_with_provenance_and_fragments() -> (
    None
):
    composer = load_composer()
    opening = cover_slide()
    opening["source_refs"] = ["source-01", "source-appendix"]
    opening["claim_refs"] = ["claim-01", "claim-guardrail"]
    plan = deck_plan(opening, metric_slide())

    result = composer.compose_deck(plan, registry_path=REGISTRY_PATH)

    assert result.slide_count == 2
    assert result.layout_ids == ("editorial-cover", "metric-contrast")
    assert 'id="opening"' in result.slides_html
    assert 'data-source-ids="source-01 source-appendix"' in result.slides_html
    assert 'data-claim-ids="claim-01 claim-guardrail"' in result.slides_html
    assert 'data-claim-ids="claim-02"' in result.slides_html
    assert 'data-fragment="1"' in result.slides_html
    assert result.slides_html.count('aria-hidden="false"') == 1
    assert 'data-qa-role="metric-item"' in result.slides_html
    assert 'data-qa-headline-max-lines="3"' in result.slides_html
    assert 'data-qa-body-min-px="20"' in result.slides_html
    assert 'style="--clara-body-min: 1.5625cqw"' in result.slides_html
    assert ".clara-metric-grid" in result.custom_css


def test_compose_deck_escapes_text_and_reserved_builder_tokens() -> None:
    composer = load_composer()
    slide = cover_slide()
    title = "Choose <control> & {{proof}}"
    slide["title"] = title
    slots = dict(slide["slots"])
    slots["title"] = title
    slide["slots"] = slots

    result = composer.compose_deck(deck_plan(slide), registry_path=REGISTRY_PATH)

    assert "&lt;control&gt; &amp; &#123;&#123;proof&#125;&#125;" in result.slides_html
    assert "{{proof}}" not in result.slides_html


def test_compose_deck_rejects_unknown_slots() -> None:
    composer = load_composer()
    slide = cover_slide()
    slots = dict(slide["slots"])
    slots["invented"] = "Not in the layout contract"
    slide["slots"] = slots

    with pytest.raises(ValueError, match="unknown slots"):
        composer.compose_deck(deck_plan(slide), registry_path=REGISTRY_PATH)


def test_compose_deck_rejects_noncontiguous_fragments() -> None:
    composer = load_composer()
    slide = metric_slide()
    slots = dict(slide["slots"])
    metrics = [dict(item) for item in slots["metrics"]]
    metrics[1]["_fragment"] = 3
    slots["metrics"] = metrics
    slide["slots"] = slots

    with pytest.raises(ValueError, match="contiguous"):
        composer.compose_deck(deck_plan(slide), registry_path=REGISTRY_PATH)


def test_compose_deck_allows_paired_items_to_reveal_together() -> None:
    composer = load_composer()
    title = "Two paths reveal on the same comparison steps"
    slide = {
        "id": "paired-paths",
        "layout_id": "paired-comparison",
        "title": title,
        "chapter": "options",
        "chapter_label": "Options",
        "notes": "Reveal equivalent dimensions together.",
        "slots": {
            "eyebrow": "Choice architecture",
            "title": title,
            "left_label": "Path A",
            "left_title": "Move now",
            "left_items": [
                {"label": "Control", "body": "Named owner.", "_fragment": 1},
                {"label": "Risk", "body": "Higher exposure.", "_fragment": 2},
            ],
            "right_label": "Path B",
            "right_title": "Stage the move",
            "right_items": [
                {"label": "Control", "body": "Gated owner.", "_fragment": 1},
                {"label": "Risk", "body": "Lower exposure.", "_fragment": 2},
            ],
            "source_note": "Compared on the same dimensions.",
        },
    }

    result = composer.compose_deck(deck_plan(slide), registry_path=REGISTRY_PATH)

    assert result.slides_html.count('data-fragment="1"') == 2
    assert result.slides_html.count('data-fragment="2"') == 2


def test_compose_deck_requires_explicit_bespoke_escape_hatch() -> None:
    composer = load_composer()
    slide = {
        "id": "custom-slide",
        "layout_id": "bespoke",
        "title": "A deliberately bespoke exhibit",
        "chapter": "evidence",
        "chapter_label": "Evidence",
        "notes": "Explain why the standard layouts are insufficient.",
        "bespoke_html": '<div class="slide-frame"><h2>Custom exhibit</h2></div>',
    }

    with pytest.raises(ValueError, match="allow_bespoke_html"):
        composer.compose_deck(deck_plan(slide), registry_path=REGISTRY_PATH)


def test_compose_deck_preserves_safe_bespoke_body_markup() -> None:
    composer = load_composer()
    bespoke_markup = (
        '<div class="slide-frame wide" data-qa-role="exhibit">'
        '<svg viewBox="0 0 20 20" role="img" aria-label="One mark">'
        '<circle cx="10" cy="10" r="4"></circle></svg></div>'
    )
    slide = {
        "id": "custom-slide",
        "layout_id": "bespoke",
        "title": "A deliberately bespoke exhibit",
        "chapter": "evidence",
        "chapter_label": "Evidence",
        "notes": "Explain why the standard layouts are insufficient.",
        "source_refs": ["source-custom"],
        "bespoke_html": bespoke_markup,
    }

    result = composer.compose_deck(
        deck_plan(slide, allow_bespoke_html=True),
        registry_path=REGISTRY_PATH,
    )

    assert bespoke_markup in result.slides_html
    assert 'data-layout-id="bespoke"' in result.slides_html


@pytest.mark.parametrize(
    "unsafe_markup",
    [
        '<a href="jav&#x61;script:alert(1)">Run</a>',
        '<svg><a href="javascript&#58;alert(1)">Run</a></svg>',
        '<svg/onload="alert(1)"></svg>',
    ],
)
def test_compose_deck_rejects_entity_obfuscated_executable_markup(
    unsafe_markup: str,
) -> None:
    composer = load_composer()
    slide = {
        "id": "custom-slide",
        "layout_id": "bespoke",
        "title": "A deliberately bespoke exhibit",
        "chapter": "evidence",
        "chapter_label": "Evidence",
        "notes": "Explain the exhibit.",
        "bespoke_html": unsafe_markup,
    }

    with pytest.raises(ValueError, match="unsafe markup"):
        composer.compose_deck(
            deck_plan(slide, allow_bespoke_html=True),
            registry_path=REGISTRY_PATH,
        )


def test_compose_deck_dispatches_data_visual_renderer_with_frozen_slide_context() -> (
    None
):
    composer = load_composer()
    captured: dict[str, object] = {}

    def render_visual(
        *, slot_name: str, value: Any, slot_schema: Any, slide: Any
    ) -> str:
        captured.update(
            slot_name=slot_name,
            renderer=value["renderer"],
            schema_renderer=slot_schema["renderer"],
            slide_id=slide.slide_id,
            source_refs=slide.source_refs,
        )
        return '<svg viewBox="0 0 100 50" role="img" aria-label="Bound visual"></svg>'

    title = "One exhibit makes the implication visible"
    slide = {
        "id": "bound-visual",
        "layout_id": "visual-takeaway",
        "title": title,
        "chapter": "evidence",
        "chapter_label": "Evidence",
        "notes": "Explain the mark and its decision threshold.",
        "source_refs": ["source-chart"],
        "slots": {
            "eyebrow": "Bound evidence",
            "title": title,
            "visual": {
                "renderer": "data_visual",
                "spec": {"kind": "bar", "values": [3, 7]},
                "source_refs": ["source-chart"],
            },
            "takeaway_label": "Implication",
            "takeaway": "The difference changes the governed next move.",
            "source_note": "Source-bound illustrative renderer test.",
        },
    }

    result = composer.compose_deck(
        deck_plan(slide),
        registry_path=REGISTRY_PATH,
        renderer_dispatch={"data_visual": render_visual},
    )

    assert captured == {
        "slot_name": "visual",
        "renderer": "data_visual",
        "schema_renderer": "data_visual",
        "slide_id": "bound-visual",
        "source_refs": ("source-chart",),
    }
    assert 'aria-label="Bound visual"' in result.slides_html


def test_compose_deck_fails_when_extension_renderer_is_missing() -> None:
    composer = load_composer()
    title = "One exhibit makes the implication visible"
    slide = {
        "id": "bound-visual",
        "layout_id": "visual-takeaway",
        "title": title,
        "chapter": "evidence",
        "chapter_label": "Evidence",
        "notes": "Explain the mark and threshold.",
        "slots": {
            "eyebrow": "Bound evidence",
            "title": title,
            "visual": {"renderer": "data_visual", "spec": {"kind": "bar"}},
            "takeaway_label": "Implication",
            "takeaway": "The difference changes the next move.",
        },
    }

    with pytest.raises(ValueError, match="No extension renderer"):
        composer.compose_deck(
            deck_plan(slide), registry_path=REGISTRY_PATH, renderer_dispatch={}
        )


def test_compose_cli_writes_editable_work_files(tmp_path: Path) -> None:
    plan_path = tmp_path / "deck-plan.json"
    plan_path.write_text(json.dumps(deck_plan(cover_slide())), encoding="utf-8")
    output_dir = tmp_path / "work"
    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = "/tmp/html-deck-composer-test-pycache"

    result = subprocess.run(
        [
            sys.executable,
            str(COMPOSER_PATH),
            str(plan_path),
            "--output-dir",
            str(output_dir),
            "--registry",
            str(REGISTRY_PATH),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "slides.html").is_file()
    assert (output_dir / "custom.css").is_file()
    assert json.loads(result.stdout)["slide_count"] == 1


def test_compose_cli_preserves_authored_css_across_forced_recompose(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "deck-plan.json"
    plan_path.write_text(json.dumps(deck_plan(cover_slide())), encoding="utf-8")
    output_dir = tmp_path / "work"
    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = "/tmp/html-deck-composer-test-pycache"
    command = [
        sys.executable,
        str(COMPOSER_PATH),
        str(plan_path),
        "--output-dir",
        str(output_dir),
        "--registry",
        str(REGISTRY_PATH),
    ]
    first = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert first.returncode == 0, first.stderr
    custom_css_path = output_dir / "custom.css"
    authored_rule = ".decision-emphasis { color: #315f55; }"
    custom_css_path.write_text(
        custom_css_path.read_text(encoding="utf-8") + authored_rule + "\n",
        encoding="utf-8",
    )

    second = subprocess.run(
        [*command, "--force"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert second.returncode == 0, second.stderr
    recomposed_css = custom_css_path.read_text(encoding="utf-8")
    assert recomposed_css.count(authored_rule) == 1
    assert recomposed_css.count("BEGIN CLARA GENERATED LAYOUT CSS") == 1
