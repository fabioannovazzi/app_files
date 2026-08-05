from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "bilancio-xbrl-it" / "scripts"


def _load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


artifact_delivery = _load_module("artifact_delivery")


def _claims() -> dict[str, str]:
    return {
        "tenant_id": "tenant_1",
        "case_id": "case_1",
        "artifact_id": "workpaper.json",
        "sha256": "a" * 64,
    }


def test_signed_artifact_grant_round_trip_and_expiry() -> None:
    service = artifact_delivery.SignedArtifactDelivery(
        b"s" * 32, "https://vera.example/v1/xbrl-artifacts/download"
    )
    issued_at = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    grant = service.issue(_claims(), ttl_seconds=60, now=issued_at)
    verified = service.verify(grant["token"], now=issued_at + timedelta(seconds=59))

    assert verified["artifact_id"] == "workpaper.json"
    assert verified["sha256"] == "a" * 64
    assert "token=" in grant["download_url"]
    with pytest.raises(artifact_delivery.ExpiredDownloadGrant, match="expired"):
        service.verify(grant["token"], now=issued_at + timedelta(seconds=60))


def test_signed_artifact_grant_rejects_tampering() -> None:
    service = artifact_delivery.SignedArtifactDelivery(
        b"s" * 32, "/v1/xbrl-artifacts/download"
    )
    grant = service.issue(_claims())
    payload, signature = grant["token"].split(".")
    replacement = "A" if signature[-1] != "A" else "B"

    with pytest.raises(ValueError, match="signature"):
        service.verify(f"{payload}.{signature[:-1]}{replacement}")


@pytest.mark.parametrize(
    ("secret", "base_url"),
    [
        (b"short", "https://vera.example/download"),
        (b"s" * 32, "http://vera.example/download"),
        (b"s" * 32, "https://vera.example/download?old=1"),
    ],
)
def test_signed_artifact_delivery_rejects_unsafe_configuration(
    secret: bytes, base_url: str
) -> None:
    with pytest.raises(ValueError):
        artifact_delivery.SignedArtifactDelivery(secret, base_url)
