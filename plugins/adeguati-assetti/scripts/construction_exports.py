"""Render the same manual snapshot to editable and readable local artifacts."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import tempfile
from pathlib import Path

from construction_core import digest, evaluate, manual_status, require, verify_snapshot

__all__ = ["export_manual", "render_case_memo", "save_snapshot"]

STATUS = {
    "draft": "Bozza da discutere",
    "professionally_reviewed": "Revisione professionale registrata; adozione non registrata",
    "adopted": "Adozione aziendale registrata; funzionamento da verificare nel periodo",
    "needs_review": "Da riesaminare dopo la modifica delle basi",
}


def write_once(path: Path, content: str) -> None:
    require(not path.is_symlink(), "Output must not be a symlink")
    if path.exists():
        require(path.read_text(encoding="utf-8") == content, "Existing output differs")
    else:
        with path.open("x", encoding="utf-8") as handle:
            path.chmod(0o600)
            handle.write(content)


def render_case_memo(state: dict) -> str:
    """Expose missingness, base versus professional judgment and original facts."""
    result = evaluate(state)
    lines = [
        f"# Costruzione degli assetti — {state['entity_name']}",
        f"Revisione {state['revision']}. Metodo {state['catalog']['methodology_version']} ({state['catalog']['status']}).",
        "Le decisioni sono dichiarazioni attribuite, non firme autenticate. Nessun indice certifica l’adeguatezza.",
        "## Criticità e limiti",
    ]
    for finding in result["critical_findings"]:
        lines.append(
            f"- {finding['observation']} — {finding['consequence']}. Priorità: {finding['priority_reason']}"
        )
    lines += [
        "## Copertura",
        f"Base: {json.dumps(result['base'], ensure_ascii=False)}",
        f"Giudizio professionale: {json.dumps(result['professional'], ensure_ascii=False)}",
        "Criteri ignoti: " + ", ".join(result["unknown_base_ids"]),
        "Esclusioni motivate e revisionate: " + ", ".join(result["excluded_ids"]),
    ]
    for row in result["rows"]:
        display = lambda value: "non determinabile" if value is None else f"{value}/4"
        lines += [
            f"## {row['id']} — {row['title']}",
            f"Base: {display(row['base'])}. Professionale: {display(row['effective'])}. Obiettivo: {display(row['target'])}.",
        ]
        assessment = state["assessments"].get(row["id"], {})
        lines.extend(
            str(assessment.get(key, ""))
            for key in (
                "rationale",
                "adequacy_judgment",
                "contradiction",
                "clarification_needed",
                "na_reason",
            )
        )
        if row["beyond_verified_evidence"]:
            lines.append(
                "Giudizio oltre le evidenze attualmente verificate; non prova adozione o funzionamento."
            )
        if row["decision"]:
            d = row["decision"]
            lines += [
                f"Rettifica: {row['decision_status']}; {d['rationale']}",
                f"Autore dichiarato: {d['created_by']}; {d['created_at']}. Rischio residuo: {d['residual_risk']}",
                f"Prossima verifica: {d['review_trigger']}",
            ]
        lines.append("Traccia: " + json.dumps(row["trace"], ensure_ascii=False))
    lines.append("## Risposte originali e sintesi")
    for row in state["answers"].values():
        lines.extend(
            [
                f"### {row['question']}",
                f"{row['speaker']} — {row['status']}",
                "\n".join("> " + x for x in row["original"].splitlines()),
                "Sintesi separata: " + row.get("summary", ""),
                "Allegati da acquisire: "
                + ", ".join(row.get("unresolved_attachment_refs", [])),
            ]
        )
    lines.append("## Manuali e cicli")
    for mid, manual in state["manuals"].items():
        lines.append(
            f"- {mid}: {STATUS[manual_status(state, mid)]}; versione {manual['manual_sha256']}"
        )
    for review in state["operation_reviews"].values():
        current = all(
            digest(state["controls"][cid]) == expected
            for cid, expected in review["control_sha256"].items()
        )
        lines.append(
            f"- Riesame {'corrente' if current else 'storico, controllo modificato: da riesaminare'} "
            f"limitato a {', '.join(review['control_ids'])}: {review['conclusion']}. {review['limitations']}"
        )
    lines.extend(
        [
            "## Prossimo passo",
            state["cursor"].get("next_step", "Da definire dalla valutazione del caso"),
        ]
    )
    return "\n\n".join(lines) + "\n"


def save_snapshot(state: dict, output: Path) -> Path:
    verify_snapshot(state)
    require(not output.is_symlink(), "Output directory must not be a symlink")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output / f"assetti-construction-{state['snapshot_sha256']}.json"
    write_once(
        path, json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    write_once(path.with_suffix(".md"), render_case_memo(state))
    return path


def _blocks(state: dict, manual_id: str) -> list[tuple[int, str]]:
    manual = state["manuals"][manual_id]
    blocks = [
        (0, "Manuale operativo degli assetti"),
        (1, state["entity_name"]),
        (2, STATUS[manual_status(state, manual_id)]),
        (2, manual["introduction"]),
        (1, "Perimetro e limiti"),
        (2, manual["limitations"]),
    ]
    for i, control in enumerate(manual["snapshot"]["controls"].values(), 1):
        blocks += [
            (1, f"Procedura {i}  {control['title']}"),
            (2, control["outcome"]),
            (2, "Rischio presidiato: " + control["risk"]),
            (
                2,
                f"Esegue: {control['owner']}. Decide: {control['decision_owner']}. Sostituto: {control['substitute']}. Ruoli: {control['role_status']}.",
            ),
            (
                2,
                f"Frequenza: {control['frequency']}. Tempi: {control['timing_status']}.",
            ),
            (2, "Dati in ingresso: " + control["inputs"]),
        ]
        blocks.extend((2, f"{j}. {step}") for j, step in enumerate(control["steps"], 1))
        blocks += [
            (2, "Risultato e destinatario: " + control["outputs"]),
            (2, "Eccezioni: " + control["exceptions"]),
            (2, "Tempo di risposta: " + control["response_time"]),
            (2, "Prova da conservare: " + control["execution_evidence"]),
            (2, "Archivio: " + control["archive"]),
            (2, "Registro da compilare: " + "; ".join(control["register_fields"])),
        ]
    blocks.append((1, "Piano di attuazione"))
    if not manual["snapshot"]["actions"]:
        blocks.append((2, "Nessuna azione ancora registrata."))
    for action in manual["snapshot"]["actions"].values():
        blocks += [
            (
                2,
                f"{action['proposal']} — {action['owner']} ({action['owner_status']}); {action['timing']} ({action['timing_status']}).",
            ),
            (2, "Completamento richiesto: " + action["completion_criterion"]),
        ]
    if manual["snapshot"]["objectives"]:
        blocks.append((1, "Come controlliamo la realizzazione degli obiettivi"))
        for objective in manual["snapshot"]["objectives"].values():
            blocks.append(
                (
                    2,
                    f"{objective['description']} — {objective['owner']} ({objective['owner_status']}); {objective['period']}.",
                )
            )
        for kpi in manual["snapshot"]["kpis"].values():
            blocks.append(
                (
                    2,
                    f"{kpi['definition']}. Formula: {kpi['formula']}; fonte: {', '.join(kpi['evidence_refs'])}; aggiorna: {kpi['data_owner']}; frequenza: {kpi['frequency']}; target: {kpi.get('target', 'da definire')} ({kpi['target_status']}).",
                )
            )
        for link in manual["snapshot"]["strategy_links"].values():
            blocks.append(
                (
                    2,
                    f"Ipotesi gestionale ({link['status']}): {link['hypothesis']}. {link['limitations']}",
                )
            )
    blocks += [
        (1, "Adozione e verifica del primo ciclo"),
        (
            2,
            "La preparazione di questo manuale non dimostra adozione o funzionamento. La decisione aziendale deve riferirsi a questa versione. Conservare per ogni ciclo prove, anomalie, destinatari e decisioni; concordare il perimetro del riesame.",
        ),
        (2, "Versione del documento: " + manual_id),
    ]
    return blocks


def export_manual(state: dict, manual_id: str, output: Path) -> Path:
    """Export all formats atomically from one frozen content snapshot."""
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    verify_snapshot(state)
    require(manual_id in state["manuals"], "Unknown manual")
    require(not output.is_symlink(), "Output directory must not be a symlink")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    export_id = digest({"snapshot": state["snapshot_sha256"], "manual_id": manual_id})
    target = output / f"manuale-{export_id}"
    require(not target.is_symlink(), "Manual output must not be a symlink")
    if target.exists():
        manifest = json.loads((target / "manifest.json").read_text())
        require(manifest["export_id"] == export_id, "Export identity mismatch")
        for name, expected in manifest["files"].items():
            file = target / name
            require(
                file.is_file() and not file.is_symlink() and file.parent == target,
                "Unsafe export path",
            )
            require(
                hashlib.sha256(file.read_bytes()).hexdigest() == expected,
                "Existing manual export changed",
            )
        return target
    blocks = _blocks(state, manual_id)
    with tempfile.TemporaryDirectory(prefix=".manual-", dir=output) as temporary:
        folder = Path(temporary)
        doc = Document()
        doc.sections[0].top_margin = Inches(0.8)
        doc.sections[0].bottom_margin = Inches(0.8)
        doc.styles["Normal"].font.name = "Arial"
        doc.styles["Normal"].font.size = Pt(10)
        doc.styles["Title"].font.color.rgb = RGBColor(0, 0, 0)
        for word_style in doc.styles:
            for border in word_style.element.findall(".//" + qn("w:pBdr")):
                border.getparent().remove(border)
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="ManualBody",
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                spaceAfter=8,
            )
        )
        flow, md = [], []
        for level, content in blocks:
            if level == 0:
                doc.add_paragraph(content, "Title")
                style = styles["Title"]
            elif level == 1:
                doc.add_heading(content, 1)
                style = styles["Heading1"]
            else:
                doc.add_paragraph(content)
                style = styles["ManualBody"]
            flow.extend(
                [
                    Paragraph(html.escape(content).replace("\n", "<br/>"), style),
                    Spacer(1, 3),
                ]
            )
            md.append(("# " if level == 0 else "## " if level == 1 else "") + content)
        doc.save(folder / "manuale.docx")
        SimpleDocTemplate(
            str(folder / "manuale.pdf"),
            pagesize=(21 * cm, 29.7 * cm),
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title="Manuale operativo degli assetti",
        ).build(flow)
        (folder / "manuale.md").write_text("\n\n".join(md) + "\n", encoding="utf-8")
        (folder / "manuale.json").write_text(
            json.dumps(state["manuals"][manual_id], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for i, control in enumerate(
            state["manuals"][manual_id]["snapshot"]["controls"].values(), 1
        ):
            with (folder / f"registro-{i:02}.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.writer(handle)
                # CSV formula prefixes are neutralized without changing the record.
                writer.writerow(
                    [
                        "'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v
                        for v in control["register_fields"]
                    ]
                )
        files = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.iterdir())
        }
        manifest = {
            "schema_version": "vera.assetti_manual_export.v1",
            "export_id": export_id,
            "case_id": state["case_id"],
            "snapshot_sha256": state["snapshot_sha256"],
            "manual_sha256": state["manuals"][manual_id]["manual_sha256"],
            "status": manual_status(state, manual_id),
            "files": files,
        }
        (folder / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for path in folder.iterdir():
            path.chmod(0o600)
        folder.rename(target)
    return target
