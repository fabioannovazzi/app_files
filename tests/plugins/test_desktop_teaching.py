"""Cross-product regressions for the actual shared desktop lifecycle.

The test participant's confirmation is synthetic; these are runtime checks,
not evidence that a human voice lesson or a native window was operated.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins._teaching_execution import execution_record

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
from desktop_teaching import cases, onboarding, teaching

WORKFLOWS = {
    "clara": ["reporting-engine", "html-deck", "deck-correction"],
    "lucia": [
        "apertura-pratica",
        "comunicazione-professionale",
        "presenza-digitale-studio",
    ],
}
PROFILE = {
    "language": "it",
    "work": "Consulenza",
    "interests": "Esempi pertinenti",
    "experience": "Già utente",
    "preferences": "Voce e due finestre",
}


@pytest.fixture(params=["clara", "lucia"])
def store(request, tmp_path):
    return onboarding.Store(
        tmp_path / request.param, plugin_root=ROOT / "plugins" / request.param
    )


def change(store, action, **data):
    state = store.status()
    return store.change(action, state.get("session", state)["revision"], data)


def prepare(store):
    store.begin()
    if store.status()["phase"] == "interview":
        change(store, "notes", notes="Synthetic interview checkpoint")
    change(store, "profile", profile=PROFILE, confirmed_by_user=True)
    change(
        store,
        "plan",
        lessons=[
            {
                "workflow_id": wf,
                "reason": "Test participant request",
                "goal": "Understand a real output",
            }
            for wf in WORKFLOWS[store.product]
        ],
    )
    change(store, "pair", teacher_thread_id="teacher", worker_thread_id="worker")


def evidence(store, phase, workflow=None):
    state = store.status()
    lesson = (
        state["session"]
        if isinstance(store, teaching.TeachingStore)
        else next(x for x in state["lessons"] if x["workflow_id"] == workflow)
    )
    folder = store.lesson_root(lesson)
    path = folder / f"{phase}.txt"
    path.write_text(f"Synthetic fixture output {phase}\n", encoding="utf-8")
    return change(
        store,
        phase,
        artifacts=[str(path)],
        execution_record=execution_record(store, phase, path, workflow),
        prompt="Mostrami il risultato",
        review="Fixture review; no professional certification",
        **({"workflow_id": workflow} if workflow else {}),
    )


def complete_onboarding(store):
    prepare(store)
    for wf in WORKFLOWS[store.product]:
        change(store, "start", workflow_id=wf)
        evidence(store, "demo", wf)
        evidence(store, "practice", wf)
        change(
            store,
            "finish",
            workflow_id=wf,
            confirmed_by_user=True,
            understanding="Synthetic participant identifies the input and the check",
        )


@pytest.mark.parametrize(
    "workflow", ["brand-fit", "hosted-interview", "research-video"]
)
@pytest.mark.parametrize("entry", ["onboarding", "repeat"])
def test_hosted_clara_lesson_is_rejected_without_changing_local_progress(
    tmp_path, workflow, entry
):
    store = onboarding.Store(tmp_path / "clara", plugin_root=ROOT / "plugins/clara")
    if entry == "repeat":
        complete_onboarding(store)
        session = teaching.TeachingStore(store.root, plugin_root=store.plugin_root)
    else:
        store.begin()
        change(store, "profile", profile=PROFILE, confirmed_by_user=True)
    before = store.path.read_bytes()

    with pytest.raises(onboarding.OnboardingError, match="requires hosted services"):
        if entry == "repeat":
            session.begin({"workflow_id": workflow, "title": "Try it", "goal": "Learn"})
        else:
            change(
                store,
                "plan",
                lessons=[
                    {"workflow_id": wf, "reason": "User request", "goal": "Learn"}
                    for wf in [workflow, "html-deck", "deck-correction"]
                ],
            )

    assert store.path.read_bytes() == before
    assert not (store.root / "lessons" / workflow).exists()
    if entry == "repeat":
        assert not session.sessions.exists()


def repeated(store, **extra):
    complete_onboarding(store)
    session = teaching.TeachingStore(store.root, plugin_root=store.plugin_root)
    session.begin(
        {
            "workflow_id": WORKFLOWS[store.product][0],
            "title": "Il mio esempio",
            "goal": "Capire il risultato",
            **extra,
        }
    )
    return session


def worker(store, state=None):
    state = state or store.status()["session"]
    return store.worker(
        "worker", state["workflow_id"], state.get("worker_token", "revoked")
    )


def test_first_use_existing_user_reload_and_profile_update(store):
    assert store.status()["phase"] == "required"
    assert not store.root.exists()
    complete_onboarding(store)
    original = store.status()
    assert original["phase"] == "complete"
    assert original["interview_notes"] == ""
    assert store.begin() == original
    change(
        store, "profile", profile={**PROFILE, "language": "fr"}, confirmed_by_user=True
    )
    result = subprocess.run(
        [
            sys.executable,
            str(store.plugin_root / "scripts/local_onboarding.py"),
            "status",
            "--state-root",
            str(store.root),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = json.loads(result.stdout)
    assert loaded["profile"]["language"] == "fr"
    assert loaded["lessons"] == original["lessons"]
    assert loaded["product"] == store.product
    assert (store.root / onboarding.MARKER).is_file()
    assert (store.root / ".mparanza-teaching-local-only").is_file()


def test_cross_product_state_and_recovery_are_rejected_without_overwrite(
    store, tmp_path
):
    store.begin()
    original = store.path.read_bytes()
    other = "lucia" if store.product == "clara" else "clara"
    foreign = onboarding.Store(store.root, plugin_root=ROOT / "plugins" / other)
    with pytest.raises(onboarding.OnboardingError, match="another product"):
        foreign.status()
    recovery = tmp_path / "copy.json"
    recovery.write_bytes(original)
    store.path.unlink()
    with pytest.raises(onboarding.OnboardingError, match="another product"):
        foreign.recover(recovery)
    assert not store.path.exists()
    assert store.recover(recovery)["revision"] == 2


@pytest.mark.parametrize(
    "data", [{}, {"profile": PROFILE}, {"confirmed_by_user": True, "profile": {}}]
)
def test_invalid_profile_never_advances(store, data):
    before = store.begin()
    with pytest.raises(onboarding.OnboardingError):
        store.change("profile", before["revision"], data)
    assert store.status() == before


def test_three_distinct_supported_lessons_stale_writer_and_real_confirmation(store):
    store.begin()
    change(store, "profile", profile=PROFILE, confirmed_by_user=True)
    for workflows in [
        WORKFLOWS[store.product][:2],
        [WORKFLOWS[store.product][0]] * 3,
        ["missing"] * 3,
    ]:
        with pytest.raises(onboarding.OnboardingError):
            change(
                store,
                "plan",
                lessons=[
                    {"workflow_id": w, "goal": "Try", "reason": "Test"}
                    for w in workflows
                ],
            )
    with pytest.raises(onboarding.OnboardingError, match="Stale"):
        store.change("notes", 1, {"notes": "Overwrite"})
    prepare(store)
    wf = WORKFLOWS[store.product][0]
    change(store, "start", workflow_id=wf)
    evidence(store, "demo", wf)
    with pytest.raises(onboarding.OnboardingError):
        change(
            store,
            "finish",
            workflow_id=wf,
            confirmed_by_user=True,
            understanding="No practice",
        )
    evidence(store, "practice", wf)
    with pytest.raises(onboarding.OnboardingError):
        change(store, "finish", workflow_id=wf, understanding="No user confirmation")


def test_repeated_show_library_fresh_session_and_profile_identity(store):
    session = repeated(store)
    original_profile = store.path.read_bytes()
    evidence(session, "demo")
    change(
        session,
        "finish",
        confirmed_by_user=True,
        understanding="Synthetic participant understands",
    )
    library = session.status()
    assert len(library["examples"]) == 4
    old = library["session"]
    with pytest.raises(onboarding.OnboardingError):
        worker(session, old)
    fresh = teaching.TeachingStore(store.root, plugin_root=store.plugin_root)
    fresh.begin(
        {
            "workflow_id": old["workflow_id"],
            "title": "Again",
            "goal": "Fresh actual result",
            "example_id": old["session_id"],
        }
    )
    assert fresh.status()["session"]["session_id"] != old["session_id"]
    assert "demo" not in fresh.status()["session"]
    assert store.path.read_bytes() == original_profile


def test_repeated_cannot_bypass_first_interview(store):
    session = teaching.TeachingStore(store.root, plugin_root=store.plugin_root)
    with pytest.raises(onboarding.OnboardingError, match="Repeated tutorial sessions"):
        session.begin(
            {"workflow_id": WORKFLOWS[store.product][0], "title": "Try", "goal": "Try"}
        )
    assert not store.root.exists()


def test_pause_repair_pair_focus_and_file_tampering(store):
    session = repeated(store, mode="together")
    old = session.status()["session"]
    assert worker(session)["local_only"]
    change(
        session,
        "checkpoint",
        next_step="Explain slowly",
        question="Why?",
        voice_preference="text_requested",
    )
    change(session, "pause", next_step="Wait for participant")
    with pytest.raises(onboarding.OnboardingError):
        worker(session, old)
    with pytest.raises(onboarding.OnboardingError):
        evidence(session, "demo")
    change(session, "resume", next_step="Continue")
    change(session, "pair", teacher_thread_id="teacher", worker_thread_id="replacement")
    with pytest.raises(onboarding.OnboardingError):
        worker(session)
    change(session, "pair", teacher_thread_id="teacher", worker_thread_id="worker")
    evidence(session, "demo")
    state = session.status()["session"]
    path = str(Path(state["directory"]) / "demo.txt")
    change(
        session,
        "focus",
        artifact="demo.txt",
        location="First line",
        host_result="queued",
        explanation="Source and output connected",
    )
    assert session.status()["session"]["focus"]["host_result"] == "queued"
    with pytest.raises(onboarding.OnboardingError):
        change(
            session, "finish", confirmed_by_user=True, understanding="Missing practice"
        )
    evidence(session, "practice")
    Path(path).write_text("Changed after review")
    with pytest.raises(onboarding.OnboardingError, match="changed"):
        change(
            session, "finish", confirmed_by_user=True, understanding="Stale evidence"
        )


def test_selected_files_scope_and_application(store, tmp_path):
    session = repeated(store, mode="together")
    evidence(session, "demo")
    selected = tmp_path / "selected.txt"
    selected.write_text("Selected real-work input")
    destination = tmp_path / "professional-output"
    destination.mkdir()
    change(
        session,
        "use-files",
        sources=[str(selected)],
        destination=str(destination),
        selected_by_user=True,
        goal="Apply to selected files",
    )
    assert not worker(session)["local_only"]
    state = session.status()["session"]
    with pytest.raises(onboarding.OnboardingError, match="normal real-work"):
        cases.prepare_case(
            session,
            thread_id="worker",
            workflow=state["workflow_id"],
            token=state["worker_token"],
            sources=[selected],
            phase="demo",
        )
    result = destination / "actual.txt"
    result.write_text("Actual reviewed output")
    change(
        session,
        "application",
        artifacts=[str(result)],
        execution_record=execution_record(session, "application", result),
        prompt="Use my files",
        review="Actual selected-source review",
    )
    change(
        session,
        "finish",
        confirmed_by_user=True,
        understanding="Synthetic user confirms",
    )
    assert result.exists()
    assert session.status()["session"]["phase"] == "complete"


def test_case_adapter_uses_real_native_product_input_contract(store):
    prepare(store)
    wf = WORKFLOWS[store.product][0]
    change(store, "start", workflow_id=wf)
    lesson = store.status()["lessons"][0]
    source = (
        store.plugin_root
        / "assets/onboarding"
        / ("actual-budget.xlsx" if store.product == "clara" else "matter-brief.md")
    )
    result = cases.prepare_case(
        store,
        thread_id="worker",
        workflow=wf,
        token=lesson["worker_token"],
        phase="demo",
        sources=[source],
    )
    assert result["local_only"] and result["workflow_id"] == wf
    assert Path(result["output_dir"]).is_relative_to(store.root)
    if store.product == "clara":
        assert result["status"] == "prepared"
        assert Path(result["inputs"][0]["path"]).read_bytes() == source.read_bytes()
    else:
        assert Path(result["context_path"]).is_file()
        assert result["run"]["status"] == "running"
    with pytest.raises(onboarding.OnboardingError):
        cases.prepare_case(
            store,
            thread_id="wrong",
            workflow=wf,
            token=lesson["worker_token"],
            phase="demo",
            sources=[source],
        )


def test_corruption_lock_and_symlink_are_not_new_enrollment(store, tmp_path):
    store.begin()
    old = store.path.read_bytes()
    store.path.write_text("corrupt")
    with pytest.raises(onboarding.OnboardingError):
        store.begin()
    store.path.write_bytes(old)
    (store.root / ".saving").mkdir()
    with pytest.raises(onboarding.OnboardingError, match="Another save"):
        change(store, "notes", notes="Do not overwrite")
    assert store.path.read_bytes() == old
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(store.root, target_is_directory=True)
    except OSError:
        pytest.skip("Host disallows symlinks")
    with pytest.raises(onboarding.OnboardingError, match="symlink"):
        onboarding.Store(linked, plugin_root=store.plugin_root)


def test_cli_first_use_recovery_and_worker_contract(store, tmp_path, capsys):
    base = ["--state-root", str(store.root)]
    invoke = lambda args: onboarding.main([*args, *base], plugin_root=store.plugin_root)
    assert invoke(["status"]) == 0
    assert invoke(["begin"]) == 0
    data = tmp_path / "unicode.json"
    data.write_text(json.dumps({"notes": "Conversazione: perché?"}))
    assert invoke(["notes", "--revision", "1", "--input", str(data)]) == 0
    assert invoke(["notes"]) == 2
    assert invoke(["worker"]) == 2
    assert invoke(["recover"]) == 2
    recovery = tmp_path / "saved.json"
    recovery.write_bytes(store.path.read_bytes())
    store.path.unlink()
    assert invoke(["recover", "--input", str(recovery)]) == 0
    prepare(store)
    wf = WORKFLOWS[store.product][0]
    change(store, "start", workflow_id=wf)
    token = store.status()["lessons"][0]["worker_token"]
    assert (
        invoke(["worker", "--thread-id", "worker", "--workflow", wf, "--token", token])
        == 0
    )
    change(store, "pause", workflow_id=wf, next_step="Return to output")
    assert (
        invoke(["worker", "--thread-id", "worker", "--workflow", wf, "--token", token])
        == 2
    )
    change(store, "checkpoint", workflow_id=wf, next_step="Explain the first row")
    change(store, "resume", workflow_id=wf, next_step="Resume")
    change(store, "feedback", feedback="Synthetic local feedback")
    assert "Conversazione" in capsys.readouterr().out


def test_cli_repeated_session_recovery_and_token_rotation(store, tmp_path, capsys):
    complete_onboarding(store)
    base = ["--state-root", str(store.root)]
    invoke = lambda args: teaching.main([*args, *base], plugin_root=store.plugin_root)
    data = tmp_path / "session-input.json"
    data.write_text(
        json.dumps(
            {
                "workflow_id": WORKFLOWS[store.product][0],
                "title": "Un esempio",
                "goal": "Capire",
            }
        )
    )
    assert invoke(["status"]) == 0
    assert invoke(["begin"]) == 2
    assert invoke(["begin", "--input", str(data)]) == 0
    overview = teaching.TeachingStore(
        store.root, plugin_root=store.plugin_root
    ).status()
    sid = overview["active_session"]
    session = teaching.TeachingStore(store.root, sid, plugin_root=store.plugin_root)
    state = session.status()["session"]
    assert invoke(["worker", "--session", sid]) == 2
    assert (
        invoke(
            [
                "worker",
                "--session",
                sid,
                "--thread-id",
                "worker",
                "--workflow",
                state["workflow_id"],
                "--token",
                state["worker_token"],
            ]
        )
        == 0
    )
    data.write_text(json.dumps({"next_step": "Riprendi qui"}))
    assert invoke(["pause", "--session", sid, "--input", str(data)]) == 2
    assert (
        invoke(
            [
                "pause",
                "--session",
                sid,
                "--revision",
                str(state["revision"]),
                "--input",
                str(data),
            ]
        )
        == 0
    )
    checkpoint = tmp_path / "checkpoint.json"
    target = session.sessions / sid / "session.json"
    checkpoint.write_bytes(target.read_bytes())
    target.unlink()
    assert invoke(["recover", "--session", sid, "--input", str(checkpoint)]) == 0
    restored = session.status()["session"]
    assert (
        restored["phase"] == "paused"
        and restored["worker_token"] != state["worker_token"]
    )
    assert invoke(["recover", "--session", sid, "--input", str(checkpoint)]) == 2
    assert "Riprendi" in capsys.readouterr().out


def test_case_cli_and_practice_preconditions(store, capsys):
    prepare(store)
    wf = WORKFLOWS[store.product][0]
    change(store, "start", workflow_id=wf)
    lesson = store.status()["lessons"][0]
    source = next((store.plugin_root / "assets/onboarding").glob("*.md"))
    args = [
        "--state-root",
        str(store.root),
        "--thread-id",
        "worker",
        "--workflow",
        wf,
        "--token",
        lesson["worker_token"],
        "--source",
        str(source),
    ]
    assert (
        cases.main([*args, "--phase", "practice"], plugin_root=store.plugin_root) == 2
    )
    assert cases.main([*args, "--phase", "demo"], plugin_root=store.plugin_root) == 0
    evidence(store, "demo", wf)
    assert (
        cases.main([*args, "--phase", "practice"], plugin_root=store.plugin_root) == 0
    )
    assert "local_only" in capsys.readouterr().out


def test_startup_suppresses_network_while_pending_active_or_corrupt(
    store, monkeypatch, capsys
):
    import types

    calls = []
    monkeypatch.setitem(
        sys.modules,
        "local_onboarding",
        types.SimpleNamespace(
            OnboardingError=onboarding.OnboardingError, Store=lambda: store
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "local_teaching",
        types.SimpleNamespace(
            TeachingStore=lambda: teaching.TeachingStore(
                store.root, plugin_root=store.plugin_root
            )
        ),
    )

    def check(*, include_change_requests):
        calls.append(include_change_requests)
        return {"hookSpecificOutput": {"additionalContext": "Public version checked."}}

    monkeypatch.setitem(
        sys.modules,
        "check_for_update",
        types.SimpleNamespace(session_start_output=check),
    )
    spec = importlib.util.spec_from_file_location(
        "tested_startup", store.plugin_root / "scripts/onboarding_session_start.py"
    )
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    assert hook.main() == 0
    assert calls == ([False] if store.product == "clara" else [])
    complete_onboarding(store)
    assert hook.main() == 0
    expected = [False, True] if store.product == "clara" else []
    assert calls == expected
    session = teaching.TeachingStore(store.root, plugin_root=store.plugin_root)
    session.begin(
        {"workflow_id": WORKFLOWS[store.product][0], "title": "Tutorial", "goal": "Try"}
    )
    assert hook.main() == 0
    expected = [False, True, False] if store.product == "clara" else []
    assert calls == expected
    (session.sessions / session.session_id / "session.json").write_text("broken")
    assert hook.main() == 0
    expected = [False, True, False, False] if store.product == "clara" else []
    assert calls == expected
    assert "Consulenza" not in capsys.readouterr().out


def test_os_user_locations_are_distinct_and_independent_of_version(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(onboarding.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(onboarding.sys, "platform", "darwin")
    assert (
        onboarding.default_root("clara") == tmp_path / ".local/share/clara/onboarding"
    )
    assert (
        onboarding.default_root("lucia") == tmp_path / ".local/share/lucia/onboarding"
    )
    monkeypatch.setattr(onboarding.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert onboarding.default_root("clara") == tmp_path / "Clara/onboarding"
    assert onboarding.default_root("lucia") == tmp_path / "Lucia/onboarding"


def test_lucia_website_prepares_project_without_a_false_ledger_context(tmp_path):
    store = onboarding.Store(tmp_path / "lucia", plugin_root=ROOT / "plugins/lucia")
    prepare(store)
    workflow = "presenza-digitale-studio"
    change(
        store,
        "plan",
        lessons=[
            {
                "workflow_id": wf,
                "reason": "Fictional website fixture",
                "goal": "Verify the selected intake",
            }
            for wf in (workflow, "apertura-pratica", "comunicazione-professionale")
        ],
    )
    state = change(store, "start", workflow_id=workflow)
    lesson = next(item for item in state["lessons"] if item["workflow_id"] == workflow)
    source = tmp_path / "studio.md"
    source.write_text("Fictional law firm for local website work.")
    result = cases.prepare_case(
        store,
        thread_id="worker",
        workflow=workflow,
        token=lesson["worker_token"],
        sources=[source],
        phase="demo",
    )
    assert result["status"] == "prepared"
    assert "context_path" not in result
    assert Path(result["inputs"][0]["path"]).read_bytes() == source.read_bytes()
    assert Path(result["output_dir"]).is_relative_to(store.root)
    assert not (Path(result["directory"]) / "Vera").exists()
