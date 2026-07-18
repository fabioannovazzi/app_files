"""Build a practical manifest review from existing mechanical evidence.

This deterministic report is justified because it only joins stable artifacts:
manifest records, role registries, dataset-profile matches, plugin parameter
contracts, render-proof statuses, and PNG file references. It does not choose
charts for a question and does not decide semantic analysis validity.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

__all__ = ["build_chart_manifest_practice_review", "main"]

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "runs" / "chart_selection_manifest_rebuild"
DEFAULT_SELECTION_MANIFEST = RUN_DIR / "selection_manifest.json"
DEFAULT_COMPATIBILITY_AUDIT = (
    RUN_DIR / "us_cosmetics_dataset_profile_chart_compatibility.json"
)
DEFAULT_PARAMETER_AUDIT = RUN_DIR / "plugin_parameter_contract_audit.json"
DEFAULT_STRESS_TEST = RUN_DIR / "chart_selection_stress_test.json"
DEFAULT_RENDER_PROOF_MATRIX = RUN_DIR / "chart_render_proof_matrix.json"
DEFAULT_FAMILY_REVIEW = RUN_DIR / "family_selector_review.json"
DEFAULT_GALLERY_MANIFEST = (
    REPO_ROOT / "static" / "shared" / "png-gallery" / "manifest.json"
)
DEFAULT_OUTPUT_JSON = RUN_DIR / "manifest_practice_review.json"
DEFAULT_OUTPUT_HTML = RUN_DIR / "manifest_practice_review.html"
DEFAULT_RENDERED_ASSET_DIR = RUN_DIR / "cosmetics_question_png_assets"
DEFAULT_STATIC_PUBLISH_DIR = REPO_ROOT / "static" / "shared" / "chart-manifest"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _optional_json(path: Path) -> dict[str, Any]:
    return _load_json(path) if path.exists() else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _records_by_capability(
    payload: dict[str, Any], key: str = "results"
) -> dict[str, dict[str, Any]]:
    return {
        str(item["capability_id"]): item
        for item in payload.get(key, [])
        if isinstance(item, dict) and item.get("capability_id")
    }


def _gallery_items_by_capability(
    gallery: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    items: dict[str, list[dict[str, Any]]] = {}
    for item in gallery.get("items", []):
        capability_id = (item.get("artifact_contract") or {}).get("capability_id")
        if capability_id:
            items.setdefault(str(capability_id), []).append(item)
    return items


def _artifact_parameter_contracts(
    gallery_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contracts = []
    for item in gallery_items:
        contract = item.get("artifact_contract") or {}
        contracts.append(
            {
                "artifact_label": item.get("label"),
                "plugin_source": item.get("plugin_source"),
                "source": item.get("source"),
                "output": item.get("output"),
                "required_parameters": contract.get("required_parameters") or [],
                "optional_parameters": contract.get("optional_parameters") or [],
                "outputs": contract.get("outputs") or [],
                "execution_contract": contract.get("execution_contract"),
                "defaults": contract.get("defaults")
                or contract.get("default_parameters"),
                "derived_parameters": contract.get("derived_parameters"),
            }
        )
    return contracts


def _question(capability: dict[str, Any], stress: dict[str, Any]) -> str:
    proof = stress.get("proof") or {}
    if proof.get("question"):
        return str(proof["question"])
    positives = (capability.get("selection_examples") or {}).get(
        "positive_questions"
    ) or []
    return str(positives[0]) if positives else "No plain-English question recorded."


def _proof_chart(stress: dict[str, Any]) -> str:
    proof = stress.get("proof") or {}
    return str(proof.get("plugin_chart") or "not exercised")


def _href(prefix: str, relative_path: str) -> str:
    return f"{prefix.rstrip('/')}/{relative_path.lstrip('/')}"


def _first_image(
    stress: dict[str, Any],
    *,
    rendered_asset_href_prefix: str,
    gallery_href_prefix: str,
) -> dict[str, Any]:
    png = stress.get("png_evidence") or {}
    if png.get("status") == "rendered_question_png":
        return {
            "status": "rendered_question_png",
            "href": _href(
                rendered_asset_href_prefix, str(png.get("relative_path") or "")
            ),
            "caption": str(png.get("renderer") or "cosmetics question render"),
        }
    if png.get("status") == "gallery_png":
        return {
            "status": "gallery_png",
            "href": _href(gallery_href_prefix, str(png.get("output") or "")),
            "caption": f"gallery fallback; examples={png.get('example_count', 1)}",
        }
    return {"status": "missing_png", "href": None, "caption": "No PNG evidence."}


def _role_lists(capability: dict[str, Any]) -> dict[str, Any]:
    requirements = (capability.get("selection_contract") or {}).get(
        "dataset_requirements", {}
    )
    metrics = requirements.get("metrics") or {}
    dimensions = requirements.get("dimensions") or {}
    period = requirements.get("period") or {}
    return {
        "source_metric_roles": [
            role.get("role") for role in metrics.get("source_metric_roles") or []
        ],
        "derived_metric_roles": [
            role.get("role") for role in metrics.get("derived_metric_roles") or []
        ],
        "display_metric_roles": metrics.get("display_metric_roles") or [],
        "period_role": period.get("role"),
        "requires_period_axis": bool(period.get("requires_period_axis")),
        "allows_period_filter": bool(period.get("allows_period_filter")),
        "required_dimension_roles": dimensions.get("required_roles") or [],
        "optional_dimension_roles": dimensions.get("optional_roles") or [],
    }


def _role_to_parameter_map(invocation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bucket in (
        "required_role_contracts",
        "optional_role_contracts",
        "variant_role_contracts",
    ):
        for contract in invocation.get(bucket) or []:
            rows.append(
                {
                    "bucket": bucket,
                    "kind": contract.get("kind"),
                    "role": contract.get("role"),
                    "status": contract.get("status"),
                    "mapping_kind": contract.get("mapping_kind"),
                    "parameter_targets": contract.get("parameter_targets") or [],
                    "depends_on_role": contract.get("depends_on_role"),
                    "artifact_label": contract.get("artifact_label"),
                    "issue": contract.get("issue"),
                }
            )
    return rows


def _column_match_evidence(compatibility: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": compatibility.get("status", "missing"),
        "issues": compatibility.get("issues") or [],
        "mechanical_role_matches": compatibility.get("mechanical_role_matches") or [],
        "unmatched_required_roles": compatibility.get("unmatched_required_roles") or [],
        "ambiguous_required_roles": compatibility.get("ambiguous_required_roles") or [],
        "rejected_column_evidence": compatibility.get("rejected_column_evidence") or [],
        "analysis_validity_status": compatibility.get(
            "analysis_validity_status", "not_checked"
        ),
    }


def _capability_record(
    capability_id: str,
    capability: dict[str, Any],
    *,
    compatibility: dict[str, Any],
    parameter_result: dict[str, Any],
    render_proof: dict[str, Any],
    stress: dict[str, Any],
    gallery_items: list[dict[str, Any]],
    rendered_asset_href_prefix: str,
    gallery_href_prefix: str,
) -> dict[str, Any]:
    invocation = capability.get("normalized_invocation_contract") or {}
    role_to_parameter = _role_to_parameter_map(invocation)
    artifact_parameter_contracts = _artifact_parameter_contracts(gallery_items)
    return {
        "capability_id": capability_id,
        "family": capability.get("family"),
        "question": _question(capability, stress),
        "proof_chart": _proof_chart(stress),
        "practice_status": render_proof.get("render_proof_status", "missing"),
        "fixture_requirement": render_proof.get("fixture_requirement", "missing"),
        "stress_status": stress.get("status", "missing"),
        "selection_emphasis": capability.get("selection_emphasis"),
        "primary_decision_cue": capability.get("primary_decision_cue"),
        "requires_question_focus": capability.get("requires_question_focus") or [],
        "reject_decision_cues": capability.get("reject_decision_cues") or [],
        "best_when": capability.get("best_when"),
        "avoid_when": capability.get("avoid_when"),
        "role_lists": _role_lists(capability),
        "role_to_parameter_map": role_to_parameter,
        "plugin_sources": invocation.get("plugin_sources") or [],
        "artifact_labels": invocation.get("artifact_labels") or [],
        "output_forms": invocation.get("output_forms") or [],
        "invocation_contract_status": invocation.get(
            "status", parameter_result.get("status", "missing")
        ),
        "parameter_audit_status": parameter_result.get("status", "missing"),
        "missing_invocation_roles": invocation.get("missing_roles") or [],
        "parameter_source_count": invocation.get("parameter_source_count"),
        "artifact_parameter_contracts": artifact_parameter_contracts,
        "contract_fields": {
            "required_parameters_recorded": any(
                item["required_parameters"] for item in artifact_parameter_contracts
            ),
            "optional_parameters_recorded": any(
                "optional_parameters" in item for item in artifact_parameter_contracts
            ),
            "defaults_recorded": any(
                item["defaults"] is not None for item in artifact_parameter_contracts
            ),
            "derived_parameters_recorded": any(
                item["derived_parameters"] is not None
                for item in artifact_parameter_contracts
            ),
        },
        "dataset_profile_evidence": _column_match_evidence(compatibility),
        "image": _first_image(
            stress,
            rendered_asset_href_prefix=rendered_asset_href_prefix,
            gallery_href_prefix=gallery_href_prefix,
        ),
        "render_proof": render_proof,
    }


def _family_review_digest(family_review: dict[str, Any]) -> list[dict[str, Any]]:
    digest = []
    for family in family_review.get("families", []):
        digest.append(
            {
                "family": family.get("family"),
                "capability_ids": family.get("capability_ids") or [],
                "answers": family.get("answers") or {},
                "evidence": family.get("evidence") or {},
                "manual_focus_review": family.get("manual_focus_review"),
            }
        )
    return digest


def _remaining_work(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "needs_question_render_fixture": [],
        "semantic_or_package_fixture_needed": [],
        "dataset_schema_fixture_needed": [],
        "invocation_or_parameter_gap": [],
    }
    for record in records:
        requirement = record["fixture_requirement"]
        status = record["practice_status"]
        item = {
            "capability_id": record["capability_id"],
            "family": record["family"],
            "practice_status": status,
            "fixture_requirement": requirement,
            "issues": record["dataset_profile_evidence"]["issues"],
        }
        if requirement == "question_render_fixture":
            buckets["needs_question_render_fixture"].append(item)
        elif requirement == "semantic_or_package_fixture":
            buckets["semantic_or_package_fixture_needed"].append(item)
        elif requirement == "dataset_with_required_schema":
            buckets["dataset_schema_fixture_needed"].append(item)
        elif status == "invocation_contract_gap":
            buckets["invocation_or_parameter_gap"].append(item)
    return buckets


def build_chart_manifest_practice_review(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    compatibility_audit_path: Path = DEFAULT_COMPATIBILITY_AUDIT,
    parameter_audit_path: Path = DEFAULT_PARAMETER_AUDIT,
    stress_test_path: Path = DEFAULT_STRESS_TEST,
    render_proof_matrix_path: Path = DEFAULT_RENDER_PROOF_MATRIX,
    family_review_path: Path = DEFAULT_FAMILY_REVIEW,
    gallery_manifest_path: Path = DEFAULT_GALLERY_MANIFEST,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_html_path: Path = DEFAULT_OUTPUT_HTML,
    rendered_asset_href_prefix: str = "cosmetics_question_png_assets/",
    gallery_href_prefix: str = "../../static/shared/png-gallery/",
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    compatibility_audit = _load_json(compatibility_audit_path)
    parameter_audit = _optional_json(parameter_audit_path)
    stress_test = _load_json(stress_test_path)
    render_proof_matrix = _load_json(render_proof_matrix_path)
    family_review = _optional_json(family_review_path)
    gallery_manifest = _load_json(gallery_manifest_path)

    compatibility_by_capability = _records_by_capability(compatibility_audit)
    parameter_by_capability = _records_by_capability(parameter_audit)
    stress_by_capability = _records_by_capability(stress_test, key="records")
    render_by_capability = _records_by_capability(render_proof_matrix, key="records")
    gallery_by_capability = _gallery_items_by_capability(gallery_manifest)

    records = [
        _capability_record(
            capability_id,
            capability,
            compatibility=compatibility_by_capability.get(capability_id, {}),
            parameter_result=parameter_by_capability.get(capability_id, {}),
            render_proof=render_by_capability.get(capability_id, {}),
            stress=stress_by_capability.get(capability_id, {}),
            gallery_items=gallery_by_capability.get(capability_id, []),
            rendered_asset_href_prefix=rendered_asset_href_prefix,
            gallery_href_prefix=gallery_href_prefix,
        )
        for capability_id, capability in sorted(
            (manifest.get("capabilities") or {}).items()
        )
    ]
    role_registry = manifest.get("role_registry") or {}
    counts = {
        "capabilities": len(records),
        "families": len({record["family"] for record in records}),
        "practice_status": dict(
            sorted(Counter(record["practice_status"] for record in records).items())
        ),
        "fixture_requirement": dict(
            sorted(Counter(record["fixture_requirement"] for record in records).items())
        ),
        "invocation_contract_status": dict(
            sorted(
                Counter(
                    record["invocation_contract_status"] for record in records
                ).items()
            )
        ),
        "dataset_compatibility_status": dict(
            sorted(
                Counter(
                    record["dataset_profile_evidence"]["status"] for record in records
                ).items()
            )
        ),
        "image_evidence": dict(
            sorted(Counter(record["image"]["status"] for record in records).items())
        ),
        "role_registry": role_registry.get("counts") or {},
    }
    payload = {
        "schema_version": "0.1",
        "purpose": (
            "Practical evidence review for the chart manifest setup. It shows, "
            "chart by chart, whether existing manifest + dataset profile + "
            "plugin contract evidence is enough to render or identify what is "
            "missing. It excludes semantic-layer and orchestrator decisions."
        ),
        "inputs": {
            "selection_manifest": str(selection_manifest_path),
            "compatibility_audit": str(compatibility_audit_path),
            "parameter_audit": str(parameter_audit_path),
            "stress_test": str(stress_test_path),
            "render_proof_matrix": str(render_proof_matrix_path),
            "family_review": str(family_review_path),
            "gallery_manifest": str(gallery_manifest_path),
        },
        "counts": counts,
        "role_registry": {
            "purpose": role_registry.get("purpose"),
            "counts": role_registry.get("counts") or {},
            "chart_roles": role_registry.get("chart_roles") or [],
            "profile_roles": role_registry.get("profile_roles") or [],
        },
        "remaining_work": _remaining_work(records),
        "family_review": _family_review_digest(family_review),
        "records": records,
    }
    _write_json(output_json_path, payload)
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = "\n".join(line.rstrip() for line in _html_page(payload).splitlines())
    output_html_path.write_text(html_text + "\n", encoding="utf-8")
    return payload


def _copy_rendered_assets(source_dir: Path, target_dir: Path) -> None:
    if not source_dir.exists():
        raise FileNotFoundError(f"Missing rendered asset directory: {source_dir}")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _list(values: Any, *, limit: int = 8) -> str:
    if isinstance(values, dict):
        values = list(values)
    elif isinstance(values, (set, tuple)):
        values = list(values)
    elif values is not None and not isinstance(values, list):
        values = [values]
    if not values:
        return '<span class="muted">none</span>'
    rendered = ", ".join(f"<code>{_esc(value)}</code>" for value in values[:limit])
    if len(values) > limit:
        rendered += f' <span class="muted">+{len(values) - limit} more</span>'
    return rendered


def _json_block(value: Any) -> str:
    return _esc(json.dumps(value, indent=2, ensure_ascii=False))


def _small_table(rows: list[tuple[str, Any]]) -> str:
    body = "\n".join(
        f"<tr><th>{_esc(label)}</th><td>{value}</td></tr>" for label, value in rows
    )
    return f"<table>{body}</table>"


def _counts_table(counts: dict[str, Any]) -> str:
    rows = []
    for group, values in counts.items():
        if isinstance(values, dict):
            value = ", ".join(f"<code>{_esc(k)}</code> {v}" for k, v in values.items())
        else:
            value = _esc(values)
        rows.append((group, value))
    return _small_table(rows)


def _remaining_work_html(payload: dict[str, Any]) -> str:
    sections = []
    labels = {
        "needs_question_render_fixture": "Gallery proof, but no question-rendered PNG yet",
        "semantic_or_package_fixture_needed": "Semantic/package fixture needed",
        "dataset_schema_fixture_needed": "Dataset schema fixture needed",
        "invocation_or_parameter_gap": "Invocation or parameter gap",
    }
    for key, label in labels.items():
        items = payload["remaining_work"].get(key) or []
        rows = "\n".join(
            "<tr>"
            f"<td><code>{_esc(item['capability_id'])}</code></td>"
            f"<td>{_esc(item['family'])}</td>"
            f"<td><code>{_esc(item['practice_status'])}</code></td>"
            f"<td>{_list(item.get('issues') or [], limit=5)}</td>"
            "</tr>"
            for item in items
        )
        rows = rows or '<tr><td colspan="4"><span class="muted">none</span></td></tr>'
        sections.append(f"""
<section class="panel">
  <h2>{_esc(label)} <span>{len(items)}</span></h2>
  <table>
    <thead><tr><th>Capability</th><th>Family</th><th>Status</th><th>Issues</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
""")
    return "\n".join(sections)


def _family_review_html(payload: dict[str, Any]) -> str:
    cards = []
    for family in payload.get("family_review") or []:
        answers = family.get("answers") or {}
        answer_rows = "\n".join(
            f"<tr><th>{_esc(key)}</th><td>{_esc(value)}</td></tr>"
            for key, value in answers.items()
        )
        manual = family.get("manual_focus_review") or {}
        reviews = manual.get("capability_reviews") or []
        review_rows = "\n".join(
            "<tr>"
            f"<td><code>{_esc(item.get('capability_id'))}</code></td>"
            f"<td>{_esc(item.get('primary_decision_cue'))}</td>"
            f"<td><code>{_esc(item.get('render_proof_status'))}</code></td>"
            "</tr>"
            for item in reviews
        )
        manual_html = (
            f"""
<details>
  <summary>Manual focus review ({len(reviews)} capabilities)</summary>
  <table>
    <thead><tr><th>Capability</th><th>Decision cue</th><th>Render proof</th></tr></thead>
    <tbody>{review_rows}</tbody>
  </table>
</details>
"""
            if reviews
            else '<p class="muted">No manual focus review for this family.</p>'
        )
        cards.append(f"""
<article class="family">
  <h3>{_esc(family.get('family'))} <span>{len(family.get('capability_ids') or [])}</span></h3>
  <table>{answer_rows}</table>
  {manual_html}
</article>
""")
    return "\n".join(cards)


def _image_html(image: dict[str, Any], capability_id: str) -> str:
    href = image.get("href")
    if href:
        return (
            f'<a href="{_esc(href)}"><img src="{_esc(href)}" '
            f'alt="{_esc(capability_id)} PNG evidence"></a>'
            f'<p class="caption">{_esc(image.get("status"))}: {_esc(image.get("caption"))}</p>'
        )
    return '<div class="missing">No PNG evidence for this capability.</div>'


def _role_match_rows(matches: list[dict[str, Any]]) -> str:
    rows = []
    for match in matches:
        rows.append(
            "<tr>"
            f"<td><code>{_esc(match.get('role'))}</code></td>"
            f"<td>{_esc(match.get('kind'))}</td>"
            f"<td><code>{_esc(match.get('fit_status'))}</code></td>"
            f"<td><code>{_esc(match.get('ambiguity_status'))}</code></td>"
            f"<td>{_esc(match.get('candidate_count'))}</td>"
            f"<td>{_list(match.get('candidate_columns') or [], limit=6)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6"><span class="muted">none</span></td></tr>'
    return "\n".join(rows)


def _parameter_target_rows(rows: list[dict[str, Any]]) -> str:
    rendered = []
    for row in rows:
        targets = row.get("parameter_targets") or []
        target_text = []
        for target in targets:
            label = target.get("target") or target.get("recipe_path") or target
            target_text.append(str(label))
        rendered.append(
            "<tr>"
            f"<td><code>{_esc(row.get('role'))}</code></td>"
            f"<td>{_esc(row.get('kind'))}</td>"
            f"<td><code>{_esc(row.get('status'))}</code></td>"
            f"<td>{_list(target_text, limit=4)}</td>"
            "</tr>"
        )
    if not rendered:
        return '<tr><td colspan="4"><span class="muted">none</span></td></tr>'
    return "\n".join(rendered)


def _artifact_contract_rows(contracts: list[dict[str, Any]]) -> str:
    rows = []
    for contract in contracts:
        rows.append(
            "<tr>"
            f"<td>{_esc(contract.get('artifact_label'))}</td>"
            f"<td>{_esc(contract.get('plugin_source'))}</td>"
            f"<td>{_list(contract.get('required_parameters') or [], limit=6)}</td>"
            f"<td>{_list(contract.get('optional_parameters') or [], limit=6)}</td>"
            f"<td>{_esc('recorded' if contract.get('defaults') is not None else 'not recorded')}</td>"
            f"<td>{_esc('recorded' if contract.get('derived_parameters') is not None else 'not recorded')}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6"><span class="muted">no gallery artifact contract</span></td></tr>'
    return "\n".join(rows)


def _rejected_columns_html(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return '<p class="muted">No rejected-column samples recorded.</p>'
    groups = []
    for item in evidence[:4]:
        samples = item.get("samples") or []
        rows = "\n".join(
            "<tr>"
            f"<td><code>{_esc(sample.get('column'))}</code></td>"
            f"<td>{_esc(sample.get('reason'))}</td>"
            f"<td>{_esc(sample.get('source_role'))}</td>"
            f"<td>{_esc(sample.get('metric_class'))}</td>"
            "</tr>"
            for sample in samples[:6]
        )
        rows = rows or '<tr><td colspan="4"><span class="muted">none</span></td></tr>'
        groups.append(f"""
<details>
  <summary>{_esc(item.get('kind'))} / <code>{_esc(item.get('role'))}</code> rejected {item.get('rejected_count')}</summary>
  <table>
    <thead><tr><th>Column</th><th>Reason</th><th>Source role</th><th>Metric class</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</details>
""")
    return "\n".join(groups)


def _capability_card(record: dict[str, Any]) -> str:
    evidence = record["dataset_profile_evidence"]
    role_lists = record["role_lists"]
    status_class = str(record["practice_status"]).replace("_", "-")
    return f"""
<article class="capability-card" id="{_esc(record['capability_id'])}">
  <div class="card-head">
    <div>
      <p class="eyebrow">{_esc(record['family'])} / {_esc(record['selection_emphasis'])}</p>
      <h3>{_esc(record['question'])}</h3>
      <p><code>{_esc(record['capability_id'])}</code> -> <code>{_esc(record['proof_chart'])}</code></p>
    </div>
    <span class="badge {status_class}">{_esc(record['practice_status'])}</span>
  </div>
  <div class="card-body">
    <section class="visual">{_image_html(record['image'], record['capability_id'])}</section>
    <section>
      {_small_table([
          ("Fixture requirement", f"<code>{_esc(record['fixture_requirement'])}</code>"),
          ("Invocation status", f"<code>{_esc(record['invocation_contract_status'])}</code>"),
          ("Dataset compatibility", f"<code>{_esc(evidence['status'])}</code>"),
          ("Output forms", _list(record["output_forms"], limit=6)),
          ("Plugin/source", _list(record["plugin_sources"], limit=6)),
          ("Primary decision cue", _esc(record.get("primary_decision_cue") or "")),
          ("Best when", _esc(record.get("best_when") or "")),
          ("Avoid when", _esc(record.get("avoid_when") or "")),
          ("Analysis validity", f"<code>{_esc(evidence['analysis_validity_status'])}</code>"),
      ])}
    </section>
  </div>
  <details open>
    <summary>Roles and matched columns</summary>
    <div class="two-col">
      <div>
        <h4>Required chart roles</h4>
        <pre>{_json_block(role_lists)}</pre>
      </div>
      <div>
        <h4>Mechanical role matches from dataset profile</h4>
        <table>
          <thead><tr><th>Role</th><th>Kind</th><th>Fit</th><th>Ambiguity</th><th>Candidates</th><th>Columns</th></tr></thead>
          <tbody>{_role_match_rows(evidence["mechanical_role_matches"])}</tbody>
        </table>
      </div>
    </div>
    <p><strong>Unmatched required roles:</strong> {_list(evidence["unmatched_required_roles"], limit=8)}</p>
    <p><strong>Ambiguous required roles:</strong> {_list([item.get("role") for item in evidence["ambiguous_required_roles"]], limit=8)}</p>
  </details>
  <details>
    <summary>Invocation contract and parameters</summary>
    <h4>Canonical role-to-parameter map</h4>
    <table>
      <thead><tr><th>Role</th><th>Kind</th><th>Status</th><th>Parameter targets</th></tr></thead>
      <tbody>{_parameter_target_rows(record["role_to_parameter_map"])}</tbody>
    </table>
    <h4>Gallery artifact parameter contract</h4>
    <table>
      <thead><tr><th>Artifact</th><th>Plugin/source</th><th>Required parameters</th><th>Optional parameters</th><th>Defaults</th><th>Derived parameters</th></tr></thead>
      <tbody>{_artifact_contract_rows(record["artifact_parameter_contracts"])}</tbody>
    </table>
    <p><strong>Missing invocation roles:</strong> {_list(record["missing_invocation_roles"], limit=8)}</p>
  </details>
  <details>
    <summary>Rejected column evidence</summary>
    {_rejected_columns_html(evidence["rejected_column_evidence"])}
  </details>
</article>
"""


def _html_page(payload: dict[str, Any]) -> str:
    cards = "\n".join(_capability_card(record) for record in payload["records"])
    family_review = _family_review_html(payload)
    remaining_work = _remaining_work_html(payload)
    role_registry = payload["role_registry"]
    role_registry_rows = _small_table(
        [
            ("Purpose", _esc(role_registry.get("purpose") or "")),
            ("Counts", _counts_table(role_registry.get("counts") or {})),
            ("Chart roles", _list(role_registry.get("chart_roles") or [], limit=24)),
            (
                "Profile roles",
                _list(role_registry.get("profile_roles") or [], limit=24),
            ),
        ]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chart Manifest Practice Review</title>
  <style>
    :root {{
      --ink: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --panel: #f7f8fa;
      --ok: #0f766e;
      --warn: #b54708;
      --bad: #b42318;
      --info: #175cd3;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #fff;
    }}
    header {{
      padding: 28px 32px 18px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 0 0 10px; font-size: 18px; letter-spacing: 0; }}
    h3 {{ margin: 0; font-size: 17px; line-height: 1.3; letter-spacing: 0; }}
    h4 {{ margin: 12px 0 6px; font-size: 13px; letter-spacing: 0; }}
    .intro {{ margin: 0; max-width: 1120px; color: var(--muted); line-height: 1.45; }}
    main {{ padding: 22px 32px 48px; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; }}
    nav a {{
      color: var(--info);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      text-decoration: none;
      font-size: 13px;
      background: #fff;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(2, minmax(280px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .panel, .family, .capability-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
      margin: 0 0 14px;
    }}
    .panel {{ padding: 14px; }}
    .panel h2 span, .family h3 span {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{
      text-align: left;
      vertical-align: top;
      border-top: 1px solid var(--line);
      padding: 7px 6px;
    }}
    th {{ color: var(--muted); font-weight: 700; width: 24%; }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    pre {{
      overflow: auto;
      background: #f3f5f7;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      line-height: 1.35;
    }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .family {{ padding: 14px; }}
    .family h3 {{ margin-bottom: 10px; }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      padding: 14px 16px;
      background: #fbfcfd;
      border-bottom: 1px solid var(--line);
    }}
    .eyebrow {{
      margin: 0 0 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .card-head p {{ margin: 6px 0 0; }}
    .badge {{
      align-self: flex-start;
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      background: #fff;
    }}
    .dataset-rendered-png-proven {{ color: var(--ok); background: #e8f6f4; border-color: #99d0c9; }}
    .gallery-png-plus-parameter-proof {{ color: var(--info); background: #eff8ff; border-color: #b2ddff; }}
    .correct-dataset-rejection {{ color: var(--warn); background: #fffaeb; border-color: #fedf89; }}
    .semantic-or-package-gap, .invocation-contract-gap, .dataset-fixture-gap, .proof-fixture-gap {{
      color: var(--bad);
      background: #fef3f2;
      border-color: #fecdca;
    }}
    .card-body {{
      display: grid;
      grid-template-columns: minmax(300px, 0.95fr) minmax(340px, 1.05fr);
      gap: 16px;
      padding: 16px;
    }}
    .visual img {{
      width: 100%;
      height: auto;
      display: block;
      border: 1px solid var(--line);
      background: #fff;
    }}
    .caption {{ margin: 7px 0 0; color: var(--muted); font-size: 12px; }}
    details {{ border-top: 1px solid var(--line); padding: 10px 16px; }}
    details summary {{ cursor: pointer; font-weight: 700; font-size: 13px; }}
    .two-col {{
      display: grid;
      grid-template-columns: minmax(260px, 0.8fr) minmax(360px, 1.2fr);
      gap: 14px;
      margin-top: 10px;
    }}
    .missing {{
      border: 1px solid var(--line);
      background: #fff7ed;
      color: var(--warn);
      padding: 20px;
      font-weight: 700;
    }}
    @media (max-width: 980px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
      .summary, .card-body, .two-col {{ grid-template-columns: 1fr; }}
      .card-head {{ flex-direction: column; }}
      .badge {{ white-space: normal; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Chart Manifest Practice Review</h1>
    <p class="intro">{_esc(payload["purpose"])}</p>
  </header>
  <main>
    <nav>
      <a href="#summary">Summary</a>
      <a href="#role-registry">Role Registry</a>
      <a href="#remaining-work">Missing / Gaps</a>
      <a href="#family-review">Family Review</a>
      <a href="#capabilities">All Capabilities</a>
    </nav>
    <section id="summary" class="summary">
      <div class="panel">
        <h2>Observed Counts</h2>
        {_counts_table(payload["counts"])}
      </div>
      <div id="role-registry" class="panel">
        <h2>Role Registry</h2>
        {role_registry_rows}
      </div>
    </section>
    <section id="remaining-work">
      <h2>Missing / Gaps</h2>
      {remaining_work}
    </section>
    <section id="family-review">
      <h2>Manual Family Review</h2>
      {family_review}
    </section>
    <section id="capabilities">
      <h2>All Capability Examples</h2>
      {cards}
    </section>
  </main>
</body>
</html>
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection-manifest", type=Path, default=DEFAULT_SELECTION_MANIFEST
    )
    parser.add_argument(
        "--compatibility-audit", type=Path, default=DEFAULT_COMPATIBILITY_AUDIT
    )
    parser.add_argument("--parameter-audit", type=Path, default=DEFAULT_PARAMETER_AUDIT)
    parser.add_argument("--stress-test", type=Path, default=DEFAULT_STRESS_TEST)
    parser.add_argument(
        "--render-proof-matrix", type=Path, default=DEFAULT_RENDER_PROOF_MATRIX
    )
    parser.add_argument("--family-review", type=Path, default=DEFAULT_FAMILY_REVIEW)
    parser.add_argument(
        "--gallery-manifest", type=Path, default=DEFAULT_GALLERY_MANIFEST
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-html", type=Path, default=DEFAULT_OUTPUT_HTML)
    parser.add_argument(
        "--publish-static-dir",
        type=Path,
        default=None,
        help=(
            "Optional served static directory. When set, writes index.html there, "
            "copies rendered PNG assets beside it, and rewrites image links for "
            "/static/shared publication."
        ),
    )
    parser.add_argument(
        "--rendered-asset-dir",
        type=Path,
        default=DEFAULT_RENDERED_ASSET_DIR,
        help="Rendered question PNG asset directory to copy for static publication.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parser().parse_args()
    output_html_path = args.output_html
    rendered_asset_href_prefix = "cosmetics_question_png_assets/"
    gallery_href_prefix = "../../static/shared/png-gallery/"
    if args.publish_static_dir:
        publish_dir = args.publish_static_dir
        _copy_rendered_assets(
            args.rendered_asset_dir, publish_dir / "cosmetics_question_png_assets"
        )
        if output_html_path == DEFAULT_OUTPUT_HTML:
            output_html_path = publish_dir / "index.html"
        rendered_asset_href_prefix = "cosmetics_question_png_assets/"
        gallery_href_prefix = "../png-gallery/"
    payload = build_chart_manifest_practice_review(
        selection_manifest_path=args.selection_manifest,
        compatibility_audit_path=args.compatibility_audit,
        parameter_audit_path=args.parameter_audit,
        stress_test_path=args.stress_test,
        render_proof_matrix_path=args.render_proof_matrix,
        family_review_path=args.family_review,
        gallery_manifest_path=args.gallery_manifest,
        output_json_path=args.output_json,
        output_html_path=output_html_path,
        rendered_asset_href_prefix=rendered_asset_href_prefix,
        gallery_href_prefix=gallery_href_prefix,
    )
    LOGGER.info("%s", args.output_json)
    LOGGER.info("%s", output_html_path)
    LOGGER.info("%s", json.dumps(payload["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
