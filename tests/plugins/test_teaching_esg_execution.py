"""Run authored fictional ESG inputs through Archive and the actual foundation.

Operator decisions below are test simulations, never learner participation.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check
from tests.plugins.test_esg_foundation import load
from tests.plugins.test_teaching_kit_execution import ROOT, _complete_teaching_case

__all__ = []
WORKFLOW = "esg-reporting-assurance"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_esg_kit_preserves_sources_and_invalidates_dependent_work(
    tmp_path, monkeypatch, record_property, language, phase
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins/vera", {WORKFLOW}).render(
        WORKFLOW, language, tmp_path / "kit"
    )
    source = (
        Path(kit["course"]).parent
        / "files"
        / ("input" if phase == "demo" else "practice")
    )
    brief = source / f"brief-{language}.md"
    original = source / "energy.csv"
    update = source / "energy-update.csv"
    with original.open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["kwh"] == ("0" if phase == "demo" else "8")
    assert rows[1]["kwh"] == rows[2]["kwh"] == ""
    assert "unresolved" in brief.read_text()
    ledger = load(
        "esg_course_ledger", ROOT / "plugins/studio-archive/scripts/client_ledger.py"
    )
    esg = load("esg_course_core", ROOT / f"plugins/{WORKFLOW}/scripts/esg_case.py")
    (tmp_path / ".vera-onboarding-local-only").write_text(
        "Synthetic mechanical verification only\n"
    )
    client_root = tmp_path / "client"
    client_root.mkdir()
    client = "client_" + "c" * 24
    ledger.create_client_manifest(client_root, client)
    engagement = ledger.create_engagement(
        client_root, client, "Fictional ESG teaching"
    )["engagement_id"]
    receipts = [
        ledger.import_document(client_root, client, engagement, p, "source")["receipt"]
        for p in (brief, original)
    ]
    version = json.loads((ROOT / "plugins/vera/.codex-plugin/plugin.json").read_text())[
        "version"
    ]

    def start_run(inputs):
        prepared = ledger.prepare_run(
            client_root, client, engagement, WORKFLOW, version, input_ids=inputs
        )
        return ledger.start_run(client_root, engagement, prepared["run"]["run_id"])

    run = start_run([r["input_id"] for r in receipts])
    context = Path(run["context_path"])
    start = dict(
        case_id=f"fictional-{phase}",
        idempotency_key="case",
        previous_context=None,
        record=dict(
            service="preparation",
            reporting_basis="unresolved",
            period=dict(start="2026-01-01", end="2026-12-31"),
            jurisdiction="IT",
            framework_version=None,
            assurance_level="not_applicable",
            synthetic=True,
        ),
    )
    esg.execute(context, "start_case", start)

    def mutation(command, request):
        return esg.execute(
            context,
            command,
            {
                "expected_state_sha256": esg.resume_case(context)["state_sha256"],
                **request,
            },
        )

    def bind(identity, row, status, value, receipt, key):
        return mutation(
            "bind_evidence",
            dict(
                id=identity,
                idempotency_key=key,
                input_id=receipt["input_id"],
                locator=dict(row=row, column="kwh"),
                observation=dict(
                    status=status,
                    value=value,
                    unit="kWh",
                    rationale="Test interpretation of declared fictional source; excluded site scope is stated in the brief",
                    disclosure_id=None,
                    metric_id=None,
                ),
            ),
        )

    energy = bind("energy", 1, "observed", rows[0]["kwh"], receipts[1], "energy-v1")
    missing = bind("prior-year", 2, "not_available", None, receipts[1], "missing")
    excluded = bind("excluded-site", 3, "not_applicable", None, receipts[1], "excluded")
    decision = mutation(
        "record_decision",
        dict(
            id="mapping-review",
            idempotency_key="review",
            dependencies=[energy["reference"]],
            record=dict(
                type="scope",
                decided_by="SYNTHETIC REGRESSION OPERATOR — not the learner",
                decided_on="2026-10-01",
                outcome="approved",
                decision="Simulated acceptance of this exact fictional cell interpretation only",
                rationale="No professional or framework qualification; test fixture simulation",
            ),
        ),
    )
    prose = {
        "it": (
            "Memo fittizio parziale",
            "Dato dichiarato",
            "Anno precedente mancante; sito escluso non applicabile. Nessuna conclusione di conformità o assurance.",
        ),
        "en": (
            "Fictional partial memo",
            "Declared value",
            "Prior year missing; excluded site not applicable. No compliance or assurance conclusion.",
        ),
        "fr": (
            "Note fictive partielle",
            "Valeur déclarée",
            "Année précédente manquante ; site exclu non applicable. Aucune conclusion de conformité ou assurance.",
        ),
        "de": (
            "Fiktiver Teilvermerk",
            "Erklärter Wert",
            "Vorjahr fehlt; ausgeschlossener Standort nicht anwendbar. Keine Konformitäts- oder Prüfungsaussage.",
        ),
        "es": (
            "Memo ficticio parcial",
            "Valor declarado",
            "Año anterior ausente; centro excluido no aplicable. Ninguna conclusión de conformidad o assurance.",
        ),
    }[language]
    artifact = mutation(
        "build_deliverables",
        dict(
            id="memo",
            idempotency_key="draft",
            claim="partial_draft",
            title=prose[0],
            content=f"{prose[1]}: {rows[0]['kwh']} kWh. {prose[2]}",
            dependencies=[
                decision["reference"],
                missing["reference"],
                excluded["reference"],
            ],
        ),
    )
    first_output = Path(run["output_dir"])
    memo = next(first_output.glob("esg-draft-*.md"))
    assert f"{rows[0]['kwh']} kWh" in memo.read_text()
    assert "PARTIAL FOUNDATION DRAFT" in memo.read_text()
    before = esg.resume_case(context)
    first_bytes = {p: p.read_bytes() for p in first_output.glob("esg*") if p.is_file()}
    (first_output / "codex_run_review.md").write_text(
        prose[2]
        + "\nSynthetic test operator only; no learner approval or host model reads.\n"
    )
    _complete_teaching_case(run, client_root)
    old_context = context
    updated = ledger.import_document(client_root, client, engagement, update, "source")[
        "receipt"
    ]
    successor = start_run([r["input_id"] for r in receipts] + [updated["input_id"]])
    context = Path(successor["context_path"])
    esg.execute(context, "start_case", {**start, "previous_context": str(old_context)})
    with update.open() as stream:
        update_rows = list(csv.DictReader(stream))
    latest = bind("energy", 1, "observed", update_rows[0]["kwh"], updated, "energy-v2")
    after = esg.resume_case(context)
    objects = {
        (x["reference"]["kind"], x["reference"]["id"], x["reference"]["version"]): x
        for x in after["objects"]
    }
    assert objects[("evidence", "energy", 1)]["current"] is False
    assert objects[("decision", "mapping-review", 1)]["current"] is False
    assert objects[("artifact", "memo", 1)]["current"] is False
    assert objects[("evidence", "energy", 2)]["current"] is True
    assert objects[("evidence", "energy", 2)]["record"]["observation"]["value"] == (
        "15" if phase == "demo" else "12"
    )
    assert (
        objects[("evidence", "prior-year", 1)]["record"]["observation"]["status"]
        == "not_available"
    )
    assert (
        objects[("evidence", "excluded-site", 1)]["record"]["observation"]["status"]
        == "not_applicable"
    )
    assert (
        objects[("evidence", "prior-year", 1)]["record"]["observation"]["value"] is None
    )
    assert (
        objects[("evidence", "excluded-site", 1)]["record"]["observation"]["value"]
        is None
    )
    assert objects[("evidence", "prior-year", 1)]["current"] is True
    assert objects[("evidence", "excluded-site", 1)]["current"] is True
    assert esg.resume_case(old_context) == before
    assert {p: p.read_bytes() for p in first_bytes} == first_bytes
    # Current partial draft does not reuse the obsolete approval.
    mutation(
        "build_deliverables",
        dict(
            id="updated-memo",
            idempotency_key="updated-draft",
            claim="partial_draft",
            title=prose[0],
            content=f"{prose[1]}: {update_rows[0]['kwh']} kWh. {prose[2]} Review pending.",
            dependencies=[
                latest["reference"],
                missing["reference"],
                excluded["reference"],
            ],
        ),
    )
    output = Path(successor["output_dir"])
    (output / "codex_run_review.md").write_text(
        prose[2]
        + "\nPrevious decision and draft outdated. New professional decision pending.\n"
    )
    _complete_teaching_case(successor, client_root)
    assert digest(original) == receipts[1]["sha256"]
    assert digest(update) == updated["sha256"]
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow=WORKFLOW,
        language=language,
        phase=phase,
    )
