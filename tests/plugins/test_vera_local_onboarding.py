from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/vera/scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module(monkeypatch):
    module = load("local_onboarding")
    monkeypatch.setitem(sys.modules, "local_onboarding", module)
    return module


@pytest.fixture
def store(module, tmp_path):
    return module.Store(tmp_path / "local-professional")


def change(store, action, **data):
    return store.change(action, store.status()["revision"], data)


def profile():
    return {
        "language": "it",
        "work": "Contabilità e controllo di gestione",
        "interests": "Controllare fatture e capire gli scostamenti",
        "experience": "Usa già Vera per leggere documenti",
        "preferences": "Esempi brevi, output Excel",
    }


def prepare(store):
    store.begin()
    change(store, "profile", confirmed_by_user=True, profile=profile())
    change(
        store,
        "plan",
        lessons=[
            {
                "workflow_id": workflow,
                "reason": "Richiesto dal professionista",
                "goal": "Provare su dati sintetici",
            }
            for workflow in (
                "fatture-xml-check",
                "journal-sampling",
                "variance-analysis",
            )
        ],
    )
    return change(
        store,
        "pair",
        teacher_thread_id="native-teacher",
        worker_thread_id="native-worker",
    )


def evidence(store, workflow, phase):
    folder = store.root / "lessons" / workflow
    output = folder / f"{phase}.csv"
    output.write_text(f"result\n{phase}\n")
    return change(
        store,
        phase,
        workflow_id=workflow,
        artifacts=[output.name],
        prompt="Controlla questo esempio",
        review="Valori confrontati con gli input; limite spiegato",
    )


def finish(store, workflow):
    change(store, "start", workflow_id=workflow)
    evidence(store, workflow, "demo")
    evidence(store, workflow, "practice")
    return change(
        store,
        "finish",
        workflow_id=workflow,
        confirmed_by_user=True,
        understanding="Il professionista ha spiegato quali file servono e cosa controllare",
    )


def test_new_and_existing_users_enroll_once_without_version_or_project_dependence(
    store, module, monkeypatch, tmp_path
):
    assert store.status()["phase"] == "required"
    assert not store.root.exists()
    started = store.begin()
    assert store.begin() == started
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "new-version"))
    other_host = module.Store(store.root)
    assert other_host.status() == started
    assert started["phase"] == "interview"
    assert not (tmp_path / "new-version").exists()


def test_confirmed_profile_replaces_temporary_notes_and_is_shared_across_processes(
    store,
):
    store.begin()
    change(store, "notes", notes="Prima risposta, resta da scegliere il primo esempio")
    with pytest.raises(ValueError, match="confirmation"):
        change(store, "profile", confirmed_by_user=False, profile=profile())
    accepted = change(store, "profile", confirmed_by_user=True, profile=profile())
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "local_onboarding.py"),
            "--state-root",
            str(store.root),
            "status",
        ],
        cwd=store.root.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == accepted
    assert accepted["interview_notes"] == ""
    assert accepted["profile"]["experience"].startswith("Usa già")


def test_whole_lifecycle_resumes_and_completed_profile_edits_do_not_repeat_lessons(
    store,
):
    prepare(store)
    finish(store, "fatture-xml-check")
    resumed = store.status()
    assert resumed["phase"] == "teaching"
    assert resumed["lessons"][0]["status"] == "complete"
    assert resumed["lessons"][1]["status"] == "pending"
    finish(store, "journal-sampling")
    completed = finish(store, "variance-analysis")
    assert completed["phase"] == "complete"
    changed = change(
        store,
        "profile",
        confirmed_by_user=True,
        profile={**profile(), "language": "fr"},
    )
    assert changed["completed_at"] == completed["completed_at"]
    assert changed["lessons"] == completed["lessons"]
    assert store.begin() == changed
    with pytest.raises(ValueError, match="already complete"):
        change(store, "start", workflow_id="fatture-xml-check")


def test_stale_writer_cannot_replace_profile_from_another_chat(store):
    revision = store.begin()["revision"]
    change(store, "notes", notes="Fatti appena confermati")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="Stale revision"):
        store.change("notes", revision, {"notes": "Vecchia risposta"})
    assert store.path.read_bytes() == before
    assert not (store.root / ".saving").exists()


def test_interrupted_save_lock_requires_recovery_without_overwriting(store):
    store.begin()
    (store.root / ".saving").mkdir()
    with pytest.raises(ValueError, match="Another save"):
        change(store, "notes", notes="Nuovo fatto")
    assert store.status()["interview_notes"] == ""


@pytest.mark.parametrize("filename", ["profile.json", "enrollment.json"])
def test_missing_enrolled_file_is_never_a_new_user(store, filename):
    store.begin()
    (store.root / filename).unlink()
    with pytest.raises(ValueError, match="Recover"):
        store.begin()


def test_corrupt_state_is_preserved_and_recovery_checks_identity(store, tmp_path):
    store.begin()
    change(store, "notes", notes="Fatto confermato")
    backup = store.root / "profile.previous.json"
    store.path.write_text("{")
    with pytest.raises(ValueError, match="invalid local JSON"):
        store.status()
    assert store.path.read_text() == "{"
    store.path.rename(store.root / "profile.damaged.json")
    wrong = json.loads(backup.read_text())
    wrong["onboarding_id"] = "a-different-professional"
    other = tmp_path / "other.json"
    other.write_text(json.dumps(wrong))
    with pytest.raises(ValueError, match="another professional"):
        store.recover(other)
    restored = store.recover(backup)
    assert restored["phase"] == "interview"
    assert (store.root / "profile.damaged.json").read_text() == "{"


def test_read_permission_error_does_not_trigger_enrollment(store, monkeypatch):
    store.begin()
    real_iterdir = Path.iterdir

    def denied(path):
        if path == store.root:
            raise PermissionError("folder access denied")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", denied)
    with pytest.raises(PermissionError):
        store.begin()


@pytest.mark.parametrize(
    "workflows",
    [
        ["fatture-xml-check"],
        ["fatture-xml-check"] * 3,
        ["fatture-xml-check", "variance-analysis", "made-up-workflow"],
        ["fatture-xml-check", "variance-analysis", "deep-research-validator"],
    ],
)
def test_plan_requires_three_or_four_real_distinct_operational_workflows(
    store, workflows
):
    store.begin()
    change(store, "profile", confirmed_by_user=True, profile=profile())
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        change(
            store,
            "plan",
            lessons=[
                {"workflow_id": w, "reason": "Rilevante", "goal": "Prova"}
                for w in workflows
            ],
        )
    assert store.path.read_bytes() == before


def test_worker_handoff_is_scoped_and_revoked_on_rebind_and_completion(store):
    prepare(store)
    started = change(store, "start", workflow_id="fatture-xml-check")
    token = started["lessons"][0]["worker_token"]
    assert (
        store.worker("native-worker", "fatture-xml-check", token)["local_only"] is True
    )
    for worker, workflow, nonce in [
        ("other-chat", "fatture-xml-check", token),
        ("native-worker", "journal-sampling", token),
        ("native-worker", "fatture-xml-check", "wrong-token"),
    ]:
        with pytest.raises(ValueError):
            store.worker(worker, workflow, nonce)
    rebound = change(
        store,
        "pair",
        teacher_thread_id="resumed-teacher",
        worker_thread_id="native-worker",
    )
    with pytest.raises(ValueError):
        store.worker("native-worker", "fatture-xml-check", token)
    token = rebound["lessons"][0]["worker_token"]
    finish(store, "fatture-xml-check")
    with pytest.raises(ValueError):
        store.worker("native-worker", "fatture-xml-check", token)


def test_cannot_finish_without_a_real_user_attempt_or_with_changed_evidence(store):
    prepare(store)
    change(store, "start", workflow_id="fatture-xml-check")
    with pytest.raises(ValueError, match="demonstration and guided practice"):
        change(
            store,
            "finish",
            workflow_id="fatture-xml-check",
            confirmed_by_user=True,
            understanding="Oui",
        )
    evidence(store, "fatture-xml-check", "demo")
    with pytest.raises(ValueError, match="own attempt"):
        change(
            store,
            "practice",
            workflow_id="fatture-xml-check",
            artifacts=["demo.csv"],
            prompt="Essai",
            review="Vu",
        )
    evidence(store, "fatture-xml-check", "practice")
    (store.root / "lessons/fatture-xml-check/practice.csv").write_text(
        "Changed after review"
    )
    with pytest.raises(ValueError, match="artifacts changed"):
        change(
            store,
            "finish",
            workflow_id="fatture-xml-check",
            confirmed_by_user=True,
            understanding="Oui",
        )
    assert store.status()["phase"] == "teaching"


@pytest.mark.parametrize("escape", ["../outside.txt", "/etc/hosts", "missing.csv"])
def test_evidence_cannot_escape_its_lesson_or_refer_to_absent_files(store, escape):
    prepare(store)
    change(store, "start", workflow_id="fatture-xml-check")
    with pytest.raises(ValueError, match="[Ee]vidence.*must"):
        change(
            store,
            "demo",
            workflow_id="fatture-xml-check",
            artifacts=[escape],
            prompt="Request",
            review="Review",
        )


def test_symlinked_profile_root_is_not_silently_followed(module, tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    link = tmp_path / "profile-link"
    link.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        module.Store(link)


def test_pending_hook_has_no_update_or_feedback_network_and_no_private_summary(
    module, store, monkeypatch, capsys
):
    prepare(store)
    monkeypatch.setattr(module, "default_root", lambda: store.root)

    def unexpected():
        pytest.fail(
            "Pending onboarding must not call hosted update or feedback services"
        )

    monkeypatch.setitem(
        sys.modules, "check_for_update", types.SimpleNamespace(main=unexpected)
    )
    hook = load("onboarding_session_start")
    assert hook.main() == 0
    output = capsys.readouterr().out
    assert "teaching" in output
    assert "Contabilità" not in output


def test_same_os_home_has_same_discovery_path_in_codex_and_work(
    module, monkeypatch, tmp_path
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "codex-versioned"))
    codex_root = module.default_root()
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "work-versioned"))
    assert (
        module.default_root() == codex_root == tmp_path / ".local/share/vera/onboarding"
    )
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData/Local"))
    assert module.default_root() == tmp_path / "AppData/Local/Vera/onboarding"


def test_tutorial_prepares_real_isolated_studio_ledger_with_bound_source(
    store, module, tmp_path
):
    prepare(store)
    state = change(store, "start", workflow_id="fatture-xml-check")
    adapter = load("local_onboarding_case")
    source = ROOT / "plugins/vera/assets/onboarding/invoice.xml"
    result = adapter.prepare_case(
        store,
        thread_id="native-worker",
        workflow="fatture-xml-check",
        token=state["lessons"][0]["worker_token"],
        sources=[source],
        phase="demo",
    )
    assert Path(result["client_root"]).is_relative_to(
        store.root / "lessons/fatture-xml-check"
    )
    assert result["run"]["status"] == "running"
    assert result["run"]["workflow_id"] == "client-file-preparation"
    assert Path(result["context_path"]).is_file()
    assert (
        source.read_bytes()
        == Path(result["context"]["input_bindings"][0]["path"]).read_bytes()
    )
    assert not (tmp_path / "studio-archive").exists()


def test_built_codex_and_local_work_load_the_same_profile_and_cowork_omits_feature(
    store, tmp_path
):
    from zipfile import ZipFile

    store.begin()
    change(store, "profile", confirmed_by_user=True, profile=profile())
    packages = ROOT / "plugin_packages/vera"
    script_bytes = (SCRIPTS / "local_onboarding.py").read_bytes()
    snapshots = []
    for surface, archive_name, prefix in [
        ("codex", "vera-plugin.zip", "vera-codex-plugin/plugins/vera/"),
        ("work", "vera-chatgpt-upload.zip", ""),
    ]:
        with ZipFile(packages / archive_name) as archive:
            assert archive.read(prefix + "scripts/local_onboarding.py") == script_bytes
            assert (
                prefix + "skills/vera/references/local-onboarding.md"
                in archive.namelist()
            )
            script = tmp_path / surface / "local_onboarding.py"
            script.parent.mkdir()
            script.write_bytes(script_bytes)
        result = subprocess.run(
            [sys.executable, str(script), "--state-root", str(store.root), "status"],
            cwd=script.parent,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        snapshots.append(json.loads(result.stdout))
    assert snapshots[0] == snapshots[1] == store.status()
    with ZipFile(packages / "vera-claude-plugin.zip") as archive:
        assert not any(
            "local_onboarding" in name or "/onboarding/" in name
            for name in archive.namelist()
        )
        for name in (
            "scripts/notarized_run_receipt.py",
            "skills/vera/SKILL.md",
            "skills/fatture-xml-check/SKILL.md",
        ):
            assert b"VERA_OPENAI_ONBOARDING" not in archive.read(name)
        assert (
            "local-onboarding"
            not in json.loads(archive.read("components.json"))["shared_services"]
        )


def test_tutorial_case_runs_actual_xml_workflow_against_its_managed_inputs(
    store, module
):
    import csv

    prepare(store)
    state = change(store, "start", workflow_id="fatture-xml-check")
    adapter = load("local_onboarding_case")
    result = adapter.prepare_case(
        store,
        thread_id="native-worker",
        workflow="fatture-xml-check",
        token=state["lessons"][0]["worker_token"],
        phase="demo",
        sources=[ROOT / "plugins/vera/assets/onboarding/invoice.xml"],
    )
    output = Path(result["output_dir"]) / "fatture"
    run = subprocess.run(
        [
            sys.executable,
            str(
                ROOT / "plugins/client-file-preparation/scripts/parse_fatturapa_xml.py"
            ),
            result["context"]["input_dir"],
            "--year",
            "2026",
            "--out",
            str(output),
            "--client-engagement",
            result["context_path"],
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    with (output / "fatture_summary.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["invoice_number"] == "DEMO-001"
    assert rows[0]["total_amount"] == "1220.00"
    assert rows[0]["malformed"] == "False"
    assert (output / "formal_anomalies.md").is_file()


@pytest.mark.parametrize(
    "mutation",
    [
        {"pair": {"teacher_thread_id": "same", "worker_thread_id": "same"}},
        {"schema_version": 2},
        {"phase": "complete"},
    ],
)
def test_invalid_persisted_state_does_not_silently_pass_gate(store, mutation):
    store.begin()
    state = json.loads(store.path.read_text())
    state.update(mutation)
    store.path.write_text(json.dumps(state))
    with pytest.raises(ValueError):
        store.status()


def test_path_in_a_corrupted_lesson_id_cannot_escape_the_profile(store):
    prepare(store)
    state = json.loads(store.path.read_text())
    state["lessons"][0]["workflow_id"] = "../../elsewhere"
    store.path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="workflow ID"):
        store.status()


def test_cli_saves_and_loads_profile_and_reports_recoverable_errors(
    module, store, capsys
):
    args = ["--state-root", str(store.root)]
    assert module.main([*args, "begin"]) == 0
    started = json.loads(capsys.readouterr().out)
    request = store.root / "confirmed-profile-input.json"
    request.write_text(json.dumps({"confirmed_by_user": True, "profile": profile()}))
    assert (
        module.main(
            [
                *args,
                "profile",
                "--revision",
                str(started["revision"]),
                "--input",
                str(request),
            ]
        )
        == 0
    )
    saved = json.loads(capsys.readouterr().out)
    assert saved["profile"] == profile()
    assert module.main([*args, "status"]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert module.main([*args, "notes"]) == 2
    assert json.loads(capsys.readouterr().out)["phase"] == "recovery_required"
    assert module.main([*args, "worker"]) == 2
    assert "actual host thread ID" in json.loads(capsys.readouterr().out)["error"]
    assert store.status() == saved


def test_hook_recovers_without_network_then_restores_normal_updates_after_completion(
    module, store, monkeypatch, capsys
):
    prepare(store)
    monkeypatch.setattr(module, "default_root", lambda: store.root)
    updates = []
    monkeypatch.setitem(
        sys.modules,
        "check_for_update",
        types.SimpleNamespace(main=lambda: updates.append("checked") or 0),
    )
    hook = load("onboarding_session_start")
    before = store.path.read_bytes()
    store.path.write_text("invalid")
    assert hook.main() == 0
    assert "recovery_required" in capsys.readouterr().out
    assert updates == []
    store.path.write_bytes(before)
    finish(store, "fatture-xml-check")
    finish(store, "journal-sampling")
    finish(store, "variance-analysis")
    assert hook.main() == 0
    assert "complete" in capsys.readouterr().out
    assert updates == ["checked"]


def test_tutorial_case_requires_the_local_marker_and_actual_source(
    store, module, tmp_path
):
    prepare(store)
    state = change(store, "start", workflow_id="fatture-xml-check")
    adapter = load("local_onboarding_case")
    args = {
        "store": store,
        "thread_id": "native-worker",
        "workflow": "fatture-xml-check",
        "token": state["lessons"][0]["worker_token"],
        "phase": "demo",
    }
    with pytest.raises(ValueError, match="existing ordinary local files"):
        adapter.prepare_case(**args, sources=[tmp_path / "missing.xml"])
    (store.root / module.MARKER).unlink()
    with pytest.raises(ValueError, match="local-only marker"):
        adapter.prepare_case(
            **args, sources=[ROOT / "plugins/vera/assets/onboarding/invoice.xml"]
        )


def test_cli_preserves_unicode_profile_on_a_non_unicode_console(module, store):
    import io
    from contextlib import redirect_stdout

    started = store.begin()
    multilingual = {**profile(), "language": "ja", "work": "会計と予算管理"}
    request = store.root / "profile-input.json"
    request.write_text(
        json.dumps({"confirmed_by_user": True, "profile": multilingual}),
        encoding="utf-8",
    )
    buffer = io.BytesIO()
    console = io.TextIOWrapper(buffer, encoding="ascii")
    with redirect_stdout(console):
        assert (
            module.main(
                [
                    "--state-root",
                    str(store.root),
                    "profile",
                    "--revision",
                    str(started["revision"]),
                    "--input",
                    str(request),
                ]
            )
            == 0
        )
    console.flush()
    assert json.loads(buffer.getvalue())["profile"] == multilingual
    assert json.loads(store.path.read_text(encoding="utf-8"))["profile"] == multilingual
