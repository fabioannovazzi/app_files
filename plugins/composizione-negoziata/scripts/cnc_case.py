"""Persist CNC judgments in Studio Archive; verify only mechanical lineage."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

__all__ = ["apply_request", "digest", "main", "render_record", "stale_nodes"]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = "composizione-negoziata"
ROLES = {"advisor", "esperto"}
KINDS = {
    "document",
    "fact",
    "assumption",
    "analysis",
    "draft",
    "gap",
    "source",
    "question",
    "event",
    "deadline",
}
CLASSIFICATIONS = {
    "documented",
    "reported",
    "calculated",
    "assumed",
    "judgment",
    "missing",
    "unreadable",
    "unverified",
}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")


def _dependencies() -> tuple[Any, Any]:
    """Resolve the existing archive and shared contract in source or packages."""
    for path in (
        ROOT / "vendor/modules",
        ROOT.parent.parent / "vendor/modules",
        ROOT.parent / "_shared/vendor/modules",
    ):
        if (path / "vera_assurance").is_dir():
            sys.path.insert(0, str(path))
            break
    archive = ROOT.parent / "studio-archive/scripts"
    if not (archive / "client_ledger.py").is_file():
        raise ValueError("Studio Archive is required; run this component through Vera")
    sys.path.insert(0, str(archive))
    import client_ledger
    from vera_assurance import load_client_engagement_context_file

    return client_ledger, load_client_engagement_context_file


def digest(value: Any) -> str:
    """Identify exact JSON content, never professional validity."""
    data = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(data).hexdigest()


def _text(value: Any, label: str, maximum: int = 100_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be nonempty bounded text")
    return value


def _exact(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} must have exactly: {', '.join(sorted(keys))}")


def _order(nodes: dict[str, dict[str, Any]]) -> list[str]:
    """Topological order is fixed because dependency IDs are explicit evidence."""
    ordered: list[str] = []
    pending = set(nodes)
    while pending:
        ready = sorted(
            key for key in pending if set(nodes[key]["depends_on"]).issubset(ordered)
        )
        if not ready:
            raise ValueError("Dependencies contain a cycle or unknown node")
        ordered.extend(ready)
        pending.difference_update(ready)
    return ordered


def stale_nodes(nodes: dict[str, dict[str, Any]]) -> list[str]:
    """Compare explicit dependency versions and propagate staleness transitively."""
    stale: set[str] = set()
    for key in _order(nodes):
        node = nodes[key]
        if any(
            dependency in stale
            or node["dependency_versions"].get(dependency)
            != nodes[dependency]["version"]
            for dependency in node["depends_on"]
        ):
            stale.add(key)
    return sorted(stale)


def _node(value: dict[str, Any], context: dict[str, Any], role: str) -> dict[str, Any]:
    _exact(
        value,
        {
            "id",
            "kind",
            "title",
            "content",
            "classification",
            "depends_on",
            "citations",
            "responsibility",
            "source",
        },
        "node",
    )
    if not isinstance(value["id"], str) or not IDENTIFIER.fullmatch(value["id"]):
        raise ValueError("Invalid node ID")
    if value["kind"] not in KINDS or value["classification"] not in CLASSIFICATIONS:
        raise ValueError("Unsupported node kind or evidence classification")
    if value["responsibility"] not in {role, "common"}:
        raise ValueError("A node cannot assume the other professional role")
    for field in ("title", "content"):
        _text(value[field], field)
    dependencies = value["depends_on"]
    if (
        not isinstance(dependencies, list)
        or not all(isinstance(item, str) for item in dependencies)
        or len(set(dependencies)) != len(dependencies)
    ):
        raise ValueError("depends_on must contain unique node IDs")
    if not isinstance(value["citations"], list):
        raise ValueError("citations must be a list")
    bindings = {row["binding_id"]: row for row in context["input_bindings"]}
    citations = []
    for citation in value["citations"]:
        _exact(citation, {"binding_id", "locator"}, "citation")
        binding = bindings.get(citation["binding_id"])
        if binding is None:
            raise ValueError("Citation must use an input bound to this managed run")
        citations.append(
            {
                "binding_id": binding["binding_id"],
                "locator": _text(citation["locator"], "locator", 2000),
                "sha256": binding["sha256"],
                "run_id": context["run_id"],
                "source_relative_path": binding["source_relative_path"],
                "upstream_workflow_id": binding.get("upstream_workflow_id"),
            }
        )
    if value["kind"] == "document" and not citations:
        raise ValueError("A document node needs a captured input citation")
    source = value["source"]
    if value["kind"] == "source":
        _exact(
            source,
            {
                "url",
                "kind",
                "checked_on",
                "applicable_on",
                "inspected_scope",
                "limitations",
            },
            "source",
        )
        for field, text in source.items():
            _text(text, f"source.{field}", 5000)
        if not source["url"].startswith("https://"):
            raise ValueError("Source URL must use HTTPS")
    elif source is not None:
        raise ValueError("Only source nodes carry public source metadata")
    if (
        value["classification"] in {"documented", "calculated"}
        and not citations
        and not dependencies
    ):
        raise ValueError("Documented or calculated claims require evidence references")
    return {**copy.deepcopy(value), "citations": citations}


def _build_payload(
    request: dict[str, Any], context: dict[str, Any], previous: dict[str, Any] | None
) -> dict[str, Any]:
    role = request["role"]
    if role not in ROLES:
        raise ValueError("Choose advisor or esperto")
    if previous and previous["role"] != role:
        raise ValueError("Role is fixed; use a separate authorized engagement")
    _text(request["stage"], "stage", 2000)
    _text(request["change_reason"], "change_reason", 10000)
    action = request["next_action"]
    _exact(action, {"task", "why", "capability", "output", "decision"}, "next_action")
    for key, value in action.items():
        _text(value, f"next_action.{key}", 10000)
    if not isinstance(request["upsert_nodes"], list) or not isinstance(
        request["reviews"], list
    ):
        raise ValueError("Nodes and reviews must be lists")
    nodes = copy.deepcopy(previous["nodes"]) if previous else {}
    changed: set[str] = set()
    for value in request["upsert_nodes"]:
        node = _node(value, context, role)
        if node["id"] in changed:
            raise ValueError("Duplicate node update")
        changed.add(node["id"])
        nodes[node["id"]] = node
    if len(nodes) > 2000:
        raise ValueError("Case exceeds the 2000-node snapshot limit")
    for key in _order(nodes):
        if key in changed:
            node = nodes[key]
            node["dependency_versions"] = {
                dep: nodes[dep]["version"] for dep in node["depends_on"]
            }
            node["version"] = digest(node)
    stale = stale_nodes(nodes)
    reviews = copy.deepcopy(previous["reviews"]) if previous else []
    for review in request["reviews"]:
        _exact(
            review,
            {
                "node_id",
                "node_version",
                "reviewer_ref",
                "confirmation_ref",
                "decision",
                "reason",
            },
            "review",
        )
        target = nodes.get(review["node_id"])
        if (
            target is None
            or target["version"] != review["node_version"]
            or review["node_id"] in stale
        ):
            raise ValueError("Review must identify a current exact node version")
        if review["decision"] not in {"accepted", "changes_requested", "rejected"}:
            raise ValueError("Unsupported recorded review decision")
        for field in ("reviewer_ref", "confirmation_ref", "reason"):
            _text(review[field], field, 10000)
        recorded = {**review, "authority": "record_only_identity_not_verified"}
        if recorded not in reviews:
            reviews.append(recorded)
    return {
        "schema_version": "vera.cnc_case.v1",
        "role": role,
        "stage": request["stage"],
        "change_reason": request["change_reason"],
        "next_action": action,
        "nodes": nodes,
        "stale_nodes": stale,
        "reviews": reviews,
        "external_action_authorized": False,
    }


def apply_request(context_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Apply one explicit model-authored update with revision conflict protection."""
    _exact(
        request,
        {
            "expected_revision",
            "idempotency_key",
            "role",
            "stage",
            "change_reason",
            "next_action",
            "upsert_nodes",
            "reviews",
        },
        "request",
    )
    if (
        type(request["expected_revision"]) is not int
        or request["expected_revision"] < 0
    ):
        raise ValueError("expected_revision must be a nonnegative integer")
    _text(request["idempotency_key"], "idempotency_key", 240)
    ledger, load_context = _dependencies()
    context = load_context(context_path, expected_workflow_id=WORKFLOW)
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise ValueError("CNC requires a portable Studio Archive run")
    client_root = Path(context["studio_client_folder"]["client_root"])
    history = ledger.load_workflow_history(
        client_root, context["engagement_id"], WORKFLOW
    )
    request_hash = digest(request)
    retry = next(
        (
            row
            for row in history
            if row["idempotency_key"] == request["idempotency_key"]
        ),
        None,
    )
    if retry is not None:
        # The ledger compares request, revision and run identity before replaying.
        payload = retry["payload"]
    else:
        if len(history) != request["expected_revision"]:
            raise ValueError("Stale workflow revision; reload and reconcile changes")
        payload = _build_payload(
            request, context, history[-1]["payload"] if history else None
        )
    return ledger.append_workflow_snapshot(
        client_root,
        context["engagement_id"],
        context["run_id"],
        payload,
        expected_revision=request["expected_revision"],
        idempotency_key=request["idempotency_key"],
        request_sha256=request_hash,
    )


def render_record(record: dict[str, Any]) -> str:
    """Render substantive drafts and current review status from the saved snapshot."""
    state = record["payload"]
    lines = [
        "# Composizione negoziata",
        "",
        f"Ruolo: {state['role']} · Revisione {record['revision']}",
        "",
        state["stage"],
        "",
        "## Variazioni",
        "",
        state["change_reason"],
        "",
        "## Prossima attività",
        "",
    ]
    labels = {
        "task": "Attività",
        "why": "Motivo",
        "capability": "Capacità",
        "output": "Elaborato",
        "decision": "Decisione professionale",
    }
    for field, label in labels.items():
        lines.extend([f"**{label}:** {state['next_action'][field]}", ""])
    for key in _order(state["nodes"]):
        node = state["nodes"][key]
        status = (
            "DA RIESAMINARE"
            if node["id"] in state["stale_nodes"]
            else "versione corrente, da valutare professionalmente"
        )
        lines.extend(
            [
                f"## {node['title']}",
                "",
                f"{node['classification']} · {status}",
                "",
                node["content"],
                "",
            ]
        )
        for citation in node["citations"]:
            lines.append(
                f"- Evidenza {citation['binding_id']}: {citation['locator']} (run {citation['run_id']}; SHA-256 {citation['sha256']})"
            )
        if node["source"]:
            source = node["source"]
            lines.extend(
                [
                    f"- Fonte: {source['url']}; {source['kind']}; verificata {source['checked_on']}; applicabilità {source['applicable_on']}",
                    source["inspected_scope"],
                    source["limitations"],
                ]
            )
        if node["depends_on"]:
            lines.append("Dipende da: " + ", ".join(node["depends_on"]))
        lines.append("")
    lines.extend(["## Decisioni registrate", ""])
    for review in state["reviews"]:
        current = state["nodes"][review["node_id"]]
        valid = (
            review["node_version"] == current["version"]
            and review["node_id"] not in state["stale_nodes"]
        )
        status = (
            "riferita alla versione corrente"
            if valid
            else "storica: nuova revisione necessaria"
        )
        lines.extend(
            [
                f"- {review['reviewer_ref']}: {review['decision']} — {review['node_id']} ({status}). {review['reason']} Riferimento conferma: {review['confirmation_ref']}."
            ]
        )
    lines.extend(
        [
            "",
            "Le decisioni sono registrazioni di conferme fornite dal professionista. Il sistema locale non autentica l'identità del revisore, non firma e non autorizza depositi o invii. Una versione corrente non costituisce una conclusione professionale approvata.",
            "",
            f"Snapshot SHA-256: {record['content_sha256']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    """Read or update an existing managed client run; never choose an output root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if bool(args.request) == args.resume:
        parser.error("Choose --request or --resume")
    ledger, load_context = _dependencies()
    context = load_context(
        args.client_engagement,
        expected_workflow_id=WORKFLOW,
        input_paths=[args.request] if args.request else [],
        allowed_statuses=(
            ("running", "ready_for_review", "completed")
            if args.resume
            else ("running",)
        ),
    )
    if args.resume:
        history = ledger.load_workflow_history(
            Path(context["studio_client_folder"]["client_root"]),
            context["engagement_id"],
            WORKFLOW,
        )
        if not history:
            raise ValueError("No CNC snapshot exists for this engagement")
        logging.info("%s", render_record(history[-1]))
        return 0
    request = json.loads(args.request.read_text(encoding="utf-8"))
    record = apply_request(args.client_engagement, request)
    path = Path(context["output_dir"]) / f"cnc-revision-{record['revision']:06d}.md"
    rendered = render_record(record)
    if path.is_symlink() or (
        path.exists() and path.read_text(encoding="utf-8") != rendered
    ):
        raise ValueError(
            "Existing CNC memo differs; do not overwrite the prior artifact"
        )
    if not path.exists():
        with path.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    logging.info("Saved CNC revision %s: %s", record["revision"], path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
