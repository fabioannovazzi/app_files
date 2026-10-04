"""Session contract and real Lethe cross-document acceptance on synthetic identities."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from mparanza_privacy_filter import session_worker, shield_ready
from mparanza_privacy_filter.contracts import FilterError
from mparanza_privacy_filter.engines import engine_for
from mparanza_privacy_filter.server import create_server
from mparanza_privacy_filter.service import FilterService, Settings
from mparanza_privacy_filter.sessions import SessionStore, run_session_worker

__all__: list[str] = []

PEOPLE = ("Anna Rossi", "Bruno Bianchi", "Carla Verdi", "Diego Neri", "Elena Gialli")


def lethe_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LETHE_DATA_DIR", str(tmp_path / "lethe-data"))
    from lethe.core import Item

    source = tmp_path / "inputs"
    source.mkdir()
    items = [Item("PERSON", name, [name], "dictionary") for name in PEOPLE]
    review = {"approved": True, "items": [asdict(item) for item in items]}
    (source / "review.json").write_text(json.dumps(review))
    settings = Settings(source, tmp_path / "out", tmp_path / "model", engine="lethe")
    return FilterService(settings)


def test_real_lethe_three_documents_five_people_and_restore_after_restart(
    tmp_path, monkeypatch
):
    service = lethe_service(tmp_path, monkeypatch)
    sid = service.create_session("review.json")["session_id"]
    (service.settings.input_root / "A.txt").write_text("; ".join(PEOPLE))
    (service.settings.input_root / "B.txt").write_text("; ".join(reversed(PEOPLE)))
    (service.settings.input_root / "C.txt").write_text(
        "; ".join(PEOPLE[2:] + PEOPLE[:2])
    )

    first = service.filter_file("A.txt", sid)
    second = service.filter_file("B.txt", sid)
    third = service.filter_file("C.txt", sid)
    reloaded = FilterService(service.settings)
    filtered = [
        reloaded.read_result(result["artifact_id"])["redacted_text"]
        for result in (first, second, third)
    ]
    tokens = filtered[0].split("; ")
    assert filtered[1].split("; ") == list(reversed(tokens))
    assert filtered[2].split("; ") == tokens[2:] + tokens[:2]
    assert reloaded.open_session(sid)["documents"] == 3
    assert not any(
        name in json.dumps((first, second, third, filtered)) for name in PEOPLE
    )
    assert (service.settings.input_root / "A.txt").read_text() == "; ".join(PEOPLE)

    (service.settings.input_root / "answer.txt").write_text(
        f"Memo: {tokens[4]} works with {tokens[0]}."
    )
    result = reloaded.restore_file(sid, "answer.txt")
    assert (
        Path(result["output_path"]).read_text()
        == f"Memo: {PEOPLE[4]} works with {PEOPLE[0]}."
    )
    assert not any(name in json.dumps(result) for name in PEOPLE)
    with pytest.raises(FilterError, match="artifact_unavailable"):
        reloaded.read_result(Path(result["output_path"]).parent.name)


@pytest.mark.parametrize("engine", ["openai", "gliner2"])
def test_redaction_engines_do_not_advertise_session_tools(tmp_path, engine):
    service = FilterService(
        Settings(tmp_path, tmp_path / "out", tmp_path / "model", engine=engine)
    )
    names = asyncio.run(create_server(service).list_tools())
    assert len(names) == 4
    assert engine_for(engine).reversible is False
    with pytest.raises(FilterError, match="sessions_not_supported"):
        service.create_session()
    with pytest.raises(FilterError, match="sessions_not_supported"):
        service.open_session("unknown")
    with pytest.raises(FilterError, match="sessions_not_supported"):
        service.restore_file("unknown", "file.txt")


@pytest.mark.parametrize(
    "engine,prefix", [("lethe", "lethe"), ("pii-shield", "pii_shield")]
)
def test_session_engines_advertise_only_safe_tools(tmp_path, engine, prefix):
    service = FilterService(
        Settings(tmp_path, tmp_path / "out", tmp_path / "model", engine=engine)
    )
    names = {tool.name for tool in asyncio.run(create_server(service).list_tools())}
    assert names == {
        f"{prefix}_{suffix}"
        for suffix in (
            "status",
            "file",
            "batch",
            "read",
            "session_create",
            "session_open",
            "restore",
        )
    }
    assert engine_for(engine).cross_document is True


@pytest.mark.parametrize(
    "attack", ["tamper", "symlink", "busy", "engine", "missing", "invalid"]
)
def test_sessions_reject_corruption_wrong_engine_and_concurrent_use(
    tmp_path, monkeypatch, attack
):
    service = lethe_service(tmp_path, monkeypatch)
    sid = service.create_session("review.json")["session_id"]
    folder = service.settings.model_root / "sessions" / sid
    (service.settings.input_root / "A.txt").write_text(PEOPLE[0])
    expected = "session_integrity_failed"
    if attack == "tamper":
        (folder / "lethe.json").write_text("[]")
    elif attack == "symlink":
        (folder / "alias").symlink_to(folder / "lethe.json")
        expected = "invalid_session_state"
    elif attack == "busy":
        folder.with_name(sid + ".lock").mkdir()
        expected = "session_busy"
    elif attack == "engine":
        service.sessions = SessionStore(replace(service.settings, engine="pii-shield"))
        expected = "session_engine_mismatch"
    elif attack == "missing":
        (folder / "receipt.json").unlink()
        expected = "session_unavailable"
    else:
        sid = "../../secrets"
        expected = "invalid_session_id"
    with pytest.raises(FilterError, match=expected):
        service.filter_file("A.txt", sid)


def test_unapproved_lethe_review_and_missing_session_fail_closed(tmp_path, monkeypatch):
    service = lethe_service(tmp_path, monkeypatch)
    path = service.settings.input_root / "review.json"
    review = json.loads(path.read_text())
    review["approved"] = False
    path.write_text(json.dumps(review))
    with pytest.raises(FilterError, match="session_creation_failed"):
        service.create_session("review.json")
    (service.settings.input_root / "A.txt").write_text(PEOPLE[0])
    with pytest.raises(FilterError, match="session_required"):
        service.filter_file("A.txt")
    with pytest.raises(FilterError, match="outside_input_directory"):
        service.create_session(str(Path(__file__).resolve()))
    with pytest.raises(FilterError, match="outside_input_directory"):
        service.restore_file("irrelevant", str(Path(__file__).resolve()))


@pytest.mark.parametrize(
    "body",
    [
        {"error": "raw identities"},
        {"redacted_text": "safe"},
        {
            "redacted_text": "safe",
            "detection_counts": {"entities": -1},
            "source_characters": 3,
        },
    ],
)
def test_failed_engine_state_is_not_reused_or_exposed(tmp_path, monkeypatch, body):
    service = lethe_service(tmp_path, monkeypatch)
    sid = service.create_session("review.json")["session_id"]
    (service.settings.input_root / "A.txt").write_text(PEOPLE[0])
    service.sessions.backend = lambda request: body
    with pytest.raises(FilterError, match="session_processing_failed"):
        service.filter_file("A.txt", sid)
    with pytest.raises(FilterError, match="session_requires_recovery"):
        service.open_session(sid)


def prepared_shield(tmp_path):
    root = tmp_path / "model"
    for name in (
        "upstream/models/model.onnx",
        "upstream/deps/installs/package.json",
        "cli/bin.mjs",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("prepared fixture")
    (root / "shield.json").write_text(
        json.dumps({"node": sys.executable, "cli": str(root / "cli/bin.mjs")})
    )
    (root / "shield-ready.json").write_text(
        json.dumps({"version": "2.2.0", "files": shield_ready.snapshot(root)})
    )
    return root


def test_prepared_shield_corrupt_cache_blocks_processing_before_upstream(
    tmp_path, monkeypatch
):
    root = prepared_shield(tmp_path)
    assert shield_ready.ready(root)
    (root / "upstream/deps/installs/package.json").write_text("corrupted")
    assert not shield_ready.ready(root)
    monkeypatch.setattr(
        session_worker.subprocess,
        "run",
        lambda *a, **k: pytest.fail("bootstrap must not run"),
    )
    with pytest.raises(FilterError, match="shield_not_prepared"):
        session_worker.execute(
            {
                "engine": "pii-shield",
                "operation": "create",
                "model_root": str(root),
                "folder": str(tmp_path),
            }
        )


def test_shield_preserves_native_id_and_uses_native_restore(tmp_path, monkeypatch):
    root = prepared_shield(tmp_path)
    folder = tmp_path / "session"
    folder.mkdir()
    requests = []

    def upstream(model_root, directory, args):
        requests.append(args)
        if args[0] == "deanonymize":
            Path(args[-1]).write_text("Anna Rossi")
            return "ignored raw diagnostics"
        out = Path(args[args.index("--out") + 1])
        out.mkdir()
        target = out / "document_anonymized.txt"
        target.write_text("<PERSON_1>")
        return json.dumps(
            {
                "session_id": "native_123",
                "ner_ready": True,
                "files_count": 1,
                "entity_count": 1,
                "results": [{"output_path": str(target)}],
                "mapping": {"<PERSON_1>": "Anna Rossi"},
            }
        )

    monkeypatch.setattr(session_worker, "_shield_command", upstream)
    base = {"engine": "pii-shield", "model_root": str(root), "folder": str(folder)}
    assert session_worker.execute({**base, "operation": "create"}) == {"created": True}
    source = tmp_path / "A.txt"
    source.write_text("Anna Rossi")
    first = session_worker.execute({**base, "operation": "filter", "path": str(source)})
    second = session_worker.execute(
        {**base, "operation": "filter", "path": str(source)}
    )
    target = tmp_path / "restored.txt"
    assert session_worker.execute(
        {**base, "operation": "restore", "path": str(source), "target": str(target)}
    ) == {"restored": True}
    assert (
        first
        == second
        == {
            "redacted_text": "<PERSON_1>",
            "detection_counts": {"entities": 1},
            "source_characters": 10,
        }
    )
    assert "--session" not in requests[0]
    assert requests[1][-2:] == ["--session", "native_123"]
    assert requests[2][requests[2].index("--session") + 1] == "native_123"
    assert target.read_text() == "Anna Rossi"
    assert "Anna" not in json.dumps(first)


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(returncode=1, stdout="raw"),
        SimpleNamespace(returncode=0, stdout='{"error":"Anna Rossi"}'),
        SimpleNamespace(returncode=0, stdout="not JSON"),
    ],
)
def test_worker_diagnostics_never_enter_response(monkeypatch, result):
    monkeypatch.setattr(
        "mparanza_privacy_filter.sessions.subprocess.run", lambda *a, **k: result
    )
    with pytest.raises(FilterError, match="session_processing_failed"):
        run_session_worker({})


def test_worker_main_errors_are_fixed_and_unknown_engine_is_rejected(
    monkeypatch, capsys
):
    import io

    monkeypatch.setattr(
        sys, "stdin", io.StringIO('{"engine":"unknown", "operation":"filter"}')
    )
    session_worker.main()
    assert json.loads(capsys.readouterr().out) == {"error": "session_processing_failed"}


def test_mcp_lethe_session_roundtrip_and_safe_errors(tmp_path, monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    service = lethe_service(tmp_path, monkeypatch)
    server = create_server(service)
    (service.settings.input_root / "A.txt").write_text(PEOPLE[0])

    created = asyncio.run(
        server.call_tool("lethe_session_create", {"state_path": "review.json"})
    )
    sid = created[1]["session_id"]
    opened = asyncio.run(server.call_tool("lethe_session_open", {"session_id": sid}))
    filtered = asyncio.run(
        server.call_tool("lethe_batch", {"paths": ["A.txt"], "session_id": sid})
    )
    (service.settings.input_root / "answer.txt").write_text("[PERSON_001]")
    restored = asyncio.run(
        server.call_tool("lethe_restore", {"session_id": sid, "path": "answer.txt"})
    )
    assert "Anna Rossi" not in repr((created, opened, filtered, restored))
    assert Path(restored[1]["output_path"]).read_text() == "Anna Rossi"
    with pytest.raises(ToolError, match="session_creation_failed"):
        asyncio.run(server.call_tool("lethe_session_create", {}))
    with pytest.raises(ToolError, match="invalid_session_id"):
        asyncio.run(server.call_tool("lethe_session_open", {"session_id": "../bad"}))
    with pytest.raises(ToolError, match="restoration_failed"):
        asyncio.run(
            server.call_tool("lethe_restore", {"session_id": sid, "path": "absent.txt"})
        )


def test_lethe_local_review_preparation_requires_approval(tmp_path, monkeypatch):
    from mparanza_privacy_filter import lethe_review

    monkeypatch.setenv("LETHE_DATA_DIR", str(tmp_path / "lethe-data"))
    source = tmp_path / "A.txt"
    source.write_text("anna@example.com")
    review = tmp_path / "review.json"
    monkeypatch.setattr(
        sys, "argv", ["lethe_review", str(source), "--output", str(review)]
    )
    lethe_review.main()
    body = json.loads(review.read_text())
    assert body["approved"] is False
    assert body["items"][0]["canonical"] == "anna@example.com"
    assert body["items"][0]["source"] == "pattern"


def test_shield_explicit_setup_downloads_before_readiness_receipt(
    tmp_path, monkeypatch
):
    from mparanza_privacy_filter import shield_prepare

    node, npm = tmp_path / "node", tmp_path / "npm-cli.js"
    node.touch()
    npm.touch()
    root = tmp_path / "model"
    commands = []

    def setup(command, **kwargs):
        commands.append(command)
        assert kwargs["env"]["ONNXRUNTIME_NODE_INSTALL"] == "skip"
        for name in (
            "cli/node_modules/pii-shield/dist/cli/bin.mjs",
            "upstream/models/model.onnx",
            "upstream/deps/installs/package.json",
        ):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("installed asset")
        assert not (root / "shield-ready.json").exists()
        return SimpleNamespace(stdout='{"ner_ready":true}')

    monkeypatch.setattr(shield_prepare.subprocess, "run", setup)
    monkeypatch.setattr(
        sys,
        "argv",
        ["prepare", "--model-dir", str(root), "--node", str(node), "--npm", str(npm)],
    )
    shield_prepare.main()
    assert commands[0][-1] == "pii-shield@2.2.0"
    assert commands[1][-2:] == ["install-model", "--yes"]
    assert commands[2][2] == "anonymize"
    assert shield_ready.ready(root)


@pytest.mark.parametrize("problem", ["not_ready", "wrong_id", "outside_output"])
def test_shield_rejects_model_fallback_session_substitution_and_external_paths(
    tmp_path, monkeypatch, problem
):
    root = prepared_shield(tmp_path)
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "shield-session.json").write_text('{"upstream_id":"expected"}')
    source = tmp_path / "source.txt"
    source.write_text("Anna Rossi")

    def upstream(model_root, directory, args):
        out = Path(args[args.index("--out") + 1])
        out.mkdir()
        target = out / "document.txt"
        target.write_text("<PERSON_1>")
        return json.dumps(
            {
                "session_id": "other" if problem == "wrong_id" else "expected",
                "ner_ready": problem != "not_ready",
                "files_count": 1,
                "entity_count": 1,
                "results": [
                    {
                        "output_path": str(
                            source if problem == "outside_output" else target
                        )
                    }
                ],
            }
        )

    monkeypatch.setattr(session_worker, "_shield_command", upstream)
    with pytest.raises(FilterError, match="invalid_shield_response"):
        session_worker.execute(
            {
                "engine": "pii-shield",
                "operation": "filter",
                "model_root": str(root),
                "folder": str(folder),
                "path": str(source),
            }
        )
