#!/usr/bin/env python3
"""Build a deterministic preview gallery for every registered Clara layout.

This fixture makes no semantic layout choice. It exercises every registered
layout mechanically at representative density so authors can inspect the
available surfaces before making a model-led presentation decision.
"""

from __future__ import annotations

import argparse
import base64
import json
import os

# Security: subprocess invokes only fixed local Clara Python entrypoints.
import subprocess  # nosec B404
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "GALLERY_SCHEMA_VERSION",
    "build_layout_gallery",
    "gallery_content_ledger",
    "gallery_deck_plan",
    "main",
]

GALLERY_SCHEMA_VERSION = "clara.html_deck_layout_gallery.v1"
PLAN_SCHEMA_VERSION = "clara.html_deck_plan.v1"
LEDGER_SCHEMA_VERSION = "clara.html_deck_ledger.v1"
SOURCE_ID = "gallery-source"
GALLERY_VIEWPORTS = (
    "presentation=1280x720",
    "compact=1024x768",
    "mobile=390x844",
)


class GalleryBuildError(RuntimeError):
    """Raised when an existing Clara command cannot complete the gallery."""


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def _registry_path() -> Path:
    return _skill_root() / "assets" / "layout-library" / "registry.json"


def _claim_id(layout_id: str) -> str:
    return f"claim-gallery-{layout_id}"


def _image_data_uri() -> str:
    """Return a small inline evidence illustration for the image-led layout."""

    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img">
<rect width="960" height="540" fill="#ebe7df"/>
<path d="M80 420H880M120 90V460" stroke="#78756f" stroke-width="3"/>
<path d="M120 390C250 360 300 330 410 278S610 190 840 126" fill="none" stroke="#ff5a36" stroke-width="14" stroke-linecap="round"/>
<path d="M120 390C260 402 420 392 560 330S720 250 840 236" fill="none" stroke="#26877f" stroke-width="8" stroke-linecap="round" stroke-dasharray="18 14"/>
<g fill="#151817"><circle cx="120" cy="390" r="14"/><circle cx="410" cy="278" r="14"/><circle cx="620" cy="188" r="14"/><circle cx="840" cy="126" r="14"/></g>
<g font-family="Arial,sans-serif" font-size="28" fill="#151817"><text x="105" y="505">Baseline</text><text x="770" y="82">Governed path</text></g>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _slide(
    layout_id: str,
    title: str,
    slots: Mapping[str, Any],
    *,
    tone: str = "light",
    chapter: str = "gallery",
    chapter_label: str = "Layout gallery",
) -> dict[str, Any]:
    return {
        "id": f"gallery-{layout_id}",
        "layout_id": layout_id,
        "title": title,
        "chapter": chapter,
        "chapter_label": chapter_label,
        "tone": tone,
        "notes": (
            f"Inspect the {layout_id} layout at representative density; this is "
            "a mechanical preview, not a recommended storyline choice."
        ),
        "source_refs": [SOURCE_ID],
        "claim_refs": [_claim_id(layout_id)],
        "slots": dict(slots),
    }


def gallery_deck_plan() -> dict[str, Any]:
    """Return a fresh plan containing each registered layout exactly once."""

    # Provenance remains available through data-source-ids and the embedded
    # ledger; the optional footer stays empty so the fixture tests content
    # density rather than repeating the same source sentence on every slide.
    source_note = ""
    slides = [
        _slide(
            "editorial-cover",
            "A governed decision starts with evidence, ownership, and a stop rule",
            {
                "eyebrow": "Clara layout gallery",
                "title": "A governed decision starts with evidence, ownership, and a stop rule",
                "subtitle": "Fifteen mechanical preview surfaces rendered from one source-bound deck plan.",
                "author": "Clara advisory systems",
                "source_note": source_note,
            },
            tone="dark",
            chapter="opening",
            chapter_label="Opening",
        ),
        _slide(
            "assertion",
            "Control improves when the evidence gate is explicit before action begins",
            {
                "eyebrow": "Governing assertion",
                "title": "Control improves when the evidence gate is explicit before action begins",
                "body": (
                    "The operating team can move quickly without weakening governance when the threshold, "
                    "owner, and escalation path are stated in advance."
                ),
                "implication_label": "Decision implication",
                "implication": (
                    "Authorize the next step only after the named evidence owner confirms the shared basis."
                ),
                "source_note": source_note,
            },
        ),
        _slide(
            "chapter-transition",
            "The next question is not whether to move, but what must be true first",
            {
                "eyebrow": "From direction to proof",
                "title": "The next question is not whether to move, but what must be true first",
                "subtitle": "Shift the room from broad intent to the evidence that governs commitment.",
                "source_note": source_note,
            },
            tone="dark",
            chapter="evidence",
            chapter_label="Evidence",
        ),
        _slide(
            "metric-contrast",
            "Four measures expose the operating gap and the governing threshold",
            {
                "eyebrow": "Directly labelled measures",
                "title": "Four measures expose the operating gap and the governing threshold",
                "metrics": [
                    {
                        "label": "Current readiness",
                        "value": "62",
                        "detail": "Observed on the common assessment basis.",
                        "tone": "neutral",
                        "_fragment": 1,
                    },
                    {
                        "label": "Required threshold",
                        "value": "80",
                        "detail": "Agreed gate before irreversible commitment.",
                        "tone": "accent",
                        "_fragment": 2,
                    },
                    {
                        "label": "Evidence complete",
                        "value": "74%",
                        "detail": "Items with a reviewable source trail.",
                        "tone": "analytical",
                        "_fragment": 3,
                    },
                    {
                        "label": "Open controls",
                        "value": "3",
                        "detail": "Material safeguards without a confirmed owner.",
                        "tone": "risk",
                        "_fragment": 4,
                    },
                ],
                "source_note": source_note,
            },
        ),
        _slide(
            "paired-comparison",
            "Staging preserves learning and control",
            {
                "eyebrow": "Choice architecture",
                "title": "Staging preserves learning and control",
                "left_label": "Path A",
                "left_title": "Commit now",
                "left_items": [
                    {
                        "label": "Speed",
                        "body": "Full launch.",
                        "_fragment": 1,
                    },
                    {
                        "label": "Evidence",
                        "body": "Proof follows.",
                        "_fragment": 2,
                    },
                    {
                        "label": "Control",
                        "body": "One review.",
                        "_fragment": 3,
                    },
                    {
                        "label": "Exposure",
                        "body": "Early exposure.",
                        "_fragment": 4,
                    },
                ],
                "right_label": "Path B",
                "right_title": "Use gates",
                "right_items": [
                    {
                        "label": "Speed",
                        "body": "Start bounded.",
                        "_fragment": 1,
                    },
                    {
                        "label": "Evidence",
                        "body": "Proof first.",
                        "_fragment": 2,
                    },
                    {
                        "label": "Control",
                        "body": "Each gate owned.",
                        "_fragment": 3,
                    },
                    {
                        "label": "Exposure",
                        "body": "Exposure follows proof.",
                        "_fragment": 4,
                    },
                ],
                "source_note": source_note,
            },
            tone="dark",
            chapter="options",
            chapter_label="Options",
        ),
        _slide(
            "evidence-split",
            "Observed readiness is improving, but ownership remains incomplete",
            {
                "eyebrow": "Evidence and implication",
                "title": "Observed readiness is improving, but ownership remains incomplete",
                "evidence_label": "Observed evidence",
                "evidence_items": [
                    {
                        "label": "Coverage",
                        "body": "Three quarters is reviewable.",
                        "_fragment": 1,
                    },
                    {
                        "label": "Trend",
                        "body": "Readiness rose each period.",
                        "_fragment": 2,
                    },
                    {
                        "label": "Control",
                        "body": "Two safeguards have operators.",
                        "_fragment": 3,
                    },
                    {
                        "label": "Gap",
                        "body": "Stop-rule ownership remains open.",
                        "_fragment": 4,
                    },
                ],
                "takeaway_label": "Advisor judgement",
                "takeaway": "Proceed with reversible preparation only.",
                "condition": "Reassess when the stop-rule owner is confirmed.",
                "source_note": source_note,
            },
        ),
        _slide(
            "visual-takeaway",
            "The readiness trajectory reaches the gate only in the final period",
            {
                "eyebrow": "Source-bound visual",
                "title": "The readiness trajectory reaches the gate only in the final period",
                "visual": {
                    "renderer": "data_visual",
                    "source_refs": [SOURCE_ID],
                    "claim_refs": [_claim_id("visual-takeaway")],
                    "spec": {
                        "schema_version": "clara.html_deck_visual.v1",
                        "type": "line",
                        "id": "gallery-readiness-line",
                        "title": "Illustrative readiness index",
                        "aria_label": "Readiness rises from 48 to 82 across five periods",
                        "description": "Five directly labelled illustrative readiness observations.",
                        "source_ids": [SOURCE_ID],
                        "source_note": source_note,
                        "data": [
                            {"label": "P1", "value": 48},
                            {"label": "P2", "value": 55},
                            {"label": "P3", "value": 63},
                            {"label": "P4", "value": 72},
                            {"label": "P5", "value": 82},
                        ],
                    },
                },
                "takeaway_label": "Implication",
                "takeaway": "Keep the current gate: earlier commitment would outrun the evidence trajectory.",
                "source_note": source_note,
            },
            tone="dark",
        ),
        _slide(
            "timeline",
            "Six evidence moments show how the decision basis develops over time",
            {
                "eyebrow": "Evidence timeline",
                "title": "Six evidence moments show how the decision basis develops over time",
                "steps": [
                    {
                        "period": "Jan",
                        "title": "Baseline",
                        "body": "Common measures and owners agreed.",
                        "status": "past",
                        "_fragment": 1,
                    },
                    {
                        "period": "Feb",
                        "title": "Sources",
                        "body": "Primary records assembled for review.",
                        "status": "past",
                        "_fragment": 2,
                    },
                    {
                        "period": "Mar",
                        "title": "Contradiction",
                        "body": "One material variance remained open.",
                        "status": "past",
                        "_fragment": 3,
                    },
                    {
                        "period": "Apr",
                        "title": "Resolution",
                        "body": "The variance received a shared basis.",
                        "status": "current",
                        "_fragment": 4,
                    },
                    {
                        "period": "May",
                        "title": "Control test",
                        "body": "Owners rehearse escalation and stop rules.",
                        "status": "future",
                        "_fragment": 5,
                    },
                    {
                        "period": "Jun",
                        "title": "Decision gate",
                        "body": "Leadership confirms evidence and exposure.",
                        "status": "risk",
                        "_fragment": 6,
                    },
                ],
                "source_note": source_note,
            },
        ),
        _slide(
            "process-flow",
            "Five operating stages connect evidence intake to a governed decision",
            {
                "eyebrow": "Operating process",
                "title": "Five operating stages connect evidence intake to a governed decision",
                "steps": [
                    {
                        "label": "01",
                        "title": "Frame",
                        "body": "Name the decision and the governing uncertainty.",
                        "_fragment": 1,
                    },
                    {
                        "label": "02",
                        "title": "Collect",
                        "body": "Assemble reviewable sources on one basis.",
                        "_fragment": 2,
                    },
                    {
                        "label": "03",
                        "title": "Test",
                        "body": "Resolve conflicts and quantify the gap.",
                        "_fragment": 3,
                    },
                    {
                        "label": "04",
                        "title": "Assign",
                        "body": "Name owners for gates and safeguards.",
                        "_fragment": 4,
                    },
                    {
                        "label": "05",
                        "title": "Decide",
                        "body": "Authorize, pause, or stop with reasons.",
                        "_fragment": 5,
                    },
                ],
                "source_note": source_note,
            },
            chapter="operating-model",
            chapter_label="Operating model",
        ),
        _slide(
            "scenario-matrix",
            "Four evidence states determine the action",
            {
                "eyebrow": "Scenario matrix",
                "title": "Four evidence states determine the action",
                "scenarios": [
                    {
                        "scenario": "Base",
                        "trigger": "Readiness stays above 80 with all owners named.",
                        "action": "Authorize the bounded next commitment.",
                        "owner": "Program lead",
                        "status": "base",
                        "_fragment": 1,
                    },
                    {
                        "scenario": "Watch",
                        "trigger": "Readiness holds, but one safeguard slips.",
                        "action": "Continue reversible work and retest weekly.",
                        "owner": "Control lead",
                        "status": "watch",
                        "_fragment": 2,
                    },
                    {
                        "scenario": "Act",
                        "trigger": "A material variance exceeds the agreed tolerance.",
                        "action": "Escalate and narrow the active scope.",
                        "owner": "Sponsor",
                        "status": "act",
                        "_fragment": 3,
                    },
                    {
                        "scenario": "Stop",
                        "trigger": "Evidence integrity or ownership cannot be confirmed.",
                        "action": "Pause commitment until the basis is restored.",
                        "owner": "Steering group",
                        "status": "stop",
                        "_fragment": 4,
                    },
                ],
                "source_note": source_note,
            },
            tone="dark",
        ),
        _slide(
            "decision-gates",
            "Five gates make permission, ownership, and the resulting action explicit",
            {
                "eyebrow": "Governance surface",
                "title": "Five gates make permission, ownership, and the resulting action explicit",
                "gates": [
                    {
                        "gate": "Basis",
                        "condition": "Primary evidence covers the agreed period.",
                        "owner": "Evidence lead",
                        "action": "Open assessment.",
                        "_fragment": 1,
                    },
                    {
                        "gate": "Variance",
                        "condition": "Material contradictions are labelled.",
                        "owner": "Finance lead",
                        "action": "Confirm basis.",
                        "_fragment": 2,
                    },
                    {
                        "gate": "Control",
                        "condition": "Safeguards have owners and escalation.",
                        "owner": "Risk lead",
                        "action": "Permit bounded work.",
                        "_fragment": 3,
                    },
                    {
                        "gate": "Exposure",
                        "condition": "Irreversible cost stays within tolerance.",
                        "owner": "Sponsor",
                        "action": "Release next tranche.",
                        "_fragment": 4,
                    },
                    {
                        "gate": "Stop rule",
                        "condition": "A named owner can pause work.",
                        "owner": "Steering group",
                        "action": "Authorize governed path.",
                        "_fragment": 5,
                    },
                ],
                "source_note": source_note,
            },
        ),
        _slide(
            "roadmap",
            "The implementation path builds evidence and control before exposure grows",
            {
                "eyebrow": "Implementation roadmap",
                "title": "The implementation path builds evidence and control before exposure grows",
                "phases": [
                    {
                        "period": "Weeks 1–2",
                        "title": "Align basis",
                        "outcome": "One evidence register and decision definition.",
                        "owner": "Evidence lead",
                        "_fragment": 1,
                    },
                    {
                        "period": "Weeks 3–4",
                        "title": "Resolve gaps",
                        "outcome": "Material variances closed or explicitly qualified.",
                        "owner": "Finance lead",
                        "_fragment": 2,
                    },
                    {
                        "period": "Weeks 5–6",
                        "title": "Test controls",
                        "outcome": "Owners rehearse safeguards and escalation.",
                        "owner": "Risk lead",
                        "_fragment": 3,
                    },
                    {
                        "period": "Weeks 7–8",
                        "title": "Bound exposure",
                        "outcome": "Commitment limits tied to evidence thresholds.",
                        "owner": "Sponsor",
                        "_fragment": 4,
                    },
                    {
                        "period": "Week 9",
                        "title": "Govern decision",
                        "outcome": "Leadership authorizes, pauses, or stops.",
                        "owner": "Steering group",
                        "_fragment": 5,
                    },
                ],
                "source_note": source_note,
            },
            chapter="delivery",
            chapter_label="Delivery",
        ),
        _slide(
            "image-led",
            "The governed path narrows exposure while the evidence base strengthens",
            {
                "eyebrow": "Image-led evidence",
                "title": "The governed path narrows exposure while the evidence base strengthens",
                "image_src": _image_data_uri(),
                "image_alt": (
                    "Illustrative rising solid path above a slower dashed baseline, with four decision nodes."
                ),
                "caption": "Synthetic path illustration created only to test the inline image surface.",
                "takeaway": "Use an image only when it carries evidence or explains a mechanism the audience must understand.",
                "source_note": source_note,
            },
            tone="dark",
        ),
        _slide(
            "evidence-register",
            "Six evidence states keep uncertainty visible",
            {
                "eyebrow": "Evidence register",
                "title": "Six evidence states keep uncertainty visible",
                "entries": [
                    {
                        "claim": "Period aligned.",
                        "evidence": "Signed basis.",
                        "status": "supported",
                        "implication": "Compare measures.",
                        "_fragment": 1,
                    },
                    {
                        "claim": "Gate one cleared.",
                        "evidence": "Reviewed index.",
                        "status": "supported",
                        "implication": "Continue preparation.",
                        "_fragment": 2,
                    },
                    {
                        "claim": "Controls owned.",
                        "evidence": "One owner pending.",
                        "status": "partial",
                        "implication": "Stay reversible.",
                        "_fragment": 3,
                    },
                    {
                        "claim": "Exposure tolerated.",
                        "evidence": "Range unverified.",
                        "status": "open",
                        "implication": "Hold tranche.",
                        "_fragment": 4,
                    },
                    {
                        "claim": "Demand supports case.",
                        "evidence": "Forecast conflicts.",
                        "status": "conflict",
                        "implication": "Retest demand.",
                        "_fragment": 5,
                    },
                    {
                        "claim": "Stop rule works.",
                        "evidence": "Owner documented.",
                        "status": "supported",
                        "implication": "Proceed governed.",
                        "_fragment": 6,
                    },
                ],
                "source_note": source_note,
            },
        ),
        _slide(
            "closing-decision",
            "Decide the next move, evidence owner, and stop rule",
            {
                "eyebrow": "Decision and next move",
                "title": "Decide the next move, evidence owner, and stop rule",
                "actions": [
                    {
                        "verb": "Authorize",
                        "body": "Release reversible preparation.",
                        "owner": "Executive sponsor",
                        "_fragment": 1,
                    },
                    {
                        "verb": "Evidence",
                        "body": "Close control and exposure gaps.",
                        "owner": "Evidence lead",
                        "_fragment": 2,
                    },
                    {
                        "verb": "Stop",
                        "body": "Pause if a governing condition fails.",
                        "owner": "Steering group",
                        "_fragment": 3,
                    },
                ],
                "closing_line": "Move at the speed of evidence, with ownership visible.",
                "source_note": source_note,
            },
            tone="dark",
            chapter="closing",
            chapter_label="Closing",
        ),
    ]
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "allow_bespoke_html": False,
        "slides": slides,
    }


def gallery_content_ledger(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return a matching source/claim ledger for a gallery deck plan."""

    raw_slides = plan.get("slides")
    if not isinstance(raw_slides, Sequence) or isinstance(raw_slides, (str, bytes)):
        raise ValueError("gallery plan slides must be an array")
    ledger_slides: list[dict[str, Any]] = []
    for raw_slide in raw_slides:
        if not isinstance(raw_slide, Mapping):
            raise ValueError("gallery plan slides must contain objects")
        slide_id = str(raw_slide.get("id", "")).strip()
        layout_id = str(raw_slide.get("layout_id", "")).strip()
        title = str(raw_slide.get("title", "")).strip()
        if not slide_id or not layout_id or not title:
            raise ValueError("gallery slides require id, layout_id, and title")
        ledger_slides.append(
            {
                "slide_id": slide_id,
                "basis_status": "source-backed",
                "basis_note": "Synthetic source-backed fixture for mechanical layout QA.",
                "claims": [
                    {
                        "id": _claim_id(layout_id),
                        "statement": f"Mechanical preview: {title}",
                        "classification": "illustrative",
                        "basis_status": "source-backed",
                        "basis_note": "Synthetic gallery content; no advisory conclusion is asserted.",
                        "source_ids": [SOURCE_ID],
                        "qualification": "Synthetic fixture; values and implications are illustrative.",
                    }
                ],
            }
        )
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "sources": [
            {
                "id": SOURCE_ID,
                "label": "Clara mechanical layout gallery fixture",
                "kind": "synthetic-fixture",
                "locator": "synthetic://clara/layout-gallery",
                "sha256": "",
                "publish_locator": False,
            }
        ],
        "slides": ledger_slides,
    }


def _metadata() -> dict[str, str]:
    return {
        "title": "Clara layout gallery",
        "subtitle": "Mechanical previews of every registered advisory layout",
        "author": "Clara advisory systems",
        "eyebrow": "Layout system QA",
        "language": "en",
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_json_command(
    command: Sequence[str],
    *,
    allowed_returncodes: frozenset[int] = frozenset({0}),
) -> tuple[dict[str, Any], int]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    # Security: no shell is used and argv is constructed inside this module.
    completed = subprocess.run(  # nosec B603
        list(command),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode not in allowed_returncodes:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise GalleryBuildError(
            f"Command failed with exit {completed.returncode}: {' '.join(command)}\n{details}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GalleryBuildError(
            f"Command did not return JSON: {' '.join(command)}"
        ) from exc
    if not isinstance(payload, dict):
        raise GalleryBuildError(
            f"Command returned non-object JSON: {' '.join(command)}"
        )
    return payload, completed.returncode


def _require_empty_output(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"Gallery output must be an empty directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _registered_layout_ids() -> tuple[str, ...]:
    payload = json.loads(_registry_path().read_text(encoding="utf-8"))
    layouts = payload.get("layouts")
    if not isinstance(layouts, list):
        raise ValueError("layout registry must contain a layouts array")
    identifiers = tuple(
        str(item.get("id", "")) for item in layouts if isinstance(item, Mapping)
    )
    if len(identifiers) != len(layouts) or any(not item for item in identifiers):
        raise ValueError("layout registry contains an invalid layout ID")
    return identifiers


def _preview_mapping(
    plan: Mapping[str, Any],
    qa_report: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    slides = plan["slides"]
    slide_to_layout = {
        str(slide["id"]): str(slide["layout_id"])
        for slide in slides
        if isinstance(slide, Mapping)
    }
    mapping = {
        str(slide["layout_id"]): {
            "slide_id": str(slide["id"]),
            "title": str(slide["title"]),
            "previews": {},
        }
        for slide in slides
        if isinstance(slide, Mapping)
    }
    if qa_report is None:
        return mapping
    for viewport in qa_report.get("viewports", []):
        if not isinstance(viewport, Mapping):
            continue
        viewport_name = str(viewport.get("name", ""))
        for slide in viewport.get("slides", []):
            if not isinstance(slide, Mapping) or not slide.get("screenshot"):
                continue
            layout_id = slide_to_layout.get(str(slide.get("id", "")))
            if layout_id is None:
                continue
            mapping[layout_id]["previews"][viewport_name] = (
                Path("qa") / str(slide["screenshot"])
            ).as_posix()
    return mapping


def build_layout_gallery(
    output_dir: Path,
    *,
    run_browser: bool = True,
    browser_executable: str | None = None,
    timeout_ms: int = 15_000,
) -> dict[str, Any]:
    """Compose, build, and optionally browser-audit the all-layout gallery."""

    if timeout_ms < 1_000:
        raise ValueError("timeout_ms must be at least 1000")
    output = output_dir.expanduser().resolve()
    _require_empty_output(output)

    plan = gallery_deck_plan()
    registered = _registered_layout_ids()
    planned = tuple(str(slide["layout_id"]) for slide in plan["slides"])
    if planned != registered:
        raise ValueError(
            "gallery plan must cover every registered layout once and in registry order; "
            f"registered={registered}, planned={planned}"
        )
    ledger = gallery_content_ledger(plan)
    work_dir = output / "work"
    metadata = _metadata()
    init_command = [
        sys.executable,
        str(_scripts_dir() / "init_html_deck.py"),
        "--work-dir",
        str(work_dir),
        "--title",
        metadata["title"],
        "--subtitle",
        metadata["subtitle"],
        "--author",
        metadata["author"],
        "--eyebrow",
        metadata["eyebrow"],
        "--language",
        metadata["language"],
    ]
    _run_json_command(init_command)
    plan_path = work_dir / "deck-plan.json"
    ledger_path = work_dir / "content-ledger.json"
    _write_json(plan_path, plan)
    _write_json(ledger_path, ledger)

    compose_report, _ = _run_json_command(
        [
            sys.executable,
            str(_scripts_dir() / "compose_html_deck.py"),
            str(plan_path),
            "--output-dir",
            str(work_dir),
            "--force",
        ]
    )
    build_report_path = output / "build-report.json"
    package_path = output / "clara-layout-gallery.zip"
    build_report, _ = _run_json_command(
        [
            sys.executable,
            str(_scripts_dir() / "build_html_deck.py"),
            str(work_dir),
            "--output-root",
            str(output / "dist"),
            "--package",
            str(package_path),
            "--report",
            str(build_report_path),
        ]
    )
    build_output = build_report.get("output")
    if not isinstance(build_output, Mapping) or not build_output.get("index_path"):
        raise GalleryBuildError("Static builder did not report an index path")
    index_path = Path(str(build_output["index_path"]))
    if not index_path.is_file():
        raise GalleryBuildError(f"Static builder output is missing: {index_path}")

    qa_report: dict[str, Any] | None = None
    qa_returncode: int | None = None
    if run_browser:
        qa_command = [
            sys.executable,
            str(_scripts_dir() / "browser_qa_html_deck.py"),
            str(index_path),
            "--output-dir",
            str(output / "qa"),
            "--report",
            str(output / "qa" / "browser-qa.json"),
            "--timeout-ms",
            str(timeout_ms),
            "--warnings-as-errors",
        ]
        for viewport in GALLERY_VIEWPORTS:
            qa_command.extend(("--viewport", viewport))
        if browser_executable:
            qa_command.extend(("--browser-executable", browser_executable))
        qa_report, qa_returncode = _run_json_command(
            qa_command,
            allowed_returncodes=frozenset({0, 1, 2}),
        )

    browser_result = str(qa_report.get("result")) if qa_report else "skipped"
    result = browser_result if qa_report else "pass"
    manifest = {
        "schema_version": GALLERY_SCHEMA_VERSION,
        "result": result,
        "layout_count": len(registered),
        "registered_layout_ids": list(registered),
        "files": {
            "deck_plan": "work/deck-plan.json",
            "content_ledger": "work/content-ledger.json",
            "slides": "work/slides.html",
            "custom_css": "work/custom.css",
            "index_html": index_path.relative_to(output).as_posix(),
            "package": package_path.relative_to(output).as_posix(),
            "build_report": build_report_path.relative_to(output).as_posix(),
            "browser_qa_report": "qa/browser-qa.json" if qa_report else None,
            "screenshot_index": (
                (Path("qa") / str(qa_report["output"]["screenshot_index"])).as_posix()
                if qa_report and qa_report.get("output", {}).get("screenshot_index")
                else None
            ),
        },
        "compose": {
            "slide_count": compose_report.get("slide_count"),
            "layout_ids": compose_report.get("layout_ids"),
        },
        "static_build": {
            "result": build_report.get("result"),
            "publication_id": build_output.get("publication_id"),
            "sha256": build_output.get("sha256"),
        },
        "browser_qa": {
            "result": browser_result,
            "returncode": qa_returncode,
            "viewports": list(GALLERY_VIEWPORTS) if qa_report else [],
        },
        "layouts": _preview_mapping(plan, qa_report),
        "boundary": (
            "This gallery verifies mechanical layout rendering only; layout selection and "
            "editorial quality remain model-led judgements."
        ),
    }
    _write_json(output / "layout-previews.json", manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    """Run the layout gallery command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--browser-executable")
    parser.add_argument("--timeout-ms", type=int, default=15_000)
    args = parser.parse_args(argv)
    try:
        manifest = build_layout_gallery(
            args.output_dir,
            run_browser=not args.skip_browser,
            browser_executable=args.browser_executable,
            timeout_ms=args.timeout_ms,
        )
        sys.stdout.write(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if manifest["result"] == "blocked":
            return 2
        if manifest["result"] == "fail":
            return 1
        return 0
    except (
        GalleryBuildError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
