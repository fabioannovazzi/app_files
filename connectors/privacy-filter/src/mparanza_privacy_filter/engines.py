"""Pinned local engines and their allowlisted output contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import LABELS, MODEL_REVISION, FilterError

__all__ = ["Engine", "engine_for", "GLINER2"]


@dataclass(frozen=True)
class Engine:
    """No user-supplied import paths or output labels cross this boundary."""

    name: str
    title: str
    prefix: str
    revision: str
    labels: frozenset[str]
    worker: str
    checkpoint_parts: tuple[str, ...]
    required_files: tuple[str, ...]


OPENAI = Engine(
    "openai",
    "OpenAI Privacy Filter",
    "privacy_filter",
    MODEL_REVISION,
    LABELS,
    "mparanza_privacy_filter.worker",
    ("checkpoint", "original"),
    ("config.json", "model.safetensors"),
)
GLINER2 = Engine(
    "gliner2",
    "GLiNER2-PII",
    "gliner2_pii",
    "1cb4166094dc58fa8d836429f060d6c95f62b495",
    frozenset(
        (
            "person",
            "full_name",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "email",
            "phone_number",
            "address",
            "street_address",
            "city",
            "state_or_region",
            "postal_code",
            "country",
            "government_id",
            "national_id_number",
            "passport_number",
            "drivers_license_number",
            "license_number",
            "tax_id",
            "tax_number",
            "bank_account",
            "account_number",
            "routing_number",
            "iban",
            "payment_card",
            "card_number",
            "card_expiry",
            "card_cvv",
            "username",
            "ip_address",
            "account_id",
            "sensitive_account_id",
            "password",
            "secret",
            "api_key",
            "access_token",
            "recovery_code",
            "sensitive_date",
            "document_date",
            "expiration_date",
            "transaction_date",
        )
    ),
    "mparanza_privacy_filter.gliner_worker",
    ("checkpoint",),
    (
        "config.json",
        "model.safetensors",
        "encoder_config/config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ),
)


def engine_for(name: str) -> Engine:
    """Resolve only explicitly supported engines."""
    if name == "openai":
        return OPENAI
    if name == "gliner2":
        return GLINER2
    raise FilterError("unsupported_engine")
