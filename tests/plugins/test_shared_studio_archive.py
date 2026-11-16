"""One client directory across products, with separate durable work areas."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_customer_folder_ledger import (
    _prepare_run,
    archive_core,
    archive_script_imports,
    client_case,
)


@pytest.fixture(autouse=True)
def product_environment(monkeypatch, archive_core):
    monkeypatch.setitem(sys.modules, "client_ledger", archive_core.ledger)
    monkeypatch.delenv("LUCIA_ASSURANCE_HOST", raising=False)
    monkeypatch.delenv("CLARA_ARCHIVE_HOST", raising=False)


def select_product(monkeypatch, product):
    monkeypatch.delenv("LUCIA_ASSURANCE_HOST", raising=False)
    monkeypatch.delenv("CLARA_ARCHIVE_HOST", raising=False)
    if product == "Lucia":
        monkeypatch.setenv("LUCIA_ASSURANCE_HOST", "1")
    elif product == "Clara":
        monkeypatch.setenv("CLARA_ARCHIVE_HOST", "1")


@pytest.mark.parametrize("origin", ["Vera", "Lucia", "Clara"])
@pytest.mark.parametrize("product", ["Vera", "Lucia", "Clara"])
def test_fresh_product_reuses_shared_default_and_client(
    archive_core, tmp_path, monkeypatch, product, origin
):
    select_product(monkeypatch, origin)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", raising=False)
    root = tmp_path / "studio"
    root.mkdir()
    first = archive_core.preferences.default_state_directory() / "sessions" / "first"
    archive_core.configure_archive(root, state_dir=first, make_studio_default=True)
    created = archive_core.create_studio_client(
        "Synthetic shared client", state_dir=first
    )
    client_id = created["client"]["client_id"]
    shared_profile = archive_core.preferences.profile_directory(first)
    select_product(monkeypatch, product)
    second = archive_core.preferences.default_state_directory() / "sessions" / product
    listed = archive_core.list_studio_clients(state_dir=second)
    assert listed["configured"] is True
    assert [item["client_id"] for item in listed["clients"]] == [client_id]
    assert archive_core.preferences.profile_directory(second) == shared_profile


def test_each_product_creates_work_under_same_client(
    archive_core, tmp_path, monkeypatch
):
    case = client_case.__wrapped__(tmp_path, archive_core)
    identity = (case.client_root / "Vera/client.json").read_bytes()
    select_product(monkeypatch, "Lucia")
    lucia = archive_core.create_studio_client_engagement(
        case.client_id, "Legal synthetic", state_dir=case.state_dir
    )["engagement"]
    select_product(monkeypatch, "Clara")
    clara = archive_core.create_studio_client_engagement(
        case.client_id, "Advisory synthetic", state_dir=case.state_dir
    )["engagement"]
    assert (
        case.client_root
        / "Lucia/engagements"
        / lucia["engagement_id"]
        / "engagement.json"
    ).is_file()
    assert (
        case.client_root
        / "Clara/engagements"
        / clara["engagement_id"]
        / "engagement.json"
    ).is_file()
    listed = archive_core.list_studio_client_engagements(
        case.client_id, state_dir=case.state_dir
    )
    assert {row["engagement_id"] for row in listed["engagements"]} == {
        case.engagement_id,
        lucia["engagement_id"],
        clara["engagement_id"],
    }
    assert (case.client_root / "Vera/client.json").read_bytes() == identity


@pytest.mark.parametrize("product", ["Vera", "Lucia", "Clara"])
def test_product_run_context_loads_and_reopens_from_other_product(
    archive_core, tmp_path, monkeypatch, product
):
    select_product(monkeypatch, product)
    case = client_case.__wrapped__(tmp_path, archive_core)
    prepared = _prepare_run(archive_core, case, idempotency_key="shared-product")
    context = prepared["client_engagement"]
    assert Path(context["output_dir"]).relative_to(case.client_root).parts[0] == product
    run_id = context["run_id"]
    context_path = Path(prepared["client_engagement_path"])
    original = context_path.read_bytes()
    select_product(monkeypatch, "Lucia" if product == "Vera" else "Vera")
    started = archive_core.start_studio_client_workflow(
        case.client_id, case.engagement_id, run_id, state_dir=case.state_dir
    )
    from vera_assurance import load_client_engagement_context_file

    loaded = load_client_engagement_context_file(
        context_path,
        expected_workflow_id="financial-analysis",
        output_dir=context["output_dir"],
    )
    assert loaded["run_id"] == run_id
    assert context_path.read_bytes() == original
    assert started["run"]["status"] == "running"


def test_duplicate_engagement_across_products_is_not_silently_selected(
    archive_core, tmp_path
):
    import shutil

    case = client_case.__wrapped__(tmp_path, archive_core)
    shutil.copytree(
        case.client_root / "Vera/engagements" / case.engagement_id,
        case.client_root / "Lucia/engagements" / case.engagement_id,
    )
    with pytest.raises(archive_core.ledger.LedgerError, match="more than one product"):
        archive_core.ledger.load_engagement_manifest(
            case.client_root, case.engagement_id
        )


def test_creation_retry_from_other_product_reuses_same_engagement(
    archive_core, tmp_path, monkeypatch
):
    case = client_case.__wrapped__(tmp_path, archive_core)
    first = archive_core.create_studio_client_engagement(
        case.client_id,
        "Cross-product retry",
        idempotency_key="same-request",
        state_dir=case.state_dir,
    )
    select_product(monkeypatch, "Lucia")
    repeated = archive_core.create_studio_client_engagement(
        case.client_id,
        "Cross-product retry",
        idempotency_key="same-request",
        state_dir=case.state_dir,
    )
    assert repeated["status"] == "already_created"
    assert (
        repeated["engagement"]["engagement_id"] == first["engagement"]["engagement_id"]
    )
    assert not (
        case.client_root / "Lucia/engagements" / first["engagement"]["engagement_id"]
    ).exists()


def test_product_symlink_cannot_redirect_engagement_reader(archive_core, tmp_path):
    case = client_case.__wrapped__(tmp_path, archive_core)
    (case.client_root / "Lucia").symlink_to(
        case.client_root / "Vera", target_is_directory=True
    )
    with pytest.raises(archive_core.ledger.LedgerError, match="real directory"):
        archive_core.ledger.load_engagement_manifest(
            case.client_root, case.engagement_id
        )


def test_product_symlink_cannot_redirect_new_work(archive_core, tmp_path, monkeypatch):
    case = client_case.__wrapped__(tmp_path, archive_core)
    outside = tmp_path / "outside"
    outside.mkdir()
    (case.client_root / "Lucia").symlink_to(outside, target_is_directory=True)
    select_product(monkeypatch, "Lucia")
    with pytest.raises(archive_core.ArchiveError, match="real directory"):
        archive_core.create_studio_client_engagement(
            case.client_id, "No write outside client", state_dir=case.state_dir
        )
    assert list(outside.iterdir()) == []


def test_concurrent_products_share_one_creation_request(archive_core, tmp_path):
    import json
    import os
    import subprocess

    case = client_case.__wrapped__(tmp_path, archive_core)
    worker = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import client_ledger as ledger
print(json.dumps(ledger.ensure_engagement(Path(sys.argv[2]),sys.argv[3],"Shared request",idempotency_key="concurrent-products")))
"""
    command = [
        sys.executable,
        "-c",
        worker,
        str(Path(archive_core.__file__).parent),
        str(case.client_root),
        case.client_id,
    ]
    first = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "LUCIA_ASSURANCE_HOST": "1", "CLARA_ARCHIVE_HOST": "0"},
    )
    second = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "LUCIA_ASSURANCE_HOST": "0", "CLARA_ARCHIVE_HOST": "1"},
    )
    first_out, first_err = first.communicate(timeout=30)
    second_out, second_err = second.communicate(timeout=30)
    assert first.returncode == 0, first_err
    assert second.returncode == 0, second_err
    result_a, result_b = json.loads(first_out), json.loads(second_out)
    assert result_a["engagement"] == result_b["engagement"]
    assert sorted([result_a["created"], result_b["created"]]) == [False, True]


def test_product_symlink_blocks_collection_enumeration(archive_core, tmp_path):
    case = client_case.__wrapped__(tmp_path, archive_core)
    outside = tmp_path / "outside"
    (outside / "engagements" / "private-name").mkdir(parents=True)
    (case.client_root / "Lucia").symlink_to(outside, target_is_directory=True)
    result = archive_core.ledger.inspect_engagements(case.client_root, case.client_id)
    assert "private-name" not in str(result)
    assert "unavailable_collection" in str(result)
    with pytest.raises(archive_core.ledger.LedgerError, match="real directory"):
        archive_core.ledger.list_engagements(case.client_root, case.client_id)
