"""Readable rendering of recorded advisory judgments; no semantic classification."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

__all__ = ["render_package"]

_LANGUAGES = ("en", "it", "fr", "de", "es")
_WORDS = {
    "title": (
        "Advisory document review",
        "Revisione del documento di consulenza",
        "Revue du document de conseil",
        "Prüfung des Beratungsdokuments",
        "Revisión del documento de consultoría",
    ),
    "readiness": (
        "Delivery readiness",
        "Utilizzabilità del documento",
        "État de préparation du document",
        "Verwendbarkeit des Dokuments",
        "Estado de uso del documento",
    ),
    "original": ("Original", "Originale", "Original", "Original", "Original"),
    "sources": (
        "Selected sources",
        "Fonti selezionate",
        "Sources sélectionnées",
        "Ausgewählte Quellen",
        "Fuentes seleccionadas",
    ),
    "findings": (
        "Main findings and proposed corrections",
        "Rilievi principali e correzioni proposte",
        "Constats principaux et corrections proposées",
        "Wesentliche Befunde und vorgeschlagene Korrekturen",
        "Hallazgos principales y correcciones propuestas",
    ),
    "action": (
        "Proposed correction",
        "Correzione proposta",
        "Correction proposée",
        "Vorgeschlagene Korrektur",
        "Corrección propuesta",
    ),
    "references": ("Sources", "Fonti", "Sources", "Quellen", "Fuentes"),
    "dimensions": (
        "Review dimensions",
        "Aspetti esaminati",
        "Dimensions examinées",
        "Geprüfte Aspekte",
        "Aspectos examinados",
    ),
    "chains": (
        "Claims compared with evidence",
        "Affermazioni confrontate con le fonti",
        "Affirmations comparées aux sources",
        "Mit Belegen abgeglichene Aussagen",
        "Afirmaciones contrastadas con fuentes",
    ),
    "provenance": (
        "Provenance mode",
        "Tipo di ricostruzione delle fonti",
        "Mode de traçabilité",
        "Art des Herkunftsnachweises",
        "Modo de trazabilidad",
    ),
    "tracked": (
        "Recorded claim",
        "Affermazione registrata",
        "Affirmation enregistrée",
        "Erfasste Aussage",
        "Afirmación registrada",
    ),
    "untracked": (
        "Reconstructed claim",
        "Affermazione ricostruita",
        "Affirmation reconstituée",
        "Rekonstruierte Aussage",
        "Afirmación reconstruida",
    ),
    "location": (
        "Passage in the document",
        "Passaggio nel documento",
        "Passage du document",
        "Textstelle im Dokument",
        "Pasaje del documento",
    ),
    "support": (
        "Evidence support",
        "Supporto delle fonti",
        "Soutien des sources",
        "Beleglage",
        "Respaldo de las fuentes",
    ),
    "reasoning": (
        "Reasoning",
        "Ragionamento",
        "Raisonnement",
        "Begründung",
        "Razonamiento",
    ),
    "analysis": ("Assessment", "Valutazione", "Évaluation", "Bewertung", "Valoración"),
    "recheck": (
        "Further check",
        "Ulteriore verifica",
        "Vérification complémentaire",
        "Weitere Prüfung",
        "Comprobación adicional",
    ),
    "resolution": (
        "Resolution",
        "Risoluzione",
        "Résolution",
        "Klärungsstand",
        "Resolución",
    ),
    "checks": (
        "Format-specific checks",
        "Controlli del formato",
        "Contrôles du format",
        "Formatspezifische Prüfungen",
        "Comprobaciones del formato",
    ),
    "correction": ("Correction", "Correzione", "Correction", "Korrektur", "Corrección"),
    "state": ("Status", "Stato", "État", "Status", "Estado"),
    "residual_heading": (
        "Remaining uncertainty and professional review",
        "Incertezze residue e revisione professionale",
        "Incertitudes résiduelles et revue professionnelle",
        "Verbleibende Unsicherheit und fachliche Prüfung",
        "Incertidumbre residual y revisión profesional",
    ),
    "residual": (
        "Remaining uncertainty",
        "Incertezza residua",
        "Incertitude résiduelle",
        "Verbleibende Unsicherheit",
        "Incertidumbre residual",
    ),
    "professional": (
        "Professional review",
        "Revisione professionale",
        "Revue professionnelle",
        "Fachliche Prüfung",
        "Revisión profesional",
    ),
    "records": (
        "Review record and file identities",
        "Registro della revisione e identità dei file",
        "Dossier de revue et identité des fichiers",
        "Prüfaufzeichnung und Dateiidentitäten",
        "Registro de revisión e identidad de archivos",
    ),
    "complete": (
        "Record complete",
        "Registro completo",
        "Dossier complet",
        "Aufzeichnung vollständig",
        "Registro completo",
    ),
    "mechanical": (
        "Record completeness checks consistency and file identity; it does not approve the document or establish that its claims are true.",
        "La completezza del registro verifica coerenza e identità dei file; non approva il documento né dimostra la verità delle sue affermazioni.",
        "La complétude du dossier vérifie cohérence et identité des fichiers ; elle n'approuve pas le document et ne démontre pas la véracité de ses affirmations.",
        "Die Vollständigkeit prüft Konsistenz und Dateiidentität; sie genehmigt das Dokument nicht und belegt nicht die Wahrheit seiner Aussagen.",
        "La integridad del registro comprueba coherencia e identidad de archivos; no aprueba el documento ni demuestra la veracidad de sus afirmaciones.",
    ),
    "original_hash": (
        "Original SHA-256",
        "SHA-256 dell'originale",
        "SHA-256 de l'original",
        "SHA-256 des Originals",
        "SHA-256 del original",
    ),
    "contract_hash": (
        "Contract SHA-256",
        "SHA-256 dell'incarico",
        "SHA-256 de la mission",
        "SHA-256 des Auftrags",
        "SHA-256 del encargo",
    ),
    "errors": (
        "Mechanical audit errors",
        "Errori della verifica formale",
        "Erreurs de contrôle formel",
        "Fehler der formalen Prüfung",
        "Errores de comprobación formal",
    ),
    "no_findings": (
        "No individual findings recorded.",
        "Nessun rilievo individuale registrato.",
        "Aucun constat individuel enregistré.",
        "Keine einzelnen Befunde erfasst.",
        "No hay hallazgos individuales registrados.",
    ),
    "no_chains": (
        "No claim assessment recorded.",
        "Nessuna valutazione delle affermazioni registrata.",
        "Aucune évaluation des affirmations enregistrée.",
        "Keine Aussagenbewertung erfasst.",
        "No hay valoración de afirmaciones registrada.",
    ),
    "no_checks": (
        "No format-specific checks recorded.",
        "Nessun controllo specifico del formato registrato.",
        "Aucun contrôle spécifique du format enregistré.",
        "Keine formatspezifischen Prüfungen erfasst.",
        "No hay comprobaciones específicas del formato registradas.",
    ),
    "none": (
        "None recorded.",
        "Nessuna voce registrata.",
        "Aucun élément enregistré.",
        "Keine Einträge erfasst.",
        "No hay elementos registrados.",
    ),
    "missing": (
        "not recorded",
        "non registrato",
        "non renseigné",
        "nicht erfasst",
        "no registrado",
    ),
    "yes": ("yes", "sì", "oui", "ja", "sí"),
    "no": ("no", "no", "non", "nein", "no"),
    "contract_conformance": (
        "Fit with the assignment",
        "Rispondenza all'incarico",
        "Conformité à la mission",
        "Übereinstimmung mit dem Auftrag",
        "Adecuación al encargo",
    ),
    "factual_source_support": (
        "Facts and source support",
        "Fatti e supporto delle fonti",
        "Faits et soutien des sources",
        "Fakten und Quellenbelege",
        "Hechos y respaldo de fuentes",
    ),
    "calculations_data_provenance": (
        "Calculations and data provenance",
        "Calcoli e provenienza dei dati",
        "Calculs et provenance des données",
        "Berechnungen und Datenherkunft",
        "Cálculos y procedencia de datos",
    ),
    "reasoning_assumptions": (
        "Reasoning and assumptions",
        "Ragionamento e ipotesi",
        "Raisonnement et hypothèses",
        "Begründung und Annahmen",
        "Razonamiento e hipótesis",
    ),
    "contradictions_missing_evidence": (
        "Contradictions and missing evidence",
        "Contraddizioni ed evidenze mancanti",
        "Contradictions et éléments manquants",
        "Widersprüche und fehlende Belege",
        "Contradicciones y evidencias ausentes",
    ),
    "recommendation_evidence_decision_fit": (
        "Recommendation and decision fit",
        "Raccomandazione e decisione",
        "Recommandation et décision",
        "Empfehlung und Entscheidung",
        "Recomendación y decisión",
    ),
    "professional_judgement_boundaries": (
        "Professional judgement",
        "Giudizio professionale",
        "Jugement professionnel",
        "Fachliches Urteil",
        "Juicio profesional",
    ),
    "correction_needs": (
        "Necessary corrections",
        "Correzioni necessarie",
        "Corrections nécessaires",
        "Erforderliche Korrekturen",
        "Correcciones necesarias",
    ),
    "residual_uncertainty": (
        "Residual uncertainty",
        "Incertezza residua",
        "Incertitude résiduelle",
        "Verbleibende Unsicherheit",
        "Incertidumbre residual",
    ),
    "delivery_readiness": (
        "Readiness for use",
        "Prontezza per l'utilizzo",
        "Préparation à l'utilisation",
        "Bereitschaft zur Verwendung",
        "Preparación para el uso",
    ),
    "conforms": ("conforms", "conforme", "conforme", "erfüllt", "conforme"),
    "partially_conforms": (
        "partly conforms",
        "parzialmente conforme",
        "partiellement conforme",
        "teilweise erfüllt",
        "parcialmente conforme",
    ),
    "does_not_conform": (
        "does not conform",
        "non conforme",
        "non conforme",
        "nicht erfüllt",
        "no conforme",
    ),
    "contradicted": (
        "contradicted",
        "contraddetto",
        "contredit",
        "widersprochen",
        "contradicha",
    ),
    "uncertain": ("uncertain", "incerto", "incertain", "ungewiss", "incierto"),
    "judgment_required": (
        "judgement required",
        "richiede giudizio",
        "jugement requis",
        "Beurteilung erforderlich",
        "requiere juicio",
    ),
    "not_applicable": (
        "not applicable",
        "non applicabile",
        "sans objet",
        "nicht anwendbar",
        "no aplicable",
    ),
    "not_needed": (
        "not needed",
        "non necessaria",
        "non nécessaire",
        "nicht nötig",
        "no necesaria",
    ),
    "proposed": ("proposed", "proposta", "proposée", "vorgeschlagen", "propuesta"),
    "completed": ("completed", "completata", "terminée", "abgeschlossen", "completada"),
    "blocked": ("blocked", "bloccato", "bloqué", "blockiert", "bloqueado"),
    "professional_review_required": (
        "professional review required",
        "richiede revisione professionale",
        "revue professionnelle requise",
        "fachliche Prüfung erforderlich",
        "requiere revisión profesional",
    ),
    "passed": ("passed", "superato", "réussi", "bestanden", "superada"),
    "issues_found": (
        "issues found",
        "problemi rilevati",
        "problèmes constatés",
        "Probleme festgestellt",
        "problemas detectados",
    ),
    "not_run": (
        "not run",
        "non eseguito",
        "non exécuté",
        "nicht ausgeführt",
        "no ejecutada",
    ),
    "ready": ("ready", "pronto", "prêt", "bereit", "listo"),
    "ready_with_residual_uncertainty": (
        "ready with residual uncertainty",
        "pronto con incertezze residue",
        "prêt avec incertitudes résiduelles",
        "bereit mit verbleibender Unsicherheit",
        "listo con incertidumbre residual",
    ),
    "not_ready": ("not ready", "non pronto", "non prêt", "nicht bereit", "no listo"),
    "approved": ("approved", "approvato", "approuvé", "genehmigt", "aprobado"),
    "pending": ("pending", "in attesa", "en attente", "ausstehend", "pendiente"),
    "not_required": (
        "not required",
        "non richiesto",
        "non requis",
        "nicht erforderlich",
        "no requerido",
    ),
    "required": ("required", "necessaria", "nécessaire", "erforderlich", "necesaria"),
    "generation_time": (
        "recorded during creation",
        "registrata durante la redazione",
        "enregistrée pendant la rédaction",
        "bei der Erstellung erfasst",
        "registrada durante la elaboración",
    ),
    "matched_support": (
        "matched to available sources; original drafting provenance unavailable",
        "confronto con le fonti disponibili; provenienza della redazione originale non disponibile",
        "rapprochement avec les sources disponibles ; provenance de la rédaction originale indisponible",
        "Abgleich mit verfügbaren Quellen; ursprüngliche Entstehung nicht belegt",
        "contraste con las fuentes disponibles; procedencia de la redacción original no disponible",
    ),
    "adequate": ("adequate", "adeguato", "adéquat", "ausreichend", "adecuado"),
    "partial": ("partial", "parziale", "partiel", "teilweise", "parcial"),
    "unsupported": (
        "unsupported",
        "non supportato",
        "non étayé",
        "nicht belegt",
        "sin respaldo",
    ),
    "sound": ("sound", "fondato", "fondé", "schlüssig", "fundado"),
    "gap": ("gap", "lacuna", "lacune", "Lücke", "laguna"),
    "no_change": (
        "no change",
        "nessuna modifica",
        "aucune modification",
        "keine Änderung",
        "sin cambios",
    ),
    "corrected": ("corrected", "corretto", "corrigé", "korrigiert", "corregida"),
    "removed": ("removed", "rimosso", "retiré", "entfernt", "retirada"),
    "qualified": ("qualified", "circoscritto", "nuancé", "eingeschränkt", "matizada"),
}


def render_package(
    inventory: dict[str, Any],
    review: dict[str, Any],
    audit: dict[str, Any],
    source_inventory: dict[str, Any],
    dimension_keys: tuple[str, ...],
) -> str:
    """Present recorded meanings and references without changing their judgments."""
    language = review.get("language", "en")
    index = _LANGUAGES.index(language) if language in _LANGUAGES else 0
    words = {key: values[index] for key, values in _WORDS.items()}

    def label(value: Any) -> str:
        return words.get(str(value), str(value))

    def mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def items(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    def file_link(path: str, name: str) -> str:
        name = name.replace("[", r"\[").replace("]", r"\]")
        return f"[{name}]({quote(path, safe='/:')})" if path else name

    sources = {
        str(source.get("id")): source
        for source in items(source_inventory.get("sources"))
        if isinstance(source, dict) and source.get("id")
    }

    def references(values: Any) -> str:
        links = []
        for value in items(values):
            source = sources.get(str(value), {})
            path = str(source.get("path", ""))
            name = str(source.get("name", value))
            links.append(file_link(path, name))
        return ", ".join(links) or words["missing"]

    overall = mapping(review.get("overall_assessment"))
    lines = [
        f"# {words['title']}",
        "",
        f"**{words['readiness']}: {label(audit['effective_delivery_readiness'])}**",
        "",
        str(overall.get("analysis", words["missing"])),
        "",
    ]
    lines.extend(
        f"- {condition}"
        for condition in items(
            mapping(review.get("delivery_readiness")).get("conditions")
        )
    )
    lines.extend(
        [
            "",
            f"{words['original']}: {file_link(str(inventory.get('source_path', '')), str(inventory.get('source_name', words['missing'])))}",
            "",
        ]
    )
    if sources:
        lines.extend([f"## {words['sources']}", ""])
        lines.extend(f"- {references([key])}" for key in sources)
    if audit.get("errors"):
        lines.extend(["", f"## {words['errors']}", ""])
        lines.extend(f"- {error}" for error in audit["errors"])
    lines.extend(["", f"## {words['findings']}", ""])
    findings = [
        item for item in items(review.get("findings")) if isinstance(item, dict)
    ]
    for finding in findings:
        lines.extend(
            [
                f"- **{label(finding.get('dimension', 'missing'))}:** {finding.get('finding', '')}",
                f"  - {words['action']}: {finding.get('correction_action', words['missing'])}",
                f"  - {words['references']}: {references(finding.get('evidence_refs'))}",
            ]
        )
    if not findings:
        lines.append(f"- {words['no_findings']}")
    lines.extend(["", f"## {words['chains']}", ""])
    lineage = mapping(review.get("lineage_review"))
    lines.extend(
        [
            f"{words['provenance']}: {label(lineage.get('provenance_mode', 'missing'))}",
            "",
        ]
    )
    chains = [
        (words[label_key], item)
        for field, label_key in (
            ("chain_assessments", "tracked"),
            ("untracked_material_claims", "untracked"),
        )
        for item in items(lineage.get(field))
        if isinstance(item, dict)
    ]
    if not chains:
        lines.append(f"- {words['no_chains']}")
    for kind, item in chains:
        recheck = mapping(item.get("recheck"))
        resolution = mapping(item.get("resolution"))
        lines.extend(
            [
                f"### {kind}: {item.get('claim_id') or item.get('id') or words['missing']}",
                "",
                str(item.get("statement", "")),
                "",
                f"- {words['location']}: {'; '.join(str(value) for value in items(item.get('deliverable_locations'))) or words['missing']}",
                f"- {words['references']}: {references(item.get('evidence_ids'))}",
                f"- {words['support']}: {label(item.get('support_status', 'missing'))}; {words['reasoning']}: {label(item.get('reasoning_status', 'missing'))}.",
                f"- {words['analysis']}: {item.get('analysis', words['missing'])}",
                f"- {words['recheck']}: {label(recheck.get('status', 'missing'))}. {recheck.get('analysis', '')}",
                f"- {words['resolution']}: {label(resolution.get('status', 'missing'))}. {resolution.get('explanation', '')}",
                "",
            ]
        )
    lines.extend([f"## {words['dimensions']}", ""])
    dimensions = mapping(review.get("dimension_reviews"))
    for dimension in dimension_keys:
        record = mapping(dimensions.get(dimension))
        lines.append(
            f"- **{label(dimension)}** — {label(record.get('status', 'missing'))}: {record.get('analysis', words['missing'])}"
        )
    lines.extend(["", f"## {words['checks']}", ""])
    checks = [
        item
        for item in items(review.get("format_specific_checks"))
        if isinstance(item, dict)
    ]
    for check in checks:
        lines.append(
            f"- **{check.get('workflow', words['missing'])}** — {label(check.get('status', 'missing'))}: {check.get('analysis', '')}"
        )
    if not checks:
        lines.append(f"- {words['no_checks']}")
    correction = mapping(review.get("correction"))
    lines.extend(
        [
            "",
            f"## {words['correction']}",
            "",
            f"{words['state']}: {label(correction.get('status', 'missing'))}",
            "",
            str(correction.get("summary", words["missing"])),
            "",
            f"## {words['residual_heading']}",
            "",
        ]
    )
    residual = items(overall.get("residual_uncertainties"))
    professional = items(overall.get("professional_review_items"))
    lines.extend(f"- {words['residual']}: {value}" for value in residual)
    lines.extend(f"- {words['professional']}: {value}" for value in professional)
    if not residual and not professional:
        lines.append(f"- {words['none']}")
    lines.extend(
        [
            "",
            f"## {words['records']}",
            "",
            f"{words['complete']}: {words['yes'] if audit['record_complete'] else words['no']}",
            "",
            words["mechanical"],
            "",
            f"{words['original_hash']}: {inventory.get('source_sha256', words['missing'])}",
            f"{words['contract_hash']}: {inventory.get('advisory_contract_sha256', words['missing'])}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
