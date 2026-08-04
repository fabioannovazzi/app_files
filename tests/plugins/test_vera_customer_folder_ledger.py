from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_CORE_PATH = ROOT / "plugins" / "studio-archive" / "scripts" / "archive_core.py"


@pytest.fixture(scope="module")
def archive_core() -> ModuleType:
    """Load Studio Archive without changing its production import boundary."""

    module_name = "test_vera_customer_folder_archive_core"
    spec = importlib.util.spec_from_file_location(module_name, ARCHIVE_CORE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client_case(tmp_path: Path, archive_core: ModuleType) -> SimpleNamespace:
    """Create one registered client, explicit engagement, and exact input."""

    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Zecca SPA"
    client_root.mkdir(parents=True)
    state_dir = tmp_path / "private-state"
    configured = archive_core.configure_archive(archive_root, state_dir=state_dir)
    scope_id = next(
        item["scope_id"]
        for item in configured["scopes"]
        if item["display_name"] == "Zecca SPA"
    )
    registration = archive_core.set_studio_client_identity(
        scope_id,
        legal_names=["Zecca SPA"],
        tax_identifiers=["01234567890"],
        state_dir=state_dir,
    )
    client_id = registration["client"]["client_id"]
    engagement = archive_core.create_studio_client_engagement(
        client_id,
        "2026 assurance work",
        state_dir=state_dir,
    )["engagement"]
    received = tmp_path / "received"
    received.mkdir()
    source = received / "journal.txt"
    source.write_text(
        "ZeccaLedgerMarker approved journal evidence\n",
        encoding="utf-8",
    )
    imported = archive_core.import_studio_client_document(
        client_id,
        source,
        "journal",
        engagement_id=engagement["engagement_id"],
        state_dir=state_dir,
    )
    return SimpleNamespace(
        archive_root=archive_root,
        client_root=client_root,
        state_dir=state_dir,
        scope_id=scope_id,
        client_id=client_id,
        engagement_id=engagement["engagement_id"],
        source=source,
        imported=imported,
    )


def _prepare_run(
    archive_core: ModuleType,
    case: SimpleNamespace,
    *,
    idempotency_key: str,
    new_run: bool = False,
) -> dict[str, object]:
    return archive_core.prepare_studio_client_workflow(
        case.engagement_id,
        "financial-analysis",
        input_ids=[case.imported["input_id"]],
        label="Zecca 2026 analysis",
        purpose="Prepare the reviewed 2026 financial analysis.",
        idempotency_key=idempotency_key,
        new_run=new_run,
        state_dir=case.state_dir,
    )


def test_client_ledger_import_selects_the_windows_process_lock_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "test_vera_customer_folder_windows_lock_import"
    fake_os = ModuleType("os")
    fake_os.__dict__.update(vars(os))
    fake_os.name = "nt"  # type: ignore[attr-defined]
    fake_msvcrt = ModuleType("msvcrt")
    monkeypatch.setitem(sys.modules, "os", fake_os)
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setitem(sys.modules, "fcntl", None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        ARCHIVE_CORE_PATH.with_name("client_ledger.py"),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    assert module._PROCESS_LOCK_MODULE is fake_msvcrt


def test_explicit_engagement_and_import_are_persisted_in_customer_folder(
    client_case: SimpleNamespace,
) -> None:
    receipt = client_case.imported["input_receipt"]
    engagement_root = (
        client_case.client_root / "Vera" / "engagements" / client_case.engagement_id
    )

    assert client_case.imported["status"] == "imported"
    assert client_case.imported["engagement"]["engagement_id"] == (
        client_case.engagement_id
    )
    assert Path(client_case.imported["imported_path"]).read_bytes() == (
        client_case.source.read_bytes()
    )
    assert receipt["relative_path"].startswith(
        f"Vera/engagements/{client_case.engagement_id}/inputs/{receipt['input_id']}/"
    )
    assert (client_case.client_root / "Vera" / "client.json").is_file()
    assert (engagement_root / "engagement.json").is_file()
    assert (engagement_root / ".vera-engagement.lock").read_bytes() == (
        b"Vera engagement mutation lock\n"
    )
    assert (engagement_root / "inputs" / receipt["input_id"] / "receipt.json").is_file()
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((client_case.client_root / "Vera").rglob("*.json"))
    )
    assert str(client_case.client_root) not in serialized
    assert "01234567890" not in serialized


def test_import_requires_an_explicit_engagement(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    with pytest.raises(
        archive_core.ArchiveError,
        match="Select or create an engagement",
    ):
        archive_core.import_studio_client_document(
            client_case.client_id,
            client_case.source,
            "journal",
            state_dir=client_case.state_dir,
        )


def test_repeated_import_reuses_one_content_addressed_input(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    replayed = archive_core.import_studio_client_document(
        client_case.client_id,
        client_case.source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )

    assert replayed["status"] == "already_imported"
    assert replayed["input_id"] == client_case.imported["input_id"]
    assert replayed["input_receipt"] == client_case.imported["input_receipt"]
    assert len(replayed["engagement"]["imports"]) == 1


def test_concurrent_import_retries_resolve_to_one_input_receipt(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    participant_count = 12
    hash_barrier = Barrier(participant_count)
    source = client_case.source.parent / "concurrent-support.txt"
    source.write_text("Concurrent support evidence\n", encoding="utf-8")
    source = source.resolve(strict=True)
    original_sha256_file = archive_core.ledger._sha256_file

    def hash_before_release(path: Path) -> str:
        digest = original_sha256_file(path)
        if path == source:
            hash_barrier.wait(timeout=10)
        return digest

    monkeypatch.setattr(archive_core.ledger, "_sha256_file", hash_before_release)

    def import_after_release() -> dict[str, object]:
        return archive_core.ledger.import_document(
            client_case.client_root,
            client_case.client_id,
            client_case.engagement_id,
            source,
            "support",
        )

    with ThreadPoolExecutor(max_workers=participant_count) as executor:
        futures = [
            executor.submit(import_after_release) for _ in range(participant_count)
        ]
        results = [future.result(timeout=20) for future in futures]

    input_ids = {result["receipt"]["input_id"] for result in results}
    statuses = [result["status"] for result in results]
    assert len(input_ids) == 1
    assert statuses.count("imported") == 1
    assert statuses.count("already_imported") == participant_count - 1
    assert (
        len(
            archive_core.ledger.list_inputs(
                client_case.client_root,
                client_case.engagement_id,
            )
        )
        == 2
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX cross-process lock contract")
def test_cross_process_import_retries_resolve_to_one_input_receipt(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    process_count = 6
    process_context = multiprocessing.get_context("fork")
    barrier = process_context.Barrier(process_count)
    outcomes = process_context.Queue()
    source = client_case.source.parent / "cross-process-support.bin"
    source.write_bytes(b"cross-process support evidence\n" * 32_768)
    source = source.resolve(strict=True)

    def import_after_release() -> None:
        barrier.wait(timeout=10)
        try:
            result = archive_core.ledger.import_document(
                client_case.client_root,
                client_case.client_id,
                client_case.engagement_id,
                source,
                "support",
            )
        except (OSError, archive_core.ledger.LedgerError) as exc:
            outcomes.put(("error", str(exc)))
            return
        outcomes.put((result["status"], result["receipt"]["input_id"]))

    processes = [
        process_context.Process(target=import_after_release)
        for _ in range(process_count)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
    results = [outcomes.get(timeout=5) for _ in range(process_count)]
    outcomes.close()
    outcomes.join_thread()

    assert all(process.exitcode == 0 for process in processes)
    assert len({result[1] for result in results}) == 1
    assert [result[0] for result in results].count("imported") == 1
    assert [result[0] for result in results].count("already_imported") == (
        process_count - 1
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_prepared_run_storage_is_owner_only(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="owner-only-run-storage",
    )
    run_root = Path(prepared["client_engagement"]["run_root"])
    execution_input = Path(prepared["client_engagement"]["input_bindings"][0]["path"])

    for directory in (
        run_root,
        run_root / "inputs",
        execution_input.parent.parent,
        execution_input.parent,
        run_root / "outputs",
    ):
        assert directory.stat().st_mode & 0o777 == 0o700
    assert execution_input.stat().st_mode & 0o777 == 0o600


def test_run_request_is_idempotent_until_new_run_is_explicit(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    first = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="financial-analysis-2026",
    )
    replayed = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="financial-analysis-2026",
    )
    explicit_new = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="financial-analysis-2026",
        new_run=True,
    )
    explicit_replay = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="financial-analysis-2026",
        new_run=True,
    )

    assert first["status"] == "prepared"
    assert replayed["status"] == "already_prepared"
    assert replayed["run"]["run_id"] == first["run"]["run_id"]
    assert replayed["input_manifest"] == first["input_manifest"]
    assert explicit_new["status"] == "prepared"
    assert explicit_new["run"]["run_id"] != first["run"]["run_id"]
    assert explicit_replay["status"] == "already_prepared"
    assert explicit_replay["run"]["run_id"] == explicit_new["run"]["run_id"]


def test_concurrent_run_prepare_resolves_one_idempotency_key_to_one_run(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    participant_count = 8
    barrier = Barrier(participant_count)

    def prepare_after_release() -> dict[str, object]:
        barrier.wait(timeout=10)
        return _prepare_run(
            archive_core,
            client_case,
            idempotency_key="concurrent-financial-analysis-2026",
        )

    with ThreadPoolExecutor(max_workers=participant_count) as executor:
        futures = [
            executor.submit(prepare_after_release) for _ in range(participant_count)
        ]
        results = [future.result(timeout=20) for future in futures]

    run_ids = {result["run"]["run_id"] for result in results}
    statuses = [result["status"] for result in results]
    assert len(run_ids) == 1
    assert statuses.count("prepared") == 1
    assert statuses.count("already_prepared") == participant_count - 1


@pytest.mark.skipif(os.name != "posix", reason="POSIX cross-process lock contract")
def test_cross_process_prepare_resolves_one_idempotency_key_to_one_run(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    process_count = 6
    process_context = multiprocessing.get_context("fork")
    barrier = process_context.Barrier(process_count)
    outcomes = process_context.Queue()

    def prepare_after_release() -> None:
        barrier.wait(timeout=10)
        try:
            result = archive_core.ledger.prepare_run(
                client_case.client_root,
                client_case.client_id,
                client_case.engagement_id,
                "financial-analysis",
                "test-version",
                input_ids=[client_case.imported["input_id"]],
                label="Zecca 2026 analysis",
                purpose="Prepare the reviewed 2026 financial analysis.",
                idempotency_key="cross-process-financial-analysis-2026",
            )
        except (OSError, archive_core.ledger.LedgerError) as exc:
            outcomes.put(("error", str(exc)))
            return
        outcomes.put((result["status"], result["run"]["run_id"]))

    processes = [
        process_context.Process(target=prepare_after_release)
        for _ in range(process_count)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
    results = [outcomes.get(timeout=5) for _ in range(process_count)]
    outcomes.close()
    outcomes.join_thread()

    assert all(process.exitcode == 0 for process in processes)
    assert len({result[1] for result in results}) == 1
    assert [result[0] for result in results].count("prepared") == 1
    assert [result[0] for result in results].count("already_prepared") == (
        process_count - 1
    )


def test_starting_an_already_running_run_is_idempotent(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="idempotent-start",
    )
    run_id = prepared["run"]["run_id"]

    started = archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    replayed = archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )

    assert replayed["run"] == started["run"]
    assert replayed["status"] == "running"


def test_prepare_and_close_race_preserves_engagement_lifecycle(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    barrier = Barrier(2)

    def prepare_after_release() -> tuple[str, str]:
        barrier.wait(timeout=10)
        try:
            prepared = _prepare_run(
                archive_core,
                client_case,
                idempotency_key="prepare-close-race",
            )
        except archive_core.ArchiveError as exc:
            return "error", str(exc)
        return "prepared", str(prepared["run"]["run_id"])

    def close_after_release() -> tuple[str, str]:
        barrier.wait(timeout=10)
        try:
            closed = archive_core.close_studio_client_engagement(
                client_case.client_id,
                client_case.engagement_id,
                state_dir=client_case.state_dir,
            )
        except archive_core.ArchiveError as exc:
            return "error", str(exc)
        return "closed", str(closed["status"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        prepare_future = executor.submit(prepare_after_release)
        close_future = executor.submit(close_after_release)
        outcomes = {
            prepare_future.result(timeout=20)[0],
            close_future.result(timeout=20)[0],
        }

    engagement = archive_core.ledger.load_engagement_manifest(
        client_case.client_root,
        client_case.engagement_id,
    )
    runs = archive_core.ledger.list_runs(
        client_case.client_root,
        client_case.engagement_id,
        verify_inputs=False,
    )
    if engagement["status"] == "closed":
        assert outcomes == {"closed", "error"}
        assert runs == ()
    else:
        assert engagement["status"] == "open"
        assert outcomes == {"prepared", "error"}
        assert len(runs) == 1
        assert runs[0]["run"]["status"] == "prepared"


def test_failed_run_cannot_restart_after_engagement_closes(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="closed-failed-run",
    )
    run_id = prepared["run"]["run_id"]
    archive_core.fail_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        "Retained terminal failure",
        state_dir=client_case.state_dir,
    )
    archive_core.close_studio_client_engagement(
        client_case.client_id,
        client_case.engagement_id,
        state_dir=client_case.state_dir,
    )

    with pytest.raises(archive_core.ArchiveError, match="engagement is closed"):
        archive_core.start_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            run_id,
            state_dir=client_case.state_dir,
        )

    retained = archive_core.ledger.load_run(
        client_case.client_root,
        client_case.engagement_id,
        run_id,
    )
    assert retained["run"]["status"] == "failed"


def test_lifecycle_seals_every_output_with_purpose_and_audience(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="artifact-lifecycle",
    )
    run_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    output_dir = Path(prepared["client_engagement"]["output_dir"])
    (output_dir / "review").mkdir()
    (output_dir / "review" / "analysis.txt").write_text(
        "Reviewed analysis\n",
        encoding="utf-8",
    )
    (output_dir / "diagnostics.json").write_text("{}\n", encoding="utf-8")

    finalized = archive_core.finalize_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        [
            {
                "artifact_id": "review.analysis",
                "path": "review/analysis.txt",
                "purpose": "Present the analysis for professional review.",
                "audience": "review",
                "media_type": "text/plain",
            },
            {
                "artifact_id": "internal.diagnostics",
                "path": "diagnostics.json",
                "purpose": "Record reproducible technical diagnostics.",
                "audience": "internal",
                "media_type": "application/json",
            },
        ],
        state_dir=client_case.state_dir,
    )
    replayed = archive_core.finalize_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        [
            {
                "artifact_id": "review.analysis",
                "path": "review/analysis.txt",
                "purpose": "Present the analysis for professional review.",
                "audience": "review",
                "media_type": "text/plain",
            },
            {
                "artifact_id": "internal.diagnostics",
                "path": "diagnostics.json",
                "purpose": "Record reproducible technical diagnostics.",
                "audience": "internal",
                "media_type": "application/json",
            },
        ],
        state_dir=client_case.state_dir,
    )
    completed = archive_core.complete_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )

    artifacts = finalized["artifact_manifest"]["artifacts"]
    assert finalized["status"] == "ready_for_review"
    assert replayed["artifact_manifest"] == finalized["artifact_manifest"]
    assert completed["status"] == "completed"
    assert {item["path"] for item in artifacts} == {
        "diagnostics.json",
        "review/analysis.txt",
    }
    assert {item["audience"] for item in artifacts} == {"internal", "review"}
    assert all(item["purpose"] for item in artifacts)
    assert all(len(item["sha256"]) == 64 for item in artifacts)


def test_concurrent_finalizers_commit_one_authoritative_declaration_set(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="concurrent-finalizers",
    )
    run_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    output_dir = Path(prepared["client_engagement"]["output_dir"])
    (output_dir / "result.bin").write_bytes(b"reviewable output\n" * 131_072)
    participant_count = 8
    barrier = Barrier(participant_count)

    def finalize_after_release(index: int) -> tuple[str, str]:
        purpose = f"Authoritative purpose {index}."
        barrier.wait(timeout=10)
        try:
            finalized = archive_core.finalize_studio_client_workflow(
                client_case.client_id,
                client_case.engagement_id,
                run_id,
                [
                    {
                        "artifact_id": "review.result",
                        "path": "result.bin",
                        "purpose": purpose,
                        "audience": "review",
                        "media_type": "application/octet-stream",
                    }
                ],
                state_dir=client_case.state_dir,
            )
        except archive_core.ArchiveError as exc:
            return "error", str(exc)
        return "finalized", finalized["artifact_manifest"]["artifacts"][0]["purpose"]

    with ThreadPoolExecutor(max_workers=participant_count) as executor:
        futures = [
            executor.submit(finalize_after_release, index)
            for index in range(participant_count)
        ]
        results = [future.result(timeout=30) for future in futures]

    successes = [result for result in results if result[0] == "finalized"]
    authoritative = archive_core.ledger.validate_run_artifacts(
        client_case.client_root,
        client_case.engagement_id,
        run_id,
    )
    assert len(successes) == 1
    assert [result[0] for result in results].count("error") == participant_count - 1
    assert authoritative["artifacts"][0]["purpose"] == successes[0][1]


def test_finalization_rejects_an_output_that_changes_while_hashed(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="changing-finalization-output",
    )
    run_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    output_dir = Path(prepared["client_engagement"]["output_dir"])
    output_path = output_dir / "changing.bin"
    output_path.write_bytes(b"A" * (2 * 1024 * 1024))
    original_read = archive_core.ledger.os.read
    mutated = False

    def read_then_mutate(descriptor: int, size: int) -> bytes:
        nonlocal mutated
        chunk = original_read(descriptor, size)
        opened = os.fstat(descriptor)
        target = output_path.stat()
        if (
            chunk
            and not mutated
            and (opened.st_dev, opened.st_ino) == (target.st_dev, target.st_ino)
        ):
            mutated = True
            output_path.write_bytes(b"changed during finalization\n")
        return chunk

    monkeypatch.setattr(archive_core.ledger.os, "read", read_then_mutate)

    with pytest.raises(archive_core.ArchiveError, match="changed while it was read"):
        archive_core.finalize_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            run_id,
            [
                {
                    "artifact_id": "review.changing",
                    "path": "changing.bin",
                    "purpose": "Exercise stable artifact sealing.",
                    "audience": "review",
                    "media_type": "application/octet-stream",
                }
            ],
            state_dir=client_case.state_dir,
        )

    retained = archive_core.ledger.load_run(
        client_case.client_root,
        client_case.engagement_id,
        run_id,
    )
    assert retained["run"]["status"] == "running"
    assert not (Path(retained["run_root"]) / "artifact_manifest.json").exists()


def test_finalize_rejects_an_artifact_without_declared_media_type(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="required-artifact-media-type",
    )
    run_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    output_dir = Path(prepared["client_engagement"]["output_dir"])
    (output_dir / "result.txt").write_text("Reviewed result\n", encoding="utf-8")

    with pytest.raises(archive_core.ArchiveError, match="media_type"):
        archive_core.finalize_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            run_id,
            [
                {
                    "artifact_id": "review.result",
                    "path": "result.txt",
                    "purpose": "Present the result for professional review.",
                    "audience": "review",
                }
            ],
            state_dir=client_case.state_dir,
        )


def test_empty_and_failed_runs_are_not_available(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    empty = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="empty-run",
    )
    failed = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="failed-run",
    )
    archive_core.fail_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        failed["run"]["run_id"],
        "Injected test failure",
        state_dir=client_case.state_dir,
    )

    listed = archive_core.list_studio_client_engagements(
        client_case.client_id,
        state_dir=client_case.state_dir,
    )

    runs = {item["run_id"]: item for item in listed["engagements"][0]["workflow_runs"]}
    assert runs[empty["run"]["run_id"]]["status"] == "prepared"
    assert runs[empty["run"]["run_id"]]["run_output_available"] is False
    assert runs[failed["run"]["run_id"]]["status"] == "failed"
    assert runs[failed["run"]["run_id"]]["run_output_available"] is False


def test_tampered_controlled_copy_blocks_run_preparation(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    Path(client_case.imported["imported_path"]).write_text(
        "tampered after receipt\n",
        encoding="utf-8",
    )

    with pytest.raises(
        archive_core.ArchiveError,
        match="Controlled input snapshot no longer matches its receipt",
    ):
        _prepare_run(
            archive_core,
            client_case,
            idempotency_key="tampered-input",
        )


def test_tampered_input_receipt_blocks_an_existing_run(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="tampered-receipt",
    )
    receipt_path = (
        client_case.client_root
        / client_case.imported["input_receipt"]["receipt_relative_path"]
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["original_name"] = "changed.txt"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(archive_core.ArchiveError, match="content digest is stale"):
        archive_core.start_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            prepared["run"]["run_id"],
            state_dir=client_case.state_dir,
        )


def test_import_rejects_symbolic_link_source(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
    tmp_path: Path,
) -> None:
    linked = tmp_path / "journal-link.txt"
    linked.symlink_to(client_case.source)

    with pytest.raises(archive_core.ArchiveError, match="non-symlink"):
        archive_core.import_studio_client_document(
            client_case.client_id,
            linked,
            "journal",
            engagement_id=client_case.engagement_id,
            state_dir=client_case.state_dir,
        )


def test_fresh_private_state_recovers_client_engagement_input_and_run(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
    tmp_path: Path,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="portable-run",
    )
    fresh_state = tmp_path / "second-machine-state"
    archive_core.configure_archive(
        client_case.archive_root,
        state_dir=fresh_state,
    )

    recovered = archive_core.recover_studio_client_ledger(state_dir=fresh_state)
    listed = archive_core.list_studio_client_engagements(
        client_case.client_id,
        state_dir=fresh_state,
    )
    clients = archive_core.list_studio_client_identities(state_dir=fresh_state)

    assert recovered == {
        "status": "recovered",
        "client_count": 1,
        "engagement_count": 1,
        "input_count": 1,
        "run_count": 1,
        "private_identity_values_recovered": False,
    }
    assert listed["engagements"][0]["engagement_id"] == client_case.engagement_id
    assert listed["engagements"][0]["workflow_runs"][0]["run_id"] == (
        prepared["run"]["run_id"]
    )
    recovered_client = next(
        item
        for item in clients["clients"]
        if item["client_id"] == client_case.client_id
    )
    assert recovered_client["legal_names"] == []
    assert recovered_client["tax_identifiers"] == []


def test_folder_rename_after_refresh_preserves_portable_run_identity(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="rename-safe-run",
    )
    renamed_root = client_case.archive_root / "Zecca Holding SPA"
    client_case.client_root.rename(renamed_root)

    archive_core.refresh_archive(state_dir=client_case.state_dir)
    archive_core.recover_studio_client_ledger(state_dir=client_case.state_dir)
    folder = archive_core.get_studio_client_folder(
        client_case.client_id,
        state_dir=client_case.state_dir,
    )["client_folder"]
    listed = archive_core.list_studio_client_engagements(
        client_case.client_id,
        state_dir=client_case.state_dir,
    )

    run = listed["engagements"][0]["workflow_runs"][0]
    assert folder["client_root"] == str(renamed_root)
    assert run["run_id"] == prepared["run"]["run_id"]
    assert Path(run["client_engagement"]["output_dir"]).is_relative_to(renamed_root)
    assert Path(run["client_engagement"]["input_bindings"][0]["path"]).is_relative_to(
        renamed_root
    )


def test_archive_search_deduplicates_import_copy_and_excludes_run_files(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    visible_original = client_case.client_root / "original-journal.txt"
    visible_original.write_bytes(client_case.source.read_bytes())
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="search-deduplication-run",
    )
    output_dir = Path(prepared["client_engagement"]["output_dir"])
    (output_dir / "technical-diagnostic.txt").write_text(
        "ZeccaLedgerMarker generated diagnostic\n",
        encoding="utf-8",
    )

    archive_core.refresh_archive(state_dir=client_case.state_dir)
    result = archive_core.search_archive(
        "ZeccaLedgerMarker",
        scope_id=client_case.scope_id,
        state_dir=client_case.state_dir,
    )

    assert result["result_count"] == 1
    relative_path = result["results"][0]["relative_path"]
    assert "/runs/" not in relative_path
    assert not relative_path.endswith("receipt.json")


@pytest.mark.parametrize("studio_wide", [False, True], ids=["client", "studio-wide"])
def test_archive_search_fills_distinct_limit_after_chunk_deduplication(
    tmp_path: Path,
    archive_core: ModuleType,
    studio_wide: bool,
) -> None:
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Zecca SPA"
    client_root.mkdir(parents=True)
    marker = "DistinctLimitMarker"
    dominant_line = ((marker + " ") * 180).strip()
    (client_root / "dominant.txt").write_text(
        (dominant_line + "\n") * 60,
        encoding="utf-8",
    )
    (client_root / "other-a.txt").write_text(
        f"{marker} corroborating alpha evidence with enough useful text\n",
        encoding="utf-8",
    )
    (client_root / "other-b.txt").write_text(
        f"{marker} corroborating beta evidence with enough useful text\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "private-state"
    configured = archive_core.configure_archive(archive_root, state_dir=state_dir)
    scope_id = configured["scopes"][0]["scope_id"]
    archive_core.refresh_archive(state_dir=state_dir)

    result = archive_core.search_archive(
        marker,
        scope_id="all" if studio_wide else scope_id,
        limit=2,
        state_dir=state_dir,
    )

    assert result["result_count"] == 2
    assert len({item["source_sha256"] for item in result["results"]}) == 2


def test_input_from_another_engagement_cannot_be_bound(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    other = archive_core.create_studio_client_engagement(
        client_case.client_id,
        "Separate engagement",
        state_dir=client_case.state_dir,
    )["engagement"]

    with pytest.raises(
        archive_core.ArchiveError, match="input snapshot is unavailable"
    ):
        archive_core.prepare_studio_client_workflow(
            other["engagement_id"],
            "financial-analysis",
            input_ids=[client_case.imported["input_id"]],
            state_dir=client_case.state_dir,
        )


def test_unreceipted_entry_inside_input_ledger_is_rejected(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    inputs_root = (
        client_case.client_root
        / "Vera"
        / "engagements"
        / client_case.engagement_id
        / "inputs"
    )
    (inputs_root / "unreceipted.txt").write_text("not controlled\n", encoding="utf-8")

    with pytest.raises(archive_core.ArchiveError, match="invalid entry"):
        archive_core.list_studio_client_engagements(
            client_case.client_id,
            state_dir=client_case.state_dir,
        )


def test_cancel_close_and_retention_report_do_not_delete_run(
    client_case: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    prepared = _prepare_run(
        archive_core,
        client_case,
        idempotency_key="cancelled-run",
    )
    run_id = prepared["run"]["run_id"]
    with pytest.raises(archive_core.ArchiveError, match="active runs"):
        archive_core.close_studio_client_engagement(
            client_case.client_id,
            client_case.engagement_id,
            state_dir=client_case.state_dir,
        )

    cancelled = archive_core.cancel_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    closed = archive_core.close_studio_client_engagement(
        client_case.client_id,
        client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    retention = archive_core.report_studio_client_retention(
        client_case.client_id,
        older_than_days=0,
        state_dir=client_case.state_dir,
    )

    assert cancelled["status"] == "cancelled"
    assert closed["status"] == "closed"
    assert retention["destructive_action_performed"] is False
    assert len(retention["runs"]) == 1
    retained = retention["runs"][0]
    assert retained["engagement_id"] == client_case.engagement_id
    assert retained["run_id"] == run_id
    assert retained["status"] == "cancelled"
    assert retained["retention_candidate"] is True
    assert Path(prepared["client_engagement"]["run_manifest_path"]).is_file()


def test_old_customer_file_and_managed_snapshot_have_one_search_result(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Zecca SPA"
    client_root.mkdir(parents=True)
    old_file = client_root / "journal-2024.txt"
    old_file.write_text(
        "ZeccaUniqueSearchMarker historical journal\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "private-state"
    configured = archive_core.configure_archive(archive_root, state_dir=state_dir)
    scope = next(
        item for item in configured["scopes"] if item["display_name"] == "Zecca SPA"
    )
    client_id = archive_core.set_studio_client_identity(
        scope["scope_id"],
        legal_names=["Zecca SPA"],
        state_dir=state_dir,
    )["client"]["client_id"]
    engagement_id = archive_core.create_studio_client_engagement(
        client_id,
        "Historical journal",
        state_dir=state_dir,
    )["engagement"]["engagement_id"]
    archive_core.import_studio_client_document(
        client_id,
        old_file,
        "journal",
        engagement_id=engagement_id,
        state_dir=state_dir,
    )
    archive_core.refresh_archive(state_dir=state_dir)

    result = archive_core.search_archive(
        "ZeccaUniqueSearchMarker",
        scope_id=scope["scope_id"],
        state_dir=state_dir,
    )

    assert result["result_count"] == 1
    assert len(result["results"]) == 1
    assert (
        result["results"][0]["source_sha256"]
        == hashlib.sha256(old_file.read_bytes()).hexdigest()
    )
