from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from tests.plugins._teaching_execution import execution_record

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
    monkeypatch.syspath_prepend(str(SCRIPTS))
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
        execution_record=execution_record(store, phase, output, workflow),
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


@pytest.mark.parametrize(
    ("skill", "component", "role"),
    [
        ("bilancio-oic", "bilancio-xbrl-it", "source"),
        ("purchase-invoice-review", "passive-invoice-audit", "source"),
        ("financial-report-builder", "report-builder", "source"),
    ],
)
def test_renamed_lesson_starts_existing_ledger_workflow(
    store, module, skill, component, role
):
    store.begin()
    change(store, "profile", confirmed_by_user=True, profile=profile())
    change(
        store,
        "plan",
        lessons=[
            {"workflow_id": workflow, "reason": "User request", "goal": "Learn it"}
            for workflow in (skill, "journal-sampling", "variance-analysis")
        ],
    )
    change(
        store,
        "pair",
        teacher_thread_id="native-teacher",
        worker_thread_id="native-worker",
    )
    state = change(store, "start", workflow_id=skill)
    adapter = load("local_onboarding_case")

    result = adapter.prepare_case(
        store,
        thread_id="native-worker",
        workflow=skill,
        token=state["lessons"][0]["worker_token"],
        sources=[ROOT / "plugins/vera/assets/onboarding/invoice.xml"],
        phase="demo",
    )

    assert result["workflow_id"] == skill
    assert result["run"]["workflow_id"] == component
    assert result["run"]["status"] == "running"
    assert result["context"]["input_bindings"][0]["role"] == role


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


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_archive_teaching_kit_runs_scoped_search_and_refresh_in_isolated_copy(
    store, module, tmp_path, monkeypatch, language
):
    import shutil

    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    store.begin()
    change(
        store,
        "profile",
        confirmed_by_user=True,
        profile={**profile(), "language": language},
    )
    change(
        store,
        "plan",
        lessons=[
            {
                "workflow_id": workflow,
                "reason": "Fictional regression exercise",
                "goal": "Learn the current workflow",
            }
            for workflow in ("studio-archive", "journal-sampling", "variance-analysis")
        ],
    )
    change(
        store,
        "pair",
        teacher_thread_id="native-teacher",
        worker_thread_id="native-worker",
    )
    started = change(store, "start", workflow_id="studio-archive")
    token = started["lessons"][0]["worker_token"]
    kit_root = tmp_path / "kit"
    kit = CourseLibrary(ROOT / "plugins/vera", {"studio-archive"}).render(
        "studio-archive", language, kit_root
    )
    sources = [Path(path) for path in kit["source_files"]]
    original_bytes = {str(path): path.read_bytes() for path in sources}
    adapter = load("local_onboarding_case")
    result = adapter.prepare_case(
        store,
        thread_id="native-worker",
        workflow="studio-archive",
        token=token,
        sources=sources,
        source_root=kit_root / "files/input/archive",
        phase="demo",
    )
    assert result["setup_required"] is True
    assert result["execution_receipt"] is False
    archive = Path(result["archive_root"])
    state_dir = Path(result["archive_state_dir"])
    assert archive.is_relative_to(store.root / "lessons/studio-archive")
    assert not state_dir.is_relative_to(archive)
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", result["archive_session_id"])
    monkeypatch.syspath_prepend(str(ROOT / "plugins/studio-archive/scripts"))
    import archive_core

    status = archive_core.configure_archive(archive, state_dir=state_dir)
    scope = next(
        item["scope_id"]
        for item in status["scopes"]
        if item["display_name"] == "Ciclo Arco"
    )
    archive_core.refresh_archive(state_dir=state_dir)
    initial = archive_core.search_archive(
        "Tecnica Esempio", scope_id=scope, state_dir=state_dir
    )
    assert initial["result_count"] == 1
    opened = archive_core.open_archive_source(
        initial["results"][0]["source_id"], state_dir=state_dir
    )
    assert opened["source_verified"] is True
    assert "Ciclo Arco" in opened["relative_path"]
    update = next(
        Path(path)
        for path in kit["practice_files"]
        if Path(path).name == f"update-{language}.md"
    )
    store.worker("native-worker", "studio-archive", token)
    shutil.copyfile(update, archive / "Ciclo Arco" / update.name)
    archive_core.refresh_archive(state_dir=state_dir)
    refreshed = archive_core.search_archive(
        "Tecnica Esempio", scope_id=scope, state_dir=state_dir
    )
    assert refreshed["result_count"] == 2
    verified = [
        archive_core.open_archive_source(row["source_id"], state_dir=state_dir)
        for row in refreshed["results"]
    ]
    assert all(row["source_verified"] for row in verified)
    assert all("Ciclo Arco" in row["relative_path"] for row in verified)
    assert any("2027" in json.dumps(row["fragments"]) for row in verified)
    assert {str(path): path.read_bytes() for path in sources} == original_bytes
    assert not (tmp_path / "studio-archive").exists()


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize(
    "dataset,expected_count", [("source_files", 3), ("practice_files", 4)]
)
def test_organization_kit_runs_real_snapshot_review_apply_and_rollback(
    store, module, tmp_path, monkeypatch, language, dataset, expected_count
):
    import hashlib

    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    store.begin()
    change(
        store,
        "profile",
        confirmed_by_user=True,
        profile={**profile(), "language": language},
    )
    change(
        store,
        "plan",
        lessons=[
            {
                "workflow_id": workflow,
                "reason": "Fictional execution fixture",
                "goal": "Verify the current workflow",
            }
            for workflow in (
                "archive-organization",
                "journal-sampling",
                "variance-analysis",
            )
        ],
    )
    change(
        store,
        "pair",
        teacher_thread_id="native-teacher",
        worker_thread_id="native-worker",
    )
    started = change(store, "start", workflow_id="archive-organization")
    kit_root = tmp_path / "kit"
    kit = CourseLibrary(ROOT / "plugins/vera", {"archive-organization"}).render(
        "archive-organization", language, kit_root
    )
    sources = [Path(path) for path in kit[dataset]]
    source_root = kit_root / (
        "files/input/client" if dataset == "source_files" else "files/practice/client"
    )
    original = {
        path.relative_to(source_root).as_posix(): path.read_bytes() for path in sources
    }
    adapter = load("local_onboarding_case")
    # Independent compatibility runs for both input sets; this does not record
    # learner demonstration, practice, understanding or professional approval.
    run = adapter.prepare_case(
        store,
        thread_id="native-worker",
        workflow="archive-organization",
        token=started["lessons"][0]["worker_token"],
        sources=sources,
        source_root=source_root,
        phase="demo",
    )
    case = Path(run["client_root"])
    context_path = Path(run["context_path"])
    context = run["context"]
    assert len(context["input_bindings"]) == 1
    snapshot = json.loads(Path(context["input_bindings"][0]["path"]).read_text())
    assert snapshot["file_count"] == expected_count
    assert all(
        not row["relative_path"].startswith("Vera/") for row in snapshot["files"]
    )
    assert Path(run["tutorial_case_path"]).parent == case / "Vera"
    monkeypatch.syspath_prepend(str(ROOT / "plugins/studio-archive/scripts"))
    import archive_core

    state_dir = tmp_path / "organization-index"
    archive_core.configure_archive(case.parent, state_dir=state_dir)
    snapshot_id = context["input_bindings"][0]["binding_id"]
    inventory = archive_core.get_studio_archive_organization_inventory(
        context["client_id"], context["engagement_id"], snapshot_id, state_dir=state_dir
    )["model_inventory"]
    proposals = []
    meanings = {
        f"maintenance-{language}.md": (
            "contratti",
            "accordo-manutenzione",
            None,
            "The supplied agreement describes this client’s monthly maintenance service.",
        ),
        f"maintenance-copy-{language}.md": (
            "contratti",
            "accordo-manutenzione",
            None,
            "This is the same maintenance agreement; exact duplication is determined by the source snapshot.",
        ),
        f"meeting-{language}.md": (
            "documenti-societari",
            "verbale-interno",
            "2026-03-10",
            "The internal dated meeting note names this client and an administrative contact.",
        ),
        f"update-{language}.md": (
            "contratti",
            "aggiornamento-accordo",
            "2026-12-15",
            "The supplied dated update extends the same maintenance agreement.",
        ),
    }
    for item in inventory["files"]:
        evidence = archive_core.open_studio_archive_organization_item(
            context["client_id"],
            context["engagement_id"],
            snapshot_id,
            item["item_ref"],
            state_dir=state_dir,
        )
        assert evidence["source_identity_revalidated"] is True
        assert evidence["google_drive_api_called"] is False
        # Explicit model-authored meanings of these exact fictional documents;
        # this lookup is not a runtime filename classification rule.
        category, doc_type, doc_date, reason = meanings[item["name"]]
        proposals.append(
            {
                "item_ref": item["item_ref"],
                "category_id": category,
                "document_type": doc_type,
                "document_date": doc_date,
                "entity": "Ciclo-Arco",
                "reference": None,
                "practice": None,
                "confidence": "high",
                "reason": reason,
                "probable_duplicate_of": None,
                "anomalies": [],
            }
        )
    proposed = tmp_path / "semantic-proposals.json"
    proposed.write_text(
        json.dumps(
            {
                "schema_version": "vera.archive_organization_model_proposals.v1",
                "inventory_ref": inventory["inventory_ref"],
                "proposals": proposals,
            }
        ),
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location(
        "kit_archive_organizer",
        ROOT / "plugins/archive-organization/scripts/archive_organization.py",
    )
    organizer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = organizer
    spec.loader.exec_module(organizer)
    review = organizer.build_review_package(context_path, proposed)
    assert review["source_archive_mutated"] is False
    assert {
        relative: (case / relative).read_bytes() for relative in original
    } == original
    payload = json.loads(Path(review["review_payload_path"]).read_text())
    decisions_path = tmp_path / "fixture-decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "reviewer": "fictional-regression-reviewer",
                "decision_source": "pytest",
                "decisions": [
                    {"item_id": item["id"], "action": "accept"}
                    for item in payload["items"]
                ],
            }
        ),
        encoding="utf-8",
    )
    saved = organizer.persist_review_decisions(context_path, decisions_path)
    approved = organizer.compile_approved_plan(
        context_path, Path(saved["ui_decisions_path"])
    )
    with pytest.raises(
        organizer.ArchiveOrganizationError, match="Explicit apply approval"
    ):
        organizer.apply_approved_plan(
            context_path, Path(approved["approved_plan_path"]), explicit_approval=False
        )
    applied = organizer.apply_approved_plan(
        context_path, Path(approved["approved_plan_path"]), explicit_approval=True
    )
    assert applied["applied_count"] == expected_count
    quarantine = list((case / "Da_verificare/Duplicati_esatti").rglob("*.md"))
    assert len(quarantine) == 1
    assert (
        quarantine[0].read_bytes()
        == original[f"Download/maintenance-copy-{language}.md"]
    )
    assert organizer.rollback_applied_plan(context_path)["status"] == "rolled_back"
    assert {
        relative: (case / relative).read_bytes() for relative in original
    } == original
    assert {
        path.relative_to(source_root).as_posix(): path.read_bytes() for path in sources
    } == original


def test_website_teaching_prepares_private_project_for_current_specialist(
    store, module, tmp_path
):
    store.begin()
    change(store, "profile", confirmed_by_user=True, profile=profile())
    workflows = ("presenza-digitale-studio", "fatture-xml-check", "variance-analysis")
    change(
        store,
        "plan",
        lessons=[
            {
                "workflow_id": wf,
                "reason": "Fictional fixture",
                "goal": "Run the current local website workflow",
            }
            for wf in workflows
        ],
    )
    change(store, "pair", teacher_thread_id="teacher", worker_thread_id="worker")
    started = change(store, "start", workflow_id=workflows[0])
    source = tmp_path / "studio.md"
    source.write_text("Fictional studio for the selected local website exercise.")
    result = load("local_onboarding_case").prepare_case(
        store,
        thread_id="worker",
        workflow=workflows[0],
        token=started["lessons"][0]["worker_token"],
        sources=[source],
        phase="demo",
    )
    assert result["status"] == "prepared"
    assert "context_path" not in result
    assert Path(result["inputs"][0]["path"]).read_bytes() == source.read_bytes()
    assert Path(result["output_dir"]).is_relative_to(store.root)
    assert not (Path(result["directory"]) / "Vera").exists()


def test_sampling_teaching_binds_one_journal_and_separate_context_note(
    store, module, tmp_path
):
    store.begin()
    change(store, "profile", confirmed_by_user=True, profile=profile())
    change(
        store,
        "plan",
        lessons=[
            {"workflow_id": wf, "reason": "Fictional fixture", "goal": "Learn sampling"}
            for wf in ("journal-sampling", "fatture-xml-check", "variance-analysis")
        ],
    )
    change(store, "pair", teacher_thread_id="teacher", worker_thread_id="worker")
    started = change(store, "start", workflow_id="journal-sampling")
    source = ROOT / "scripts/course_materials/inputs/accounting/journal-march.csv"
    note = ROOT / "scripts/course_materials/inputs/journal-sampling/context-it.md"
    result = load("local_onboarding_case").prepare_case(
        store,
        thread_id="worker",
        workflow="journal-sampling",
        token=started["lessons"][0]["worker_token"],
        sources=[source, note],
        phase="demo",
    )
    bindings = result["context"]["input_bindings"]
    assert [item["role"] for item in bindings] == ["journal", "source"]
    assert Path(bindings[0]["path"]).read_bytes() == source.read_bytes()
    assert Path(bindings[1]["path"]).read_bytes() == note.read_bytes()


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_vouching_kit_runs_live_sample_handoff_and_current_checks(
    store, module, tmp_path, monkeypatch, language
):
    import csv
    import mimetypes

    monkeypatch.syspath_prepend(str(ROOT / "tests/plugins"))
    from test_teaching_kit_execution import _sample_teaching_journal

    from tests.model_data_helpers import write_no_model_report

    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins/vera", {"vouching"}).render(
        "vouching", language, tmp_path / "kit"
    )
    store.begin()
    change(
        store,
        "profile",
        confirmed_by_user=True,
        profile={**profile(), "language": language},
    )
    change(
        store,
        "plan",
        lessons=[
            {
                "workflow_id": wf,
                "reason": "Fictional regression",
                "goal": "Learn document checks",
            }
            for wf in ("vouching", "journal-sampling", "variance-analysis")
        ],
    )
    change(store, "pair", teacher_thread_id="teacher", worker_thread_id="worker")
    started = change(store, "start", workflow_id="vouching")
    token = started["lessons"][0]["worker_token"]
    adapter = load("local_onboarding_case")
    # Reject invoices alone: no fake predecessor or raw-journal check run.
    with pytest.raises(module.OnboardingError, match="one CSV/Excel journal"):
        adapter.prepare_case(
            store,
            thread_id="worker",
            workflow="vouching",
            token=token,
            sources=[Path(p) for p in kit["source_files"] if p.endswith(".xml")],
            phase="demo",
        )
    first_result = None
    for phase, size, selected in (
        ("demo", 2, kit["source_files"]),
        ("practice", 3, kit["practice_files"]),
    ):
        prepared = adapter.prepare_case(
            store,
            thread_id="worker",
            workflow="vouching",
            token=token,
            sources=[Path(p) for p in selected],
            phase=phase,
        )
        assert prepared["prerequisite_workflow"] == "journal-sampling"
        assert prepared["run"]["workflow_id"] == "journal-sampling"
        assert len(prepared["support_input_ids"]) == 3
        assert {item["role"] for item in prepared["context"]["input_bindings"]} == {
            "journal",
            "source",
        }
        _sample_teaching_journal(
            prepared,
            monkeypatch,
            language,
            population=9,
            size=size,
            include_accounts="2100",
        )
        ledger = adapter._ledger()
        output = Path(prepared["output_dir"])
        context = prepared["context"]
        client = context["client_id"]
        engagement = context["engagement_id"]
        sample_run = context["run_id"]
        special = {
            "normalization/normalized_journal.csv": "prepared.normalized_journal",
            "normalization/normalization_diagnostics.json": "internal.normalization_diagnostics",
            "sample/journal_sample.csv": "prepared.journal_sample_csv",
        }
        declarations = [
            {
                "artifact_id": special.get(
                    path.relative_to(output).as_posix(), f"internal.teaching.{index}"
                ),
                "path": path.relative_to(output).as_posix(),
                "purpose": "Preserve actual fictional sampling output for document checks",
                "audience": "review",
                "media_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
            }
            for index, path in enumerate(
                sorted(p for p in output.rglob("*") if p.is_file())
            )
        ]
        declarations.extend(
            write_no_model_report(output, "journal-sampling", sample_run)
        )
        ledger.finalize_run(
            Path(prepared["client_root"]), engagement, sample_run, declarations
        )
        ledger.complete_run(Path(prepared["client_root"]), engagement, sample_run)
        # Reuse the configured in-process archive instance and its session lock.
        archive = sys.modules["vera_tutorial_archive"]
        handoff = archive.start_check_entries_from_sample(
            client,
            engagement,
            sample_run,
            support_input_ids=prepared["support_input_ids"],
            state_dir=Path(prepared["archive_state_dir"]),
        )
        check_context = handoff["client_engagement"]
        normalized = next(
            Path(item["path"])
            for item in check_context["input_bindings"]
            if item.get("upstream_artifact_id") == "prepared.normalized_journal"
        )
        support = next(
            Path(item["path"])
            for item in check_context["input_bindings"]
            if item["role"] == "support"
        ).parent.parent
        check_output = Path(check_context["output_dir"])
        for script, destination, extra in (
            ("inspect_entries.py", "inspection", []),
            (
                "run_checks.py",
                "checks",
                ["--recipe", str(check_output / "inspection/suggested_recipe.json")],
            ),
        ):
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(ROOT / "plugins/check-entries/scripts" / script),
                    str(normalized),
                    str(support),
                    "--output-dir",
                    str(check_output / destination),
                    "--client-engagement",
                    handoff["client_engagement_path"],
                    "--language",
                    language,
                    "--document-language",
                    "it",
                    *extra,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        result_path = check_output / "checks/check_results.csv"
        with result_path.open(encoding="utf-8-sig", newline="") as stream:
            checked = list(csv.DictReader(stream))
        assert len(checked) == size
        assert all(
            row["professional_conclusion"] == "pending_review" for row in checked
        )
        assert (check_output / "checks/check_results.xlsx").is_file()
        assert (check_output / "checks/review_notes.md").is_file()
        audit = json.loads((check_output / "checks/check_audit.json").read_text())
        assert audit["invoice_count"] == 3
        assert audit["invoice_error_count"] == 0
        check_run = check_context["run_id"]
        check_declarations = [
            {
                "artifact_id": f"internal.vouching.{index}",
                "path": path.relative_to(check_output).as_posix(),
                "purpose": "Preserve actual fictional document-check output",
                "audience": "review",
                "media_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
            }
            for index, path in enumerate(
                sorted(p for p in check_output.rglob("*") if p.is_file())
            )
        ]
        check_declarations.extend(
            write_no_model_report(check_output, "check-entries", check_run)
        )
        ledger.finalize_run(
            Path(prepared["client_root"]), engagement, check_run, check_declarations
        )
        completed = ledger.complete_run(
            Path(prepared["client_root"]), engagement, check_run
        )
        assert completed["run"]["status"] == "completed"
        if first_result is None:
            first_result = (result_path, result_path.read_bytes())
        else:
            assert first_result[0].read_bytes() == first_result[1]
        # Persist actual generated evidence, without claiming learner approval.
        change(
            store,
            phase,
            workflow_id="vouching",
            artifacts=[str(result_path.relative_to(store.root / "lessons/vouching"))],
            execution_record=execution_record(
                store,
                phase,
                result_path,
                "vouching",
                inputs=[Path(item["path"]) for item in check_context["input_bindings"]],
                native=[check_output / "checks/check_audit.json"],
            ),
            prompt="Run the prepared fictional document check",
            review="Mechanical regression evidence only; native learner review unverified",
        )
