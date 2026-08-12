"""Build the public privacy register from canonical product manifests."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = ["get_public_privacy_register"]


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = "https://github.com/fabioannovazzi/app_files/blob/main"


_ITALIAN_WORKFLOW_NAMES = {
    "archive-organization": "Organizzazione dell’archivio",
    "apertura-pratica": "Apertura pratica",
    "attribute-reporting": "Analisi degli attributi retail",
    "audit-reconciliation": "Riconciliazione di revisione",
    "bandi-agevolazioni": "Bandi e agevolazioni",
    "bilancio-xbrl-it": "Bilancio XBRL italiano",
    "brand-fit": "Coerenza della presenza di marca",
    "check-entries": "Verifica delle registrazioni",
    "claim-basis-map": "Mappa delle basi informative",
    "clara": "Clara",
    "client-file-preparation": "Preparazione del fascicolo cliente",
    "comunicazione-professionale": "Comunicazione professionale",
    "concordato-plan-review": "Revisione del piano di concordato",
    "deck-correction": "Correzione di presentazioni",
    "deep-research-validator": "Validazione della ricerca approfondita",
    "financial-analysis": "Analisi finanziaria",
    "html-deck": "Presentazione HTML",
    "interview": "Intervista",
    "journal-bank-reconciliation": "Riconciliazione contabilità-banca",
    "journal-sampling": "Campionamento delle registrazioni contabili",
    "new-client": "Nuovo cliente",
    "presenza-digitale-studio": "Presenza digitale dello studio",
    "previdenza-inps": "Previdenza INPS",
    "prompt-optimizer": "Ottimizzazione della richiesta",
    "registro-imprese-sari": "Registro Imprese e SARI",
    "report-builder": "Costruzione del report",
    "reporting-engine": "Analisi e reporting",
    "sales-plan": "Piano commerciale",
    "studio-archive": "Archivio dello studio",
    "transcribe": "Trascrizione",
}


_COPY = {
    "en": {
        "eyebrow": "Public function register",
        "title": "Check the boundary of each function.",
        "intro": (
            "Choose a Vera, Clara or Lucia function to see what the selected model may read, "
            "which additional destinations can be used, and whether a Mparanza-hosted "
            "service is part of the function."
        ),
        "assurance_title": "What the register verifies",
        "assurance_body": (
            "Release checks require one record for every registered workflow and shared "
            "service, validate its structure, and detect changes to its reviewed source code."
        ),
        "limits_title": "What it does not do",
        "limits_body": (
            "The register does not inspect customer files at runtime, trace every outbound "
            "request, or act as a network firewall. It records reviewed design boundaries "
            "and the concrete controls declared in source."
        ),
        "jump_label": "Open the function register",
        "search_label": "Find a function or destination",
        "search_placeholder": "For example: journal, INPS, interview…",
        "result_singular": "entry shown",
        "result_plural": "entries shown",
        "no_results": "No function or service matches this search.",
        "model_heading": "Selected model account",
        "local_heading": "Local workspace",
        "local_note": (
            "Source files, helper execution, and outputs can remain in the selected "
            "workspace. The technical register does not enumerate every local operation; "
            "the model and external boundaries are stated separately below."
        ),
        "model_intro_vera": (
            "Real case data needed for the work may enter the model context of the "
            "firm’s selected Codex or Cowork account."
        ),
        "model_intro_clara": (
            "Real professional data needed for the work may enter the model context "
            "of the user’s selected ChatGPT or Codex account."
        ),
        "model_intro_lucia": (
            "Real client, matter and law-firm data needed for the work may enter the "
            "model context of the firm’s selected Codex or Cowork account."
        ),
        "data_classes": "Information the model may use",
        "purpose": "Purpose",
        "content": "Information",
        "mparanza_heading": "Mparanza-hosted services",
        "mparanza_none": "No Mparanza-hosted service specific to this function is declared.",
        "mparanza_used": "This function can use a separately documented Mparanza service.",
        "other_heading": "Other external destinations",
        "other_none": "No additional external destination is declared for this function.",
        "optional": "Optional route",
        "automatic": "Automatic route",
        "chosen": "Used when selected",
        "reviewed": "Boundary reviewed",
        "source": "Inspect the technical record",
        "canonical_note": (
            "Purposes and information classes below reproduce the reviewed technical "
            "record in English. Interface explanations are localized."
        ),
        "services_eyebrow": "Service-level routes",
        "services_title": "What reaches hosted and external services.",
        "services_intro": (
            "These records describe shared technical and hosted routes separately from "
            "ordinary model work. Expand a service to see its provider, what is sent, "
            "and what the reviewed source says about retention."
        ),
        "used_by": "Used by",
        "provider": "Provider or recipients",
        "sent": "Information sent",
        "returned": "Information returned",
        "when": "When",
        "retention": "Retention and deletion",
        "access": "Access arrangement",
        "shared_service": "Shared technical service",
        "shared_service_note": (
            "Shared Vera services are product-level routes rather than one professional "
            "function. The provider below may be Mparanza or a separate external service."
        ),
        "register_note": (
            "This register is a reviewed engineering record, not a live traffic monitor "
            "or runtime firewall. It is not a DPIA, legal advice, or proof of GDPR "
            "compliance."
        ),
    },
    "it": {
        "eyebrow": "Registro pubblico delle funzioni",
        "title": "Controlla il confine di ogni funzione.",
        "intro": (
            "Scegli una funzione di Vera, Clara o Lucia per vedere che cosa può leggere il "
            "modello selezionato, quali destinazioni aggiuntive può usare e se interviene "
            "un servizio hosted da Mparanza."
        ),
        "assurance_title": "Che cosa verifica il registro",
        "assurance_body": (
            "I controlli di rilascio richiedono un record per ogni workflow e servizio "
            "condiviso registrato, ne convalidano la struttura e rilevano le modifiche "
            "al codice sorgente riesaminato."
        ),
        "limits_title": "Che cosa non fa",
        "limits_body": (
            "Il registro non ispeziona i file dei clienti durante l'esecuzione, non "
            "traccia ogni richiesta in uscita e non opera come firewall di rete. Registra "
            "i confini tecnici riesaminati e i controlli concreti dichiarati nel codice."
        ),
        "jump_label": "Apri il registro delle funzioni",
        "search_label": "Cerca una funzione o destinazione",
        "search_placeholder": "Per esempio: giornale, INPS, intervista…",
        "result_singular": "voce visibile",
        "result_plural": "voci visibili",
        "no_results": "Nessuna funzione o servizio corrisponde alla ricerca.",
        "model_heading": "Account del modello selezionato",
        "local_heading": "Workspace locale",
        "local_note": (
            "File sorgente, processi di supporto e risultati possono restare nel workspace "
            "selezionato. Il registro tecnico non enumera ogni operazione locale; il "
            "contesto del modello e le destinazioni esterne sono indicati separatamente."
        ),
        "model_intro_vera": (
            "I dati reali del caso necessari al lavoro possono entrare nel contesto del "
            "modello dell’account Codex o Cowork scelto dallo studio."
        ),
        "model_intro_clara": (
            "I dati professionali reali necessari al lavoro possono entrare nel contesto "
            "del modello dell’account ChatGPT o Codex scelto dall’utente."
        ),
        "model_intro_lucia": (
            "I dati reali del cliente, della pratica e dello studio legale necessari al "
            "lavoro possono entrare nel contesto del modello dell’account Codex o "
            "Cowork scelto dallo studio."
        ),
        "data_classes": "Informazioni che il modello può usare",
        "purpose": "Finalità",
        "content": "Informazioni",
        "mparanza_heading": "Servizi hosted da Mparanza",
        "mparanza_none": "Non è dichiarato un servizio hosted da Mparanza specifico per questa funzione.",
        "mparanza_used": "Questa funzione può usare un servizio Mparanza documentato separatamente.",
        "other_heading": "Altre destinazioni esterne",
        "other_none": "Non è dichiarata un’altra destinazione esterna per questa funzione.",
        "optional": "Percorso facoltativo",
        "automatic": "Percorso automatico",
        "chosen": "Usato quando selezionato",
        "reviewed": "Confine riesaminato",
        "source": "Esamina il registro tecnico",
        "canonical_note": (
            "Le finalità e le classi di informazioni riportate sotto riproducono in "
            "inglese il registro tecnico riesaminato. Le spiegazioni dell’interfaccia "
            "sono in italiano."
        ),
        "services_eyebrow": "Percorsi a livello di servizio",
        "services_title": "Che cosa raggiunge servizi hosted ed esterni.",
        "services_intro": (
            "Questi record descrivono i percorsi tecnici condivisi e hosted separatamente "
            "dal normale lavoro del modello. Apri un servizio per vedere il fornitore, "
            "che cosa viene inviato e che cosa stabilisce il codice riesaminato sulla "
            "conservazione."
        ),
        "used_by": "Usato da",
        "provider": "Fornitore o destinatari",
        "sent": "Informazioni inviate",
        "returned": "Informazioni restituite",
        "when": "Quando",
        "retention": "Conservazione e cancellazione",
        "access": "Modalità di accesso",
        "shared_service": "Servizio tecnico condiviso",
        "shared_service_note": (
            "I servizi condivisi di Vera operano a livello di prodotto, non di una sola "
            "funzione professionale. Il fornitore indicato sotto può essere Mparanza o "
            "un servizio esterno distinto."
        ),
        "register_note": (
            "Il registro è un record tecnico riesaminato, non un monitor del traffico in "
            "tempo reale né un firewall di runtime. Non è una DPIA, un parere legale o "
            "una prova di conformità al GDPR."
        ),
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Privacy manifest must contain an object: {path}")
    return payload


def _localized_name(identifier: str, display_name: str, lang: str) -> str:
    if lang == "it":
        return _ITALIAN_WORKFLOW_NAMES.get(identifier, display_name)
    return display_name


def _source_url(relative_path: Path) -> str:
    return f"{SOURCE_ROOT}/{relative_path.as_posix()}"


def _public_boundary(boundary: dict[str, Any]) -> dict[str, Any]:
    activation = boundary.get("activation")
    if activation and str(activation).startswith("automatic_"):
        route_mode = "automatic"
    elif boundary.get("optional"):
        route_mode = "optional"
    else:
        route_mode = "chosen"
    return {
        "kind": boundary["kind"],
        "destination": boundary["destination"],
        "purpose": boundary["purpose"],
        "content": boundary["content"],
        "route_mode": route_mode,
    }


def _clara_services(root: Path, lang: str) -> tuple[dict[str, Any], ...]:
    service_dir = root / "plugins" / "clara" / "privacy" / "hosted-services"
    services = []
    for path in sorted(service_dir.glob("*.json")):
        manifest = _read_json(path)
        service_id = str(manifest["service_id"])
        services.append(
            {
                "id": f"clara-{service_id}",
                "service_id": service_id,
                "product": "Clara",
                "name": str(manifest["display_name"]),
                "automatic": bool(manifest["automatic"]),
                "workflows": [
                    _localized_name(item, item, lang) for item in manifest["workflows"]
                ],
                "providers": list(manifest["provider_or_recipients"]),
                "data_sent": [
                    {"when": item["when"], "content": item["content"]}
                    for item in manifest["data_sent"]
                ],
                "data_returned": [
                    {"when": item["when"], "content": item["content"]}
                    for item in manifest["data_returned"]
                ],
                "retention": manifest["retention"]["statement"],
                "access": manifest["access"]["arrangement"],
                "reviewed_at": manifest["review"]["reviewed_at"],
                "source_url": _source_url(path.relative_to(root)),
            }
        )
    return tuple(services)


def _vera_services(root: Path) -> tuple[dict[str, Any], ...]:
    service_dir = root / "plugins" / "vera" / "privacy" / "services"
    services = []
    for path in sorted(service_dir.glob("*.json")):
        manifest = _read_json(path)
        service_id = str(manifest["service_id"])
        boundaries = manifest["external_boundaries"]
        services.append(
            {
                "id": f"vera-{service_id}",
                "service_id": service_id,
                "product": "Vera",
                "name": str(manifest["display_name"]),
                "automatic": any(
                    str(item["activation"]).startswith("automatic_")
                    for item in boundaries
                ),
                "workflows": [],
                "providers": sorted({str(item["destination"]) for item in boundaries}),
                "data_sent": [
                    {"when": item["purpose"], "content": item["content"]}
                    for item in boundaries
                ],
                "data_returned": [],
                "retention": " ".join(str(item["retention"]) for item in boundaries),
                "access": "",
                "reviewed_at": manifest["review"]["reviewed_at"],
                "source_url": _source_url(path.relative_to(root)),
            }
        )
    return tuple(services)


def _vera_workflows(root: Path, lang: str) -> tuple[dict[str, Any], ...]:
    manifest_dir = root / "plugins" / "vera" / "privacy" / "workstreams"
    workflows = []
    for path in sorted(manifest_dir.glob("*.json")):
        manifest = _read_json(path)
        identifier = str(manifest["workstream"])
        workflows.append(
            {
                "id": identifier,
                "product": "Vera",
                "name": _localized_name(
                    identifier, str(manifest["display_name"]), lang
                ),
                "technical_name": str(manifest["display_name"]),
                "model_intro_key": "model_intro_vera",
                "model_classes": [
                    {"purpose": item["purpose"], "content": item["content"]}
                    for item in manifest["model_context"]["classes"]
                ],
                "service_ids": [],
                "other_boundaries": [
                    _public_boundary(item) for item in manifest["external_boundaries"]
                ],
                "reviewed_at": manifest["review"]["reviewed_at"],
                "source_url": _source_url(path.relative_to(root)),
            }
        )
    return tuple(workflows)


def _clara_workflows(root: Path, lang: str) -> tuple[dict[str, Any], ...]:
    manifest_dir = root / "plugins" / "clara" / "privacy" / "workflows"
    workflows = []
    for path in sorted(manifest_dir.glob("*.json")):
        manifest = _read_json(path)
        identifier = str(manifest["workflow"])
        service_ids = [str(item) for item in manifest["hosted_service_ids"]]
        workflows.append(
            {
                "id": identifier,
                "product": "Clara",
                "name": _localized_name(
                    identifier, str(manifest["display_name"]), lang
                ),
                "technical_name": str(manifest["display_name"]),
                "model_intro_key": "model_intro_clara",
                "model_classes": [
                    {"purpose": item["purpose"], "content": item["content"]}
                    for item in manifest["codex_context"]["classes"]
                ],
                "service_ids": [f"clara-{item}" for item in service_ids],
                "other_boundaries": [
                    _public_boundary(item)
                    for item in manifest["boundaries_beyond_codex"]
                    if item["kind"] != "hosted_service"
                ],
                "reviewed_at": manifest["review"]["reviewed_at"],
                "source_url": _source_url(path.relative_to(root)),
            }
        )
    return tuple(workflows)


def _lucia_public_text(value: str) -> str:
    """Project canonical Vera mechanics through Lucia's public identity."""

    replacements = (
        ("Vera-default", "Lucia-proposed"),
        ("Vera defaults", "Lucia proposals"),
        ("Vera default", "Lucia proposal"),
        ("Vera package", "Lucia package"),
        ("Vera", "Lucia"),
        ("commercialista", "lawyer"),
    )
    result = value
    for source, target in replacements:
        result = result.replace(source, target)
    return result


def _lucia_workflows(root: Path, lang: str) -> tuple[dict[str, Any], ...]:
    """Load Lucia-native boundaries, falling back to shared Vera mechanics."""

    lucia_root = root / "plugins" / "lucia"
    components = _read_json(lucia_root / "components.json")
    roles = components.get("workflow_roles", {})
    public_ids = {
        str(identifier)
        for identifier in components.get("plugins", [])
        if isinstance(roles.get(identifier), dict)
        and roles[identifier].get("kind") == "public_workflow"
    }
    vera_manifest_dir = root / "plugins" / "vera" / "privacy" / "workstreams"
    lucia_manifest_dir = lucia_root / "privacy" / "workstreams"
    manifest_paths = {path.stem: path for path in vera_manifest_dir.glob("*.json")}
    native_ids = {path.stem for path in lucia_manifest_dir.glob("*.json")}
    manifest_paths.update(
        {path.stem: path for path in lucia_manifest_dir.glob("*.json")}
    )
    missing = sorted(public_ids - manifest_paths.keys())
    if missing:
        raise ValueError(
            "Lucia workflow has no canonical privacy boundary: " + ", ".join(missing)
        )

    workflows = []
    for identifier in sorted(public_ids):
        path = manifest_paths[identifier]
        manifest = _read_json(path)
        project_identity = identifier not in native_ids
        workflows.append(
            {
                "id": identifier,
                "product": "Lucia",
                "name": _localized_name(
                    identifier, str(manifest["display_name"]), lang
                ),
                "technical_name": str(manifest["display_name"]),
                "model_intro_key": "model_intro_lucia",
                "model_classes": [
                    {
                        "purpose": (
                            _lucia_public_text(str(item["purpose"]))
                            if project_identity
                            else str(item["purpose"])
                        ),
                        "content": (
                            _lucia_public_text(str(item["content"]))
                            if project_identity
                            else str(item["content"])
                        ),
                    }
                    for item in manifest["model_context"]["classes"]
                ],
                "service_ids": [],
                "other_boundaries": [
                    {
                        **_public_boundary(item),
                        "destination": (
                            _lucia_public_text(str(item["destination"]))
                            if project_identity
                            else str(item["destination"])
                        ),
                        "purpose": (
                            _lucia_public_text(str(item["purpose"]))
                            if project_identity
                            else str(item["purpose"])
                        ),
                        "content": (
                            _lucia_public_text(str(item["content"]))
                            if project_identity
                            else str(item["content"])
                        ),
                    }
                    for item in manifest["external_boundaries"]
                ],
                "reviewed_at": manifest["review"]["reviewed_at"],
                "source_url": _source_url(path.relative_to(root)),
            }
        )
    return tuple(workflows)


@lru_cache(maxsize=10)
def get_public_privacy_register(lang: str = "en") -> dict[str, Any]:
    """Return a safe public projection of the canonical privacy manifests."""

    resolved_lang = "it" if lang == "it" else "en"
    copy = _COPY[resolved_lang]
    services = (*_vera_services(ROOT), *_clara_services(ROOT, resolved_lang))
    service_names = {item["id"]: item["name"] for item in services}
    workflows = (
        *_vera_workflows(ROOT, resolved_lang),
        *_clara_workflows(ROOT, resolved_lang),
        *_lucia_workflows(ROOT, resolved_lang),
    )
    public_workflows = []
    for workflow in workflows:
        public_workflows.append(
            {
                **workflow,
                "service_names": [
                    service_names[service_id] for service_id in workflow["service_ids"]
                ],
            }
        )
    return {
        "copy": copy,
        "products": tuple(
            {
                "name": product,
                "workflows": tuple(
                    item for item in public_workflows if item["product"] == product
                ),
            }
            for product in ("Vera", "Clara", "Lucia")
        ),
        "services": services,
        "entry_count": len(public_workflows) + len(services),
    }
