"""Mechanically verifiable contracts for Vera financial analysis."""

from __future__ import annotations

from vera_assurance.serialization import canonical_json_sha256

from .contracts import (
    REGISTERED_ANALYSIS_PACKS,
    REGISTERED_ANALYSIS_PACK_RECIPES,
    FinancialAnalysisContractError,
    build_analysis_pack_request,
    build_crosswalk_manifest,
    build_data_package_manifest,
    build_dataset_contract,
    build_prepared_evidence_manifest,
    build_reconciliation_result,
    build_relationship_contract,
    validate_analysis_pack_request,
    validate_crosswalk_manifest,
    validate_data_package_manifest,
    validate_dataset_contract,
    validate_prepared_evidence_manifest,
    validate_reconciliation_result,
    validate_relationship_contract,
)

__all__ = [
    "FinancialAnalysisContractError",
    "REGISTERED_ANALYSIS_PACKS",
    "REGISTERED_ANALYSIS_PACK_RECIPES",
    "build_analysis_pack_request",
    "build_crosswalk_manifest",
    "build_data_package_manifest",
    "build_dataset_contract",
    "build_prepared_evidence_manifest",
    "build_reconciliation_result",
    "build_relationship_contract",
    "canonical_json_sha256",
    "validate_analysis_pack_request",
    "validate_crosswalk_manifest",
    "validate_data_package_manifest",
    "validate_dataset_contract",
    "validate_prepared_evidence_manifest",
    "validate_reconciliation_result",
    "validate_relationship_contract",
]
