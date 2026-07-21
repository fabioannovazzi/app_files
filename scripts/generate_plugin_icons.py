#!/usr/bin/env python3
"""Generate cohesive SVG icons for local Codex plugins."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

__all__ = ["IconSpec", "build_svg", "generate_icons", "main"]

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
THEME_MARKER = "mparanza-plugin-icon-v1"


@dataclass(frozen=True)
class IconSpec:
    """Visual settings for one plugin icon."""

    plugin: str
    label: str
    color: str
    accent: str
    motif: str


SPECS = (
    IconSpec(
        "audit-reconciliation",
        "Riconciliazione partite",
        "#17365D",
        "#D89B3D",
        "reconcile",
    ),
    IconSpec(
        "client-file-preparation",
        "New Client · File Preparation",
        "#486F62",
        "#7CB7A7",
        "folder",
    ),
    IconSpec(
        "new-client",
        "New Client",
        "#36586F",
        "#82B6C9",
        "onboard",
    ),
    IconSpec(
        "journal-sampling",
        "Journal Sampling",
        "#0F766E",
        "#F0A23B",
        "sample",
    ),
    IconSpec(
        "check-entries",
        "Check Entries",
        "#355F6F",
        "#63B28D",
        "check",
    ),
    IconSpec(
        "journal-bank-reconciliation",
        "Journal-Bank Reconciliation",
        "#496373",
        "#85C7B5",
        "bank",
    ),
    IconSpec(
        "report-builder",
        "Build Report",
        "#5D685C",
        "#C99B57",
        "report",
    ),
    IconSpec(
        "attribute-reporting",
        "Attribute Reporting",
        "#516254",
        "#D59B52",
        "attribute_report",
    ),
    IconSpec(
        "reporting-engine",
        "Reporting Engine",
        "#455E68",
        "#7CB7A7",
        "reporting_engine",
    ),
    IconSpec(
        "prompt-optimizer",
        "Optimize Prompt",
        "#4F6B78",
        "#D89B3D",
        "prompt",
    ),
    IconSpec(
        "deep-research-validator",
        "Validate Deep Research",
        "#4F6B78",
        "#8AA15F",
        "validate",
    ),
    IconSpec(
        "mix-contribution-analysis",
        "Mix and Contribution Analysis",
        "#4F6F52",
        "#E08C48",
        "mix",
    ),
    IconSpec(
        "scatter-bubble-analysis",
        "Scatter and Bubble Analysis",
        "#315F72",
        "#F28F3B",
        "scatter",
    ),
    IconSpec(
        "distribution-analysis",
        "Distribution Analysis",
        "#7A563A",
        "#C4804D",
        "distribution",
    ),
    IconSpec(
        "set-overlap-analysis",
        "Set Overlap Analysis",
        "#343434",
        "#CB2026",
        "overlap",
    ),
    IconSpec(
        "variance-analysis",
        "Variance Analysis",
        "#386C75",
        "#F07F68",
        "variance",
    ),
    IconSpec(
        "period-comparison",
        "Period-over-Period Analysis",
        "#4F6F52",
        "#6EA4B8",
        "period",
    ),
    IconSpec(
        "funnel-analysis",
        "Funnel Analysis",
        "#4C6759",
        "#D89B3D",
        "funnel",
    ),
    IconSpec(
        "statement-analysis",
        "Statement Analysis",
        "#4F5F68",
        "#C99B57",
        "statement",
    ),
    IconSpec(
        "concordato-plan-review",
        "Revisione Piano Concordato",
        "#31493C",
        "#B45F3D",
        "concordato",
    ),
    IconSpec(
        "registro-imprese-sari",
        "Registro Imprese e SARI",
        "#145F5A",
        "#D89B3D",
        "registry",
    ),
    IconSpec(
        "previdenza-inps",
        "Previdenza INPS",
        "#4B5F70",
        "#C58B47",
        "pension",
    ),
    IconSpec(
        "clara",
        "Clara",
        "#002060",
        "#00B0F0",
        "advisor",
    ),
    IconSpec(
        "vera",
        "Vera",
        "#002060",
        "#00B0F0",
        "reviewer",
    ),
)


def _frame(spec: IconSpec, body: str) -> str:
    if spec.motif in {"advisor", "reviewer"}:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{spec.label}" data-theme="{THEME_MARKER}">
  <rect width="64" height="64" rx="14" fill="{spec.color}"/>
  <path d="M49 0h1l14 14v1H49z" fill="#0070C0"/>
  <circle cx="51" cy="50" r="7" fill="#0070C0"/>
  <circle cx="51" cy="50" r="3" fill="{spec.color}"/>
{body}
</svg>
"""
    if spec.motif == "studio":
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{spec.label}" data-theme="{THEME_MARKER}">
  <rect width="64" height="64" rx="14" fill="#171816"/>
{body}
  <rect x="50" y="48" width="5" height="5" rx="1" fill="{spec.accent}"/>
</svg>
"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{spec.label}" data-theme="{THEME_MARKER}">
  <rect width="64" height="64" rx="14" fill="#171816"/>
  <path d="M49 0h1l14 14v1H49z" fill="{spec.accent}"/>
  <circle cx="51" cy="50" r="7" fill="{spec.accent}"/>
  <circle cx="51" cy="50" r="3" fill="#171816"/>
{body}
</svg>
"""


def _body(spec: IconSpec) -> str:
    paper = "#FFFFFF" if spec.motif in {"advisor", "reviewer"} else "#F7F0DF"
    ink = "#22302A"
    color = "#1F211D"
    accent = spec.accent
    bodies = {
        "studio": f"""
  <path d="M12 17 32 31v8L22 31v18H12zm40 0L32 31v8l10-8v18h10z" fill="{paper}"/>
  <path d="m18 26 9 7v12M46 26l-9 7v12" fill="none" stroke="#171816" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>""",
        "reconcile": f"""
  <rect x="13" y="17" width="38" height="30" rx="5" fill="{paper}"/>
  <path d="M24 17v30M18 27h28M18 37h28" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M20 30l5-5 5 5M44 34l-5 5-5-5" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M22 45h8M35 45h8" stroke="{color}" stroke-width="3" stroke-linecap="round"/>""",
        "folder": f"""
  <path d="M12 24a5 5 0 0 1 5-5h10l5 6h15a5 5 0 0 1 5 5v15a5 5 0 0 1-5 5H17a5 5 0 0 1-5-5z" fill="{paper}"/>
  <circle cx="28" cy="35" r="5" fill="{color}"/>
  <path d="M18 47c2-7 18-7 20 0" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round"/>
  <path d="M40 34h7M40 41h5" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>""",
        "onboard": f"""
  <path d="M16 15h29l7 8v28H16z" fill="{paper}"/>
  <path d="M45 15v9h7" fill="#DCE5E8"/>
  <circle cx="27" cy="29" r="5" fill="{color}"/>
  <path d="M20 42c1-6 13-6 14 0" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round"/>
  <path d="m37 39 4 4 9-12" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>""",
        "sample": f"""
  <rect x="15" y="13" width="30" height="38" rx="5" fill="{paper}"/>
  <path d="M21 23h18M21 31h15M21 39h10" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <rect x="35" y="34" width="16" height="16" rx="4" fill="{accent}"/>
  <circle cx="40" cy="39" r="1.9" fill="{ink}"/>
  <circle cx="46" cy="45" r="1.9" fill="{ink}"/>""",
        "check": f"""
  <path d="M16 14h25l8 9v27H16z" fill="{paper}"/>
  <path d="M41 14v10h8" fill="#E8E0D2"/>
  <path d="M23 27h16M23 35h11" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <circle cx="41" cy="43" r="9" fill="{paper}" stroke="{color}" stroke-width="4"/>
  <path d="m37 43 3 3 7-9" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>""",
        "bank": f"""
  <path d="M32 13 14 24h36z" fill="{paper}"/>
  <path d="M17 28h30M18 48h28" stroke="{paper}" stroke-width="5" stroke-linecap="round"/>
  <path d="M22 29v16M32 29v16M42 29v16" stroke="{paper}" stroke-width="4" stroke-linecap="round"/>
  <path d="M17 36h-3a4 4 0 0 1 0-8h5M47 36h3a4 4 0 0 0 0-8h-5" fill="none" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>
  <path d="m24 52 5 5 12-14" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>""",
        "report": f"""
  <path d="M17 13h27l7 8v31H17z" fill="{paper}"/>
  <path d="M44 13v9h7" fill="#E8E0D2"/>
  <path d="M25 44V33M33 44V25M41 44V37" stroke="{color}" stroke-width="5" stroke-linecap="round"/>
  <path d="M24 49h20M25 22h11" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>""",
        "prompt": f"""
  <path d="M13 18h33a6 6 0 0 1 6 6v13a6 6 0 0 1-6 6H32l-10 8v-8h-9z" fill="{paper}"/>
  <path d="M22 29h19M22 37h12" stroke="{color}" stroke-width="4" stroke-linecap="round"/>
  <path d="M48 12l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" fill="{accent}"/>""",
        "validate": f"""
  <rect x="15" y="15" width="34" height="34" rx="5" fill="{paper}"/>
  <path d="M23 25h17M23 33h19M23 41h10" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M43 40l5 5 10-13" fill="none" stroke="{accent}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="20" cy="25" r="2" fill="{accent}"/><circle cx="20" cy="33" r="2" fill="{accent}"/><circle cx="20" cy="41" r="2" fill="{accent}"/>""",
        "mix": f"""
  <path d="M13 48h38" stroke="{paper}" stroke-width="4" stroke-linecap="round"/>
  <rect x="17" y="29" width="8" height="16" rx="2" fill="#AEC8B3"/>
  <rect x="28" y="19" width="8" height="26" rx="2" fill="{paper}"/>
  <rect x="39" y="25" width="8" height="20" rx="2" fill="{accent}"/>
  <path d="M16 18h11l7 7h14" fill="none" stroke="{paper}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>""",
        "scatter": f"""
  <path d="M14 50h38M14 50V14" stroke="{paper}" stroke-width="3" stroke-linecap="round"/>
  <circle cx="24" cy="39" r="4" fill="{accent}"/>
  <circle cx="36" cy="31" r="7" fill="#8FD6C2"/>
  <circle cx="48" cy="20" r="5" fill="{paper}"/>
  <circle cx="21" cy="24" r="3" fill="#D7E8BA"/>""",
        "distribution": f"""
  <path d="M15 49h36" stroke="{paper}" stroke-width="4" stroke-linecap="round"/>
  <path d="M20 46V34c0-3 2-5 5-5s5 2 5 5v12M31 46V24c0-3 2-5 5-5s5 2 5 5v22M42 46V31c0-3 2-5 5-5s5 2 5 5v15" fill="none" stroke="{paper}" stroke-width="5" stroke-linecap="round"/>
  <path d="M16 25c9-11 18-11 27 0 5 6 10 7 15 1" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>""",
        "overlap": f"""
  <circle cx="28" cy="33" r="15" fill="{paper}" fill-opacity=".82"/>
  <circle cx="39" cy="33" r="15" fill="{accent}" fill-opacity=".74"/>
  <circle cx="34" cy="43" r="15" fill="#8FA1A9" fill-opacity=".7"/>
  <path d="M18 53h30" stroke="{paper}" stroke-width="4" stroke-linecap="round"/>""",
        "variance": f"""
  <path d="M13 47h38" stroke="{paper}" stroke-width="4" stroke-linecap="round"/>
  <path d="M18 44V30h8v14M30 44V18h8v26M42 44V25h8v19" fill="none" stroke="{paper}" stroke-width="5" stroke-linejoin="round"/>
  <path d="M16 19h11l6 8 7-12h8" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>""",
        "period": f"""
  <path d="M15 24h34M15 41h34" stroke="{paper}" stroke-width="5" stroke-linecap="round"/>
  <path d="M25 16v32M39 16v32" stroke="{paper}" stroke-width="3" stroke-linecap="round"/>
  <path d="M20 24l6-6 6 6M44 41l-6 6-6-6" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="32" cy="32" r="5" fill="{accent}"/>""",
        "funnel": f"""
  <path d="M15 16h34L38 31v15l-12 6V31z" fill="{paper}"/>
  <path d="M21 22h22M25 30h14M29 38h6" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M45 17l-7 13M38 45l8-4" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
  <circle cx="48" cy="18" r="3" fill="{accent}"/><circle cx="46" cy="41" r="3" fill="{accent}"/>""",
        "statement": f"""
  <rect x="14" y="13" width="36" height="39" rx="5" fill="{paper}"/>
  <path d="M22 23h15M22 31h20M22 39h16M20 46h24" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M18 35h28" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>
  <path d="M44 17v10h6" fill="#E8E0D2"/>""",
        "attribute_report": f"""
  <path d="M19 13h25l8 8v31H19z" fill="{paper}"/>
  <path d="M44 13v9h8" fill="#E7DDC8"/>
  <rect x="10" y="20" width="23" height="8" rx="4" fill="{accent}"/>
  <rect x="10" y="31" width="28" height="8" rx="4" fill="#9EB7A3"/>
  <rect x="10" y="42" width="20" height="8" rx="4" fill="#738D79"/>
  <circle cx="15" cy="24" r="2" fill="{paper}"/>
  <circle cx="15" cy="35" r="2" fill="{paper}"/>
  <circle cx="15" cy="46" r="2" fill="{paper}"/>
  <path d="m39 39 4 4 8-11" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>""",
        "reporting_engine": f"""
  <rect x="13" y="15" width="38" height="34" rx="5" fill="{paper}"/>
  <path d="M20 40V29M29 40V23M38 40V33M47 40V26" stroke="{color}" stroke-width="4" stroke-linecap="round"/>
  <path d="M19 44h29" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M18 22h14M18 28h8" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>
  <path d="M35 18h10l4 4-4 4H35z" fill="{accent}"/>
  <circle cx="41" cy="22" r="2" fill="#171816"/>""",
        "concordato": f"""
  <path d="M18 13h27l8 9v31H18z" fill="{paper}"/>
  <path d="M45 13v10h8" fill="#E1D1AC"/>
  <path d="M26 31h18M26 39h15" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M32 47h11" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
  <path d="m44 44 4 4 8-11" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>""",
        "registry": f"""
  <path d="M31 12 12 23h38z" fill="{paper}"/>
  <path d="M16 27h28M17 47h26" stroke="{paper}" stroke-width="5" stroke-linecap="round"/>
  <path d="M21 28v16M30 28v16M39 28v16" stroke="{paper}" stroke-width="4" stroke-linecap="round"/>
  <rect x="37" y="31" width="18" height="20" rx="4" fill="{accent}"/>
  <path d="M42 37h8M42 42h8" stroke="#171816" stroke-width="2.5" stroke-linecap="round"/>
  <path d="m42 47 2 2 5-5" fill="none" stroke="#171816" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>""",
        "pension": f"""
  <path d="M16 13h29l7 8v31H16z" fill="{paper}"/>
  <path d="M45 13v9h7" fill="#E1D6C3"/>
  <path d="M23 25h17M23 33h12M23 41h10" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
  <circle cx="43" cy="42" r="10" fill="{accent}"/>
  <path d="M43 36v6l4 3" fill="none" stroke="#171816" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M20 18h10" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>""",
        "advisor": f"""
  <circle cx="32" cy="22" r="8" fill="{paper}"/>
  <path d="M18 51c2.2-11 8.7-17 14-17s11.8 6 14 17" fill="none" stroke="{paper}" stroke-width="7" stroke-linecap="round"/>
  <path d="M23 51h18" stroke="{paper}" stroke-width="7" stroke-linecap="round"/>
  <path d="M45 20c3 2 5 5.5 5 9s-2 7-5 9" fill="none" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>""",
        "reviewer": f"""
  <path d="M21 20c0-6.4 4.7-10 10.2-10 4.2 0 7.6 2.1 9.1 5.6-4.8-.5-9.7 1.1-13.5 5.3z" fill="{accent}"/>
  <circle cx="30" cy="21" r="8" fill="{paper}"/>
  <path d="M14 51c1.8-11.8 7.9-18 16-18s14.2 6.2 16 18z" fill="{paper}"/>
  <path d="M23 35l7 12 7-12" fill="none" stroke="{spec.color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M19 51h22" stroke="{paper}" stroke-width="5" stroke-linecap="round"/>""",
    }
    return bodies[spec.motif]


def build_svg(spec: IconSpec) -> str:
    """Build one SVG string from a plugin icon spec."""

    return _frame(spec, _body(spec))


def generate_icons(
    *,
    plugins_root: Path = ROOT / "plugins",
    plugin_names: set[str] | None = None,
) -> list[Path]:
    """Write all configured icon files and return changed paths."""

    changed: list[Path] = []
    for spec in SPECS:
        if plugin_names is not None and spec.plugin not in plugin_names:
            continue
        icon_path = plugins_root / spec.plugin / "assets" / "icon.svg"
        if not icon_path.exists():
            LOGGER.warning("Skipping missing icon path: %s", icon_path)
            continue
        content = build_svg(spec)
        if icon_path.read_text(encoding="utf-8") == content:
            continue
        icon_path.write_text(content, encoding="utf-8")
        changed.append(icon_path)
    return changed


def main() -> int:
    """Run the icon generator."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugins-root",
        type=Path,
        default=ROOT / "plugins",
        help="Directory containing plugin folders.",
    )
    parser.add_argument(
        "--plugin",
        action="append",
        default=[],
        help="Generate only the named plugin icon; repeat for multiple plugins.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    changed = generate_icons(
        plugins_root=args.plugins_root,
        plugin_names=set(args.plugin) if args.plugin else None,
    )
    LOGGER.info("Updated %s plugin icon(s).", len(changed))
    for path in changed:
        LOGGER.info("Updated %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
