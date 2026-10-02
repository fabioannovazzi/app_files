"""Check ordinary IVP18 front-page data without claiming Anagrafe acceptance.

The official XSD, 2024 technical blocking rules and DM 23 December 1976 checksum
tables justify these mechanical checks. Identifier ownership, powers and source
meaning remain professional judgments; this helper makes no registry requests.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import jsonschema
from lipe_core import ROOT, ContractError, check_references, digest, read_json

__all__ = ["validate_frontpage", "check_identifier"]

CF_PATTERN = r"(?:[0-9]{11}|[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z])"
ODD_VALUES = (
    1,
    0,
    5,
    7,
    9,
    13,
    15,
    17,
    19,
    21,
    2,
    4,
    18,
    20,
    11,
    3,
    6,
    8,
    12,
    14,
    16,
    10,
    22,
    25,
    24,
    23,
)
IDENTIFIERS = (
    "CodiceFiscale",
    "PartitaIVA",
    "CFDichiarante",
    "CodiceFiscaleSocieta",
    "CFIntermediario",
)


def check_identifier(value: str, *, vat: bool = False) -> None:
    """Verify syntax and transcription checksum; never infer existence or ownership."""
    if not re.fullmatch(r"[0-7][0-9]{10}" if vat else CF_PATTERN, value):
        raise ContractError("Invalid identifier syntax")
    if len(value) == 11:
        digits = [int(character) for character in value[:10]]
        total = sum(digits[::2]) + sum(
            number * 2 if number < 5 else number * 2 - 9 for number in digits[1::2]
        )
        valid = int(value[-1]) == (10 - total % 10) % 10
    else:
        total = 0
        for index, character in enumerate(value[:15]):
            position = (
                int(character) if character.isdigit() else ord(character) - ord("A")
            )
            total += ODD_VALUES[position] if index % 2 == 0 else position
        valid = value[-1] == chr(ord("A") + total % 26)
    if not valid:
        raise ContractError("Invalid identifier transcription checksum")


def _quoted(value: str, reference: dict, name: str) -> None:
    if not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", reference["quote"]):
        raise ContractError(f"Front-page {name} is absent from its exact quotation")


def validate_frontpage(
    front: dict, case: dict, source_root: Path, *, on_date: date
) -> dict:
    """Bind an ordinary front page to the case and verify current filing constraints."""
    schema = read_json(ROOT / "schemas/frontpage.schema.json")
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(
        validator.iter_errors(front), key=lambda error: str(error.json_path)
    )
    if errors:
        raise ContractError(f"Front page {errors[0].json_path}: {errors[0].message}")
    if any(
        front[key] != case[key] for key in ("client_id", "engagement_id", "data_origin")
    ):
        raise ContractError(
            "Front page belongs to a different case identity or data origin"
        )
    fields = front["fields"]
    if fields["AnnoImposta"] != case["tax_year"]:
        raise ContractError("Front-page tax year differs from the reviewed case")
    if not on_date.year - 1 <= fields["AnnoImposta"] <= on_date.year:
        raise ContractError("Tax year is outside the current submission window")
    if front["review"]["status"] != "CONFIRMED":
        raise ContractError(
            "Front page requires an actual attributed professional review"
        )
    if date.fromisoformat(front["review"]["reviewed_on"]) > on_date:
        raise ContractError("Front-page review cannot be in the future")
    for key in IDENTIFIERS:
        if fields[key] is not None:
            check_identifier(fields[key], vat=key == "PartitaIVA")
    if front["taxpayer_kind"] == "OTHER":
        if len(fields["CodiceFiscale"]) != 11 or fields["CFDichiarante"] is None:
            raise ContractError(
                "A non-natural taxpayer needs a numeric code and a representative"
            )
    if fields["CFDichiarante"] is not None and len(fields["CFDichiarante"]) != 16:
        raise ContractError("The declarant must have a sixteen-character fiscal code")
    if (fields["CFDichiarante"] is None) != (fields["CodiceCaricaDichiarante"] is None):
        raise ContractError("Declarant and office code must be supplied together")
    has_intermediary = fields["CFIntermediario"] is not None
    if any(
        (fields[key] is not None) != has_intermediary
        for key in ("ImpegnoPresentazione", "DataImpegno", "FirmaIntermediario")
    ):
        raise ContractError(
            "Intermediary identification and commitment fields must be complete together"
        )
    if has_intermediary:
        committed = date.fromisoformat(fields["DataImpegno"])
        if not date(on_date.year - 4, 1, 1) <= committed <= on_date:
            raise ContractError(
                "Intermediary commitment date is future or older than the allowed window"
            )
    # Signature flags are proposed declarations bound by the separate approval,
    # not literal numbers extracted from identity papers or a digital XML signature.
    populated = {
        key
        for key, value in fields.items()
        if value is not None and key not in {"FirmaDichiarazione", "FirmaIntermediario"}
    }
    if set(front["field_evidence"]) != populated:
        raise ContractError(
            "Every populated front-page field needs its own source reference"
        )
    references = list(front["field_evidence"].values())
    for key, ref in front["field_evidence"].items():
        value = str(fields[key])
        if key == "DataImpegno":
            when = date.fromisoformat(value)
            if not any(
                re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", ref["quote"])
                for token in (value, when.strftime("%d/%m/%Y"), when.strftime("%d%m%Y"))
            ):
                raise ContractError("Commitment date is absent from the quoted source")
        elif key in IDENTIFIERS or key == "AnnoImposta":
            _quoted(value, ref, key)
    checks = {item["field"]: item for item in front["registry_checks"]}
    expected_checks = {key for key in IDENTIFIERS if fields[key] is not None}
    if len(checks) != len(front["registry_checks"]) or set(checks) != expected_checks:
        raise ContractError(
            "Each populated identifier needs one explicit registry-evidence review"
        )
    for key, check in checks.items():
        if check["review"]["status"] != "CONFIRMED":
            raise ContractError(
                "Registry evidence has not been professionally confirmed"
            )
        checked, reviewed = date.fromisoformat(
            check["verified_on"]
        ), date.fromisoformat(check["review"]["reviewed_on"])
        if (
            not checked
            <= reviewed
            <= date.fromisoformat(front["review"]["reviewed_on"])
            <= on_date
        ):
            raise ContractError("Registry check and review dates are inconsistent")
        _quoted(fields[key], check["evidence"], key)
        references.append(check["evidence"])
    check_references(front["sources"], references, source_root)
    return {
        "frontpage_hash": digest(front),
        "validated_on": on_date.isoformat(),
        "fields": {
            key: (
                date.fromisoformat(value).strftime("%d%m%Y")
                if key == "DataImpegno"
                else str(value)
            )
            for key, value in fields.items()
            if value is not None
        },
        "identifier_checks": "SYNTAX_AND_TRANSCRIPTION_CHECKSUM_ONLY",
        "registry_status": "SOURCE_BOUND_PROFESSIONAL_DECLARATION_NOT_A_LIVE_REGISTRY_CHECK",
        "professional_identity_authenticated": False,
        "network_calls": False,
    }
