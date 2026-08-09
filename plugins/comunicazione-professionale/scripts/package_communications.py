#!/usr/bin/env python3
"""Package accepted professional communications and their technical basis."""

from __future__ import annotations

import argparse
import html
import logging
from pathlib import Path
from typing import Any

from workflow_core import (
    atomic_write_json,
    atomic_write_text,
    file_digest,
    load_json,
    package_digest,
    recompute_contribution_digest,
    require_accepted_render_review,
    require_accepted_reviews,
    utc_now,
    validate_input_integrity,
    verify_visual_manifest,
    workflow_lock,
)

__all__ = ["package_communications", "main"]

LOGGER = logging.getLogger(__name__)
EXTENSIONS = {
    "client_email": ".txt",
    "client_circular": ".md",
    "linkedin": ".txt",
    "newsletter": ".md",
    "website_article": ".html",
    "client_alert": ".md",
    "faq": ".md",
}

LABELS = {
    "it": {
        "subject": "Oggetto",
        "sources": "Fonti",
        "no_publish": "Nessuna pubblicazione consigliata",
    },
    "en": {
        "subject": "Subject",
        "sources": "Sources",
        "no_publish": "No publication recommended",
    },
    "fr": {
        "subject": "Objet",
        "sources": "Sources",
        "no_publish": "Publication non recommandée",
    },
    "de": {
        "subject": "Betreff",
        "sources": "Quellen",
        "no_publish": "Keine Veröffentlichung empfohlen",
    },
    "es": {
        "subject": "Asunto",
        "sources": "Fuentes",
        "no_publish": "No se recomienda publicar",
    },
}


def _language_key(language: str) -> str:
    """Select deterministic interface labels without judging content language."""

    key = language.replace("_", "-").split("-", maxsplit=1)[0].lower()
    return key if key in LABELS else "en"


def _public_source_lines(draft: dict[str, Any]) -> list[str]:
    """Return the exact reviewed public notes, preserving their public URLs."""

    lines: list[str] = []
    for note in draft["public_source_notes"]:
        text = note["text"].strip()
        public_url = str(note.get("public_url") or "").strip()
        lines.append(
            f"{text} — {public_url}" if public_url and public_url not in text else text
        )
    return lines


def _artifact(
    root: Path, path: Path, *, kind: str, required_text: list[str] | None = None
) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "kind": kind,
        "status": "ready",
        "size_bytes": path.stat().st_size,
        "sha256": file_digest(path),
        "required_text": required_text or [],
    }


def _studio_profile(
    intake: dict[str, Any], contribution: dict[str, Any]
) -> dict[str, Any]:
    proposal = contribution.get("studio_profile_proposal")
    if proposal is not None:
        return proposal
    stored = intake.get("studio_profile")
    if not isinstance(stored, dict) or not isinstance(stored.get("payload"), dict):
        raise ValueError("Studio profile is required to package formatted output")
    return stored["payload"]["profile"]


def _website_html(
    draft: dict[str, Any],
    *,
    brand: dict[str, str],
    profile: dict[str, Any],
    reference_date: str,
    language: str,
) -> str:
    website = profile["website"]
    sections = "".join(
        f"<section><h2>{html.escape((str(index) + '. ') if website['heading_style'] == 'numbered' else '')}{html.escape(section['heading'])}</h2>"
        + "".join(
            f"<p>{html.escape(part)}</p>"
            for part in section["body"].split("\n\n")
            if part.strip()
        )
        + (
            "<ul>"
            + "".join(f"<li>{html.escape(item)}</li>" for item in section["bullets"])
            + "</ul>"
            if section["bullets"]
            else ""
        )
        + "</section>"
        for index, section in enumerate(draft["sections"], start=1)
    )
    introduction = "".join(
        f"<p>{html.escape(part)}</p>"
        for part in draft["body"].split("\n\n")
        if part.strip()
    )
    sections = introduction + sections
    byline = website["byline_pattern"].replace("{studio}", brand["studio_name"])
    visible_date = website["date_pattern"].replace("{date}", reference_date)
    update = (
        f'<time datetime="{html.escape(reference_date)}">{html.escape(visible_date)}</time>'
        if website["show_update_date"]
        else ""
    )
    contact = str(brand.get("contact_line") or "").strip()
    contact_html = (
        f'<footer class="contact">{html.escape(contact)}</footer>' if contact else ""
    )
    source_items = "".join(
        (
            f'<li>{html.escape(note["text"])} — <a href="{html.escape(note["public_url"], quote=True)}">{html.escape(note["public_url"])}</a></li>'
            if note.get("public_url") and note["public_url"] not in note["text"]
            else f'<li>{html.escape(note["text"])}</li>'
        )
        for note in draft["public_source_notes"]
    )
    language_key = _language_key(language)
    source_heading = (
        website["source_heading"]
        if language_key == "it"
        else LABELS[language_key]["sources"]
    )
    source_block = (
        f'<section class="sources"><h2>{html.escape(source_heading)}</h2><ul>{source_items}</ul></section>'
        if source_items
        else ""
    )
    html_language = html.escape(language.replace("_", "-"), quote=True)
    return f"""<!doctype html>
<html lang="{html_language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(draft['title'])}</title><style>
:root{{--primary:{brand['primary_color']};--accent:{brand['accent_color']};--background:{brand['background_color']};--text:{brand['text_color']}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--background);color:var(--text);font-family:"Instrument Sans","Segoe UI",sans-serif;line-height:1.62}}
article{{max-width:820px;margin:0 auto;padding:72px 32px 96px}}header{{border-top:6px solid var(--primary);padding-top:42px;margin-bottom:50px}}
.studio{{color:var(--primary);font-weight:650;letter-spacing:.02em}}h1{{font-size:clamp(2.35rem,6vw,4.6rem);line-height:.98;letter-spacing:-.045em;color:var(--primary);margin:.6rem 0 1.5rem}}
.meta{{display:flex;gap:1rem;flex-wrap:wrap;color:#59636d;font-size:.92rem}}h2{{font-size:1.45rem;line-height:1.2;color:var(--primary);margin:2.8rem 0 1rem;padding-top:1rem;border-top:1px solid #d7dce2}}
p,li{{font-size:1.05rem}}ul{{padding-left:1.2rem}}aside{{margin-top:3.5rem;padding:1.5rem 0;border-top:3px solid var(--accent);color:var(--primary);font-weight:550}}
.sources{{margin-top:2.5rem;color:#59636d;font-size:.9rem}}.sources h2{{font-size:1rem}}.sources li{{font-size:.9rem}}.contact{{margin-top:2.5rem;padding-top:1rem;border-top:1px solid #d7dce2;color:#59636d;font-size:.9rem}}
</style></head><body><article><header><div class="studio">{html.escape(brand['studio_name'])}</div><h1>{html.escape(draft['title'])}</h1><div class="meta"><span>{html.escape(byline)}</span>{update}</div></header>{sections}{source_block}<aside>{html.escape(website['cta'])}</aside>{contact_html}</article></body></html>"""


def _structured_plain_text(draft: dict[str, Any]) -> str:
    """Preserve a draft body and every structured section in plain text."""

    parts = [draft["body"].strip()]
    for section in draft["sections"]:
        block = [section["heading"].strip(), section["body"].strip()]
        block.extend(f"- {item}" for item in section["bullets"])
        parts.append("\n".join(item for item in block if item))
    return "\n\n".join(part for part in parts if part)


def _structured_markdown(draft: dict[str, Any], *, language: str) -> str:
    """Preserve body, headings, and bullets for every Markdown channel."""

    parts = [f"# {draft['title']}"]
    if draft.get("subject"):
        parts.append(
            f"**{LABELS[_language_key(language)]['subject']}:** {draft['subject']}"
        )
    if draft["body"].strip():
        parts.append(draft["body"].strip())
    for section in draft["sections"]:
        block = [f"## {section['heading']}"]
        if section["body"].strip():
            block.append(section["body"].strip())
        if section["bullets"]:
            block.append("\n".join(f"- {item}" for item in section["bullets"]))
        parts.append("\n\n".join(block))
    source_lines = _public_source_lines(draft)
    if source_lines:
        parts.append(
            f"## {LABELS[_language_key(language)]['sources']}\n\n"
            + "\n".join(f"- {line}" for line in source_lines)
        )
    return "\n\n".join(parts).rstrip() + "\n"


def _draft_content_required_text(draft: dict[str, Any]) -> list[str]:
    values = [draft["title"], draft["body"][:80]]
    for section in draft["sections"]:
        values.extend([section["heading"], section["body"][:80]])
        values.extend(section["bullets"])
    return [value for value in values if value]


def _draft_required_text(draft: dict[str, Any]) -> list[str]:
    return [*_draft_content_required_text(draft), *_public_source_lines(draft)]


def _client_email_text(
    draft: dict[str, Any],
    *,
    profile: dict[str, Any],
    include_attachment_note: bool,
    language: str,
) -> str:
    email_profile = profile["email"]
    subject = draft.get("subject") or draft["title"]
    pattern = email_profile["subject_pattern"] or "{subject}"
    subject_line = pattern.replace("{subject}", subject).replace(
        "{title}", draft["title"]
    )
    parts = [f"{LABELS[_language_key(language)]['subject']}: {subject_line}"]
    if email_profile["salutation"]:
        parts.append(email_profile["salutation"])
    parts.append(_structured_plain_text(draft))
    source_lines = _public_source_lines(draft)
    if source_lines:
        parts.append(
            f"{LABELS[_language_key(language)]['sources']}:\n"
            + "\n".join(f"- {line}" for line in source_lines)
        )
    if include_attachment_note and email_profile["attachment_note"]:
        parts.append(email_profile["attachment_note"])
    if email_profile["closing"]:
        parts.append(email_profile["closing"])
    if email_profile["signature_lines"]:
        parts.append("\n".join(email_profile["signature_lines"]))
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def _social_text(draft: dict[str, Any], *, profile: dict[str, Any]) -> str:
    social = profile["social"]
    body = f"{draft['title']}\n\n{_structured_plain_text(draft)}"
    if social["show_source_note"]:
        source_lines = _public_source_lines(draft)
        if not source_lines:
            raise ValueError("LinkedIn format requires reviewed public source notes")
        body = f"{body}\n\n" + "\n".join(source_lines)
    hashtags = [tag for tag in social["hashtags"] if tag not in body]
    if hashtags:
        body = f"{body}\n\n{' '.join(hashtags)}"
    return body.rstrip() + "\n"


def _technical_basis(
    contribution: dict[str, Any],
    source_register: dict[str, Any],
    answer_contract: dict[str, Any],
    claim_assurance: dict[str, Any],
    editorial_assessment: dict[str, Any],
) -> str:
    source_by_id = {
        row["id"]: row
        for row in [*source_register["sources"], *source_register["history"]]
    }
    lines = [
        "# Technical and editorial basis",
        "",
        f"Recommendation: **{contribution['recommendation']}**",
        "",
        "## Answer contract",
        "",
        f"Purpose: {answer_contract['purpose']}",
        "",
        f"Audience: {answer_contract['audience']}",
        "",
        f"Jurisdiction: {answer_contract['jurisdiction']} ({answer_contract['jurisdiction_status']})",
        "",
        f"Validation scope: `{answer_contract['validation_scope']}`",
        "",
        "## Independent claim assurance",
        "",
        claim_assurance["overall_assessment"]["analysis"],
        "",
        f"Outcome: `{claim_assurance['overall_assessment']['outcome']}`",
        "",
        "## Editorial value",
        "",
    ]
    for key, value in contribution["editorial_value"].items():
        lines.extend((f"### {key.replace('_', ' ').title()}", "", value, ""))
    lines.extend(("## Independent editorial assessment", ""))
    for key, value in editorial_assessment.items():
        if key in {
            "schema_version",
            "run_id",
            "assessed_contribution_digest",
            "channel_assessments",
            "slide_assessments",
        }:
            continue
        heading = key.replace("_", " ").title()
        if isinstance(value, list):
            rendered = "\n".join(f"- {item}" for item in value) or "- None"
        else:
            rendered = str(value)
        lines.extend((f"### {heading}", "", rendered, ""))
    lines.extend(("## Sources", ""))
    for assessment in contribution["source_assessments"]:
        source = source_by_id[assessment["source_id"]]
        title = (
            source.get("title")
            or source.get("original_name")
            or assessment["source_id"]
        )
        lines.extend(
            (
                f"### {assessment['source_id']} · {title}",
                "",
                f"Role: `{assessment['semantic_role']}`",
                "",
                assessment["authority_assessment"],
                "",
                f"Limitations: {assessment['limitations'] or 'None recorded.'}",
                "",
            )
        )
    if contribution["claims"]:
        lines.extend(("## Claims", ""))
        for claim in contribution["claims"]:
            lines.extend(
                (
                    f"### {claim['id']}",
                    "",
                    claim["statement"],
                    "",
                    f"Sources: {', '.join(claim['source_ids'])}",
                    "",
                    f"Temporal qualification: {claim['temporal_qualification']}",
                    "",
                    f"Uncertainty: {claim['uncertainty'] or 'None recorded.'}",
                    "",
                    f"Professional judgment: {claim['professional_judgment'] or 'None recorded.'}",
                    "",
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def package_communications(run_dir: Path) -> Path:
    """Write channel files and one strict final artifact manifest."""

    root = run_dir.resolve()
    with workflow_lock(root):
        return _package_communications_locked(root)


def _package_communications_locked(root: Path) -> Path:
    """Build a validation-pending package under one mutation lock."""

    existing_path = root / "final_artifacts.json"
    if existing_path.is_file():
        existing = load_json(existing_path)
        if existing.get("status") in {
            "final_ready",
            "no_publication_recommended",
        }:
            raise ValueError(
                "Package is already finalized; supersede the contribution for a new package"
            )
    validate_input_integrity(root)
    intake = load_json(root / "run_intake.json")
    workbench = load_json(root / "content_workbench.json")
    recompute_contribution_digest(root)
    contribution = workbench["contribution"]
    decisions = require_accepted_reviews(root, workbench["required_review_scopes"])
    source_register = load_json(root / "source_register.json")
    artifacts: list[dict[str, Any]] = []

    basis_path = root / "technical_basis.md"
    atomic_write_text(
        basis_path,
        _technical_basis(
            contribution,
            source_register,
            workbench["answer_contract"],
            workbench["claim_assurance"],
            workbench["editorial_assessment"],
        ),
    )
    artifacts.append(
        _artifact(
            root,
            basis_path,
            kind="technical_basis",
            required_text=[
                "# Technical and editorial basis",
                "## Answer contract",
                "## Independent claim assurance",
                "## Editorial value",
                "## Independent editorial assessment",
                "## Sources",
            ],
        )
    )
    answer_contract_path = root / "answer_contract_record.json"
    atomic_write_json(
        answer_contract_path,
        {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": workbench["run_id"],
            "contribution_digest": workbench["contribution_digest"],
            "answer_contract": workbench["answer_contract"],
        },
    )
    artifacts.append(_artifact(root, answer_contract_path, kind="answer_contract"))
    claim_assurance_path = root / "claim_assurance_record.json"
    atomic_write_json(
        claim_assurance_path,
        {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": workbench["run_id"],
            "contribution_digest": workbench["contribution_digest"],
            "model_provenance": workbench["model_provenance"]["claim_assessor"],
            "assessment": workbench["claim_assurance"],
        },
    )
    artifacts.append(
        _artifact(root, claim_assurance_path, kind="claim_model_assessment")
    )
    editorial_assessment_path = root / "editorial_assessment_record.json"
    atomic_write_json(
        editorial_assessment_path,
        {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": workbench["run_id"],
            "contribution_digest": workbench["contribution_digest"],
            "model_provenance": workbench["model_provenance"]["editorial_assessor"],
            "assessment": workbench["editorial_assessment"],
        },
    )
    artifacts.append(
        _artifact(
            root,
            editorial_assessment_path,
            kind="editorial_model_assessment",
        )
    )

    if contribution["recommendation"] == "no_publish":
        recommendation_path = root / "no-publication-recommendation.md"
        atomic_write_text(
            recommendation_path,
            f"# {LABELS[_language_key(intake['language'])]['no_publish']}\n\n"
            + contribution["recommendation_reason"].strip()
            + "\n",
        )
        artifacts.append(
            _artifact(
                root,
                recommendation_path,
                kind="no_publication_recommendation",
                required_text=[LABELS[_language_key(intake["language"])]["no_publish"]],
            )
        )
        target_status = "no_publication_recommended"
    else:
        profile = _studio_profile(intake, contribution)
        needs_render = bool(
            contribution["visual_story"]["slides"]
            or "client_circular" in intake["requested_channels"]
        )
        visual_manifest = None
        if needs_render:
            verify_visual_manifest(root)
            require_accepted_render_review(root)
            visual_manifest = load_json(root / "visual_manifest.json")
        circular_attachment_present = bool(
            visual_manifest
            and any(
                output.get("kind") == "client_circular_pdf"
                for output in visual_manifest["outputs"]
            )
        )
        drafts_dir = root / "drafts"
        drafts_dir.mkdir(exist_ok=True)
        for draft in contribution["channel_drafts"]:
            channel = draft["channel"]
            path = drafts_dir / f"{channel}{EXTENSIONS[channel]}"
            if channel == "website_article":
                content = _website_html(
                    draft,
                    brand=intake["brand_profile"],
                    profile=profile,
                    reference_date=intake["reference_date"],
                    language=intake["language"],
                )
                required_text = [
                    "<article>",
                    *(
                        html.escape(value)
                        for value in _draft_content_required_text(draft)
                    ),
                    *(
                        html.escape(note["text"])
                        for note in draft["public_source_notes"]
                    ),
                    *(
                        html.escape(note["public_url"])
                        for note in draft["public_source_notes"]
                        if note.get("public_url")
                    ),
                ]
            elif channel == "client_email":
                content = _client_email_text(
                    draft,
                    profile=profile,
                    include_attachment_note=circular_attachment_present,
                    language=intake["language"],
                )
                required_text = [
                    f"{LABELS[_language_key(intake['language'])]['subject']}:",
                    *_draft_required_text(draft),
                ]
            elif channel == "linkedin":
                content = _social_text(draft, profile=profile)
                required_text = _draft_required_text(draft)
            else:
                content = _structured_markdown(draft, language=intake["language"])
                required_text = _draft_required_text(draft)
            atomic_write_text(path, content)
            artifacts.append(
                _artifact(
                    root, path, kind=f"{channel}_draft", required_text=required_text
                )
            )

        if needs_render:
            visual_manifest_path = root / "visual_manifest.json"
            if visual_manifest is None:
                raise ValueError("Verified visual manifest is unavailable")
            for output in visual_manifest["outputs"]:
                path = root / output["path"]
                artifacts.append(_artifact(root, path, kind=output["kind"]))
            artifacts.append(
                _artifact(root, visual_manifest_path, kind="visual_manifest")
            )
            visual_assessment_path = root / "visual_assessment_record.json"
            artifacts.append(
                _artifact(
                    root,
                    visual_assessment_path,
                    kind="visual_model_assessment",
                )
            )
        target_status = "final_ready"

    handoff_path = root / "artifact_card.md"
    atomic_write_text(
        handoff_path,
        "# Professional communication artifact card\n\n"
        f"- Run: `{intake['run_id']}`\n"
        f"- Validation target: **{target_status}**\n"
        f"- Recommendation: **{contribution['recommendation']}**\n"
        f"- Studio: {intake['brand_profile']['studio_name']}\n"
        f"- Channels: {', '.join(intake['requested_channels'])}\n"
        f"- Accepted review scopes: {', '.join(sorted(decisions))}\n\n"
        "## Boundaries\n\n"
        "The commercialista retains the technical position, audience judgment, recipient selection, and final send or publication decision.\n",
    )
    artifacts.append(
        _artifact(
            root,
            handoff_path,
            kind="artifact_card",
            required_text=[
                "# Professional communication artifact card",
                "## Boundaries",
            ],
        )
    )
    final = {
        "schema_version": 1,
        "plugin": "comunicazione-professionale",
        "workflow": "comunicazione-professionale",
        "run_id": intake["run_id"],
        "status": "validation_pending",
        "validation_target_status": target_status,
        "input_digest": workbench["input_digest"],
        "contribution_digest": workbench["contribution_digest"],
        "packaged_at": utc_now(),
        "review_status": {
            scope: event["decision"] for scope, event in decisions.items()
        },
        "outputs": artifacts,
        "blockers": [],
        "caveats": [
            "Source-ID closure and file hashes do not establish semantic support; accepted professional reviews govern the package.",
            "No email, upload, or publication has occurred unless a separate external receipt records visible confirmation.",
        ],
        "next_actions": (
            ["Keep the no-publication recommendation as the completed outcome."]
            if target_status == "no_publication_recommended"
            else [
                "Visually inspect every PNG, HTML page, and PDF before external use.",
                "Choose and verify exact recipients or publishing account only when ready to send or publish.",
            ]
        ),
    }
    if target_status == "final_ready" and (
        contribution["visual_story"]["slides"]
        or "client_circular" in intake["requested_channels"]
    ):
        final["review_status"]["rendered_output"] = "accepted"
    final["package_digest"] = package_digest(final)
    return atomic_write_json(root / "final_artifacts.json", final)


def main(argv: list[str] | None = None) -> int:
    """Package one accepted run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = package_communications(args.run_dir)
    except (OSError, ValueError) as exc:
        LOGGER.error("COMMUNICATION_PACKAGE_FAILED: %s", exc)
        return 1
    LOGGER.info("Packaged professional communication: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
