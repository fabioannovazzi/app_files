from __future__ import annotations

import calendar
import csv
import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "AML_A_FACTOR_IDS",
    "AML_B_FACTOR_IDS",
    "AML_TRIGGER_IDS",
    "APPLICABILITY_TOPICS",
    "EXPECTED_ARTIFACTS",
    "SCHEMA_VERSION",
    "SCREENING_TYPES",
    "SUPPORTED_JURISDICTIONS",
    "SUPPORTED_LANGUAGES",
    "ValidationError",
    "add_months_clamped",
    "build_applicability_plan",
    "build_case_facts",
    "build_document_plan",
    "build_export_domain_blockers",
    "build_missing_evidence",
    "build_monitoring_plan",
    "build_review_payload",
    "build_temporal_validity",
    "calculate_aml",
    "canonical_json_hash",
    "ensure_private_output_directory",
    "load_json",
    "load_source_registry",
    "sha256_file",
    "utc_now",
    "validate_contract",
    "validate_new_client_input",
    "validate_review_payload_privacy",
    "validate_source_references",
    "verify_client_file_preparation_binding",
    "verify_evidence_register",
    "verify_template_references",
    "write_private_json",
    "write_private_text",
]

SCHEMA_VERSION = "1.1"
AML_A_FACTOR_IDS = ("A1", "A2", "A3", "A4")
AML_B_FACTOR_IDS = ("B1", "B2", "B3", "B4", "B5", "B6")
AML_TRIGGER_IDS = (
    "pep_private_capacity",
    "high_risk_third_country",
    "qualified_cross_border_correspondence",
)
APPLICABILITY_TOPICS = (
    "mandate",
    "privacy_notice",
    "ai_transparency_notice",
    "article_28_terms",
    "aml_assessment",
)
SCREENING_TYPES = ("pep", "sanctions", "country")
SUPPORTED_LANGUAGES = ("it", "en", "fr", "de")
SUPPORTED_JURISDICTIONS = ("IT",)
ITALY_COUNTRY_PACK = "it-professional-setup-2026"
TEMPORAL_VALIDITY_POLICY = "inclusive_earliest_material_deadline_v1"
TEMPORAL_APPLY_RULE = "system_utc_date_must_not_exceed_valid_through"
CLIENT_FILE_PREPARATION_FINAL_STATUSES = {"final_ready"}
CLIENT_FILE_PREPARATION_PACKAGE_HASH_BASIS = (
    "sorted_outputs_path_size_sha256_canonical_json_v1"
)
CLIENT_FILE_PREPARATION_SOURCE_LIMITS = {
    "max_entry_count": 20_000,
    "max_file_count": 5_000,
    "max_file_bytes": 256 * 1024 * 1024,
    "max_total_bytes": 2 * 1024 * 1024 * 1024,
}
CLIENT_FILE_PREPARATION_INVENTORY_COLUMNS = (
    "relative_path",
    "file_name",
    "extension",
    "size_bytes",
    "modified_iso",
    "sha256",
    "category",
    "confidence",
    "years",
    "notes",
)
EXPECTED_ARTIFACTS = (
    "run_intake.json",
    "case_facts_validated.json",
    "source_registry.json",
    "applicability_plan_validated.json",
    "aml_assessment_draft.json",
    "aml_calculation_audit.json",
    "missing_evidence.json",
    "document_plan.json",
    "monitoring_plan.json",
    "studio_new_client_memo.md",
    "client_missing_information_draft.md",
    "review_payload.json",
    "ui_decisions.json",
    "review_handoff.md",
    "final_artifacts.json",
)

_FORBIDDEN_OUTCOME_STATUSES = {"active", "compliant", "complete", "signed"}
_REVIEW_FORBIDDEN_KEYS = {
    "access_token",
    "auth_token",
    "authorization_header",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "one_time_code",
    "otp",
    "otp_code",
    "password",
    "private_session_url",
    "refresh_token",
    "session_cookie",
    "session_token",
    "session_url",
    "token",
    "raw_path",
    "local_path",
    "evidence_path",
}
_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,79}$")

_REVIEW_COPY: dict[str, dict[str, str]] = {
    "title.privacy_processing": {
        "it": "Decisione sul trattamento dei dati — finalità {number}",
        "en": "Privacy processing decision — purpose {number}",
        "fr": "Décision relative au traitement des données — finalité {number}",
        "de": "Entscheidung zur Datenverarbeitung — Zweck {number}",
    },
    "title.marketing_consent": {
        "it": "Consenso marketing separato",
        "en": "Separate marketing-consent record",
        "fr": "Consentement marketing distinct",
        "de": "Gesonderte Einwilligung für Marketing",
    },
    "title.applicability": {
        "it": "Applicabilità — {topic}",
        "en": "Applicability — {topic}",
        "fr": "Applicabilité — {topic}",
        "de": "Anwendbarkeit — {topic}",
    },
    "title.aml_table_1": {
        "it": "Applicabilità della Tabella 1 antiriciclaggio",
        "en": "AML Table 1 applicability",
        "fr": "Applicabilité du tableau 1 LCB-FT",
        "de": "Anwendbarkeit der AML-Tabelle 1",
    },
    "title.monitoring_plan": {
        "it": "Calendario dei riesami periodici",
        "en": "Ongoing-review schedule",
        "fr": "Calendrier des réexamens périodiques",
        "de": "Zeitplan für regelmäßige Überprüfungen",
    },
    "title.party_profile": {
        "it": "Profilo del cliente e documenti di identità",
        "en": "Client profile and identity evidence",
        "fr": "Profil du client et justificatifs d’identité",
        "de": "Mandantenprofil und Identitätsnachweise",
    },
    "title.party_structure": {
        "it": "Rappresentanti, esecutore e titolarità effettiva",
        "en": "Representatives, executor and beneficial ownership",
        "fr": "Représentants, exécutant et bénéficiaires effectifs",
        "de": "Vertreter, ausführende Person und wirtschaftlich Berechtigte",
    },
    "title.engagement": {
        "it": "Ambito e condizioni dell’incarico",
        "en": "Engagement scope and terms",
        "fr": "Périmètre et conditions de la mission",
        "de": "Umfang und Bedingungen des Auftrags",
    },
    "title.screening_subject": {
        "it": "Copertura delle verifiche — {subject_reference}",
        "en": "Screening coverage — {subject_reference}",
        "fr": "Couverture des vérifications — {subject_reference}",
        "de": "Abdeckung der Prüfungen — {subject_reference}",
    },
    "title.aml_factor_section": {
        "it": "Sezione {section} dei fattori di rischio antiriciclaggio",
        "en": "AML risk-factor section {section}",
        "fr": "Section {section} des facteurs de risque LCB-FT",
        "de": "Abschnitt {section} der AML-Risikofaktoren",
    },
    "title.aml_trigger_set": {
        "it": "Indicatori che impongono misure rafforzate",
        "en": "Mandatory enhanced-measure triggers",
        "fr": "Facteurs imposant des mesures de vigilance renforcée",
        "de": "Auslöser für verpflichtende verstärkte Maßnahmen",
    },
    "title.missing_evidence": {
        "it": "Evidenze mancanti e informazioni irrisolte",
        "en": "Missing evidence and unresolved information",
        "fr": "Justificatifs manquants et informations non résolues",
        "de": "Fehlende Nachweise und ungeklärte Angaben",
    },
}

_REVIEW_TOPIC_COPY: dict[str, dict[str, str]] = {
    "mandate": {
        "it": "incarico professionale",
        "en": "professional engagement",
        "fr": "mission professionnelle",
        "de": "Berufsauftrag",
    },
    "privacy_notice": {
        "it": "informativa privacy",
        "en": "privacy notice",
        "fr": "information sur la protection des données",
        "de": "Datenschutzhinweis",
    },
    "ai_transparency_notice": {
        "it": "informativa sull’uso dell’IA",
        "en": "AI transparency notice",
        "fr": "information sur l’utilisation de l’IA",
        "de": "Information zum KI-Einsatz",
    },
    "article_28_terms": {
        "it": "nomina ai sensi dell’articolo 28",
        "en": "Article 28 terms",
        "fr": "clauses de l’article 28",
        "de": "Vereinbarung nach Artikel 28",
    },
    "aml_assessment": {
        "it": "valutazione antiriciclaggio",
        "en": "AML assessment",
        "fr": "évaluation LCB-FT",
        "de": "AML-Risikobewertung",
    },
}


class ValidationError(ValueError):
    """Raised when new-client input or generated artifacts violate the contract."""


def utc_now() -> str:
    """Return a stable, second-resolution UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json_hash(payload: Any) -> str:
    """Hash a JSON-compatible value using canonical UTF-8 serialization."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    """Load a UTF-8 JSON object and raise a contract-oriented error on failure."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"Cannot read JSON file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"Expected a JSON object in {path}.")
    return payload


def _write_private_bytes(path: Path, content: bytes) -> Path:
    """Atomically replace a regular file with owner-only bytes."""

    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    try:
        existing_mode = target.lstat().st_mode
    except FileNotFoundError:
        existing_mode = None
    if existing_mode is not None and not stat.S_ISREG(existing_mode):
        raise ValidationError(f"Refusing to replace non-regular output file {target}.")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
    return target


def write_private_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Atomically write JSON and restrict the resulting file to its owner."""

    content = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return _write_private_bytes(path, content)


def write_private_text(path: Path, text: str) -> Path:
    """Atomically write text and restrict the resulting file to its owner."""

    return _write_private_bytes(path, (text.rstrip() + "\n").encode("utf-8"))


def _protected_source_roots() -> tuple[Path, ...]:
    """Return repository and installed-plugin roots that must never hold runs."""

    current = Path(__file__).resolve()
    roots: list[Path] = []
    for candidate in current.parents:
        if (candidate / ".git").exists() or (
            candidate / ".codex-plugin" / "plugin.json"
        ).is_file():
            roots.append(candidate.resolve())
    plugin_root = current.parents[1]
    if plugin_root not in roots:
        roots.append(plugin_root)
    return tuple(dict.fromkeys(roots))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def ensure_private_output_directory(
    output_dir: Path,
    *,
    allowed_existing: Iterable[str] = (),
) -> Path:
    """Create or validate a dedicated owner-only case directory."""

    requested = output_dir.expanduser().absolute()
    for component in (requested, *requested.parents):
        if component.is_symlink():
            raise ValidationError(
                "New-client output paths may not traverse symbolic links."
            )
    resolved = requested.resolve(strict=False)
    if any(_is_within(resolved, root) for root in _protected_source_roots()):
        raise ValidationError(
            "New-client outputs must be stored outside the source repository "
            "and installed plugin directories."
        )
    broad_roots = {
        Path(resolved.anchor).resolve(),
        Path.home().resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    if resolved in broad_roots:
        raise ValidationError(
            "New-client output must be a dedicated case directory, not a broad root."
        )
    allowed_names = set(allowed_existing)
    if resolved.exists():
        stat_result = resolved.lstat()
        if not stat.S_ISDIR(stat_result.st_mode) or resolved.is_symlink():
            raise ValidationError(
                "New-client output must be a regular directory without symlinks."
            )
        entries = list(resolved.iterdir())
        unexpected = sorted(
            entry.name for entry in entries if entry.name not in allowed_names
        )
        if unexpected:
            raise ValidationError(
                "New-client output directory must be new or contain only explicitly "
                "replaceable case files. Preserve prior contents and use a new run "
                "directory. Unexpected entries: " + ", ".join(unexpected)
            )
        for entry in entries:
            entry_stat = entry.lstat()
            if not stat.S_ISREG(entry_stat.st_mode) or entry.is_symlink():
                raise ValidationError(
                    "Existing replaceable case files must be regular files without symlinks."
                )
    else:
        resolved.mkdir(parents=True, mode=0o700)
    resolved.chmod(0o700)
    return resolved


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object.")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be an array.")
    return value


def _require_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValidationError(f"{field} must be a non-empty string.")
    return value.strip()


def _require_reference(value: Any, field: str) -> str:
    reference = _require_string(value, field)
    if not _REFERENCE_RE.fullmatch(reference):
        raise ValidationError(
            f"{field} must be an opaque 3-80 character reference using letters, "
            "numbers, dots, colons, underscores, or hyphens."
        )
    return reference


def _parse_date(value: Any, field: str) -> date:
    text = _require_string(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(f"{field} must use YYYY-MM-DD format.") from exc


def _parse_timestamp(value: Any, field: str) -> datetime:
    text = _require_string(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{field} must include a timezone offset.")
    return parsed


def _require_sha256(value: Any, field: str) -> str:
    digest = _require_string(value, field).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValidationError(f"{field} must be a SHA-256 digest.")
    return digest


def _resolve_local_file(path_value: Any, *, field: str, base_dir: Path) -> Path:
    raw_path = Path(_require_string(path_value, field)).expanduser()
    candidate = raw_path if raw_path.is_absolute() else base_dir / raw_path
    try:
        if candidate.is_symlink():
            raise ValidationError(f"{field} must not refer to a symbolic link.")
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValidationError(f"{field} cannot be resolved: {exc}") from exc
    if not resolved.is_file():
        raise ValidationError(f"{field} must refer to a regular file.")
    return resolved


def _decimal_score(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number from 1 to 4.")
    try:
        score = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a number from 1 to 4.") from exc
    if score < Decimal("1") or score > Decimal("4"):
        raise ValidationError(f"{field} must be between 1 and 4.")
    return score


def _validate_evidence_ids(
    value: Any,
    field: str,
    known_evidence_ids: set[str],
) -> list[str]:
    values = _require_list(value, field)
    result: list[str] = []
    for index, item in enumerate(values):
        evidence_id = _require_reference(item, f"{field}[{index}]")
        if evidence_id not in known_evidence_ids:
            raise ValidationError(
                f"{field}[{index}] refers to unknown evidence ID {evidence_id!r}."
            )
        result.append(evidence_id)
    if len(result) != len(set(result)):
        raise ValidationError(f"{field} must not contain duplicate evidence IDs.")
    return result


def _validate_professional_confirmation(
    record: Mapping[str, Any],
    *,
    status_field: str,
    field: str,
) -> None:
    """Mechanically verify attribution without judging the confirmed substance."""

    confirmed_by_role = record.get("confirmed_by_role")
    confirmed_at = record.get("confirmed_at")
    if record.get(status_field) == "confirmed":
        if confirmed_by_role != "professional":
            raise ValidationError(
                f"Confirmed {field} must be confirmed_by_role=professional."
            )
        _parse_timestamp(confirmed_at, f"{field}.confirmed_at")
    elif confirmed_by_role is not None or confirmed_at is not None:
        raise ValidationError(
            f"Proposed {field} confirmation fields must be null or absent."
        )


def _validate_factor_group(
    factors: Any,
    *,
    expected_ids: Sequence[str],
    field: str,
    allow_null_scores: bool,
    known_evidence_ids: set[str],
) -> None:
    values = _require_list(factors, field)
    if len(values) != len(expected_ids):
        raise ValidationError(
            f"{field} must contain exactly {len(expected_ids)} factors."
        )
    found_ids: list[str] = []
    for index, raw_factor in enumerate(values):
        factor = _require_object(raw_factor, f"{field}[{index}]")
        factor_id = _require_string(
            factor.get("factor_id"), f"{field}[{index}].factor_id"
        )
        found_ids.append(factor_id)
        score = factor.get("score")
        if score is None:
            if not allow_null_scores:
                raise ValidationError(f"{field}[{index}].score is required.")
        else:
            _decimal_score(score, f"{field}[{index}].score")
        status = factor.get("assessment_status")
        if status not in {"proposed", "confirmed"}:
            raise ValidationError(
                f"{field}[{index}].assessment_status must be proposed or confirmed."
            )
        _validate_professional_confirmation(
            factor,
            status_field="assessment_status",
            field=f"{field}[{index}]",
        )
        _require_string(factor.get("basis"), f"{field}[{index}].basis")
        _validate_evidence_ids(
            factor.get("evidence_ids", []),
            f"{field}[{index}].evidence_ids",
            known_evidence_ids,
        )
    if set(found_ids) != set(expected_ids) or len(found_ids) != len(set(found_ids)):
        raise ValidationError(
            f"{field} must contain each of {', '.join(expected_ids)} exactly once."
        )


def _validate_identity_document(
    value: Any,
    field: str,
    known_evidence_ids: set[str],
) -> None:
    identity = _require_object(value, field)
    status = identity.get("verification_status")
    if status not in {"unknown", "reported", "verified", "not_applicable"}:
        raise ValidationError(f"{field}.verification_status is not supported.")
    for text_field in (
        "document_type",
        "document_number",
        "issuer",
        "verification_method",
    ):
        if identity.get(text_field) is not None:
            _require_string(identity.get(text_field), f"{field}.{text_field}")
    parsed_dates: dict[str, date] = {}
    for date_field in ("issued_on", "expires_on", "verified_on"):
        if identity.get(date_field) is not None:
            parsed_dates[date_field] = _parse_date(
                identity.get(date_field), f"{field}.{date_field}"
            )
    if (
        "issued_on" in parsed_dates
        and "expires_on" in parsed_dates
        and parsed_dates["expires_on"] < parsed_dates["issued_on"]
    ):
        raise ValidationError(f"{field}.expires_on must not precede issued_on.")
    if (
        "issued_on" in parsed_dates
        and "verified_on" in parsed_dates
        and parsed_dates["verified_on"] < parsed_dates["issued_on"]
    ):
        raise ValidationError(f"{field}.verified_on must not precede issued_on.")
    if (
        "expires_on" in parsed_dates
        and "verified_on" in parsed_dates
        and parsed_dates["verified_on"] > parsed_dates["expires_on"]
    ):
        raise ValidationError(f"{field}.verified_on must not follow expires_on.")
    evidence_ids = _validate_evidence_ids(
        identity.get("evidence_ids", []),
        f"{field}.evidence_ids",
        known_evidence_ids,
    )
    if status == "verified":
        if not evidence_ids:
            raise ValidationError(f"{field} cannot be verified without evidence.")
        if identity.get("verified_on") is None:
            raise ValidationError(f"{field}.verified_on is required when verified.")
        if identity.get("verification_method") is None:
            raise ValidationError(
                f"{field}.verification_method is required when verified."
            )
    if status == "not_applicable" and any(
        identity.get(key) not in {None, ""}
        for key in (
            "document_type",
            "document_number",
            "issuer",
            "issued_on",
            "expires_on",
            "verified_on",
            "verification_method",
        )
    ):
        raise ValidationError(
            f"{field} document metadata must be null when not_applicable."
        )


def validate_new_client_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the new-client input contract without making legal judgments."""

    data = dict(payload)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError(f"schema_version must be {SCHEMA_VERSION!r}.")
    expected_top_level_fields = {
        "schema_version",
        "jurisdiction",
        "language",
        "client_file_preparation_binding",
        "client_reference",
        "client_type",
        "tax_facts",
        "party_facts",
        "party_identity_document",
        "representatives",
        "representative_posture",
        "beneficial_owners",
        "ownership_status",
        "screening_results",
        "engagement",
        "privacy_processing_decisions",
        "marketing_consent",
        "evidence_register",
        "applicability",
        "template_references",
        "aml",
    }
    if set(data) != expected_top_level_fields:
        missing = sorted(expected_top_level_fields - set(data))
        extra = sorted(set(data) - expected_top_level_fields)
        raise ValidationError(
            "New-client input fields do not match the 1.1 contract; "
            f"missing={missing}, extra={extra}."
        )
    if data.get("language") not in SUPPORTED_LANGUAGES:
        raise ValidationError(
            "language must be one of " + ", ".join(SUPPORTED_LANGUAGES) + "."
        )
    if data.get("jurisdiction") not in SUPPORTED_JURISDICTIONS:
        raise ValidationError(
            "No Vera professional-setup country pack is available for "
            f"jurisdiction {data.get('jurisdiction')!r}; available packs: "
            + ", ".join(SUPPORTED_JURISDICTIONS)
            + "."
        )
    _require_reference(data.get("client_reference"), "client_reference")
    if data.get("client_type") not in {
        "individual",
        "sole_trader",
        "company",
        "entity",
    }:
        raise ValidationError(
            "client_type must be individual, sole_trader, company, or entity."
        )

    evidence_register = _require_list(
        data.get("evidence_register"), "evidence_register"
    )
    evidence_ids: set[str] = set()
    for index, raw_evidence in enumerate(evidence_register):
        evidence = _require_object(raw_evidence, f"evidence_register[{index}]")
        evidence_id = _require_reference(
            evidence.get("evidence_id"), f"evidence_register[{index}].evidence_id"
        )
        if evidence_id in evidence_ids:
            raise ValidationError(f"Duplicate evidence_id {evidence_id!r}.")
        evidence_ids.add(evidence_id)
        _require_string(
            evidence.get("evidence_type"),
            f"evidence_register[{index}].evidence_type",
        )
        if evidence.get("status") not in {
            "verified",
            "available",
            "requested",
            "missing",
            "stale",
        }:
            raise ValidationError(
                f"evidence_register[{index}].status is not supported."
            )
        obtained_on = None
        expires_on = None
        if evidence.get("obtained_on") is not None:
            obtained_on = _parse_date(
                evidence.get("obtained_on"),
                f"evidence_register[{index}].obtained_on",
            )
        if evidence.get("expires_on") is not None:
            expires_on = _parse_date(
                evidence.get("expires_on"),
                f"evidence_register[{index}].expires_on",
            )
        if (
            obtained_on is not None
            and expires_on is not None
            and expires_on < obtained_on
        ):
            raise ValidationError(
                f"evidence_register[{index}].expires_on must not precede obtained_on."
            )
        if evidence.get("sha256") is not None:
            _require_sha256(
                evidence.get("sha256"), f"evidence_register[{index}].sha256"
            )
        if evidence.get("local_path") is not None:
            _require_string(
                evidence.get("local_path"),
                f"evidence_register[{index}].local_path",
            )
        if evidence.get("status") in {"verified", "available"}:
            if evidence.get("sha256") is None or evidence.get("local_path") is None:
                raise ValidationError(
                    f"evidence_register[{index}] requires local_path and sha256 "
                    "when status is verified or available."
                )

    client_file_preparation_binding = _require_object(
        data.get("client_file_preparation_binding"), "client_file_preparation_binding"
    )
    binding_mode = client_file_preparation_binding.get("mode")
    if binding_mode == "client_file_preparation_run":
        expected_binding_fields = {
            "mode",
            "run_id",
            "final_artifacts_path",
            "final_artifacts_sha256",
            "upstream_package_hash",
            "promoted_evidence_ids",
        }
        if set(client_file_preparation_binding) != expected_binding_fields:
            raise ValidationError(
                "client_file_preparation_binding client_file_preparation_run fields must be exactly: "
                + ", ".join(sorted(expected_binding_fields))
            )
        _require_reference(
            client_file_preparation_binding.get("run_id"),
            "client_file_preparation_binding.run_id",
        )
        _require_string(
            client_file_preparation_binding.get("final_artifacts_path"),
            "client_file_preparation_binding.final_artifacts_path",
        )
        _require_sha256(
            client_file_preparation_binding.get("final_artifacts_sha256"),
            "client_file_preparation_binding.final_artifacts_sha256",
        )
        _require_sha256(
            client_file_preparation_binding.get("upstream_package_hash"),
            "client_file_preparation_binding.upstream_package_hash",
        )
        _validate_evidence_ids(
            client_file_preparation_binding.get("promoted_evidence_ids", []),
            "client_file_preparation_binding.promoted_evidence_ids",
            evidence_ids,
        )
    elif binding_mode == "standalone_evidence":
        expected_binding_fields = {"mode", "reason", "evidence_ids"}
        if set(client_file_preparation_binding) != expected_binding_fields:
            raise ValidationError(
                "client_file_preparation_binding standalone_evidence fields must be exactly: "
                + ", ".join(sorted(expected_binding_fields))
            )
        _require_string(
            client_file_preparation_binding.get("reason"),
            "client_file_preparation_binding.reason",
        )
        _validate_evidence_ids(
            client_file_preparation_binding.get("evidence_ids", []),
            "client_file_preparation_binding.evidence_ids",
            evidence_ids,
        )
    else:
        raise ValidationError(
            "client_file_preparation_binding.mode must be client_file_preparation_run or "
            "standalone_evidence."
        )

    tax_facts = _require_object(data.get("tax_facts"), "tax_facts")
    if set(tax_facts) != {"codice_fiscale", "partita_iva"}:
        raise ValidationError(
            "tax_facts must contain separate codice_fiscale and partita_iva facts."
        )
    for fact_name in ("codice_fiscale", "partita_iva"):
        fact = _require_object(tax_facts[fact_name], f"tax_facts.{fact_name}")
        status = fact.get("verification_status")
        if status not in {"unknown", "reported", "verified", "not_applicable"}:
            raise ValidationError(
                f"tax_facts.{fact_name}.verification_status is not supported."
            )
        value = fact.get("value")
        if status == "not_applicable":
            if value not in {None, ""}:
                raise ValidationError(
                    f"tax_facts.{fact_name}.value must be null when not_applicable."
                )
        elif value is not None:
            _require_string(value, f"tax_facts.{fact_name}.value")
        fact_evidence = _validate_evidence_ids(
            fact.get("evidence_ids", []),
            f"tax_facts.{fact_name}.evidence_ids",
            evidence_ids,
        )
        if status == "verified" and not fact_evidence:
            raise ValidationError(
                f"tax_facts.{fact_name} cannot be verified without evidence."
            )

    party_facts = _require_list(data.get("party_facts"), "party_facts")
    if not party_facts:
        raise ValidationError("party_facts must contain at least one fact record.")
    party_fact_ids: set[str] = set()
    for index, raw_fact in enumerate(party_facts):
        fact = _require_object(raw_fact, f"party_facts[{index}]")
        fact_id = _require_reference(
            fact.get("fact_id"), f"party_facts[{index}].fact_id"
        )
        if fact_id in party_fact_ids:
            raise ValidationError(f"Duplicate party fact ID {fact_id!r}.")
        party_fact_ids.add(fact_id)
        _require_reference(fact.get("fact_code"), f"party_facts[{index}].fact_code")
        if isinstance(fact.get("value"), (dict, list)):
            raise ValidationError(
                f"party_facts[{index}].value must be a JSON scalar or null."
            )
        if fact.get("verification_status") not in {
            "unknown",
            "reported",
            "verified",
            "not_applicable",
        }:
            raise ValidationError(
                f"party_facts[{index}].verification_status is not supported."
            )
        fact_evidence = _validate_evidence_ids(
            fact.get("evidence_ids", []),
            f"party_facts[{index}].evidence_ids",
            evidence_ids,
        )
        if fact.get("verification_status") == "verified" and not fact_evidence:
            raise ValidationError(
                f"party_facts[{index}] cannot be verified without evidence."
            )

    _validate_identity_document(
        data.get("party_identity_document"),
        "party_identity_document",
        evidence_ids,
    )

    representatives = _require_list(data.get("representatives"), "representatives")
    representative_ids: set[str] = set()
    for index, raw_representative in enumerate(representatives):
        representative = _require_object(
            raw_representative, f"representatives[{index}]"
        )
        representative_id = _require_reference(
            representative.get("representative_reference"),
            f"representatives[{index}].representative_reference",
        )
        if representative_id in representative_ids:
            raise ValidationError(
                f"Duplicate representative_reference {representative_id!r}."
            )
        representative_ids.add(representative_id)
        if representative.get("role") not in {
            "executor",
            "legal_representative",
            "delegate",
            "other",
        }:
            raise ValidationError(f"representatives[{index}].role is not supported.")
        _require_string(
            representative.get("authority_basis"),
            f"representatives[{index}].authority_basis",
        )
        _validate_evidence_ids(
            representative.get("evidence_ids", []),
            f"representatives[{index}].evidence_ids",
            evidence_ids,
        )
        _validate_identity_document(
            representative.get("identity_document"),
            f"representatives[{index}].identity_document",
            evidence_ids,
        )

    representative_posture = _require_object(
        data.get("representative_posture"), "representative_posture"
    )
    expected_posture_fields = {
        "status",
        "executor_reference",
        "basis",
        "evidence_ids",
        "confirmed_by_role",
        "confirmed_at",
    }
    if set(representative_posture) != expected_posture_fields:
        raise ValidationError(
            "representative_posture fields must be exactly: "
            + ", ".join(sorted(expected_posture_fields))
        )
    posture_status = representative_posture.get("status")
    if posture_status not in {"recorded", "none_required_confirmed", "pending"}:
        raise ValidationError("representative_posture.status is not supported.")
    posture_evidence_ids = _validate_evidence_ids(
        representative_posture.get("evidence_ids", []),
        "representative_posture.evidence_ids",
        evidence_ids,
    )
    if posture_status == "recorded":
        executor_reference = _require_reference(
            representative_posture.get("executor_reference"),
            "representative_posture.executor_reference",
        )
        if executor_reference not in representative_ids:
            raise ValidationError(
                "representative_posture.executor_reference must identify a recorded "
                "representative or executor."
            )
        executor_record = next(
            representative
            for representative in representatives
            if representative["representative_reference"] == executor_reference
        )
        if executor_record["role"] != "executor":
            raise ValidationError(
                "representative_posture.executor_reference must identify a "
                "representative whose role is executor."
            )
        if not representatives:
            raise ValidationError(
                "representative_posture recorded requires at least one representative."
            )
        _require_string(
            representative_posture.get("basis"), "representative_posture.basis"
        )
        if not posture_evidence_ids:
            raise ValidationError(
                "representative_posture recorded requires supporting evidence_ids."
            )
        if (
            representative_posture.get("confirmed_by_role") is not None
            or representative_posture.get("confirmed_at") is not None
        ):
            raise ValidationError(
                "representative_posture recorded derives from the recorded parties "
                "and must not contain separate confirmation metadata."
            )
    elif posture_status == "none_required_confirmed":
        if (
            representatives
            or representative_posture.get("executor_reference") is not None
        ):
            raise ValidationError(
                "representative_posture none_required_confirmed requires no recorded "
                "representatives or executor_reference."
            )
        _require_string(
            representative_posture.get("basis"), "representative_posture.basis"
        )
        if representative_posture.get("confirmed_by_role") != "professional":
            raise ValidationError(
                "representative_posture none_required_confirmed must be confirmed "
                "by the professional."
            )
        _parse_timestamp(
            representative_posture.get("confirmed_at"),
            "representative_posture.confirmed_at",
        )
    else:
        if (
            any(
                representative_posture.get(field) not in {None, ""}
                for field in (
                    "executor_reference",
                    "confirmed_by_role",
                    "confirmed_at",
                )
            )
            or posture_evidence_ids
        ):
            raise ValidationError(
                "Pending representative_posture cannot contain a resolved executor, "
                "confirmation metadata, or evidence."
            )
        _require_string(
            representative_posture.get("basis"), "representative_posture.basis"
        )

    owners = _require_list(data.get("beneficial_owners"), "beneficial_owners")
    owner_ids: set[str] = set()
    for index, raw_owner in enumerate(owners):
        owner = _require_object(raw_owner, f"beneficial_owners[{index}]")
        owner_id = _require_reference(
            owner.get("owner_reference"),
            f"beneficial_owners[{index}].owner_reference",
        )
        if owner_id in owner_ids:
            raise ValidationError(f"Duplicate owner_reference {owner_id!r}.")
        owner_ids.add(owner_id)
        _require_string(
            owner.get("control_basis"),
            f"beneficial_owners[{index}].control_basis",
        )
        if owner.get("verification_status") not in {
            "unknown",
            "reported",
            "verified",
        }:
            raise ValidationError(
                f"beneficial_owners[{index}].verification_status is not supported."
            )
        owner_evidence = _validate_evidence_ids(
            owner.get("evidence_ids", []),
            f"beneficial_owners[{index}].evidence_ids",
            evidence_ids,
        )
        if owner.get("verification_status") == "verified" and not owner_evidence:
            raise ValidationError(
                f"beneficial_owners[{index}] cannot be verified without evidence."
            )
        _validate_identity_document(
            owner.get("identity_document"),
            f"beneficial_owners[{index}].identity_document",
            evidence_ids,
        )

    ownership_status = _require_object(data.get("ownership_status"), "ownership_status")
    expected_ownership_fields = {
        "status",
        "basis",
        "evidence_ids",
        "confirmed_by_role",
        "confirmed_at",
    }
    if set(ownership_status) != expected_ownership_fields:
        raise ValidationError(
            "ownership_status fields must be exactly: "
            + ", ".join(sorted(expected_ownership_fields))
        )
    ownership_state = ownership_status.get("status")
    if ownership_state not in {
        "owners_recorded",
        "none_confirmed",
        "not_applicable_confirmed",
        "pending",
    }:
        raise ValidationError("ownership_status.status is not supported.")
    ownership_evidence_ids = _validate_evidence_ids(
        ownership_status.get("evidence_ids", []),
        "ownership_status.evidence_ids",
        evidence_ids,
    )
    _require_string(ownership_status.get("basis"), "ownership_status.basis")
    if data["client_type"] in {"company", "entity"}:
        if ownership_state == "owners_recorded":
            if not owners:
                raise ValidationError(
                    "A company/entity with ownership_status=owners_recorded must "
                    "record at least one beneficial owner."
                )
            if not ownership_evidence_ids:
                raise ValidationError(
                    "ownership_status owners_recorded requires supporting evidence_ids."
                )
        elif ownership_state == "none_confirmed":
            if owners:
                raise ValidationError(
                    "ownership_status none_confirmed requires an empty "
                    "beneficial_owners list."
                )
            if ownership_status.get("confirmed_by_role") != "professional":
                raise ValidationError(
                    "ownership_status none_confirmed must be confirmed by the "
                    "professional."
                )
            _parse_timestamp(
                ownership_status.get("confirmed_at"),
                "ownership_status.confirmed_at",
            )
        elif ownership_state == "not_applicable_confirmed":
            raise ValidationError(
                "ownership_status not_applicable_confirmed is not valid for a "
                "company or entity."
            )
    elif ownership_state not in {"not_applicable_confirmed", "pending"}:
        raise ValidationError(
            "An individual/sole trader ownership_status must be "
            "not_applicable_confirmed or pending."
        )
    elif owners:
        raise ValidationError(
            "An individual/sole trader cannot record beneficial owners while its "
            "ownership_status is not_applicable_confirmed or pending."
        )
    if ownership_state in {"none_confirmed", "not_applicable_confirmed"}:
        if ownership_status.get("confirmed_by_role") != "professional":
            raise ValidationError(
                "Confirmed ownership_status must be confirmed_by_role=professional."
            )
        _parse_timestamp(
            ownership_status.get("confirmed_at"), "ownership_status.confirmed_at"
        )
    elif ownership_state == "pending":
        if (
            owners
            or ownership_evidence_ids
            or any(
                ownership_status.get(field) is not None
                for field in ("confirmed_by_role", "confirmed_at")
            )
        ):
            raise ValidationError(
                "Pending ownership_status cannot contain owners, evidence, or "
                "confirmation metadata."
            )
    elif any(
        ownership_status.get(field) is not None
        for field in ("confirmed_by_role", "confirmed_at")
    ):
        raise ValidationError(
            "ownership_status owners_recorded derives from recorded owners and must "
            "not claim a separate professional confirmation."
        )

    screening_results = _require_list(
        data.get("screening_results"), "screening_results"
    )
    if not screening_results:
        raise ValidationError(
            "screening_results must contain PEP, sanctions, and country records."
        )
    screening_ids: set[str] = set()
    found_screening_pairs: set[tuple[str, str]] = set()
    valid_subjects = {
        data["client_reference"],
        *representative_ids,
        *owner_ids,
    }
    for index, raw_screening in enumerate(screening_results):
        screening = _require_object(raw_screening, f"screening_results[{index}]")
        screening_id = _require_reference(
            screening.get("screening_id"),
            f"screening_results[{index}].screening_id",
        )
        if screening_id in screening_ids:
            raise ValidationError(f"Duplicate screening_id {screening_id!r}.")
        screening_ids.add(screening_id)
        subject_reference = _require_reference(
            screening.get("subject_reference"),
            f"screening_results[{index}].subject_reference",
        )
        if subject_reference not in valid_subjects:
            raise ValidationError(
                f"screening_results[{index}].subject_reference is not a registered "
                "party, representative, or beneficial owner reference."
            )
        screening_type = screening.get("screening_type")
        if screening_type not in SCREENING_TYPES:
            raise ValidationError(
                f"screening_results[{index}].screening_type is not supported."
            )
        screening_pair = (subject_reference, screening_type)
        if screening_pair in found_screening_pairs:
            raise ValidationError(
                "screening_results must not duplicate a subject/screening-type pair: "
                f"{subject_reference!r} / {screening_type!r}."
            )
        found_screening_pairs.add(screening_pair)
        if screening.get("source_reference") is not None:
            _require_string(
                screening.get("source_reference"),
                f"screening_results[{index}].source_reference",
            )
        if screening.get("checked_at") is not None:
            _parse_timestamp(
                screening.get("checked_at"),
                f"screening_results[{index}].checked_at",
            )
        if screening.get("outcome") not in {
            "clear",
            "potential_match",
            "confirmed_match",
            "unknown",
        }:
            raise ValidationError(
                f"screening_results[{index}].outcome is not supported."
            )
        if screening.get("review_status") not in {"proposed", "confirmed"}:
            raise ValidationError(
                f"screening_results[{index}].review_status is not supported."
            )
        screening_evidence = _validate_evidence_ids(
            screening.get("evidence_ids", []),
            f"screening_results[{index}].evidence_ids",
            evidence_ids,
        )
        if screening.get("review_status") == "confirmed" and not screening_evidence:
            raise ValidationError(
                f"screening_results[{index}] cannot be confirmed without evidence."
            )
        if screening.get("review_status") == "confirmed" and (
            screening.get("source_reference") is None
            or screening.get("checked_at") is None
        ):
            raise ValidationError(
                f"screening_results[{index}] confirmed screening requires a real "
                "source_reference and checked_at timestamp."
            )
        outcome = screening["outcome"]
        resolution = screening.get("professional_resolution")
        if outcome == "clear":
            if resolution is not None and resolution != {}:
                raise ValidationError(
                    f"screening_results[{index}].professional_resolution must be "
                    "null for a clear outcome."
                )
        else:
            resolution_data = _require_object(
                resolution,
                f"screening_results[{index}].professional_resolution",
            )
            resolution_status = resolution_data.get("status")
            if resolution_status not in {"unresolved", "confirmed"}:
                raise ValidationError(
                    f"screening_results[{index}].professional_resolution.status "
                    "must be unresolved or confirmed."
                )
            _require_string(
                resolution_data.get("basis"),
                f"screening_results[{index}].professional_resolution.basis",
            )
            relationship_decision = resolution_data.get("relationship_decision")
            resolution_evidence = _validate_evidence_ids(
                resolution_data.get("evidence_ids", []),
                f"screening_results[{index}].professional_resolution.evidence_ids",
                evidence_ids,
            )
            if resolution_status == "confirmed":
                if relationship_decision not in {
                    "proceed",
                    "proceed_with_controls",
                    "do_not_proceed",
                }:
                    raise ValidationError(
                        f"screening_results[{index}].professional_resolution."
                        "relationship_decision is required when confirmed."
                    )
                if resolution_data.get("confirmed_by_role") != "professional":
                    raise ValidationError(
                        f"screening_results[{index}].professional_resolution must "
                        "be confirmed_by_role=professional."
                    )
                _parse_timestamp(
                    resolution_data.get("confirmed_at"),
                    f"screening_results[{index}].professional_resolution.confirmed_at",
                )
                if not resolution_evidence:
                    raise ValidationError(
                        f"screening_results[{index}].professional_resolution cannot "
                        "be confirmed without evidence."
                    )
            elif any(
                resolution_data.get(field) not in {None, ""}
                for field in (
                    "relationship_decision",
                    "confirmed_by_role",
                    "confirmed_at",
                )
            ):
                raise ValidationError(
                    f"screening_results[{index}] unresolved professional_resolution "
                    "cannot contain confirmation metadata."
                )
    expected_screening_pairs = {
        (subject, screening_type)
        for subject in valid_subjects
        for screening_type in SCREENING_TYPES
    }
    if found_screening_pairs != expected_screening_pairs:
        missing_pairs = sorted(expected_screening_pairs - found_screening_pairs)
        raise ValidationError(
            "screening_results must contain exactly one PEP, sanctions, and country "
            "record for every client, representative, and beneficial owner; missing: "
            + ", ".join(f"{subject}/{kind}" for subject, kind in missing_pairs)
        )

    engagement = _require_object(data.get("engagement"), "engagement")
    if engagement.get("kind") not in {"ongoing", "one_off"}:
        raise ValidationError("engagement.kind must be ongoing or one_off.")
    _parse_date(engagement.get("start_date"), "engagement.start_date")
    services = _require_list(engagement.get("services"), "engagement.services")
    if not services:
        raise ValidationError("engagement.services must contain at least one service.")
    service_ids: set[str] = set()
    for index, raw_service in enumerate(services):
        service = _require_object(raw_service, f"engagement.services[{index}]")
        service_id = _require_reference(
            service.get("service_id"), f"engagement.services[{index}].service_id"
        )
        if service_id in service_ids:
            raise ValidationError(f"Duplicate service_id {service_id!r}.")
        service_ids.add(service_id)
        _require_string(
            service.get("description"), f"engagement.services[{index}].description"
        )
        if service.get("assessment_status") not in {"proposed", "confirmed"}:
            raise ValidationError(
                f"engagement.services[{index}].assessment_status is not supported."
            )
    terms = _require_object(engagement.get("terms"), "engagement.terms")
    if terms.get("review_status") not in {"proposed", "confirmed", "incomplete"}:
        raise ValidationError("engagement.terms.review_status is not supported.")
    for numeric_field in ("duration_months", "notice_days"):
        value = terms.get(numeric_field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValidationError(
                f"engagement.terms.{numeric_field} must be a non-negative integer or null."
            )
    advance = terms.get("advance_amount")
    if advance is not None:
        try:
            if Decimal(str(advance)) < 0:
                raise ValidationError(
                    "engagement.terms.advance_amount must not be negative."
                )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError(
                "engagement.terms.advance_amount must be numeric or null."
            ) from exc
    _require_string(terms.get("currency", "EUR"), "engagement.terms.currency")
    for text_field in (
        "payment_terms",
        "indexation_basis",
        "insurance_reference",
    ):
        if terms.get(text_field) is not None:
            _require_string(terms.get(text_field), f"engagement.terms.{text_field}")
    if terms.get("review_status") == "confirmed" and all(
        terms.get(field) in {None, ""}
        for field in (
            "duration_months",
            "notice_days",
            "advance_amount",
            "payment_terms",
            "indexation_basis",
            "insurance_reference",
        )
    ):
        raise ValidationError(
            "Confirmed engagement terms must record at least one substantive term."
        )

    privacy_decisions = _require_list(
        data.get("privacy_processing_decisions"), "privacy_processing_decisions"
    )
    if not privacy_decisions:
        raise ValidationError(
            "privacy_processing_decisions must contain at least one processing purpose."
        )
    privacy_ids: set[str] = set()
    legal_basis_codes = {
        "consent",
        "contract",
        "legal_obligation",
        "vital_interests",
        "public_task",
        "legitimate_interests",
    }
    for index, raw_decision in enumerate(privacy_decisions):
        decision = _require_object(
            raw_decision, f"privacy_processing_decisions[{index}]"
        )
        decision_id = _require_reference(
            decision.get("decision_id"),
            f"privacy_processing_decisions[{index}].decision_id",
        )
        if decision_id in privacy_ids:
            raise ValidationError(f"Duplicate privacy decision ID {decision_id!r}.")
        privacy_ids.add(decision_id)
        _require_string(
            decision.get("purpose"),
            f"privacy_processing_decisions[{index}].purpose",
        )
        role = decision.get("role")
        if role not in {
            "controller",
            "processor",
            "joint_controller",
            "undetermined",
        }:
            raise ValidationError(
                f"privacy_processing_decisions[{index}].role is not supported."
            )
        legal_basis = decision.get("controller_legal_basis")
        processor_authority = decision.get("processor_authority_reference")
        if role in {"controller", "joint_controller"}:
            legal_basis_data = _require_object(
                legal_basis,
                f"privacy_processing_decisions[{index}].controller_legal_basis",
            )
            if legal_basis_data.get("code") not in legal_basis_codes:
                raise ValidationError(
                    f"privacy_processing_decisions[{index}].controller_legal_basis."
                    "code is not supported."
                )
            _require_string(
                legal_basis_data.get("basis"),
                f"privacy_processing_decisions[{index}].controller_legal_basis.basis",
            )
            if processor_authority is not None:
                raise ValidationError(
                    f"privacy_processing_decisions[{index}]."
                    "processor_authority_reference must be null for a controller role."
                )
        elif role == "processor":
            if legal_basis is not None:
                raise ValidationError(
                    f"privacy_processing_decisions[{index}].controller_legal_basis "
                    "must be null for a processor role."
                )
            _require_string(
                processor_authority,
                f"privacy_processing_decisions[{index}]."
                "processor_authority_reference",
            )
        else:
            if legal_basis is not None or processor_authority is not None:
                raise ValidationError(
                    f"privacy_processing_decisions[{index}] cannot record a legal "
                    "basis or processor authority while the role is undetermined."
                )
        retention = _require_object(
            decision.get("retention"),
            f"privacy_processing_decisions[{index}].retention",
        )
        retention_status = retention.get("status")
        if retention_status not in {"defined", "undetermined"}:
            raise ValidationError(
                f"privacy_processing_decisions[{index}].retention.status must be "
                "defined or undetermined."
            )
        if retention_status == "defined":
            _require_string(
                retention.get("period_or_criteria"),
                f"privacy_processing_decisions[{index}].retention.period_or_criteria",
            )
        elif retention.get("period_or_criteria") is not None:
            raise ValidationError(
                f"privacy_processing_decisions[{index}].retention."
                "period_or_criteria must be null when undetermined."
            )
        source_ids = _require_list(
            decision.get("source_ids"),
            f"privacy_processing_decisions[{index}].source_ids",
        )
        for source_index, source_id in enumerate(source_ids):
            _require_reference(
                source_id,
                f"privacy_processing_decisions[{index}].source_ids[{source_index}]",
            )
        if len(source_ids) != len(set(source_ids)):
            raise ValidationError(
                f"privacy_processing_decisions[{index}].source_ids must be unique."
            )
        review_status = decision.get("review_status")
        if review_status not in {"proposed", "confirmed"}:
            raise ValidationError(
                f"privacy_processing_decisions[{index}].review_status is not supported."
            )
        if review_status == "confirmed":
            if role == "undetermined" or retention_status != "defined":
                raise ValidationError(
                    f"privacy_processing_decisions[{index}] cannot be confirmed "
                    "until role and retention are resolved."
                )
            if not source_ids:
                raise ValidationError(
                    f"privacy_processing_decisions[{index}] cannot be confirmed "
                    "without source_ids."
                )
            if decision.get("confirmed_by_role") != "professional":
                raise ValidationError(
                    f"privacy_processing_decisions[{index}] must be "
                    "confirmed_by_role=professional."
                )
            _parse_timestamp(
                decision.get("confirmed_at"),
                f"privacy_processing_decisions[{index}].confirmed_at",
            )
        elif (
            decision.get("confirmed_by_role") is not None
            or decision.get("confirmed_at") is not None
        ):
            raise ValidationError(
                f"privacy_processing_decisions[{index}] proposed confirmation "
                "metadata must be null."
            )

    marketing = _require_object(data.get("marketing_consent"), "marketing_consent")
    if marketing.get("scope") != "marketing_only":
        raise ValidationError("marketing_consent.scope must be marketing_only.")
    request_status = marketing.get("request_status")
    if request_status not in {"not_requested", "requested"}:
        raise ValidationError(
            "marketing_consent.request_status must be not_requested or requested."
        )
    purposes = _require_list(marketing.get("purposes"), "marketing_consent.purposes")
    channels = _require_list(marketing.get("channels"), "marketing_consent.channels")
    for field, values in (("purposes", purposes), ("channels", channels)):
        for index, value in enumerate(values):
            _require_string(value, f"marketing_consent.{field}[{index}]")
        if len(values) != len(set(values)):
            raise ValidationError(f"marketing_consent.{field} must be unique.")
    marketing_evidence = _validate_evidence_ids(
        marketing.get("evidence_ids", []),
        "marketing_consent.evidence_ids",
        evidence_ids,
    )
    choice = marketing.get("choice")
    marketing_review_status = marketing.get("review_status")
    if request_status == "not_requested":
        if (
            choice is not None
            or purposes
            or channels
            or marketing_evidence
            or marketing_review_status != "not_required"
            or marketing.get("requested_at") is not None
            or marketing.get("recorded_at") is not None
            or marketing.get("withdrawn_at") is not None
            or marketing.get("confirmed_by_role") is not None
            or marketing.get("confirmed_at") is not None
        ):
            raise ValidationError(
                "A not_requested marketing consent must have no choice, purposes, "
                "channels, evidence, or review metadata."
            )
    else:
        if not purposes or not channels:
            raise ValidationError(
                "A requested marketing consent requires purposes and channels."
            )
        _parse_timestamp(
            marketing.get("requested_at"), "marketing_consent.requested_at"
        )
        if marketing_review_status not in {"proposed", "confirmed"}:
            raise ValidationError(
                "Requested marketing_consent.review_status must be proposed or confirmed."
            )
        if marketing_review_status == "confirmed":
            if choice not in {"granted", "refused", "withdrawn"}:
                raise ValidationError(
                    "Confirmed marketing_consent.choice must be granted, refused, "
                    "or withdrawn."
                )
            recorded_at = _parse_timestamp(
                marketing.get("recorded_at"), "marketing_consent.recorded_at"
            )
            if not marketing_evidence:
                raise ValidationError(
                    "Confirmed marketing_consent requires recorded evidence."
                )
            if choice == "withdrawn":
                withdrawn_at = _parse_timestamp(
                    marketing.get("withdrawn_at"),
                    "marketing_consent.withdrawn_at",
                )
                if withdrawn_at < recorded_at:
                    raise ValidationError(
                        "marketing_consent.withdrawn_at must not precede recorded_at."
                    )
            elif marketing.get("withdrawn_at") is not None:
                raise ValidationError(
                    "marketing_consent.withdrawn_at is only valid for a withdrawn choice."
                )
            if marketing.get("confirmed_by_role") != "professional":
                raise ValidationError(
                    "Confirmed marketing_consent must be "
                    "confirmed_by_role=professional."
                )
            _parse_timestamp(
                marketing.get("confirmed_at"), "marketing_consent.confirmed_at"
            )
        elif (
            choice is not None
            or marketing.get("recorded_at") is not None
            or marketing.get("withdrawn_at") is not None
            or marketing.get("confirmed_by_role") is not None
            or marketing.get("confirmed_at") is not None
        ):
            raise ValidationError(
                "Proposed marketing_consent cannot contain a choice or confirmation "
                "metadata."
            )

    applicability = _require_list(data.get("applicability"), "applicability")
    topics: set[str] = set()
    for index, raw_record in enumerate(applicability):
        record = _require_object(raw_record, f"applicability[{index}]")
        topic = _require_string(record.get("topic"), f"applicability[{index}].topic")
        if topic not in APPLICABILITY_TOPICS:
            raise ValidationError(f"Unsupported applicability topic {topic!r}.")
        if topic in topics:
            raise ValidationError(f"Duplicate applicability topic {topic!r}.")
        topics.add(topic)
        if record.get("applicability_status") not in {
            "applicable",
            "not_applicable",
            "unclear",
        }:
            raise ValidationError(
                f"applicability[{index}].applicability_status is not supported."
            )
        if record.get("review_status") not in {"proposed", "confirmed"}:
            raise ValidationError(
                f"applicability[{index}].review_status is not supported."
            )
        _validate_professional_confirmation(
            record,
            status_field="review_status",
            field=f"applicability[{index}]",
        )
        _require_string(record.get("basis"), f"applicability[{index}].basis")
        source_ids = _require_list(
            record.get("source_ids", []), f"applicability[{index}].source_ids"
        )
        for source_index, source_id in enumerate(source_ids):
            _require_reference(
                source_id, f"applicability[{index}].source_ids[{source_index}]"
            )
        case_fact_ids = _require_list(
            record.get("case_fact_ids", []),
            f"applicability[{index}].case_fact_ids",
        )
        if not case_fact_ids:
            raise ValidationError(
                f"applicability[{index}].case_fact_ids must identify the case facts "
                "supporting the proposal."
            )
        for fact_index, fact_id in enumerate(case_fact_ids):
            reference = _require_reference(
                fact_id, f"applicability[{index}].case_fact_ids[{fact_index}]"
            )
            if reference not in party_fact_ids:
                raise ValidationError(
                    f"applicability[{index}].case_fact_ids[{fact_index}] refers to "
                    f"unknown party fact {reference!r}."
                )
        if len(case_fact_ids) != len(set(case_fact_ids)):
            raise ValidationError(
                f"applicability[{index}].case_fact_ids must be unique."
            )
    if topics != set(APPLICABILITY_TOPICS):
        missing = sorted(set(APPLICABILITY_TOPICS) - topics)
        raise ValidationError(
            "applicability must include every required topic; missing: "
            + ", ".join(missing)
        )

    template_references = _require_list(
        data.get("template_references", []), "template_references"
    )
    template_topics: set[str] = set()
    template_ids: set[str] = set()
    for index, raw_template in enumerate(template_references):
        template = _require_object(raw_template, f"template_references[{index}]")
        topic = _require_string(
            template.get("document_type"),
            f"template_references[{index}].document_type",
        )
        if topic not in APPLICABILITY_TOPICS:
            raise ValidationError(
                f"template_references[{index}].document_type is not supported."
            )
        if topic in template_topics:
            raise ValidationError(f"Duplicate template reference for {topic!r}.")
        template_topics.add(topic)
        template_id = _require_reference(
            template.get("template_id"),
            f"template_references[{index}].template_id",
        )
        if template_id in template_ids:
            raise ValidationError(f"Duplicate template_id {template_id!r}.")
        template_ids.add(template_id)
        _require_string(
            template.get("version"), f"template_references[{index}].version"
        )
        _require_string(
            template.get("local_path"), f"template_references[{index}].local_path"
        )
        _require_sha256(template.get("sha256"), f"template_references[{index}].sha256")
        template_source_ids = _require_list(
            template.get("source_ids"), f"template_references[{index}].source_ids"
        )
        for source_index, source_id in enumerate(template_source_ids):
            _require_reference(
                source_id,
                f"template_references[{index}].source_ids[{source_index}]",
            )
        if len(template_source_ids) != len(set(template_source_ids)):
            raise ValidationError(
                f"template_references[{index}].source_ids must be unique."
            )
        _require_sha256(
            template.get("source_basis_sha256"),
            f"template_references[{index}].source_basis_sha256",
        )
        approval_status = template.get("approval_status")
        if approval_status not in {"approved", "pending", "withdrawn"}:
            raise ValidationError(
                f"template_references[{index}].approval_status is not supported."
            )
        if approval_status in {"approved", "withdrawn"}:
            if template.get("approved_by_role") != "professional":
                raise ValidationError(
                    f"template_references[{index}] must be "
                    "approved_by_role=professional when approved."
                )
            approved_at = _parse_timestamp(
                template.get("approved_at"),
                f"template_references[{index}].approved_at",
            )
            if approval_status == "withdrawn":
                withdrawn_at = _parse_timestamp(
                    template.get("approval_withdrawn_at"),
                    f"template_references[{index}].approval_withdrawn_at",
                )
                if withdrawn_at < approved_at:
                    raise ValidationError(
                        f"template_references[{index}].approval_withdrawn_at must "
                        "not precede approved_at."
                    )
            elif template.get("approval_withdrawn_at") is not None:
                raise ValidationError(
                    f"template_references[{index}].approval_withdrawn_at is only "
                    "valid for withdrawn approval."
                )
        elif (
            template.get("approved_by_role") is not None
            or template.get("approved_at") is not None
            or template.get("approval_withdrawn_at") is not None
        ):
            raise ValidationError(
                f"template_references[{index}] pending approval metadata "
                "must be null."
            )
        if template.get("reuse_status") not in {
            "studio_owned",
            "licensed_for_client_use",
            "reference_only",
            "prohibited",
            "unknown",
        }:
            raise ValidationError(
                f"template_references[{index}].reuse_status is not supported."
            )
        if template.get("reuse_scope") not in {None, "single_case", "studio_clients"}:
            raise ValidationError(
                f"template_references[{index}].reuse_scope is not supported."
            )
        _require_string(
            template.get("jurisdiction"),
            f"template_references[{index}].jurisdiction",
        )
        _require_string(
            template.get("language"), f"template_references[{index}].language"
        )
        valid_from = _parse_date(
            template.get("valid_from"), f"template_references[{index}].valid_from"
        )
        if template.get("valid_until") is not None:
            valid_until = _parse_date(
                template.get("valid_until"),
                f"template_references[{index}].valid_until",
            )
            if valid_until < valid_from:
                raise ValidationError(
                    f"template_references[{index}].valid_until must not precede "
                    "valid_from."
                )
        review_due_on = _parse_date(
            template.get("review_due_on"),
            f"template_references[{index}].review_due_on",
        )
        if review_due_on < valid_from:
            raise ValidationError(
                f"template_references[{index}].review_due_on must not precede "
                "valid_from."
            )

    aml = _require_object(data.get("aml"), "aml")
    _parse_date(aml.get("assessment_date"), "aml.assessment_date")
    _decimal_score(aml.get("inherent_risk"), "aml.inherent_risk")
    if aml.get("inherent_risk_status") not in {"proposed", "confirmed"}:
        raise ValidationError("aml.inherent_risk_status must be proposed or confirmed.")
    mode = aml.get("section_b_mode")
    if mode not in {"full", "excluded_confirmed"}:
        raise ValidationError("aml.section_b_mode must be full or excluded_confirmed.")
    confirmation = aml.get("section_b_exclusion_confirmation")
    if mode == "excluded_confirmed":
        confirmation_data = _require_object(
            confirmation, "aml.section_b_exclusion_confirmation"
        )
        if confirmation_data.get("confirmed") is not True:
            raise ValidationError("Section B can be excluded only with confirmed=true.")
        _require_string(
            confirmation_data.get("reason"),
            "aml.section_b_exclusion_confirmation.reason",
        )
        if confirmation_data.get("confirmed_by_role") != "professional":
            raise ValidationError(
                "Section B exclusion must be confirmed_by_role=professional."
            )
        _parse_timestamp(
            confirmation_data.get("confirmed_at"),
            "aml.section_b_exclusion_confirmation.confirmed_at",
        )
    elif confirmation is not None and confirmation != {}:
        raise ValidationError(
            "aml.section_b_exclusion_confirmation must be null in full mode."
        )
    _validate_factor_group(
        aml.get("factors_a"),
        expected_ids=AML_A_FACTOR_IDS,
        field="aml.factors_a",
        allow_null_scores=False,
        known_evidence_ids=evidence_ids,
    )
    _validate_factor_group(
        aml.get("factors_b"),
        expected_ids=AML_B_FACTOR_IDS,
        field="aml.factors_b",
        allow_null_scores=mode == "excluded_confirmed",
        known_evidence_ids=evidence_ids,
    )
    if mode == "excluded_confirmed":
        for index, factor in enumerate(aml["factors_b"]):
            if factor.get("score") is not None:
                raise ValidationError(
                    f"aml.factors_b[{index}].score must be null when Section B is excluded."
                )
    triggers = _require_list(
        aml.get("mandatory_enhanced_triggers"),
        "aml.mandatory_enhanced_triggers",
    )
    if len(triggers) != len(AML_TRIGGER_IDS):
        raise ValidationError(
            "aml.mandatory_enhanced_triggers must contain exactly three records."
        )
    found_triggers: set[str] = set()
    for index, raw_trigger in enumerate(triggers):
        trigger = _require_object(
            raw_trigger, f"aml.mandatory_enhanced_triggers[{index}]"
        )
        trigger_id = _require_string(
            trigger.get("trigger_id"),
            f"aml.mandatory_enhanced_triggers[{index}].trigger_id",
        )
        if trigger_id not in AML_TRIGGER_IDS or trigger_id in found_triggers:
            raise ValidationError(
                "aml.mandatory_enhanced_triggers must contain each supported "
                "trigger exactly once."
            )
        found_triggers.add(trigger_id)
        if trigger.get("status") not in {"yes", "no", "unknown"}:
            raise ValidationError(
                f"aml.mandatory_enhanced_triggers[{index}].status is not supported."
            )
        if trigger.get("review_status") not in {"proposed", "confirmed"}:
            raise ValidationError(
                f"aml.mandatory_enhanced_triggers[{index}].review_status is not supported."
            )
        _validate_professional_confirmation(
            trigger,
            status_field="review_status",
            field=f"aml.mandatory_enhanced_triggers[{index}]",
        )
        _require_string(
            trigger.get("basis"),
            f"aml.mandatory_enhanced_triggers[{index}].basis",
        )
        _validate_evidence_ids(
            trigger.get("evidence_ids", []),
            f"aml.mandatory_enhanced_triggers[{index}].evidence_ids",
            evidence_ids,
        )
    if found_triggers != set(AML_TRIGGER_IDS):
        raise ValidationError(
            "aml.mandatory_enhanced_triggers must contain all supported triggers."
        )
    table_1 = _require_object(aml.get("table_1_assessment"), "aml.table_1_assessment")
    table_1_status = table_1.get("status")
    if table_1_status not in {"yes", "no", "unknown"}:
        raise ValidationError("aml.table_1_assessment.status is not supported.")
    table_1_review_status = table_1.get("review_status")
    if table_1_review_status not in {"proposed", "confirmed"}:
        raise ValidationError("aml.table_1_assessment.review_status is not supported.")
    _require_string(table_1.get("basis"), "aml.table_1_assessment.basis")
    confirmed_by_role = table_1.get("confirmed_by_role")
    confirmed_at = table_1.get("confirmed_at")
    if table_1_review_status == "confirmed":
        if table_1_status == "unknown":
            raise ValidationError(
                "A confirmed Table 1 assessment must resolve status to yes or no."
            )
        if confirmed_by_role != "professional":
            raise ValidationError(
                "Table 1 assessment must be confirmed_by_role=professional."
            )
        _parse_timestamp(confirmed_at, "aml.table_1_assessment.confirmed_at")
    elif confirmed_by_role is not None or confirmed_at is not None:
        raise ValidationError(
            "Proposed Table 1 assessment confirmation fields must be null."
        )
    current_mode = aml.get("current_verification_mode")
    if current_mode not in {
        None,
        "conduct_rule",
        "simplified",
        "ordinary",
        "enhanced",
    }:
        raise ValidationError("aml.current_verification_mode is not supported.")
    interval = aml.get("enhanced_review_interval_months")
    if interval not in {None, 6, 12}:
        raise ValidationError(
            "aml.enhanced_review_interval_months must be 6, 12, or null."
        )
    return data


def load_source_registry(path: Path) -> dict[str, Any]:
    """Load and validate the versioned source registry."""

    registry = load_json(path)
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError("Source registry schema_version is unsupported.")
    if registry.get("jurisdiction") != "IT":
        raise ValidationError(
            "The bundled professional-setup source registry must declare "
            "jurisdiction=IT."
        )
    if registry.get("country_pack") != ITALY_COUNTRY_PACK:
        raise ValidationError(
            "The bundled source registry does not identify the supported Italy "
            "country pack."
        )
    currentness = _require_object(
        registry.get("currentness"), "source_registry.currentness"
    )
    if currentness.get("status") != "verified_current":
        raise ValidationError(
            "source_registry.currentness.status must be verified_current."
        )
    reviewed_on = _parse_date(
        currentness.get("reviewed_on"), "source_registry.currentness.reviewed_on"
    )
    review_by = _parse_date(
        currentness.get("review_by"), "source_registry.currentness.review_by"
    )
    if review_by < reviewed_on:
        raise ValidationError(
            "source_registry.currentness.review_by must not precede reviewed_on."
        )
    if registry.get("last_reviewed") != reviewed_on.isoformat():
        raise ValidationError(
            "source_registry.last_reviewed must match currentness.reviewed_on."
        )
    sources = _require_list(registry.get("sources"), "source_registry.sources")
    if not sources:
        raise ValidationError("Source registry must contain at least one source.")
    source_ids: set[str] = set()
    for index, raw_source in enumerate(sources):
        source = _require_object(raw_source, f"source_registry.sources[{index}]")
        source_id = _require_reference(
            source.get("source_id"), f"source_registry.sources[{index}].source_id"
        )
        if source_id in source_ids:
            raise ValidationError(f"Duplicate source_id {source_id!r}.")
        source_ids.add(source_id)
        for field in ("title", "issuer", "version", "source_type", "url"):
            _require_string(
                source.get(field), f"source_registry.sources[{index}].{field}"
            )
        if source.get("authority") not in {
            "binding_law",
            "official_professional_guidance",
            "official_operational_material",
        }:
            raise ValidationError(
                f"source_registry.sources[{index}].authority is unsupported."
            )
        if source.get("effective_date") is not None:
            _parse_date(
                source.get("effective_date"),
                f"source_registry.sources[{index}].effective_date",
            )
        _require_string(
            source.get("use_constraint"),
            f"source_registry.sources[{index}].use_constraint",
        )
    return registry


def build_temporal_validity(
    facts: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    *,
    generated_at: str,
    document_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive the inclusive Apply horizon from explicit material deadlines.

    Date comparison is deterministic because expiry and review-by dates are
    mechanically verifiable validity boundaries. No legal applicability or
    source-quality judgment is inferred here.
    """

    evaluated_on = _parse_date(generated_at[:10], "generated_at date")
    deadlines: dict[str, list[date]] = {
        "authoritative_source_registry_review_by": [],
        "evidence_expires_on": [],
        "primary_identity_expires_on": [],
        "representative_identity_expires_on": [],
        "beneficial_owner_identity_expires_on": [],
        "template_valid_until": [],
        "template_review_due_on": [],
    }
    currentness = _require_object(
        source_registry.get("currentness"), "source_registry.currentness"
    )
    if currentness.get("status") != "verified_current":
        raise ValidationError(
            "source_registry.currentness.status must be verified_current."
        )
    deadlines["authoritative_source_registry_review_by"].append(
        _parse_date(
            currentness.get("review_by"),
            "source_registry.currentness.review_by",
        )
    )

    for index, evidence in enumerate(
        _require_list(facts.get("evidence_register"), "evidence_register")
    ):
        expires_on = _require_object(evidence, f"evidence_register[{index}]").get(
            "expires_on"
        )
        if expires_on is not None:
            deadlines["evidence_expires_on"].append(
                _parse_date(expires_on, f"evidence_register[{index}].expires_on")
            )

    primary_identity = _require_object(
        facts.get("party_identity_document"), "party_identity_document"
    )
    if primary_identity.get("expires_on") is not None:
        deadlines["primary_identity_expires_on"].append(
            _parse_date(
                primary_identity["expires_on"],
                "party_identity_document.expires_on",
            )
        )

    for index, representative in enumerate(
        _require_list(facts.get("representatives"), "representatives")
    ):
        identity = _require_object(
            _require_object(representative, f"representatives[{index}]").get(
                "identity_document"
            ),
            f"representatives[{index}].identity_document",
        )
        if identity.get("expires_on") is not None:
            deadlines["representative_identity_expires_on"].append(
                _parse_date(
                    identity["expires_on"],
                    f"representatives[{index}].identity_document.expires_on",
                )
            )

    for index, owner in enumerate(
        _require_list(facts.get("beneficial_owners"), "beneficial_owners")
    ):
        identity = _require_object(
            _require_object(owner, f"beneficial_owners[{index}]").get(
                "identity_document"
            ),
            f"beneficial_owners[{index}].identity_document",
        )
        if identity.get("expires_on") is not None:
            deadlines["beneficial_owner_identity_expires_on"].append(
                _parse_date(
                    identity["expires_on"],
                    f"beneficial_owners[{index}].identity_document.expires_on",
                )
            )

    if document_plan is None:
        template_records = _require_list(
            facts.get("template_references"), "template_references"
        )
    else:
        template_records = []
        for index, raw_document in enumerate(
            _require_list(document_plan.get("documents"), "document_plan.documents")
        ):
            document = _require_object(
                raw_document, f"document_plan.documents[{index}]"
            )
            template = document.get("template_reference")
            if template is not None:
                template_records.append(
                    _require_object(
                        template,
                        f"document_plan.documents[{index}].template_reference",
                    )
                )
    for index, template in enumerate(template_records):
        template_data = _require_object(template, f"template_references[{index}]")
        if template_data.get("valid_until") is not None:
            deadlines["template_valid_until"].append(
                _parse_date(
                    template_data["valid_until"],
                    f"template_references[{index}].valid_until",
                )
            )
        deadlines["template_review_due_on"].append(
            _parse_date(
                template_data.get("review_due_on"),
                f"template_references[{index}].review_due_on",
            )
        )

    deadline_summaries = [
        {
            "kind": kind,
            "count": len(values),
            "valid_through": min(values).isoformat(),
        }
        for kind, values in deadlines.items()
        if values
    ]
    all_deadlines = [value for values in deadlines.values() for value in values]
    valid_through = min(all_deadlines)
    return {
        "policy": TEMPORAL_VALIDITY_POLICY,
        "evaluated_on": evaluated_on.isoformat(),
        "valid_through": valid_through.isoformat(),
        "deadline_count": len(all_deadlines),
        "deadlines": deadline_summaries,
        "source_currentness_status": currentness["status"],
        "apply_rule": TEMPORAL_APPLY_RULE,
    }


def validate_source_references(
    intake: Mapping[str, Any], registry: Mapping[str, Any]
) -> None:
    """Ensure every source-backed decision cites only registered sources."""

    if intake["jurisdiction"] != registry["jurisdiction"]:
        raise ValidationError(
            "The source registry jurisdiction does not match the new-client intake."
        )

    known = {source["source_id"] for source in registry["sources"]}
    for record in intake["applicability"]:
        unknown = sorted(set(record.get("source_ids", [])) - known)
        if unknown:
            raise ValidationError(
                f"Applicability topic {record['topic']!r} cites unknown sources: "
                + ", ".join(unknown)
            )
    for decision in intake["privacy_processing_decisions"]:
        unknown = sorted(set(decision.get("source_ids", [])) - known)
        if unknown:
            raise ValidationError(
                f"Privacy decision {decision['decision_id']!r} cites unknown sources: "
                + ", ".join(unknown)
            )
    for template in intake["template_references"]:
        unknown = sorted(set(template.get("source_ids", [])) - known)
        if unknown:
            raise ValidationError(
                f"Template reference {template['template_id']!r} cites unknown "
                "sources: " + ", ".join(unknown)
            )


def verify_evidence_register(
    intake: Mapping[str, Any], *, base_dir: Path
) -> list[dict[str, Any]]:
    """Verify bytes for every evidence record represented as locally held."""

    results: list[dict[str, Any]] = []
    for record in intake["evidence_register"]:
        result: dict[str, Any] = {
            "evidence_id": record["evidence_id"],
            "declared_status": record["status"],
            "byte_verification_status": "not_required_for_declared_status",
        }
        if record["status"] in {"verified", "available"}:
            resolved = _resolve_local_file(
                record.get("local_path"),
                field=f"evidence_register[{record['evidence_id']}].local_path",
                base_dir=base_dir,
            )
            expected_hash = _require_sha256(
                record.get("sha256"),
                f"evidence_register[{record['evidence_id']}].sha256",
            )
            actual_hash = sha256_file(resolved)
            if actual_hash != expected_hash:
                raise ValidationError(
                    f"Evidence hash mismatch for {record['evidence_id']!r}."
                )
            result.update(
                {
                    "byte_verification_status": "hash_verified",
                    "resolved_path": resolved.as_posix(),
                    "sha256": actual_hash,
                    "size_bytes": resolved.stat().st_size,
                }
            )
        results.append(result)
    return results


def _review_records_by_item_id(
    value: Any,
    *,
    field: str,
    expected_item_ids: set[str],
) -> dict[str, Mapping[str, Any]]:
    records = _require_list(value, field)
    by_item_id: dict[str, Mapping[str, Any]] = {}
    for index, raw_record in enumerate(records):
        record = _require_object(raw_record, f"{field}[{index}]")
        item_id = _require_reference(record.get("item_id"), f"{field}[{index}].item_id")
        if item_id in by_item_id:
            raise ValidationError(f"{field} contains duplicate item_id {item_id!r}.")
        if item_id not in expected_item_ids:
            raise ValidationError(
                f"{field}[{index}].item_id does not reference a real review item."
            )
        by_item_id[item_id] = record
    if set(by_item_id) != expected_item_ids:
        missing = sorted(expected_item_ids - set(by_item_id))
        raise ValidationError(
            f"{field} must cover every review item exactly once; missing: "
            + ", ".join(missing)
        )
    return by_item_id


def _require_exact_review_count(value: Any, *, field: str, expected: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise ValidationError(f"{field} must equal {expected}.")


def _verify_client_file_preparation_review_provenance(
    *,
    manifest: Mapping[str, Any],
    run_dir: Path,
    bound_run_id: str,
    outputs_by_path: Mapping[str, Mapping[str, Any]],
    review_application: Mapping[str, Any],
) -> None:
    """Fail closed on final-ready phase-one reviewer and coverage provenance."""

    review_payload = load_json(run_dir / "review_payload.json")
    ui_decisions = load_json(run_dir / "ui_decisions.json")
    applied_decisions = load_json(run_dir / "applied_decisions.json")
    for field, payload in (
        ("review_payload", review_payload),
        ("ui_decisions", ui_decisions),
        ("applied_decisions", applied_decisions),
    ):
        if (
            payload.get("plugin") != "client-file-preparation"
            or payload.get("workflow") != "client-file-preparation"
            or payload.get("run_id") != bound_run_id
        ):
            raise ValidationError(
                f"Bound {field}.json identity does not match the final-ready manifest."
            )

    raw_items = _require_list(review_payload.get("items"), "bound_review_payload.items")
    if not raw_items:
        raise ValidationError("Bound review_payload.items must not be empty.")
    items_by_id: dict[str, Mapping[str, Any]] = {}
    for index, raw_item in enumerate(raw_items):
        item = _require_object(raw_item, f"bound_review_payload.items[{index}]")
        item_id = _require_reference(
            item.get("id"), f"bound_review_payload.items[{index}].id"
        )
        if item_id in items_by_id:
            raise ValidationError(
                f"Bound review_payload.items contains duplicate id {item_id!r}."
            )
        _require_reference(
            item.get("item_type"),
            f"bound_review_payload.items[{index}].item_type",
        )
        items_by_id[item_id] = item
    item_count = len(items_by_id)
    _require_exact_review_count(
        review_payload.get("item_count"),
        field="bound_review_payload.item_count",
        expected=item_count,
    )

    reviewer = _require_reference(
        applied_decisions.get("reviewer"), "bound_applied_decisions.reviewer"
    )
    if (
        _require_reference(ui_decisions.get("reviewer"), "bound_ui_decisions.reviewer")
        != reviewer
    ):
        raise ValidationError(
            "Bound ui_decisions and applied_decisions must use the same stable reviewer alias."
        )

    expected_item_ids = set(items_by_id)
    ui_by_id = _review_records_by_item_id(
        ui_decisions.get("decisions"),
        field="bound_ui_decisions.decisions",
        expected_item_ids=expected_item_ids,
    )
    applied_by_id = _review_records_by_item_id(
        applied_decisions.get("decisions"),
        field="bound_applied_decisions.decisions",
        expected_item_ids=expected_item_ids,
    )
    effects_by_id = _review_records_by_item_id(
        applied_decisions.get("effects"),
        field="bound_applied_decisions.effects",
        expected_item_ids=expected_item_ids,
    )
    for item_id, item in items_by_id.items():
        ui_action = ui_by_id[item_id].get("action")
        applied_action = applied_by_id[item_id].get("action")
        effect = effects_by_id[item_id]
        if ui_action not in {"accept", "edit"}:
            raise ValidationError(
                "Final-ready phase-one decisions may contain only accept or edit actions."
            )
        if applied_action != ui_action or effect.get("action") != ui_action:
            raise ValidationError(
                f"Decision/effect action mismatch for phase-one review item {item_id!r}."
            )
        for field, record in (
            ("ui_decisions", ui_by_id[item_id]),
            ("applied_decisions", applied_by_id[item_id]),
        ):
            if record.get("item_type") != item.get("item_type"):
                raise ValidationError(
                    f"{field} item_type mismatch for phase-one review item {item_id!r}."
                )
        if effect.get("item_type") != item.get("item_type"):
            raise ValidationError(
                f"Effect item_type mismatch for phase-one review item {item_id!r}."
            )
        if effect.get("applied") is not True:
            raise ValidationError(
                f"Effect for phase-one review item {item_id!r} must be marked applied."
            )
        review_records = (
            ("ui_decisions", ui_by_id[item_id]),
            ("applied_decisions", applied_by_id[item_id]),
            ("effect", effect),
        )
        if ui_action == "edit":
            # Exact equality is an audit boundary: promotion must consume the same
            # replacement the reviewer saved, applied, and sealed as an effect.
            edit_values: list[str] = []
            for field, record in review_records:
                edit_value = record.get("edit_value")
                if not isinstance(edit_value, str) or not edit_value.strip():
                    raise ValidationError(
                        f"{field}.edit_value is required for edited phase-one "
                        f"review item {item_id!r}."
                    )
                edit_values.append(edit_value)
            if len(set(edit_values)) != 1:
                raise ValidationError(
                    "UI, applied-decision, and effect edit_value must match exactly "
                    f"for phase-one review item {item_id!r}."
                )
        elif any("edit_value" in record for _field, record in review_records):
            raise ValidationError(
                "Accepted phase-one review items must not contain edit_value: "
                f"{item_id!r}."
            )

    for field, payload in (
        ("bound_ui_decisions", ui_decisions),
        ("bound_applied_decisions", applied_decisions),
    ):
        _require_exact_review_count(
            payload.get("decision_count"),
            field=f"{field}.decision_count",
            expected=item_count,
        )
        _require_exact_review_count(
            payload.get("item_count"),
            field=f"{field}.item_count",
            expected=item_count,
        )
    if ui_decisions.get("status") != "reviewed":
        raise ValidationError("Bound ui_decisions.status must be reviewed.")
    _require_exact_review_count(
        applied_decisions.get("blocker_count"),
        field="bound_applied_decisions.blocker_count",
        expected=0,
    )

    review_output = outputs_by_path["review_payload.json"]
    review_bytes_hash = sha256_file(run_dir / "review_payload.json")
    review_canonical_hash = canonical_json_hash(review_payload)
    if review_output.get("sha256") != review_bytes_hash:
        raise ValidationError(
            "Bound review_payload.json byte hash does not match its manifest record."
        )
    if manifest.get("review_payload_sha256") != review_bytes_hash:
        raise ValidationError(
            "Final-ready manifest must bind the review_payload.json byte hash."
        )
    if manifest.get("review_payload_canonical_sha256") != review_canonical_hash:
        raise ValidationError(
            "Final-ready manifest must bind the canonical review payload hash."
        )
    if (
        ui_decisions.get("review_payload_sha256") != review_bytes_hash
        or ui_decisions.get("review_payload_canonical_sha256") != review_canonical_hash
    ):
        raise ValidationError(
            "Bound ui_decisions must bind both review payload byte and canonical hashes."
        )
    applied_review = _require_object(
        applied_decisions.get("review_payload"),
        "bound_applied_decisions.review_payload",
    )
    if (
        applied_review.get("path") != "review_payload.json"
        or applied_review.get("item_count") != item_count
        or applied_review.get("sha256") != review_bytes_hash
        or applied_review.get("canonical_sha256") != review_canonical_hash
    ):
        raise ValidationError(
            "Bound applied_decisions.review_payload must bind path, coverage, and exact hashes."
        )
    _require_exact_review_count(
        review_application.get("decision_count"),
        field="bound_review_application.decision_count",
        expected=item_count,
    )
    _require_exact_review_count(
        review_application.get("item_count"),
        field="bound_review_application.item_count",
        expected=item_count,
    )
    _require_exact_review_count(
        review_application.get("blocker_count"),
        field="bound_review_application.blocker_count",
        expected=0,
    )


def _source_snapshot_relative_path(value: Any, *, field: str) -> str:
    """Return one canonical POSIX run-relative source path."""

    relative_path = _require_string(value, field)
    path_object = Path(relative_path)
    if (
        value != relative_path
        or path_object.is_absolute()
        or "\\" in relative_path
        or relative_path != path_object.as_posix()
        or any(part in {"", ".", ".."} for part in path_object.parts)
        or any(ord(character) < 32 for character in relative_path)
    ):
        raise ValidationError(
            f"{field} must be a normalized, non-empty POSIX relative path."
        )
    return relative_path


def _source_snapshot_nonnegative_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field} must be a non-negative integer.")
    return value


def _source_snapshot_modified_iso(value: Any, *, field: str) -> str:
    modified_iso = _require_string(value, field)
    if value != modified_iso:
        raise ValidationError(f"{field} must be a canonical ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(modified_iso)
    except ValueError as exc:
        raise ValidationError(
            f"{field} must be a canonical ISO-8601 timestamp."
        ) from exc
    if parsed.isoformat() != modified_iso:
        raise ValidationError(f"{field} must be a canonical ISO-8601 timestamp.")
    return modified_iso


def _verify_client_file_preparation_source_snapshot(
    *,
    run_dir: Path,
    bound_run_id: str,
) -> dict[str, int]:
    """Verify the sealed phase-one scan ledger against its CSV inventory.

    This is deliberately deterministic because paths, sizes, hashes, counts, and
    CSV rows are a mechanical integrity boundary for downstream evidence use.
    """

    run_intake = load_json(run_dir / "run_intake.json")
    if (
        run_intake.get("plugin") != "client-file-preparation"
        or run_intake.get("workflow") != "client-file-preparation"
        or run_intake.get("run_id") != bound_run_id
    ):
        raise ValidationError(
            "Bound run_intake.json identity does not match the phase-one manifest."
        )

    source_snapshot = _require_object(
        run_intake.get("source_snapshot"), "bound_run_intake.source_snapshot"
    )
    if set(source_snapshot) != {"algorithm", "limits", "observed", "files"}:
        raise ValidationError(
            "Bound source_snapshot must contain exactly algorithm, limits, "
            "observed, and files."
        )
    if source_snapshot.get("algorithm") != "sha256":
        raise ValidationError("Bound source_snapshot.algorithm must be sha256.")

    limits = _require_object(
        source_snapshot.get("limits"), "bound_source_snapshot.limits"
    )
    if set(limits) != set(CLIENT_FILE_PREPARATION_SOURCE_LIMITS):
        raise ValidationError(
            "Bound source_snapshot.limits must contain exactly max_entry_count, "
            "max_file_count, max_file_bytes, and max_total_bytes."
        )
    validated_limits: dict[str, int] = {}
    for name, contract_maximum in CLIENT_FILE_PREPARATION_SOURCE_LIMITS.items():
        limit = _source_snapshot_nonnegative_integer(
            limits.get(name), field=f"bound_source_snapshot.limits.{name}"
        )
        if limit < 1 or limit > contract_maximum:
            raise ValidationError(
                f"bound_source_snapshot.limits.{name} must be between 1 and "
                f"{contract_maximum}."
            )
        validated_limits[name] = limit
    if validated_limits["max_file_count"] > validated_limits["max_entry_count"]:
        raise ValidationError(
            "Bound source_snapshot max_file_count must not exceed max_entry_count."
        )
    if validated_limits["max_file_bytes"] > validated_limits["max_total_bytes"]:
        raise ValidationError(
            "Bound source_snapshot max_file_bytes must not exceed max_total_bytes."
        )

    observed = _require_object(
        source_snapshot.get("observed"), "bound_source_snapshot.observed"
    )
    observed_fields = {
        "file_count",
        "regular_file_count",
        "symlink_count",
        "total_regular_bytes",
    }
    if set(observed) != observed_fields:
        raise ValidationError(
            "Bound source_snapshot.observed must contain exactly file_count, "
            "regular_file_count, symlink_count, and total_regular_bytes."
        )
    validated_observed = {
        name: _source_snapshot_nonnegative_integer(
            observed.get(name), field=f"bound_source_snapshot.observed.{name}"
        )
        for name in observed_fields
    }

    raw_files = _require_list(
        source_snapshot.get("files"), "bound_source_snapshot.files"
    )
    if not raw_files:
        raise ValidationError("Bound source_snapshot.files must not be empty.")
    snapshot_by_path: dict[str, dict[str, Any]] = {}
    regular_file_count = 0
    symlink_count = 0
    total_regular_bytes = 0
    snapshot_file_fields = {
        "relative_path",
        "size_bytes",
        "modified_iso",
        "sha256",
        "entry_type",
    }
    for index, raw_file in enumerate(raw_files):
        record = _require_object(raw_file, f"bound_source_snapshot.files[{index}]")
        if set(record) != snapshot_file_fields:
            raise ValidationError(
                f"bound_source_snapshot.files[{index}] must contain exactly "
                "relative_path, size_bytes, modified_iso, sha256, and entry_type."
            )
        relative_path = _source_snapshot_relative_path(
            record.get("relative_path"),
            field=f"bound_source_snapshot.files[{index}].relative_path",
        )
        if relative_path in snapshot_by_path:
            raise ValidationError(
                "Bound source_snapshot.files contains a duplicate relative path: "
                f"{relative_path!r}."
            )
        size_bytes = _source_snapshot_nonnegative_integer(
            record.get("size_bytes"),
            field=f"bound_source_snapshot.files[{index}].size_bytes",
        )
        modified_iso = _source_snapshot_modified_iso(
            record.get("modified_iso"),
            field=f"bound_source_snapshot.files[{index}].modified_iso",
        )
        entry_type = record.get("entry_type")
        raw_hash = record.get("sha256")
        if entry_type == "regular_file":
            source_hash = _require_sha256(
                raw_hash, f"bound_source_snapshot.files[{index}].sha256"
            )
            if raw_hash != source_hash:
                raise ValidationError(
                    f"bound_source_snapshot.files[{index}].sha256 must use "
                    "canonical lowercase hexadecimal."
                )
            if size_bytes > validated_limits["max_file_bytes"]:
                raise ValidationError(
                    f"Bound regular source {relative_path!r} exceeds the declared "
                    "per-file limit."
                )
            regular_file_count += 1
            total_regular_bytes += size_bytes
        elif entry_type == "symlink_not_followed":
            if raw_hash != "":
                raise ValidationError(
                    f"Bound symlink source {relative_path!r} must have an empty sha256."
                )
            source_hash = ""
            symlink_count += 1
        else:
            raise ValidationError(
                f"bound_source_snapshot.files[{index}].entry_type must be "
                "regular_file or symlink_not_followed."
            )
        snapshot_by_path[relative_path] = {
            "size_bytes": size_bytes,
            "modified_iso": modified_iso,
            "sha256": source_hash,
        }

    calculated_observed = {
        "file_count": len(snapshot_by_path),
        "regular_file_count": regular_file_count,
        "symlink_count": symlink_count,
        "total_regular_bytes": total_regular_bytes,
    }
    if validated_observed != calculated_observed:
        raise ValidationError(
            "Bound source_snapshot.observed does not match its source file records."
        )
    if calculated_observed["file_count"] > validated_limits["max_entry_count"]:
        raise ValidationError(
            "Bound source_snapshot file count exceeds the declared entry limit."
        )
    if calculated_observed["file_count"] > validated_limits["max_file_count"]:
        raise ValidationError(
            "Bound source_snapshot file count exceeds the declared file limit."
        )
    if calculated_observed["total_regular_bytes"] > validated_limits["max_total_bytes"]:
        raise ValidationError(
            "Bound source_snapshot total regular bytes exceed the declared total limit."
        )

    inventory_path = run_dir / "01_document_inventory.csv"
    try:
        with inventory_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if (
                tuple(reader.fieldnames or ())
                != CLIENT_FILE_PREPARATION_INVENTORY_COLUMNS
            ):
                raise ValidationError(
                    "Bound 01_document_inventory.csv has an unsupported column contract."
                )
            inventory_rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValidationError(
            f"Cannot parse bound 01_document_inventory.csv: {exc}"
        ) from exc

    inventory_by_path: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(inventory_rows):
        if None in row or set(row) != set(CLIENT_FILE_PREPARATION_INVENTORY_COLUMNS):
            raise ValidationError(
                f"Bound inventory row {index + 2} does not match its column contract."
            )
        relative_path = _source_snapshot_relative_path(
            row.get("relative_path"),
            field=f"bound_inventory.rows[{index}].relative_path",
        )
        if relative_path in inventory_by_path:
            raise ValidationError(
                "Bound 01_document_inventory.csv contains a duplicate relative path: "
                f"{relative_path!r}."
            )
        raw_size = row.get("size_bytes")
        if not isinstance(raw_size, str) or not re.fullmatch(
            r"0|[1-9][0-9]*", raw_size
        ):
            raise ValidationError(
                f"bound_inventory.rows[{index}].size_bytes must be a canonical "
                "non-negative integer."
            )
        modified_iso = _source_snapshot_modified_iso(
            row.get("modified_iso"),
            field=f"bound_inventory.rows[{index}].modified_iso",
        )
        raw_hash = row.get("sha256")
        if not isinstance(raw_hash, str):
            raise ValidationError(
                f"bound_inventory.rows[{index}].sha256 must be a string."
            )
        if raw_hash:
            source_hash = _require_sha256(
                raw_hash, f"bound_inventory.rows[{index}].sha256"
            )
            if raw_hash != source_hash:
                raise ValidationError(
                    f"bound_inventory.rows[{index}].sha256 must use canonical "
                    "lowercase hexadecimal."
                )
        else:
            source_hash = ""
        inventory_by_path[relative_path] = {
            "size_bytes": int(raw_size),
            "modified_iso": modified_iso,
            "sha256": source_hash,
        }

    if inventory_by_path != snapshot_by_path:
        raise ValidationError(
            "Bound source_snapshot.files does not exactly match inventory "
            "path, size_bytes, modified_iso, and sha256 rows."
        )
    return calculated_observed


def verify_client_file_preparation_binding(
    intake: Mapping[str, Any], *, base_dir: Path
) -> dict[str, Any]:
    """Verify a Client File Preparation final manifest or record an explicit standalone mode."""

    binding = intake["client_file_preparation_binding"]
    if binding["mode"] == "standalone_evidence":
        return {
            "mode": "standalone_evidence",
            "verification_status": "standalone_evidence_recorded",
            "reviewed_client_file_preparation": False,
            "final_ready": False,
            "relationship_blocker": False,
            "reason": binding["reason"],
            "evidence_ids": list(binding.get("evidence_ids", [])),
            "manifest_sha256": None,
        }

    resolved = _resolve_local_file(
        binding["final_artifacts_path"],
        field="client_file_preparation_binding.final_artifacts_path",
        base_dir=base_dir,
    )
    expected_hash = binding["final_artifacts_sha256"].casefold()
    actual_hash = sha256_file(resolved)
    if actual_hash != expected_hash:
        raise ValidationError(
            "Client File Preparation final_artifacts byte hash mismatch."
        )
    manifest = load_json(resolved)
    for field in ("plugin", "workflow", "run_id", "status", "outputs"):
        if field not in manifest:
            raise ValidationError(
                f"Bound Client File Preparation final_artifacts is malformed: missing {field}."
            )
    if manifest["plugin"] != "client-file-preparation":
        raise ValidationError(
            "Bound Client File Preparation final_artifacts.plugin must be client-file-preparation."
        )
    if manifest["workflow"] != "client-file-preparation":
        raise ValidationError(
            "Bound Client File Preparation final_artifacts.workflow must be client-file-preparation."
        )
    bound_run_id = _require_reference(
        manifest["run_id"], "bound_client_file_preparation.run_id"
    )
    if bound_run_id != binding["run_id"]:
        raise ValidationError(
            "Bound Client File Preparation final_artifacts.run_id does not match the binding."
        )
    status = _require_reference(
        manifest["status"], "bound_client_file_preparation.status"
    )
    outputs = _require_list(
        manifest["outputs"], "bound_client_file_preparation.outputs"
    )
    if not outputs:
        raise ValidationError(
            "Bound Client File Preparation final_artifacts.outputs must not be empty."
        )
    verified_outputs: list[dict[str, Any]] = []
    seen_output_paths: set[str] = set()
    for index, raw_output in enumerate(outputs):
        output = _require_object(
            raw_output, f"bound_client_file_preparation.outputs[{index}]"
        )
        relative_path = _require_string(
            output.get("path"), f"bound_client_file_preparation.outputs[{index}].path"
        )
        path_object = Path(relative_path)
        if (
            path_object.is_absolute()
            or relative_path != path_object.as_posix()
            or any(part in {"", ".", ".."} for part in path_object.parts)
            or relative_path == "final_artifacts.json"
        ):
            raise ValidationError(
                "Bound Client File Preparation outputs must use unique run-local "
                "relative paths and must exclude final_artifacts.json."
            )
        if relative_path in seen_output_paths:
            raise ValidationError(
                "Bound Client File Preparation outputs contain a duplicate path: "
                f"{relative_path}."
            )
        seen_output_paths.add(relative_path)
        _require_string(
            output.get("status"),
            f"bound_client_file_preparation.outputs[{index}].status",
        )
        expected_size = output.get("size_bytes")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int):
            raise ValidationError(
                f"bound_client_file_preparation.outputs[{index}].size_bytes must "
                "be an integer."
            )
        expected_hash = _require_sha256(
            output.get("sha256"),
            f"bound_client_file_preparation.outputs[{index}].sha256",
        )
        candidate = resolved.parent / path_object
        if candidate.is_symlink():
            raise ValidationError(
                f"Bound Client File Preparation output {relative_path!r} must not "
                "be a symbolic link."
            )
        try:
            output_path = candidate.resolve(strict=True)
        except OSError as exc:
            raise ValidationError(
                f"Cannot resolve bound Client File Preparation output "
                f"{relative_path!r}: {exc}"
            ) from exc
        if not _is_within(output_path, resolved.parent) or not output_path.is_file():
            raise ValidationError(
                f"Bound Client File Preparation output {relative_path!r} must be "
                "a regular file inside the run directory."
            )
        actual_size = output_path.stat().st_size
        actual_output_hash = sha256_file(output_path)
        if actual_size != expected_size:
            raise ValidationError(
                f"Bound Client File Preparation output size mismatch for "
                f"{relative_path!r}."
            )
        if actual_output_hash != expected_hash:
            raise ValidationError(
                f"Bound Client File Preparation output hash mismatch for "
                f"{relative_path!r}."
            )
        verified_outputs.append(
            {
                "path": relative_path,
                "resolved_path": output_path.as_posix(),
                "size_bytes": actual_size,
                "sha256": actual_output_hash,
                "status": output["status"],
            }
        )
    integrity = _require_object(
        manifest.get("integrity"), "bound_client_file_preparation.integrity"
    )
    if set(integrity) != {"algorithm", "package_hash_basis", "package_hash"}:
        raise ValidationError(
            "Bound Client File Preparation integrity must contain exactly algorithm, "
            "package_hash_basis, and package_hash."
        )
    if integrity.get("algorithm") != "sha256":
        raise ValidationError(
            "Bound Client File Preparation integrity.algorithm must be sha256."
        )
    if (
        integrity.get("package_hash_basis")
        != CLIENT_FILE_PREPARATION_PACKAGE_HASH_BASIS
    ):
        raise ValidationError(
            "Bound Client File Preparation package_hash_basis is unsupported."
        )
    expected_package_hash = _require_sha256(
        integrity.get("package_hash"),
        "bound_client_file_preparation.integrity.package_hash",
    )
    actual_package_hash = canonical_json_hash(
        [
            {
                "path": record["path"],
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
            for record in sorted(verified_outputs, key=lambda item: item["path"])
        ]
    )
    if actual_package_hash != expected_package_hash:
        raise ValidationError(
            "Bound Client File Preparation package hash does not match its verified "
            "outputs."
        )
    if binding["upstream_package_hash"].casefold() != actual_package_hash:
        raise ValidationError(
            "Client File Preparation binding upstream_package_hash does not match "
            "the verified package."
        )
    required_source_outputs = {"run_intake.json", "01_document_inventory.csv"}
    missing_source_outputs = sorted(required_source_outputs - seen_output_paths)
    if missing_source_outputs:
        raise ValidationError(
            "Bound Client File Preparation package is missing sealed source "
            "provenance outputs: " + ", ".join(missing_source_outputs)
        )
    source_snapshot_observed = _verify_client_file_preparation_source_snapshot(
        run_dir=resolved.parent,
        bound_run_id=bound_run_id,
    )
    final_ready = status == "final_ready"
    if final_ready:
        if manifest.get("review_status") != "final_ready":
            raise ValidationError(
                "Bound Client File Preparation final-ready manifest must have "
                "review_status=final_ready."
            )
        review_application = _require_object(
            manifest.get("review_application"),
            "bound_client_file_preparation.review_application",
        )
        if review_application.get("application_status") != "final_ready":
            raise ValidationError(
                "Bound Client File Preparation final-ready manifest must have "
                "review_application.application_status=final_ready."
            )
        applied_outputs = [
            output
            for output in outputs
            if isinstance(output, dict)
            and output.get("path") == "applied_decisions.json"
        ]
        if (
            len(applied_outputs) != 1
            or applied_outputs[0].get("status") != "final_ready"
        ):
            raise ValidationError(
                "Bound Client File Preparation final-ready manifest must list exactly one "
                "applied_decisions.json output with status=final_ready."
            )
        required_final_outputs = {
            "run_intake.json",
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "review_handoff.md",
        }
        missing_final_outputs = sorted(required_final_outputs - seen_output_paths)
        if missing_final_outputs:
            raise ValidationError(
                "Bound Client File Preparation final-ready package is missing "
                "review provenance outputs: " + ", ".join(missing_final_outputs)
            )
        applied_decisions_path = resolved.parent / "applied_decisions.json"
        applied_decisions = load_json(applied_decisions_path)
        if applied_decisions.get("run_id") != bound_run_id:
            raise ValidationError(
                "Bound applied_decisions.json run_id does not match the manifest."
            )
        if applied_decisions.get("application_status") != "final_ready":
            raise ValidationError(
                "Bound applied_decisions.json must have application_status=final_ready."
            )
        outputs_by_path = {record["path"]: record for record in verified_outputs}
        _verify_client_file_preparation_review_provenance(
            manifest=manifest,
            run_dir=resolved.parent,
            bound_run_id=bound_run_id,
            outputs_by_path=outputs_by_path,
            review_application=review_application,
        )
    return {
        "mode": "client_file_preparation_run",
        "verification_status": (
            "verified_final_ready" if final_ready else "verified_not_final"
        ),
        "reviewed_client_file_preparation": final_ready,
        "final_ready": final_ready,
        "relationship_blocker": not final_ready,
        "bound_manifest_path": resolved.as_posix(),
        "manifest_sha256": actual_hash,
        "package_hash": actual_package_hash,
        "bound_run_id_sha256": canonical_json_hash(bound_run_id),
        "bound_status": status,
        "output_count": len(outputs),
        "source_snapshot_observed": source_snapshot_observed,
        "verified_outputs": verified_outputs,
    }


def verify_template_references(
    intake: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    base_dir: Path,
    as_of: date,
) -> list[dict[str, Any]]:
    """Verify template bytes and recorded source basis without rendering content."""

    sources_by_id = {source["source_id"]: source for source in registry["sources"]}
    results: list[dict[str, Any]] = []
    for template in intake["template_references"]:
        resolved = _resolve_local_file(
            template["local_path"],
            field=f"template_references[{template['template_id']}].local_path",
            base_dir=base_dir,
        )
        expected_hash = template["sha256"].casefold()
        actual_hash = sha256_file(resolved)
        if actual_hash != expected_hash:
            raise ValidationError(
                f"Template content hash mismatch for {template['template_id']!r}."
            )
        source_basis = [
            sources_by_id[source_id] for source_id in sorted(template["source_ids"])
        ]
        actual_source_hash = canonical_json_hash(source_basis)
        if actual_source_hash != template["source_basis_sha256"].casefold():
            raise ValidationError(
                f"Template source-basis hash mismatch for {template['template_id']!r}."
            )
        valid_from = _parse_date(
            template["valid_from"],
            f"template_references[{template['template_id']}].valid_from",
        )
        valid_until = (
            _parse_date(
                template["valid_until"],
                f"template_references[{template['template_id']}].valid_until",
            )
            if template.get("valid_until") is not None
            else None
        )
        review_due = _parse_date(
            template["review_due_on"],
            f"template_references[{template['template_id']}].review_due_on",
        )
        freshness_status = "current"
        if as_of < valid_from:
            freshness_status = "not_yet_valid"
        elif valid_until is not None and as_of > valid_until:
            freshness_status = "expired"
        elif as_of > review_due:
            freshness_status = "review_overdue"
        blockers: list[str] = []
        if template["approval_status"] != "approved":
            blockers.append("not_professionally_approved")
        if template["reuse_status"] not in {
            "studio_owned",
            "licensed_for_client_use",
        }:
            blockers.append("not_approved_for_reuse")
        if template["reuse_scope"] is None:
            blockers.append("reuse_scope_not_recorded")
        if template["jurisdiction"].casefold() != intake["jurisdiction"].casefold():
            blockers.append("jurisdiction_mismatch")
        if template["language"].casefold() != intake["language"].casefold():
            blockers.append("language_mismatch")
        if freshness_status != "current":
            blockers.append(f"freshness_{freshness_status}")
        results.append(
            {
                "document_type": template["document_type"],
                "template_id": template["template_id"],
                "version": template["version"],
                "content_verification_status": "hash_verified",
                "sha256": actual_hash,
                "source_basis_verification_status": "hash_verified",
                "source_basis_sha256": actual_source_hash,
                "resolved_path": resolved.as_posix(),
                "approval_status": template["approval_status"],
                "reuse_status": template["reuse_status"],
                "reuse_scope": template["reuse_scope"],
                "jurisdiction": template["jurisdiction"],
                "language": template["language"],
                "freshness_status": freshness_status,
                "ready_for_document_plan": not blockers,
                "blockers": blockers,
            }
        )
    return results


def _as_number(value: Decimal) -> int | float:
    integral = value.to_integral_value()
    if value == integral:
        return int(integral)
    return float(value.quantize(Decimal("0.0001")).normalize())


def _risk_band(score: Decimal) -> dict[str, str]:
    if Decimal("1") <= score < Decimal("1.6"):
        return {
            "code": "not_significant",
            "label_it": "non significativo",
            "interval": "[1, 1.6)",
        }
    if Decimal("1.6") <= score < Decimal("2.6"):
        return {
            "code": "low_significance",
            "label_it": "poco significativo",
            "interval": "[1.6, 2.6)",
        }
    if Decimal("2.6") <= score < Decimal("3.6"):
        return {
            "code": "medium_significance",
            "label_it": "abbastanza significativo",
            "interval": "[2.6, 3.6)",
        }
    if Decimal("3.6") <= score <= Decimal("4"):
        return {
            "code": "high_significance",
            "label_it": "molto significativo",
            "interval": "[3.6, 4]",
        }
    raise ValidationError("Calculated effective risk is outside [1, 4].")


def calculate_aml(aml: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate the CNDCEC-style arithmetic while preserving human review."""

    ri = _decimal_score(aml.get("inherent_risk"), "aml.inherent_risk")
    a_scores = [
        _decimal_score(factor.get("score"), f"aml.factors_a.{factor.get('factor_id')}")
        for factor in aml["factors_a"]
    ]
    a_total = sum(a_scores, Decimal("0"))
    section_b_mode = aml["section_b_mode"]
    b_scores: list[Decimal] = []
    if section_b_mode == "full":
        b_scores = [
            _decimal_score(
                factor.get("score"), f"aml.factors_b.{factor.get('factor_id')}"
            )
            for factor in aml["factors_b"]
        ]
        b_total = sum(b_scores, Decimal("0"))
        specific_risk = (a_total + b_total) / Decimal("10")
        specific_formula = "RS = (sum(A1..A4) + sum(B1..B6)) / 10"
    else:
        confirmation = aml.get("section_b_exclusion_confirmation")
        if (
            not isinstance(confirmation, dict)
            or confirmation.get("confirmed") is not True
        ):
            raise ValidationError(
                "Section B exclusion is not effective without explicit confirmation."
            )
        b_total = None
        specific_risk = a_total / Decimal("4")
        specific_formula = "RS = sum(A1..A4) / 4 (Section B exclusion confirmed)"
    effective_risk = (ri * Decimal("0.30")) + (specific_risk * Decimal("0.70"))
    band = _risk_band(effective_risk)

    triggers = list(aml["mandatory_enhanced_triggers"])
    unknown_trigger_ids = [
        trigger["trigger_id"] for trigger in triggers if trigger["status"] == "unknown"
    ]
    unconfirmed_positive_ids = [
        trigger["trigger_id"]
        for trigger in triggers
        if trigger["status"] == "yes" and trigger["review_status"] != "confirmed"
    ]
    confirmed_positive_ids = [
        trigger["trigger_id"]
        for trigger in triggers
        if trigger["status"] == "yes" and trigger["review_status"] == "confirmed"
    ]

    table_1 = aml["table_1_assessment"]
    table_1_resolved = (
        table_1["status"] in {"yes", "no"} and table_1["review_status"] == "confirmed"
    )
    baseline_mode: str | None = None
    if table_1_resolved:
        if band["code"] == "not_significant":
            baseline_mode = (
                "conduct_rule" if table_1["status"] == "yes" else "simplified"
            )
        elif band["code"] == "low_significance":
            baseline_mode = "simplified"
        elif band["code"] == "medium_significance":
            baseline_mode = "ordinary"
        else:
            baseline_mode = "enhanced"

    mode_rank = {"conduct_rule": 0, "simplified": 1, "ordinary": 2, "enhanced": 3}
    current_mode = aml.get("current_verification_mode")
    minimum_mode = baseline_mode
    no_declassification_applied = False
    if current_mode is not None and (
        minimum_mode is None or mode_rank[current_mode] > mode_rank[minimum_mode]
    ):
        minimum_mode = current_mode
        no_declassification_applied = baseline_mode is not None
    if confirmed_positive_ids and minimum_mode != "enhanced":
        minimum_mode = "enhanced"
    if not table_1_resolved:
        decision_status = "blocked_unresolved_table_1"
    elif unknown_trigger_ids:
        decision_status = "blocked_unknown_mandatory_trigger"
    elif unconfirmed_positive_ids:
        decision_status = "blocked_unconfirmed_positive_trigger"
    else:
        decision_status = "calculated_for_professional_review"

    proposed_inputs = (
        aml.get("inherent_risk_status") == "proposed"
        or not table_1_resolved
        or any(
            factor.get("assessment_status") == "proposed"
            for factor in [*aml["factors_a"], *aml["factors_b"]]
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": decision_status,
        "professional_review_required": True,
        "calculation_scope": (
            "Arithmetic support only; factor selection, scores, exclusions, trigger "
            "findings, and the final professional conclusion remain reviewer-owned."
        ),
        "uses_proposed_inputs": proposed_inputs,
        "inherent_risk": _as_number(ri),
        "inherent_risk_weight": 0.30,
        "factor_a_total": _as_number(a_total),
        "factor_a_count": 4,
        "factor_b_total": None if b_total is None else _as_number(b_total),
        "factor_b_count": 6,
        "section_b_mode": section_b_mode,
        "specific_risk": _as_number(specific_risk),
        "specific_risk_formula": specific_formula,
        "specific_risk_weight": 0.70,
        "effective_risk": _as_number(effective_risk),
        "effective_risk_formula": "RE = (RI * 30%) + (RS * 70%)",
        "calculated_band": band,
        "table_1_assessment": table_1,
        "table_1_resolved": table_1_resolved,
        "baseline_verification_mode": baseline_mode,
        "confirmed_positive_trigger_ids": confirmed_positive_ids,
        "unknown_trigger_ids": unknown_trigger_ids,
        "unconfirmed_positive_trigger_ids": unconfirmed_positive_ids,
        "current_verification_mode": current_mode,
        "minimum_verification_mode_for_review": minimum_mode,
        "no_declassification_applied": no_declassification_applied,
    }


def build_case_facts(
    intake: Mapping[str, Any],
    *,
    generated_at: str,
    client_file_preparation_verification: Mapping[str, Any] | None = None,
    evidence_verifications: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the validated local facts artifact, including sensitive local facts."""

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "validated_for_professional_review",
        "jurisdiction": intake["jurisdiction"],
        "country_pack": ITALY_COUNTRY_PACK,
        "language": intake["language"],
        "client_reference": intake["client_reference"],
        "client_type": intake["client_type"],
        "tax_facts": intake["tax_facts"],
        "party_facts": intake["party_facts"],
        "party_identity_document": intake["party_identity_document"],
        "representatives": intake["representatives"],
        "representative_posture": intake["representative_posture"],
        "beneficial_owners": intake["beneficial_owners"],
        "ownership_status": intake["ownership_status"],
        "screening_results": intake["screening_results"],
        "privacy_processing_decisions": intake["privacy_processing_decisions"],
        "marketing_consent": intake["marketing_consent"],
        "client_file_preparation_binding": intake["client_file_preparation_binding"],
        "client_file_preparation_verification": (
            dict(client_file_preparation_verification)
            if client_file_preparation_verification is not None
            else None
        ),
        "engagement": intake["engagement"],
        "evidence_register": intake["evidence_register"],
        "evidence_verifications": [dict(record) for record in evidence_verifications],
        "input_hash": canonical_json_hash(intake),
    }


def build_applicability_plan(
    intake: Mapping[str, Any], *, generated_at: str
) -> dict[str, Any]:
    """Record proposed or confirmed applicability without deciding it automatically."""

    records: list[dict[str, Any]] = []
    for record in intake["applicability"]:
        records.append(
            {
                **record,
                "workflow_status": (
                    "professional_input_recorded"
                    if record["review_status"] == "confirmed"
                    else "needs_professional_review"
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "needs_professional_review",
        "professional_review_required": True,
        "records": records,
    }


def _evidence_status_by_id(intake: Mapping[str, Any]) -> dict[str, str]:
    return {
        record["evidence_id"]: record["status"]
        for record in intake["evidence_register"]
    }


def build_missing_evidence(
    intake: Mapping[str, Any],
    aml_result: Mapping[str, Any],
    *,
    generated_at: str,
    as_of: date,
    client_file_preparation_verification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Identify mechanically missing or unresolved records without judging substance."""

    evidence_status = _evidence_status_by_id(intake)
    items: list[dict[str, Any]] = []

    def add_unverified_support(
        *,
        item_id: str,
        item_type: str,
        reference: str,
        evidence_ids: Sequence[str],
    ) -> None:
        if evidence_ids and all(
            evidence_status.get(evidence_id) == "verified"
            for evidence_id in evidence_ids
        ):
            return
        items.append(
            {
                "item_id": item_id,
                "item_type": item_type,
                "reference": reference,
                "reason": "supporting_evidence_not_verified",
            }
        )

    for record in intake["evidence_register"]:
        if record["status"] in {"requested", "missing", "stale"}:
            items.append(
                {
                    "item_id": f"evidence:{record['evidence_id']}",
                    "item_type": "evidence_record",
                    "reference": record["evidence_id"],
                    "reason": f"evidence_status_{record['status']}",
                }
            )
        elif (
            record.get("expires_on") is not None
            and _parse_date(
                record["expires_on"],
                f"evidence_register[{record['evidence_id']}].expires_on",
            )
            < as_of
        ):
            items.append(
                {
                    "item_id": f"evidence:{record['evidence_id']}:expired",
                    "item_type": "evidence_record",
                    "reference": record["evidence_id"],
                    "reason": "evidence_expired",
                }
            )
    for fact_name, fact in intake["tax_facts"].items():
        if fact["verification_status"] in {"unknown", "reported"}:
            items.append(
                {
                    "item_id": f"tax_fact:{fact_name}",
                    "item_type": "tax_fact",
                    "reference": fact_name,
                    "reason": f"verification_status_{fact['verification_status']}",
                }
            )
        elif fact["verification_status"] == "verified" and any(
            evidence_status[evidence_id] != "verified"
            for evidence_id in fact.get("evidence_ids", [])
        ):
            items.append(
                {
                    "item_id": f"tax_fact:{fact_name}:evidence",
                    "item_type": "tax_fact",
                    "reference": fact_name,
                    "reason": "supporting_evidence_not_verified",
                }
            )
    for fact in intake["party_facts"]:
        if fact["verification_status"] in {"unknown", "reported"}:
            items.append(
                {
                    "item_id": f"party_fact:{fact['fact_id']}",
                    "item_type": "party_fact",
                    "reference": fact["fact_id"],
                    "reason": f"verification_status_{fact['verification_status']}",
                }
            )
        elif fact["verification_status"] == "verified":
            add_unverified_support(
                item_id=f"party_fact:{fact['fact_id']}:evidence",
                item_type="party_fact",
                reference=fact["fact_id"],
                evidence_ids=fact.get("evidence_ids", []),
            )
    party_identity = intake["party_identity_document"]
    if party_identity["verification_status"] in {"unknown", "reported"}:
        items.append(
            {
                "item_id": "party_identity:primary",
                "item_type": "identity_document",
                "reference": "primary_party",
                "reason": (
                    "verification_status_" + party_identity["verification_status"]
                ),
            }
        )
    elif party_identity["verification_status"] == "verified":
        add_unverified_support(
            item_id="party_identity:primary:evidence",
            item_type="identity_document",
            reference="primary_party",
            evidence_ids=party_identity.get("evidence_ids", []),
        )
    if (
        party_identity.get("expires_on") is not None
        and _parse_date(
            party_identity["expires_on"], "party_identity_document.expires_on"
        )
        < as_of
    ):
        items.append(
            {
                "item_id": "party_identity:primary:expired",
                "item_type": "identity_document",
                "reference": "primary_party",
                "reason": "identity_document_expired",
            }
        )
    for representative in intake["representatives"]:
        add_unverified_support(
            item_id=(
                "representative_authority:"
                + representative["representative_reference"]
                + ":evidence"
            ),
            item_type="representative",
            reference=representative["representative_reference"],
            evidence_ids=representative.get("evidence_ids", []),
        )
        identity = representative["identity_document"]
        if identity["verification_status"] != "verified":
            items.append(
                {
                    "item_id": (
                        "representative_identity:"
                        + representative["representative_reference"]
                    ),
                    "item_type": "representative",
                    "reference": representative["representative_reference"],
                    "reason": (
                        "identity_verification_status_"
                        + identity["verification_status"]
                    ),
                }
            )
        else:
            add_unverified_support(
                item_id=(
                    "representative_identity:"
                    + representative["representative_reference"]
                    + ":evidence"
                ),
                item_type="representative",
                reference=representative["representative_reference"],
                evidence_ids=identity.get("evidence_ids", []),
            )
        if (
            identity.get("expires_on") is not None
            and _parse_date(
                identity["expires_on"],
                "representative.identity_document.expires_on",
            )
            < as_of
        ):
            items.append(
                {
                    "item_id": (
                        "representative_identity:"
                        + representative["representative_reference"]
                        + ":expired"
                    ),
                    "item_type": "representative",
                    "reference": representative["representative_reference"],
                    "reason": "identity_document_expired",
                }
            )
    for owner in intake["beneficial_owners"]:
        if owner["verification_status"] != "verified":
            items.append(
                {
                    "item_id": f"owner:{owner['owner_reference']}",
                    "item_type": "beneficial_owner",
                    "reference": owner["owner_reference"],
                    "reason": f"verification_status_{owner['verification_status']}",
                }
            )
        else:
            add_unverified_support(
                item_id=f"owner:{owner['owner_reference']}:evidence",
                item_type="beneficial_owner",
                reference=owner["owner_reference"],
                evidence_ids=owner.get("evidence_ids", []),
            )
        identity = owner["identity_document"]
        if identity["verification_status"] != "verified":
            items.append(
                {
                    "item_id": f"owner_identity:{owner['owner_reference']}",
                    "item_type": "beneficial_owner",
                    "reference": owner["owner_reference"],
                    "reason": (
                        "identity_verification_status_"
                        + identity["verification_status"]
                    ),
                }
            )
        else:
            add_unverified_support(
                item_id=f"owner_identity:{owner['owner_reference']}:evidence",
                item_type="beneficial_owner",
                reference=owner["owner_reference"],
                evidence_ids=identity.get("evidence_ids", []),
            )
        if (
            identity.get("expires_on") is not None
            and _parse_date(
                identity["expires_on"], "beneficial_owner.identity_document.expires_on"
            )
            < as_of
        ):
            items.append(
                {
                    "item_id": f"owner_identity:{owner['owner_reference']}:expired",
                    "item_type": "beneficial_owner",
                    "reference": owner["owner_reference"],
                    "reason": "identity_document_expired",
                }
            )
    if intake["representative_posture"]["status"] == "pending":
        items.append(
            {
                "item_id": "representative_posture:resolution",
                "item_type": "representative_posture",
                "reference": "representative_posture",
                "reason": "representative_or_executor_posture_pending",
            }
        )
    elif intake["representative_posture"]["status"] == "recorded":
        add_unverified_support(
            item_id="representative_posture:resolution:evidence",
            item_type="representative_posture",
            reference="representative_posture",
            evidence_ids=intake["representative_posture"].get("evidence_ids", []),
        )
    if intake["ownership_status"]["status"] == "pending":
        items.append(
            {
                "item_id": "ownership_status:resolution",
                "item_type": "ownership_status",
                "reference": "ownership_status",
                "reason": "beneficial_ownership_posture_pending",
            }
        )
    elif intake["ownership_status"]["status"] == "owners_recorded":
        add_unverified_support(
            item_id="ownership_status:resolution:evidence",
            item_type="ownership_status",
            reference="ownership_status",
            evidence_ids=intake["ownership_status"].get("evidence_ids", []),
        )
    for screening in intake["screening_results"]:
        resolution = screening.get("professional_resolution")
        unresolved_resolution = screening["outcome"] != "clear" and (
            not isinstance(resolution, dict) or resolution.get("status") != "confirmed"
        )
        do_not_proceed = (
            isinstance(resolution, dict)
            and resolution.get("status") == "confirmed"
            and resolution.get("relationship_decision") == "do_not_proceed"
        )
        if screening["review_status"] != "confirmed" or unresolved_resolution:
            items.append(
                {
                    "item_id": f"screening:{screening['screening_id']}",
                    "item_type": "screening_result",
                    "reference": screening["screening_id"],
                    "reason": (
                        "professional_resolution_pending"
                        if unresolved_resolution
                        else "professional_confirmation_pending"
                    ),
                }
            )
        elif do_not_proceed:
            items.append(
                {
                    "item_id": f"screening:{screening['screening_id']}:relationship",
                    "item_type": "screening_result",
                    "reference": screening["screening_id"],
                    "reason": "professional_resolution_do_not_proceed",
                }
            )
    for decision in intake["privacy_processing_decisions"]:
        if decision["review_status"] != "confirmed":
            items.append(
                {
                    "item_id": f"privacy:{decision['decision_id']}",
                    "item_type": "privacy_processing",
                    "reference": decision["decision_id"],
                    "reason": "privacy_processing_decision_pending",
                }
            )
    for record in intake["applicability"]:
        if (
            record["applicability_status"] == "unclear"
            or record["review_status"] != "confirmed"
        ):
            items.append(
                {
                    "item_id": f"applicability:{record['topic']}",
                    "item_type": "applicability",
                    "reference": record["topic"],
                    "reason": (
                        "applicability_unclear"
                        if record["applicability_status"] == "unclear"
                        else "professional_confirmation_pending"
                    ),
                }
            )
    if not aml_result["table_1_resolved"]:
        table_1 = intake["aml"]["table_1_assessment"]
        items.append(
            {
                "item_id": "aml:table_1",
                "item_type": "aml_assessment",
                "reference": "table_1",
                "reason": (
                    "table_1_status_unknown"
                    if table_1["status"] == "unknown"
                    else "professional_confirmation_pending"
                ),
            }
        )
    for trigger_id in aml_result["unknown_trigger_ids"]:
        items.append(
            {
                "item_id": f"aml_trigger:{trigger_id}",
                "item_type": "aml_trigger",
                "reference": trigger_id,
                "reason": "mandatory_trigger_status_unknown",
            }
        )
    for trigger_id in aml_result["unconfirmed_positive_trigger_ids"]:
        items.append(
            {
                "item_id": f"aml_trigger:{trigger_id}:confirmation",
                "item_type": "aml_trigger",
                "reference": trigger_id,
                "reason": "positive_trigger_requires_confirmation",
            }
        )
    if intake["engagement"]["terms"]["review_status"] == "incomplete":
        items.append(
            {
                "item_id": "engagement:terms",
                "item_type": "engagement_terms",
                "reference": "terms",
                "reason": "engagement_terms_incomplete",
            }
        )
    if (
        client_file_preparation_verification is not None
        and client_file_preparation_verification.get("relationship_blocker") is True
    ):
        items.append(
            {
                "item_id": "client_file_preparation:binding",
                "item_type": "client_file_preparation_binding",
                "reference": "client_file_preparation_binding",
                "reason": "bound_client_file_preparation_run_not_final_ready",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "missing_information" if items else "ready_for_professional_review",
        "count": len(items),
        "items": items,
    }


def build_document_plan(
    intake: Mapping[str, Any],
    *,
    generated_at: str,
    template_verifications: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Plan documents from applicability and verified references without rendering."""

    templates = {
        record["document_type"]: record for record in intake["template_references"]
    }
    verification_by_type = {
        record["document_type"]: record for record in template_verifications
    }
    documents: list[dict[str, Any]] = []
    for record in intake["applicability"]:
        template = templates.get(record["topic"])
        verification = verification_by_type.get(record["topic"])
        if (
            record["applicability_status"] == "applicable"
            and record["review_status"] == "confirmed"
        ):
            if template is None:
                plan_status = "template_reference_required"
            elif verification is None:
                plan_status = "template_reference_verification_required"
            elif verification["ready_for_document_plan"]:
                plan_status = "approved_reusable_reference_available"
            else:
                plan_status = "template_reference_not_ready"
        elif (
            record["applicability_status"] == "not_applicable"
            and record["review_status"] == "confirmed"
        ):
            plan_status = "not_planned_by_confirmed_applicability"
        else:
            plan_status = "applicability_review_required"
        documents.append(
            {
                "document_type": record["topic"],
                "status": plan_status,
                "applicability_status": record["applicability_status"],
                "applicability_review_status": record["review_status"],
                "source_ids": record.get("source_ids", []),
                "template_reference": (
                    None
                    if template is None
                    else {
                        "template_id": template["template_id"],
                        "version": template["version"],
                        "approval_status": template["approval_status"],
                        "reuse_status": template["reuse_status"],
                        "reuse_scope": template["reuse_scope"],
                        "approved_by_role": template["approved_by_role"],
                        "approved_at": template["approved_at"],
                        "jurisdiction": template["jurisdiction"],
                        "language": template["language"],
                        "valid_until": template.get("valid_until"),
                        "review_due_on": template["review_due_on"],
                        "freshness_status": (
                            verification["freshness_status"]
                            if verification is not None
                            else "not_verified"
                        ),
                        "content_hash_verified": (
                            verification is not None
                            and verification["content_verification_status"]
                            == "hash_verified"
                        ),
                        "sha256": (
                            verification["sha256"]
                            if verification is not None
                            else template["sha256"]
                        ),
                        "source_basis_hash_verified": (
                            verification is not None
                            and verification["source_basis_verification_status"]
                            == "hash_verified"
                        ),
                        "source_basis_sha256": (
                            verification["source_basis_sha256"]
                            if verification is not None
                            else template["source_basis_sha256"]
                        ),
                        "blockers": (
                            list(verification["blockers"])
                            if verification is not None
                            else ["verification_not_run"]
                        ),
                    }
                ),
                "document_policy": (
                    "Reference and document planning only. This component does not "
                    "render, merge, populate, sign, or send document content."
                ),
            }
        )
    blocking_statuses = {
        "template_reference_required",
        "template_reference_verification_required",
        "template_reference_not_ready",
        "applicability_review_required",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": (
            "blocked_document_plan"
            if any(document["status"] in blocking_statuses for document in documents)
            else "draft_plan_for_professional_review"
        ),
        "professional_review_required": True,
        "rendering_performed": False,
        "population_performed": False,
        "documents": documents,
    }


def build_export_domain_blockers(
    missing_evidence: Mapping[str, Any],
    aml_result: Mapping[str, Any],
    document_plan: Mapping[str, Any],
    monitoring_plan: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build relationship blockers from explicit facts, never review decisions."""

    blockers: list[dict[str, str]] = [
        {
            "code": item["reason"],
            "reference": item["item_id"],
            "scope": "relationship_export",
            "domain": item["item_type"],
        }
        for item in missing_evidence["items"]
    ]
    if str(aml_result["status"]).startswith("blocked_"):
        blockers.append(
            {
                "code": str(aml_result["status"]),
                "reference": "aml:calculation",
                "scope": "relationship_export",
                "domain": "aml",
            }
        )
    if str(monitoring_plan["status"]).startswith("blocked_"):
        blockers.append(
            {
                "code": str(monitoring_plan["status"]),
                "reference": "monitoring:plan",
                "scope": "relationship_export",
                "domain": "monitoring",
            }
        )
    nonblocking_document_statuses = {
        "approved_reusable_reference_available",
        "not_planned_by_confirmed_applicability",
    }
    for document in document_plan["documents"]:
        if document["status"] not in nonblocking_document_statuses:
            blockers.append(
                {
                    "code": document["status"],
                    "reference": f"document:{document['document_type']}",
                    "scope": f"document:{document['document_type']}",
                    "domain": "document_plan",
                }
            )
    unique: dict[str, dict[str, str]] = {}
    for blocker in blockers:
        unique.setdefault(blocker["reference"], blocker)
    return list(unique.values())


def add_months_clamped(value: date, months: int) -> date:
    """Add calendar months, clamping to the destination month's last day."""

    if months < 0:
        raise ValidationError("months must not be negative.")
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_monitoring_plan(
    intake: Mapping[str, Any], aml_result: Mapping[str, Any], *, generated_at: str
) -> dict[str, Any]:
    """Build a review schedule from explicit engagement and review-mode inputs."""

    engagement_kind = intake["engagement"]["kind"]
    assessment_date = _parse_date(
        intake["aml"]["assessment_date"], "aml.assessment_date"
    )
    if engagement_kind == "one_off":
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "not_scheduled_one_off",
            "engagement_kind": engagement_kind,
            "minimum_verification_mode_for_review": aml_result[
                "minimum_verification_mode_for_review"
            ],
            "review_interval_months": None,
            "next_review_date": None,
            "professional_review_required": True,
        }
    mode = aml_result["minimum_verification_mode_for_review"]
    if not aml_result["table_1_resolved"]:
        interval = None
        status = "blocked_table_1_assessment"
        schedule_basis = (
            "No cadence is proposed until the professional resolves the explicit "
            "Table 1 assessment."
        )
    elif mode == "conduct_rule":
        interval = None
        status = "not_scheduled_conduct_rule"
        schedule_basis = (
            "A confirmed Table 1 conduct rule applies; this engine does not assign "
            "the simplified, ordinary, or enhanced periodic-review cadence."
        )
    elif mode == "simplified":
        interval = 36
        status = "draft_schedule_for_professional_review"
        schedule_basis = (
            "36 months for simplified, 24 months for ordinary, and an explicit "
            "professional choice of 6 or 12 months for enhanced review."
        )
    elif mode == "ordinary":
        interval = 24
        status = "draft_schedule_for_professional_review"
        schedule_basis = (
            "36 months for simplified, 24 months for ordinary, and an explicit "
            "professional choice of 6 or 12 months for enhanced review."
        )
    elif mode == "enhanced":
        interval = intake["aml"].get("enhanced_review_interval_months")
        status = (
            "draft_schedule_for_professional_review"
            if interval in {6, 12}
            else "blocked_enhanced_interval_selection"
        )
        schedule_basis = (
            "36 months for simplified, 24 months for ordinary, and an explicit "
            "professional choice of 6 or 12 months for enhanced review."
        )
    else:
        raise ValidationError("Cannot schedule monitoring without a supported mode.")
    next_date = (
        add_months_clamped(assessment_date, interval).isoformat()
        if interval is not None
        else None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": status,
        "engagement_kind": engagement_kind,
        "minimum_verification_mode_for_review": mode,
        "review_interval_months": interval,
        "next_review_date": next_date,
        "professional_review_required": True,
        "schedule_basis": schedule_basis,
    }


def _review_item(
    *,
    item_id: str,
    item_type: str,
    title: str,
    data: Mapping[str, Any],
    source_ids: Iterable[str] = (),
    recommended_action: str = "mark_unclear",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "item_type": item_type,
        "title": title,
        "status": "needs_review",
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "recommended_action": recommended_action,
        "source_ids": list(source_ids),
        "data": dict(data),
    }


def _localized_review_copy(language: str, key: str, **values: object) -> str:
    """Render complete reviewer-facing copy in the requested intake language."""

    translations = _REVIEW_COPY.get(key)
    if translations is None or language not in translations:
        raise ValidationError(
            f"Review copy {key!r} is unavailable for language {language!r}."
        )
    return translations[language].format(**values)


def _localized_review_topic(language: str, topic: str) -> str:
    """Return a display label while leaving the topic code itself unchanged."""

    translations = _REVIEW_TOPIC_COPY.get(topic)
    if translations is None or language not in translations:
        raise ValidationError(
            f"Review topic {topic!r} is unavailable for language {language!r}."
        )
    return translations[language]


def _localize_review_items(
    items: Sequence[Mapping[str, Any]], *, language: str
) -> list[dict[str, Any]]:
    """Localize every final review title and fail closed for an unmapped item type."""

    static_title_keys = {
        "marketing_consent": "title.marketing_consent",
        "aml_assessment": "title.aml_table_1",
        "monitoring_plan": "title.monitoring_plan",
        "party_profile": "title.party_profile",
        "party_structure": "title.party_structure",
        "engagement": "title.engagement",
        "aml_trigger_set": "title.aml_trigger_set",
        "missing_evidence": "title.missing_evidence",
    }
    localized: list[dict[str, Any]] = []
    for item in items:
        item_type = str(item["item_type"])
        data = item["data"]
        if item_type == "privacy_processing":
            title = _localized_review_copy(
                language,
                "title.privacy_processing",
                number=str(item["id"]).rsplit("-", 1)[-1],
            )
        elif item_type == "document_applicability":
            topic = str(data["topic"])
            title = _localized_review_copy(
                language,
                "title.applicability",
                topic=_localized_review_topic(language, topic),
            )
        elif item_type == "screening_subject":
            title = _localized_review_copy(
                language,
                "title.screening_subject",
                subject_reference=data["subject_reference"],
            )
        elif item_type == "aml_factor_section":
            title = _localized_review_copy(
                language,
                "title.aml_factor_section",
                section=data["section"],
            )
        elif item_type in static_title_keys:
            title = _localized_review_copy(language, static_title_keys[item_type])
        else:
            raise ValidationError(
                "Final review item type has no localized title: " f"{item_type!r}."
            )
        localized_item = dict(item)
        localized_item["title"] = title
        localized.append(localized_item)
    return localized


def build_review_payload(
    intake: Mapping[str, Any],
    aml_result: Mapping[str, Any],
    missing_evidence: Mapping[str, Any],
    document_plan: Mapping[str, Any],
    monitoring_plan: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    *,
    run_id: str,
    generated_at: str,
    case_facts_artifact: Mapping[str, Any] | None = None,
    applicability_artifact: Mapping[str, Any] | None = None,
    source_registry_artifact: Mapping[str, Any] | None = None,
    client_file_preparation_verification: Mapping[str, Any] | None = None,
    temporal_validity: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a bounded private review payload with professionally useful case data."""

    items: list[dict[str, Any]] = []
    fact_codes_by_id = {
        fact["fact_id"]: fact["fact_code"] for fact in intake["party_facts"]
    }

    for fact_name, fact in intake["tax_facts"].items():
        items.append(
            _review_item(
                item_id=f"party_tax_fact:{fact_name}",
                item_type="party_fact",
                title=f"Party tax fact — {fact_name}",
                data={
                    "fact_code": fact_name,
                    "value": fact.get("value"),
                    "confirmation_status": fact["verification_status"],
                    "evidence_count": len(fact.get("evidence_ids", [])),
                },
            )
        )
    binding_verification = dict(client_file_preparation_verification or {})
    items.append(
        _review_item(
            item_id="client_file_preparation:binding",
            item_type="client_file_preparation_binding",
            title="Client File Preparation evidence binding",
            data={
                "binding_mode": intake["client_file_preparation_binding"]["mode"],
                "verification_status": binding_verification.get(
                    "verification_status", "verification_not_run"
                ),
                "final_ready": binding_verification.get("final_ready") is True,
                "reviewed_client_file_preparation": binding_verification.get(
                    "reviewed_client_file_preparation"
                )
                is True,
                "manifest_sha256": binding_verification.get("manifest_sha256"),
                "package_hash": binding_verification.get("package_hash"),
                "verified_output_count": binding_verification.get("output_count", 0),
                "relationship_blocker": binding_verification.get("relationship_blocker")
                is True,
            },
        )
    )
    items.append(
        _review_item(
            item_id="party:representative-posture",
            item_type="representative_posture",
            title="Representative and executor posture",
            data={
                "status": intake["representative_posture"]["status"],
                "representative_count": len(intake["representatives"]),
                "executor_selected": bool(
                    intake["representative_posture"].get("executor_reference")
                ),
                "basis_recorded": bool(intake["representative_posture"].get("basis")),
                "evidence_count": len(
                    intake["representative_posture"].get("evidence_ids", [])
                ),
            },
        )
    )
    items.append(
        _review_item(
            item_id="party:ownership-posture",
            item_type="ownership_status",
            title="Beneficial-ownership posture",
            data={
                "status": intake["ownership_status"]["status"],
                "owner_count": len(intake["beneficial_owners"]),
                "basis_recorded": bool(intake["ownership_status"].get("basis")),
                "evidence_count": len(
                    intake["ownership_status"].get("evidence_ids", [])
                ),
            },
        )
    )
    as_of = date.fromisoformat(generated_at[:10])
    for evidence in intake["evidence_register"]:
        expires_on = evidence.get("expires_on")
        items.append(
            _review_item(
                item_id=f"evidence:{evidence['evidence_id']}",
                item_type="evidence_record",
                title="Evidence record — " + evidence["evidence_id"],
                data={
                    "evidence_id": evidence["evidence_id"],
                    "evidence_type": evidence["evidence_type"],
                    "declared_status": evidence["status"],
                    "obtained_on": evidence.get("obtained_on"),
                    "expires_on": expires_on,
                    "freshness_status": (
                        "expired"
                        if expires_on is not None
                        and _parse_date(expires_on, "review_evidence.expires_on")
                        < as_of
                        else "current_or_not_dated"
                    ),
                    "byte_hash_recorded": bool(evidence.get("sha256")),
                    "local_path_excluded": True,
                },
            )
        )
    for index, decision in enumerate(intake["privacy_processing_decisions"], start=1):
        legal_basis = decision.get("controller_legal_basis")
        items.append(
            _review_item(
                item_id=f"privacy:processing-{index:02d}",
                item_type="privacy_processing",
                title=f"Privacy processing decision — purpose {index:02d}",
                source_ids=decision["source_ids"],
                recommended_action=(
                    "accept"
                    if decision["review_status"] == "confirmed"
                    else "mark_unclear"
                ),
                data={
                    "decision_alias": f"processing-{index:02d}",
                    "purpose": decision["purpose"],
                    "role": decision["role"],
                    "legal_basis_code": (
                        legal_basis.get("code")
                        if isinstance(legal_basis, dict)
                        else None
                    ),
                    "processor_authority_recorded": bool(
                        decision.get("processor_authority_reference")
                    ),
                    "retention_status": decision["retention"]["status"],
                    "review_status": decision["review_status"],
                    "source_count": len(decision["source_ids"]),
                },
            )
        )
    marketing = intake["marketing_consent"]
    items.append(
        _review_item(
            item_id="marketing:consent",
            item_type="marketing_consent",
            title="Separate marketing-consent record",
            recommended_action=(
                "accept"
                if marketing["review_status"] in {"confirmed", "not_required"}
                else "mark_unclear"
            ),
            data={
                "scope": "marketing_only",
                "request_status": marketing["request_status"],
                "choice": marketing["choice"],
                "purpose_count": len(marketing["purposes"]),
                "channel_count": len(marketing["channels"]),
                "review_status": marketing["review_status"],
                "relationship_export_blocking": False,
            },
        )
    )
    for fact in intake["party_facts"]:
        items.append(
            _review_item(
                item_id=f"party_fact:{fact['fact_id']}",
                item_type="party_fact",
                title=f"Party fact — {fact['fact_code']}",
                data={
                    "fact_code": fact["fact_code"],
                    "value": fact.get("value"),
                    "confirmation_status": fact["verification_status"],
                    "evidence_count": len(fact.get("evidence_ids", [])),
                },
            )
        )
    party_identity = intake["party_identity_document"]
    items.append(
        _review_item(
            item_id="party_identity:primary",
            item_type="party_fact",
            title="Primary party identity verification",
            data={
                "fact_code": "identity_document_verification",
                "confirmation_status": party_identity["verification_status"],
                "document_type": party_identity.get("document_type"),
                "document_number": party_identity.get("document_number"),
                "verification_date": party_identity.get("verified_on"),
                "expires_on": party_identity.get("expires_on"),
                "freshness_status": (
                    "expired"
                    if party_identity.get("expires_on") is not None
                    and _parse_date(
                        party_identity["expires_on"],
                        "party_identity_document.expires_on",
                    )
                    < as_of
                    else "current_or_not_dated"
                ),
                "evidence_count": len(party_identity.get("evidence_ids", [])),
            },
        )
    )
    for representative in intake["representatives"]:
        identity = representative["identity_document"]
        reference = representative["representative_reference"]
        items.append(
            _review_item(
                item_id=f"representative:{reference}",
                item_type="representative_fact",
                title=f"Representative or executor — {reference}",
                data={
                    "representative_reference": reference,
                    "role": representative["role"],
                    "authority_basis": representative.get("authority_basis"),
                    "confirmation_status": identity["verification_status"],
                    "verification_date": identity.get("verified_on"),
                    "expires_on": identity.get("expires_on"),
                    "freshness_status": (
                        "expired"
                        if identity.get("expires_on") is not None
                        and _parse_date(
                            identity["expires_on"],
                            "representative.identity_document.expires_on",
                        )
                        < as_of
                        else "current_or_not_dated"
                    ),
                    "document_number": identity.get("document_number"),
                    "evidence_count": len(
                        set(representative.get("evidence_ids", []))
                        | set(identity.get("evidence_ids", []))
                    ),
                },
            )
        )
    for owner in intake["beneficial_owners"]:
        identity = owner["identity_document"]
        reference = owner["owner_reference"]
        items.append(
            _review_item(
                item_id=f"beneficial_owner:{reference}",
                item_type="beneficial_owner_fact",
                title=f"Beneficial owner — {reference}",
                data={
                    "owner_reference": reference,
                    "control_basis": owner.get("control_basis"),
                    "confirmation_status": owner["verification_status"],
                    "identity_verification_status": identity["verification_status"],
                    "verification_date": identity.get("verified_on"),
                    "expires_on": identity.get("expires_on"),
                    "freshness_status": (
                        "expired"
                        if identity.get("expires_on") is not None
                        and _parse_date(
                            identity["expires_on"],
                            "beneficial_owner.identity_document.expires_on",
                        )
                        < as_of
                        else "current_or_not_dated"
                    ),
                    "document_number": identity.get("document_number"),
                    "evidence_count": len(
                        set(owner.get("evidence_ids", []))
                        | set(identity.get("evidence_ids", []))
                    ),
                },
            )
        )
    for service in intake["engagement"]["services"]:
        items.append(
            _review_item(
                item_id=f"engagement_service:{service['service_id']}",
                item_type="engagement_service",
                title=f"Engagement service — {service['service_id']}",
                data={
                    "service_id": service["service_id"],
                    "confirmation_status": service["assessment_status"],
                    "description": service.get("description"),
                },
            )
        )
    terms = intake["engagement"]["terms"]
    items.append(
        _review_item(
            item_id="engagement:terms",
            item_type="engagement_terms",
            title="Engagement terms",
            data={
                "review_status": terms["review_status"],
                "duration_months": terms.get("duration_months"),
                "notice_days": terms.get("notice_days"),
                "advance_amount": terms.get("advance_amount"),
                "currency": terms.get("currency"),
                "payment_terms_recorded": bool(terms.get("payment_terms")),
                "indexation_basis_recorded": bool(terms.get("indexation_basis")),
                "insurance_reference_recorded": bool(terms.get("insurance_reference")),
            },
        )
    )
    for screening in intake["screening_results"]:
        resolution = screening.get("professional_resolution")
        items.append(
            _review_item(
                item_id=f"screening:{screening['screening_id']}",
                item_type="screening_result",
                title=f"Screening result — {screening['screening_type']}",
                data={
                    "screening_id": screening["screening_id"],
                    "subject_reference": screening["subject_reference"],
                    "screening_type": screening["screening_type"],
                    "source_reference": screening["source_reference"],
                    "checked_at": screening["checked_at"],
                    "outcome": screening["outcome"],
                    "confirmation_status": screening["review_status"],
                    "resolution_status": (
                        resolution.get("status")
                        if isinstance(resolution, dict)
                        else None
                    ),
                    "relationship_decision": (
                        resolution.get("relationship_decision")
                        if isinstance(resolution, dict)
                        else None
                    ),
                    "resolution_evidence_count": (
                        len(resolution.get("evidence_ids", []))
                        if isinstance(resolution, dict)
                        else 0
                    ),
                },
            )
        )
    for group_name in ("factors_a", "factors_b"):
        for factor in intake["aml"][group_name]:
            items.append(
                _review_item(
                    item_id=f"aml_factor:{factor['factor_id']}",
                    item_type="aml_risk_factor",
                    title=f"AML risk factor — {factor['factor_id']}",
                    data={
                        "factor_code": factor["factor_id"],
                        "score": factor["score"],
                        "confirmation_status": factor["assessment_status"],
                        "basis": factor.get("basis"),
                        "evidence_count": len(factor.get("evidence_ids", [])),
                    },
                )
            )
    for record in intake["applicability"]:
        supporting_fact_codes = [
            fact_codes_by_id[fact_id] for fact_id in record["case_fact_ids"]
        ]
        items.append(
            _review_item(
                item_id=f"applicability:{record['topic']}",
                item_type="document_applicability",
                title=f"Applicability — {record['topic']}",
                source_ids=record.get("source_ids", []),
                recommended_action=(
                    "accept"
                    if record["review_status"] == "confirmed"
                    and record["applicability_status"] != "unclear"
                    else "mark_unclear"
                ),
                data={
                    "topic": record["topic"],
                    "applicability_status": record["applicability_status"],
                    "review_status": record["review_status"],
                    "basis": record.get("basis"),
                    "supporting_case_fact_codes": supporting_fact_codes,
                    "supporting_case_fact_count": len(supporting_fact_codes),
                },
            )
        )
    table_1 = intake["aml"]["table_1_assessment"]
    items.append(
        _review_item(
            item_id="aml:table_1",
            item_type="aml_assessment",
            title="AML Table 1 applicability",
            recommended_action=(
                "accept" if aml_result["table_1_resolved"] else "mark_unclear"
            ),
            data={
                "calculation_status": (
                    f"table_1_{table_1['review_status']}_{table_1['status']}_"
                    "basis_recorded"
                ),
                "minimum_verification_mode_for_review": aml_result[
                    "baseline_verification_mode"
                ],
                "uses_proposed_inputs": not aml_result["table_1_resolved"],
                "professional_review_required": True,
            },
        )
    )
    items.append(
        _review_item(
            item_id="aml:calculation",
            item_type="aml_assessment",
            title="AML arithmetic and treatment floor",
            data={
                "calculation_status": aml_result["status"],
                "effective_risk": aml_result["effective_risk"],
                "minimum_verification_mode_for_review": aml_result[
                    "minimum_verification_mode_for_review"
                ],
                "uses_proposed_inputs": aml_result["uses_proposed_inputs"],
                "professional_review_required": True,
            },
        )
    )
    items.append(
        _review_item(
            item_id="missing:summary",
            item_type="missing_evidence",
            title="Missing evidence and unresolved information summary",
            data={
                "missing_evidence_count": missing_evidence["count"],
                "evidence_status": missing_evidence["status"],
            },
        )
    )
    for trigger in intake["aml"]["mandatory_enhanced_triggers"]:
        items.append(
            _review_item(
                item_id=f"aml_trigger:{trigger['trigger_id']}",
                item_type="aml_mandatory_trigger",
                title=f"Mandatory enhanced-measure trigger — {trigger['trigger_id']}",
                data={
                    "trigger_id": trigger["trigger_id"],
                    "status": trigger["status"],
                    "review_status": trigger["review_status"],
                    "basis": trigger.get("basis"),
                },
            )
        )
    for index, item in enumerate(missing_evidence["items"], start=1):
        items.append(
            _review_item(
                item_id=f"missing:item-{index:02d}",
                item_type="missing_evidence",
                title=f"Missing information — {item['item_type']}",
                data={
                    "reference": item["reference"],
                    "reason": item["reason"],
                },
            )
        )
    items.append(
        _review_item(
            item_id="documents:plan",
            item_type="document_plan",
            title="Document applicability and template-reference plan",
            data={
                "documents": [
                    {
                        "document_type": document["document_type"],
                        "status": document["status"],
                        "template_reference_id": (
                            document["template_reference"]["template_id"]
                            if document["template_reference"] is not None
                            else None
                        ),
                    }
                    for document in document_plan["documents"]
                ]
            },
        )
    )
    used_source_ids = {
        source_id
        for record in intake["applicability"]
        for source_id in record.get("source_ids", [])
    }
    used_source_ids.update(
        source_id
        for decision in intake["privacy_processing_decisions"]
        for source_id in decision.get("source_ids", [])
    )
    used_source_ids.update(
        source_id
        for template in intake["template_references"]
        for source_id in template.get("source_ids", [])
    )
    for source in source_registry["sources"]:
        if source["source_id"] not in used_source_ids:
            continue
        items.append(
            _review_item(
                item_id=f"official_source:{source['source_id']}",
                item_type="official_source",
                title=f"Source — {source['source_id']}",
                source_ids=[source["source_id"]],
                data={
                    "source_id": source["source_id"],
                    "title": source["title"],
                    "issuer": source["issuer"],
                    "version": source["version"],
                    "authority": source["authority"],
                    "public_url_recorded_locally": bool(source.get("url")),
                },
            )
        )
    items.append(
        _review_item(
            item_id="monitoring:plan",
            item_type="monitoring_plan",
            title="Ongoing-review schedule",
            recommended_action=(
                "accept"
                if not str(monitoring_plan["status"]).startswith("blocked_")
                else "mark_unclear"
            ),
            data={
                "status": monitoring_plan["status"],
                "review_interval_months": monitoring_plan["review_interval_months"],
                "next_review_date": monitoring_plan["next_review_date"],
                "minimum_verification_mode_for_review": monitoring_plan[
                    "minimum_verification_mode_for_review"
                ],
            },
        )
    )
    # Mechanically verified and duplicative rows remain available in the bound local
    # artifacts. The professional workbench groups the decisions that actually need
    # judgment so a normal company is not forced through dozens of redundant accepts.
    omitted_types = {
        "party_fact",
        "representative_fact",
        "beneficial_owner_fact",
        "representative_posture",
        "ownership_status",
        "evidence_record",
        "engagement_service",
        "engagement_terms",
        "screening_result",
        "aml_risk_factor",
        "aml_mandatory_trigger",
        "missing_evidence",
        "document_plan",
        "official_source",
        "client_file_preparation_binding",
    }
    items = [
        item
        for item in items
        if item["item_type"] not in omitted_types and item["id"] != "aml:calculation"
    ]
    items.extend(
        [
            _review_item(
                item_id="party:profile",
                item_type="party_profile",
                title="Party profile and identity evidence",
                recommended_action=(
                    "accept"
                    if all(
                        fact["verification_status"] in {"verified", "not_applicable"}
                        for fact in intake["tax_facts"].values()
                    )
                    and all(
                        fact["verification_status"] in {"verified", "not_applicable"}
                        for fact in intake["party_facts"]
                    )
                    and intake["party_identity_document"]["verification_status"]
                    in {"verified", "not_applicable"}
                    and not any(
                        item["reason"]
                        in {"evidence_expired", "identity_document_expired"}
                        for item in missing_evidence["items"]
                    )
                    else "mark_unclear"
                ),
                data={
                    "client_reference": intake["client_reference"],
                    "client_type": intake["client_type"],
                    "tax_fact_statuses": [
                        {
                            "tax_fact_type": name,
                            "value": fact.get("value"),
                            "verification_status": fact["verification_status"],
                        }
                        for name, fact in intake["tax_facts"].items()
                    ],
                    "party_facts": [
                        {
                            "fact_code": fact["fact_code"],
                            "value": fact.get("value"),
                            "verification_status": fact["verification_status"],
                        }
                        for fact in intake["party_facts"]
                    ],
                    "identity_status": intake["party_identity_document"][
                        "verification_status"
                    ],
                    "identity_expires_on": intake["party_identity_document"].get(
                        "expires_on"
                    ),
                    "identity_document_number": intake["party_identity_document"].get(
                        "document_number"
                    ),
                },
            ),
            _review_item(
                item_id="party:structure",
                item_type="party_structure",
                title="Representatives, executor and beneficial ownership",
                recommended_action=(
                    "accept"
                    if intake["representative_posture"]["status"] != "pending"
                    and intake["ownership_status"]["status"] != "pending"
                    and all(
                        representative["identity_document"]["verification_status"]
                        == "verified"
                        for representative in intake["representatives"]
                    )
                    and all(
                        owner["verification_status"] == "verified"
                        and owner["identity_document"]["verification_status"]
                        == "verified"
                        for owner in intake["beneficial_owners"]
                    )
                    else "mark_unclear"
                ),
                data={
                    "representative_posture_status": intake["representative_posture"][
                        "status"
                    ],
                    "representative_roles": [
                        representative["role"]
                        for representative in intake["representatives"]
                    ],
                    "representative_identity_statuses": [
                        representative["identity_document"]["verification_status"]
                        for representative in intake["representatives"]
                    ],
                    "executor_selected": bool(
                        intake["representative_posture"].get("executor_reference")
                    ),
                    "ownership_status": intake["ownership_status"]["status"],
                    "owner_count": len(intake["beneficial_owners"]),
                    "owner_verification_statuses": [
                        owner["verification_status"]
                        for owner in intake["beneficial_owners"]
                    ],
                    "owner_identity_statuses": [
                        owner["identity_document"]["verification_status"]
                        for owner in intake["beneficial_owners"]
                    ],
                    "representatives": [
                        {
                            "representative_reference": representative[
                                "representative_reference"
                            ],
                            "role": representative["role"],
                            "authority_basis": representative.get("authority_basis"),
                            "document_number": representative["identity_document"].get(
                                "document_number"
                            ),
                        }
                        for representative in intake["representatives"]
                    ],
                    "beneficial_owners": [
                        {
                            "owner_reference": owner["owner_reference"],
                            "control_basis": owner.get("control_basis"),
                            "document_number": owner["identity_document"].get(
                                "document_number"
                            ),
                        }
                        for owner in intake["beneficial_owners"]
                    ],
                },
            ),
            _review_item(
                item_id="engagement:scope-and-terms",
                item_type="engagement",
                title="Engagement scope and terms",
                recommended_action=(
                    "accept"
                    if all(
                        service["assessment_status"] == "confirmed"
                        for service in intake["engagement"]["services"]
                    )
                    and terms["review_status"] == "confirmed"
                    else "mark_unclear"
                ),
                data={
                    "engagement_kind": intake["engagement"]["kind"],
                    "services": [
                        {
                            "service_id": service["service_id"],
                            "assessment_status": service["assessment_status"],
                            "description": service["description"],
                        }
                        for service in intake["engagement"]["services"]
                    ],
                    "terms_review_status": terms["review_status"],
                    "duration_months": terms.get("duration_months"),
                    "notice_days": terms.get("notice_days"),
                    "advance_amount": terms.get("advance_amount"),
                    "currency": terms.get("currency"),
                    "payment_terms_recorded": bool(terms.get("payment_terms")),
                    "indexation_basis_recorded": bool(terms.get("indexation_basis")),
                    "insurance_reference_recorded": bool(
                        terms.get("insurance_reference")
                    ),
                },
            ),
        ]
    )
    screenings_by_subject: dict[str, list[dict[str, Any]]] = {}
    for screening in intake["screening_results"]:
        resolution = screening.get("professional_resolution")
        screenings_by_subject.setdefault(screening["subject_reference"], []).append(
            {
                "screening_id": screening["screening_id"],
                "screening_type": screening["screening_type"],
                "subject_reference": screening["subject_reference"],
                "source_reference": screening["source_reference"],
                "outcome": screening["outcome"],
                "review_status": screening["review_status"],
                "checked_at": screening.get("checked_at"),
                "source_recorded": bool(screening.get("source_reference")),
                "resolution_status": (
                    resolution.get("status") if isinstance(resolution, dict) else None
                ),
                "relationship_decision": (
                    resolution.get("relationship_decision")
                    if isinstance(resolution, dict)
                    else None
                ),
            }
        )
    for subject_reference, results in screenings_by_subject.items():
        items.append(
            _review_item(
                item_id=f"screening_subject:{subject_reference}",
                item_type="screening_subject",
                title=f"Screening coverage — {subject_reference}",
                recommended_action=(
                    "accept"
                    if all(
                        result["review_status"] == "confirmed"
                        and (
                            result["outcome"] == "clear"
                            or result["resolution_status"] == "confirmed"
                        )
                        for result in results
                    )
                    else "mark_unclear"
                ),
                data={
                    "subject_reference": subject_reference,
                    "coverage_complete": {
                        result["screening_type"] for result in results
                    }
                    == set(SCREENING_TYPES),
                    "results": sorted(
                        results, key=lambda result: result["screening_type"]
                    ),
                },
            )
        )
    for group_name, label in (("factors_a", "A"), ("factors_b", "B")):
        factors = intake["aml"][group_name]
        items.append(
            _review_item(
                item_id=f"aml_factor_section:{label}",
                item_type="aml_factor_section",
                title=f"AML risk-factor section {label}",
                recommended_action=(
                    "accept"
                    if all(
                        factor["assessment_status"] == "confirmed" for factor in factors
                    )
                    else "mark_unclear"
                ),
                data={
                    "section": label,
                    "factors": [
                        {
                            "factor_code": factor["factor_id"],
                            "score": factor["score"],
                            "assessment_status": factor["assessment_status"],
                            "basis": factor.get("basis"),
                            "evidence_count": len(factor.get("evidence_ids", [])),
                        }
                        for factor in factors
                    ],
                },
            )
        )
    items.append(
        _review_item(
            item_id="aml:mandatory-trigger-set",
            item_type="aml_trigger_set",
            title="Mandatory enhanced-measure triggers",
            recommended_action=(
                "accept"
                if all(
                    trigger["review_status"] == "confirmed"
                    and trigger["status"] != "unknown"
                    for trigger in intake["aml"]["mandatory_enhanced_triggers"]
                )
                else "mark_unclear"
            ),
            data={
                "triggers": [
                    {
                        "trigger_id": trigger["trigger_id"],
                        "status": trigger["status"],
                        "review_status": trigger["review_status"],
                        "basis": trigger.get("basis"),
                    }
                    for trigger in intake["aml"]["mandatory_enhanced_triggers"]
                ],
            },
        )
    )
    if missing_evidence["count"]:
        reason_counts: dict[str, int] = {}
        missing_type_counts: dict[str, int] = {}
        for missing_item in missing_evidence["items"]:
            reason = str(missing_item["reason"])
            item_type = str(missing_item["item_type"])
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            missing_type_counts[item_type] = missing_type_counts.get(item_type, 0) + 1
        items.append(
            _review_item(
                item_id="missing:grouped",
                item_type="missing_evidence",
                title="Missing evidence and unresolved information",
                recommended_action="request_more_documents",
                data={
                    "missing_evidence_count": missing_evidence["count"],
                    "evidence_status": missing_evidence["status"],
                    "reason_counts": reason_counts,
                    "item_type_counts": missing_type_counts,
                },
            )
        )
    review_language = str(intake["language"])
    items = _localize_review_items(items, language=review_language)
    case_facts_value = case_facts_artifact or build_case_facts(
        intake,
        generated_at=generated_at,
        client_file_preparation_verification=client_file_preparation_verification,
    )
    applicability_value = applicability_artifact or build_applicability_plan(
        intake, generated_at=generated_at
    )
    source_registry_value = source_registry_artifact or source_registry
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": SCHEMA_VERSION,
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": run_id,
        "review_revision": 1,
        "generated_at": generated_at,
        "temporal_validity": dict(temporal_validity),
        "status": "pending_review",
        "source_paths": [],
        "review_type": "professional_new_client",
        "item_count": len(items),
        "columns": ["title", "status", "source_ids", "data"],
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "privacy": {
            "classification": "private_professional_review",
            "excluded": ["credentials", "session secrets", "raw evidence paths"],
        },
        "summary": {
            "review_item_count": len(items),
            "missing_information_count": missing_evidence["count"],
            "aml_status": aml_result["status"],
            "document_count": len(document_plan["documents"]),
            "jurisdiction": intake["jurisdiction"],
            "country_pack": ITALY_COUNTRY_PACK,
            "language": intake["language"],
        },
        "source_artifacts": {
            "facts": {
                "path": "case_facts_validated.json",
                "type": "private_professional_facts",
                "sha256": canonical_json_hash(case_facts_value),
            },
            "sources": {
                "path": "source_registry.json",
                "type": "source_versions",
                "count": len(source_registry["sources"]),
                "sha256": canonical_json_hash(source_registry_value),
            },
            "applicability": {
                "path": "applicability_plan_validated.json",
                "type": "professional_applicability_inputs",
                "sha256": canonical_json_hash(applicability_value),
            },
            "aml": {
                "path": "aml_calculation_audit.json",
                "type": "formula_audit",
                "sha256": canonical_json_hash(aml_result),
            },
            "documents": {
                "path": "document_plan.json",
                "type": "document_plan",
                "count": len(document_plan["documents"]),
                "sha256": canonical_json_hash(document_plan),
            },
            "monitoring": {
                "path": "monitoring_plan.json",
                "type": "review_schedule",
                "sha256": canonical_json_hash(monitoring_plan),
            },
        },
        "basis_hashes": {
            "new_client_input": canonical_json_hash(intake),
            "aml": canonical_json_hash(aml_result),
            "documents": canonical_json_hash(document_plan),
            "monitoring": canonical_json_hash(monitoring_plan),
            "sources": canonical_json_hash(source_registry_value),
        },
        "professional_review_required": True,
        "signature_performed": False,
        "client_communication_sent": False,
        "relationship_activation_performed": False,
        "items": items,
    }
    validate_review_payload_privacy(payload, intake)
    return payload


def _walk_json(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key, nested
            yield from _walk_json(nested)
    elif isinstance(value, list):
        for nested in value:
            yield None, nested
            yield from _walk_json(nested)


def validate_review_payload_privacy(
    payload: Mapping[str, Any], intake: Mapping[str, Any] | None = None
) -> None:
    """Reject credentials, session material, and raw local evidence paths."""

    for key, value in _walk_json(payload):
        if key is not None and key.casefold() in _REVIEW_FORBIDDEN_KEYS:
            raise ValidationError(
                "review_payload.json contains forbidden credential, session, "
                f"or local-path field {key!r}."
            )


def _assert_no_forbidden_statuses(payload: Any, artifact_name: str) -> None:
    for key, value in _walk_json(payload):
        if key == "status" and isinstance(value, str):
            if value.casefold() in _FORBIDDEN_OUTCOME_STATUSES:
                raise ValidationError(
                    f"{artifact_name} contains forbidden outcome status {value!r}."
                )


def _validate_aml_audit(payload: Mapping[str, Any]) -> None:
    try:
        ri = Decimal(str(payload["inherent_risk"]))
        rs = Decimal(str(payload["specific_risk"]))
        expected = (ri * Decimal("0.30")) + (rs * Decimal("0.70"))
        actual = Decimal(str(payload["effective_risk"]))
    except (KeyError, InvalidOperation) as exc:
        raise ValidationError("AML calculation audit is incomplete.") from exc
    if abs(expected - actual) > Decimal("0.0001"):
        raise ValidationError("AML effective-risk arithmetic does not reconcile.")
    section_b_mode = payload.get("section_b_mode")
    a_total = Decimal(str(payload.get("factor_a_total")))
    if section_b_mode == "full":
        b_total = Decimal(str(payload.get("factor_b_total")))
        expected_rs = (a_total + b_total) / Decimal("10")
    elif section_b_mode == "excluded_confirmed":
        expected_rs = a_total / Decimal("4")
    else:
        raise ValidationError("AML calculation audit has an invalid Section B mode.")
    if abs(expected_rs - rs) > Decimal("0.0001"):
        raise ValidationError("AML specific-risk arithmetic does not reconcile.")


def _validate_export_gate(
    manifest: Mapping[str, Any],
    review_payload: Mapping[str, Any],
    *,
    output_dir: Path,
    outputs_by_name: Mapping[str, Any],
) -> None:
    gate = _require_object(manifest.get("export_gate"), "final_artifacts.export_gate")
    if gate.get("contract_version") != SCHEMA_VERSION:
        raise ValidationError(
            f"final_artifacts.export_gate.contract_version must be {SCHEMA_VERSION}."
        )
    if gate.get("export_scope") != "owner_only_professional_review_dossier":
        raise ValidationError("final_artifacts.export_gate.export_scope is invalid.")
    _parse_timestamp(
        gate.get("evaluated_at"), "final_artifacts.export_gate.evaluated_at"
    )
    if gate.get("review_revision") != review_payload.get("review_revision"):
        raise ValidationError(
            "final_artifacts.export_gate.review_revision must match review_payload."
            "review_revision."
        )
    if gate.get("status") not in {
        "blocked",
        "pending_review",
        "ready_for_professional_export",
    }:
        raise ValidationError("final_artifacts.export_gate.status is unsupported.")
    if manifest.get("status") != gate["status"]:
        raise ValidationError(
            "final_artifacts.status must match final_artifacts.export_gate.status."
        )
    blocker_groups: dict[str, list[Any]] = {}
    for group in (
        "domain_blockers",
        "review_blockers",
        "artifact_blockers",
        "marketing_only_blockers",
    ):
        blockers = _require_list(
            gate.get(group), f"final_artifacts.export_gate.{group}"
        )
        blocker_groups[group] = blockers
        for index, raw_blocker in enumerate(blockers):
            blocker = _require_object(
                raw_blocker, f"final_artifacts.export_gate.{group}[{index}]"
            )
            expected_fields = {"code", "reference", "scope"}
            if group == "domain_blockers":
                expected_fields.add("domain")
            if set(blocker) != expected_fields:
                raise ValidationError(
                    f"final_artifacts.export_gate.{group}[{index}] must contain "
                    f"exactly {sorted(expected_fields)}."
                )
            _require_reference(
                blocker.get("code"),
                f"final_artifacts.export_gate.{group}[{index}].code",
            )
            _require_reference(
                blocker.get("reference"),
                f"final_artifacts.export_gate.{group}[{index}].reference",
            )
            scope = _require_string(
                blocker.get("scope"),
                f"final_artifacts.export_gate.{group}[{index}].scope",
            )
            if scope not in {
                "relationship_export",
                "marketing_use",
            } and not re.fullmatch(r"document:[A-Za-z0-9_.:-]{3,80}", scope):
                raise ValidationError(
                    f"final_artifacts.export_gate.{group}[{index}].scope is invalid."
                )
            if group == "marketing_only_blockers" and scope != "marketing_use":
                raise ValidationError(
                    "Every marketing_only_blocker must have scope=marketing_use."
                )
            if group == "domain_blockers":
                _require_reference(
                    blocker.get("domain"),
                    f"final_artifacts.export_gate.{group}[{index}].domain",
                )
    required_outputs = _require_list(
        gate.get("required_outputs"), "final_artifacts.export_gate.required_outputs"
    )
    if not required_outputs:
        raise ValidationError("final_artifacts.export_gate.required_outputs is empty.")
    required_names: list[str] = []
    for index, raw_name in enumerate(required_outputs):
        name = _require_string(
            raw_name, f"final_artifacts.export_gate.required_outputs[{index}]"
        )
        if Path(name).name != name or name in {".", "..", "final_artifacts.json"}:
            raise ValidationError(
                "final_artifacts.export_gate.required_outputs must contain only "
                "run-local basenames excluding final_artifacts.json."
            )
        required_names.append(name)
    if len(required_names) != len(set(required_names)):
        raise ValidationError(
            "final_artifacts.export_gate.required_outputs must be unique."
        )
    expected_names = set(EXPECTED_ARTIFACTS) - {"final_artifacts.json"}
    if set(required_names) != expected_names:
        raise ValidationError(
            "final_artifacts.export_gate.required_outputs does not match the "
            "required package outputs."
        )
    for name in required_names:
        record = outputs_by_name.get(name)
        if not isinstance(record, dict):
            raise ValidationError(f"Required output {name!r} is not listed.")
        path = output_dir / name
        if path.stat().st_size <= 0 or record.get("size_bytes") != path.stat().st_size:
            raise ValidationError(f"Required output {name!r} is empty or mis-sized.")
        if record.get("sha256") != sha256_file(path):
            raise ValidationError(f"Required output hash mismatch for {name}.")
    basis_hashes = _require_object(
        gate.get("basis_hashes"), "final_artifacts.export_gate.basis_hashes"
    )
    if basis_hashes != review_payload.get("basis_hashes"):
        raise ValidationError(
            "final_artifacts.export_gate.basis_hashes must equal review_payload."
            "basis_hashes."
        )
    relationship_review_blockers = [
        blocker
        for blocker in blocker_groups["review_blockers"]
        if isinstance(blocker, dict) and blocker.get("scope") != "marketing_use"
    ]
    relationship_blocked = bool(
        blocker_groups["domain_blockers"]
        or blocker_groups["artifact_blockers"]
        or relationship_review_blockers
    )
    relationship_ready = gate.get("relationship_ready")
    if not isinstance(relationship_ready, bool):
        raise ValidationError(
            "final_artifacts.export_gate.relationship_ready must be boolean."
        )
    if gate["status"] == "ready_for_professional_export":
        if relationship_blocked or relationship_ready is not True:
            raise ValidationError(
                "ready_for_professional_export requires all relationship domain, "
                "review, and artifact gates to be clear."
            )
    elif relationship_ready:
        raise ValidationError(
            "relationship_ready can be true only for ready_for_professional_export."
        )


def validate_contract(output_dir: Path) -> dict[str, Any]:
    """Validate a generated new-client package and its privacy boundary."""

    resolved = output_dir.expanduser().resolve()
    missing: list[str] = []
    non_regular: list[str] = []
    for name in EXPECTED_ARTIFACTS:
        try:
            mode = (resolved / name).lstat().st_mode
        except FileNotFoundError:
            missing.append(name)
            continue
        if not stat.S_ISREG(mode):
            non_regular.append(name)
    if missing:
        raise ValidationError("Missing generated artifacts: " + ", ".join(missing))
    if non_regular:
        raise ValidationError(
            "Generated artifacts must be regular files, not links or special files: "
            + ", ".join(non_regular)
        )
    for name in EXPECTED_ARTIFACTS:
        mode = (resolved / name).stat().st_mode & 0o777
        if mode & 0o077:
            raise ValidationError(f"{name} is not owner-only (mode {oct(mode)}).")
    dir_mode = resolved.stat().st_mode & 0o777
    if dir_mode & 0o077:
        raise ValidationError(
            f"Output directory is not owner-only (mode {oct(dir_mode)})."
        )

    json_payloads: dict[str, dict[str, Any]] = {}
    for name in EXPECTED_ARTIFACTS:
        if name.endswith(".json"):
            payload = load_json(resolved / name)
            json_payloads[name] = payload
            _assert_no_forbidden_statuses(payload, name)
    validate_review_payload_privacy(json_payloads["review_payload.json"])
    _validate_aml_audit(json_payloads["aml_calculation_audit.json"])

    review_payload = json_payloads["review_payload.json"]
    source_artifacts = _require_object(
        review_payload.get("source_artifacts"), "review_payload.source_artifacts"
    )
    expected_source_artifacts = {
        "facts": "case_facts_validated.json",
        "sources": "source_registry.json",
        "applicability": "applicability_plan_validated.json",
        "aml": "aml_calculation_audit.json",
        "documents": "document_plan.json",
        "monitoring": "monitoring_plan.json",
    }
    if set(source_artifacts) != set(expected_source_artifacts):
        raise ValidationError(
            "review_payload.source_artifacts must contain the exact six contract "
            "bindings."
        )
    for key, expected_name in expected_source_artifacts.items():
        binding = _require_object(
            source_artifacts[key], f"review_payload.source_artifacts.{key}"
        )
        if binding.get("path") != expected_name:
            raise ValidationError(
                f"review_payload.source_artifacts.{key}.path must be {expected_name}."
            )
        expected_hash = canonical_json_hash(json_payloads[expected_name])
        if binding.get("sha256") != expected_hash:
            raise ValidationError(
                f"Canonical source artifact hash mismatch for {expected_name}."
            )
    basis_hashes = _require_object(
        review_payload.get("basis_hashes"), "review_payload.basis_hashes"
    )
    if set(basis_hashes) != {
        "new_client_input",
        "aml",
        "documents",
        "monitoring",
        "sources",
    }:
        raise ValidationError("review_payload.basis_hashes has an invalid key set.")
    expected_basis_hashes = {
        "new_client_input": json_payloads["case_facts_validated.json"].get(
            "input_hash"
        ),
        "aml": canonical_json_hash(json_payloads["aml_calculation_audit.json"]),
        "documents": canonical_json_hash(json_payloads["document_plan.json"]),
        "monitoring": canonical_json_hash(json_payloads["monitoring_plan.json"]),
        "sources": canonical_json_hash(json_payloads["source_registry.json"]),
    }
    if basis_hashes != expected_basis_hashes:
        raise ValidationError(
            "review_payload.basis_hashes does not match persisted source artifacts."
        )

    temporal_validity = build_temporal_validity(
        json_payloads["case_facts_validated.json"],
        json_payloads["source_registry.json"],
        generated_at=_require_string(
            review_payload.get("generated_at"), "review_payload.generated_at"
        ),
        document_plan=json_payloads["document_plan.json"],
    )
    if review_payload.get("temporal_validity") != temporal_validity:
        raise ValidationError(
            "review_payload.temporal_validity does not match the persisted material "
            "deadlines."
        )
    if json_payloads["run_intake.json"].get("temporal_validity") != temporal_validity:
        raise ValidationError(
            "run_intake.temporal_validity does not match the persisted material "
            "deadlines."
        )

    manifest = json_payloads["final_artifacts.json"]
    if manifest.get("temporal_validity") != temporal_validity:
        raise ValidationError(
            "final_artifacts.temporal_validity does not match the persisted material "
            "deadlines."
        )
    records = _require_list(manifest.get("outputs"), "final_artifacts.outputs")
    by_name = {
        record.get("path"): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    if len(by_name) != len(records):
        raise ValidationError(
            "final_artifacts.outputs must contain unique records with local paths."
        )
    expected_package_hash = canonical_json_hash(
        {
            record["path"]: record.get("sha256")
            for record in records
            if isinstance(record, dict) and isinstance(record.get("path"), str)
        }
    )
    if manifest.get("package_hash") != expected_package_hash:
        raise ValidationError(
            "final_artifacts.package_hash does not match manifest outputs."
        )
    for name in EXPECTED_ARTIFACTS:
        if name == "final_artifacts.json":
            continue
        record = by_name.get(name)
        if record is None:
            raise ValidationError(f"final_artifacts.json does not list {name}.")
        if record.get("sha256") != sha256_file(resolved / name):
            raise ValidationError(f"Artifact hash mismatch for {name}.")
    _validate_export_gate(
        manifest,
        review_payload,
        output_dir=resolved,
        outputs_by_name=by_name,
    )
    run_id = _require_reference(manifest.get("run_id"), "final_artifacts.run_id")
    if not re.fullmatch(r"new-client-[0-9]{14,}-[0-9a-f]{12}", run_id):
        raise ValidationError(
            "final_artifacts.run_id must be opaque and contract-shaped."
        )
    return {
        "status": "contract_validated_for_professional_review",
        "artifact_count": len(EXPECTED_ARTIFACTS),
        "output_dir": resolved.as_posix(),
    }
