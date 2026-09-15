from __future__ import annotations

import csv
import json
import subprocess
import sys
import types
from pathlib import Path
from zipfile import ZipFile

import pytest
from test_vera_local_onboarding import ROOT, SCRIPTS, change, finish, load, prepare


@pytest.fixture
def teaching(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    onboarding = load("local_onboarding")
    monkeypatch.setitem(sys.modules, "local_onboarding", onboarding)
    module = load("local_teaching")
    monkeypatch.setitem(sys.modules, "local_teaching", module)
    profile = onboarding.Store(tmp_path / "professional")
    prepare(profile)
    finish(profile, "fatture-xml-check")
    finish(profile, "journal-sampling")
    finish(profile, "variance-analysis")
    return module, module.TeachingStore(profile.root), profile


def begin(store, **extra):
    return store.begin(
        {
            "workflow_id": "fatture-xml-check",
            "title": "Controllo XML",
            "goal": "Capire i controlli e i limiti",
            **extra,
        }
    )["session"]


def update(store, action, **data):
    return store.change(action, store.status()["session"]["revision"], data)["session"]


def output(store, phase="demo", **extra):
    directory = Path(store.status()["session"]["directory"])
    result = directory / f"{phase}.csv"
    result.write_text(f"amount\n{1220 if phase == 'demo' else 2440}\n")
    return update(
        store,
        phase,
        artifacts=[result.name],
        prompt="Controlla le fatture",
        review="Totale confrontato con l'input; nessuna certificazione fiscale",
        **extra,
    )


def complete(store):
    return update(
        store,
        "finish",
        confirmed_by_user=True,
        understanding="Il partecipante fittizio della prova ha indicato input e controlli",
    )


def test_repeated_examples_keep_completed_onboarding_and_reload_latest_profile(
    teaching,
):
    module, store, profile = teaching
    before = profile.path.read_bytes()
    state = begin(store, example_id="onboarding:fatture-xml-check")
    output(store)
    complete(store)
    original = module.TeachingStore(store.root, state["session_id"]).status()["session"]
    again = begin(store, example_id=state["session_id"])
    assert again["session_id"] != original["session_id"]
    assert "demo" not in again
    assert again["pair"] == original["pair"]
    assert again["voice_preference"] == "native_voice"
    assert profile.path.read_bytes() == before
    changed = {**profile.status()["profile"], "language": "fr"}
    change(profile, "profile", confirmed_by_user=True, profile=changed)
    assert (
        store.worker("native-worker", "fatture-xml-check", again["worker_token"])[
            "profile"
        ]["language"]
        == "fr"
    )
    assert len(store.status()["examples"]) == 5


def test_repeated_tutorial_requires_introduction_without_automatically_enrolling(
    teaching, tmp_path
):
    module, _, profile = teaching
    other = module.TeachingStore(tmp_path / "first-use")
    assert other.status()["onboarding_phase"] == "required"
    with pytest.raises(ValueError):
        begin(other)
    assert not other.enrollment.exists()
    assert profile.status()["phase"] == "complete"


def test_pause_resume_pair_replacement_and_stale_writer_are_bounded(teaching):
    module, store, _ = teaching
    state = begin(store)
    old_token = state["worker_token"]
    paused = update(
        store, "pause", next_step="Attendere il risultato già in esecuzione"
    )
    with pytest.raises(ValueError, match="active paired"):
        store.worker("native-worker", "fatture-xml-check", old_token)
    with pytest.raises(ValueError, match="paused"):
        output(store)
    replacement = update(
        store, "pair", teacher_thread_id="teacher-2", worker_thread_id="worker-2"
    )
    checkpoint = update(
        store,
        "checkpoint",
        next_step="Spiegare la riga 2",
        question="Perché questo importo?",
        voice_preference="text_requested",
    )
    resumed = update(store, "resume", next_step=checkpoint["checkpoint"])
    assert (
        resumed["worker_token"] != replacement["worker_token"] != paused["worker_token"]
    )
    assert (
        store.worker("worker-2", "fatture-xml-check", resumed["worker_token"])[
            "local_only"
        ]
        is True
    )
    with pytest.raises(ValueError, match="Stale revision"):
        store.change("feedback", state["revision"], {"feedback": "stale"})
    other = module.TeachingStore(store.root)
    with pytest.raises(ValueError, match="active teaching"):
        begin(other)
    update(store, "pause", next_step="Riprendere la riga 2")
    begin(other)
    with pytest.raises(ValueError, match="other active"):
        update(store, "resume", next_step="Riprendere")


@pytest.mark.parametrize(
    "thread,workflow,token",
    [
        ("wrong", "fatture-xml-check", None),
        ("native-worker", "variance-analysis", None),
        ("native-worker", "fatture-xml-check", "wrong"),
    ],
)
def test_unrelated_worker_workflow_and_revoked_token_do_not_run(
    teaching, thread, workflow, token
):
    _, store, _ = teaching
    state = begin(store)
    with pytest.raises(ValueError, match="active paired"):
        store.worker(thread, workflow, token or state["worker_token"])


def test_focus_links_to_verified_actual_result_and_preserves_queued_visibility(
    teaching,
):
    _, store, _ = teaching
    begin(store)
    output(store)
    state = update(
        store,
        "focus",
        result="demo",
        artifact="demo.csv",
        location="riga 2",
        explanation="Il totale viene dall'XML",
        host_result="queued",
    )
    assert state["focus"]["host_result"] == "queued"
    Path(state["directory"], "demo.csv").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        update(
            store,
            "focus",
            result="demo",
            artifact="demo.csv",
            location="riga 2",
            explanation="Vecchio dato",
            host_result="opened",
        )
    with pytest.raises(ValueError, match="changed"):
        complete(store)


def test_guided_mode_requires_user_attempt_and_completion_revokes_worker(teaching):
    _, store, _ = teaching
    begin(store, mode="together")
    output(store)
    with pytest.raises(ValueError, match="guided attempt"):
        complete(store)
    with pytest.raises(ValueError, match="distinct"):
        update(store, "practice", artifacts=["demo.csv"], prompt="Same", review="Same")
    state = output(store, "practice")
    complete(store)
    with pytest.raises(ValueError, match="active paired"):
        store.worker("native-worker", "fatture-xml-check", state["worker_token"])
    with pytest.raises(ValueError, match="fresh session"):
        update(store, "resume", next_step="repeat")
    assert (
        update(store, "feedback", feedback="Utile, grazie")["feedback"]
        == "Utile, grazie"
    )


def test_selected_user_files_switch_scope_and_real_result_is_preserved(
    teaching, tmp_path
):
    _, store, _ = teaching
    start = begin(store, mode="together")
    output(store)
    source = tmp_path / "selected.xml"
    source.write_text("user-selected synthetic acceptance input")
    destination = tmp_path / "professional-work"
    destination.mkdir()
    real = update(
        store,
        "use-files",
        selected_by_user=True,
        sources=[str(source)],
        destination=str(destination),
        goal="Controllare i documenti scelti",
    )
    with pytest.raises(ValueError, match="active paired"):
        store.worker("native-worker", "fatture-xml-check", start["worker_token"])
    handoff = store.worker("native-worker", "fatture-xml-check", real["worker_token"])
    assert handoff["local_only"] is False
    assert handoff["assignment"] == "professional"
    adapter = load("local_onboarding_case")
    with pytest.raises(ValueError, match="normal real-work"):
        adapter.prepare_case(
            store,
            thread_id="native-worker",
            workflow="fatture-xml-check",
            token=real["worker_token"],
            phase="practice",
            sources=[source],
        )
    with pytest.raises(ValueError):
        complete(store)
    reviewed = destination / "review.md"
    reviewed.write_text("Reviewed result with limits and professional checks")
    result = update(
        store,
        "application",
        artifacts=[str(reviewed)],
        prompt="Il mio controllo",
        review="Fonti e conclusioni riviste",
    )
    assert result["application"]["artifacts"][0]["path"] == "review.md"
    complete(store)
    assert reviewed.read_text().startswith("Reviewed result")
    assert not (destination / ".vera-onboarding-local-only").exists()


def test_real_work_rechecks_source_identity_and_rejects_outside_output(
    teaching, tmp_path
):
    _, store, _ = teaching
    begin(store)
    output(store)
    source = tmp_path / "source.csv"
    source.write_text("amount\n10\n")
    destination = tmp_path / "real-work"
    destination.mkdir()
    state = update(
        store,
        "use-files",
        selected_by_user=True,
        sources=[str(source)],
        destination=str(destination),
        goal="Controllare",
    )
    with pytest.raises(ValueError, match="inside this lesson"):
        update(
            store, "application", artifacts=[str(source)], prompt="Test", review="Test"
        )
    source.write_text("amount\n20\n")
    with pytest.raises(ValueError, match="source changed"):
        store.worker("native-worker", "fatture-xml-check", state["worker_token"])
    with pytest.raises(ValueError, match="retain the tutorial"):
        output(store, "practice")


def test_teaching_worker_executes_real_managed_xml_pipeline(teaching):
    _, store, _ = teaching
    state = begin(store)
    adapter = load("local_onboarding_case")
    case = adapter.prepare_case(
        store,
        thread_id="native-worker",
        workflow="fatture-xml-check",
        token=state["worker_token"],
        sources=[ROOT / "plugins/vera/assets/onboarding/invoice.xml"],
        phase="demo",
    )
    destination = Path(case["output_dir"]) / "fatture"
    run = subprocess.run(
        [
            sys.executable,
            str(
                ROOT / "plugins/client-file-preparation/scripts/parse_fatturapa_xml.py"
            ),
            case["context"]["input_dir"],
            "--year",
            "2026",
            "--out",
            str(destination),
            "--client-engagement",
            case["context_path"],
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    with (destination / "fatture_summary.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["total_amount"] == "1220.00"
    assert rows[0]["invoice_number"] == "DEMO-001"
    update(
        store,
        "demo",
        artifacts=[str(destination / "fatture_summary.csv")],
        prompt="Controlla questa fattura",
        review="1.000 imponibile + 220 IVA = 1.220; verifica documentale ancora professionale",
    )
    assert complete(store)["phase"] == "complete"


def test_hook_suppresses_optional_network_for_active_or_corrupt_teaching(
    teaching, monkeypatch, capsys
):
    _, store, profile = teaching
    onboarding = sys.modules["local_onboarding"]
    monkeypatch.setattr(onboarding, "default_root", lambda: profile.root)
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "check_for_update",
        types.SimpleNamespace(main=lambda: calls.append("update") or 0),
    )
    hook = load("onboarding_session_start")
    assert hook.main() == 0
    assert calls == ["update"]
    begin(store)
    assert hook.main() == 0
    assert calls == ["update"]
    path = store.sessions / store.session_id / "session.json"
    path.write_text("broken")
    assert hook.main() == 0
    assert calls == ["update"]
    assert "profile" not in json.loads(capsys.readouterr().out.splitlines()[-1])


def test_recovery_retains_old_files_and_revokes_prior_token(teaching):
    module, store, profile = teaching
    original = begin(store)
    output(store)
    path = store.sessions / store.session_id / "session.json"
    path.rename(path.with_name("damaged-session.json"))
    with pytest.raises(ValueError):
        store.status()
    recovered = store.recover_session(path.with_name("session.previous.json"))[
        "session"
    ]
    assert recovered["phase"] == "paused"
    assert recovered["worker_token"] != original["worker_token"]
    assert profile.status()["phase"] == "complete"
    assert Path(recovered["directory"], "demo.csv").is_file()
    with pytest.raises(ValueError, match="Preserve"):
        store.recover_session(path.with_name("session.previous.json"))
    with pytest.raises(ValueError):
        module.TeachingStore(store.root, "../escape")


@pytest.mark.parametrize(
    "data",
    [
        {"workflow_id": "invented"},
        {"workflow_id": "learn-with-vera"},
        {"mode": "automatic"},
        {"title": ""},
        {"example_id": "missing"},
    ],
)
def test_invalid_new_session_does_not_damage_profile(teaching, data):
    _, store, profile = teaching
    before = profile.path.read_bytes()
    with pytest.raises(ValueError):
        begin(store, **data)
    assert profile.path.read_bytes() == before
    assert store.status()["active_session"] is None


@pytest.mark.parametrize(
    "action,data",
    [
        ("pair", {"teacher_thread_id": "same", "worker_thread_id": "same"}),
        ("checkpoint", {"next_step": "next", "voice_preference": "api"}),
        ("finish", {"confirmed_by_user": False}),
        ("focus", {"result": "missing"}),
        ("focus", {"result": "demo", "artifact": "missing"}),
        ("focus", {"result": "demo", "artifact": "demo.csv", "host_result": "guessed"}),
        ("application", {"artifacts": ["demo.csv"]}),
        ("use-files", {"selected_by_user": False}),
        ("invented", {}),
    ],
)
def test_invalid_transitions_preserve_checkpoint(teaching, action, data):
    _, store, _ = teaching
    begin(store)
    output(store)
    before = store.status()["session"]
    with pytest.raises(ValueError):
        update(store, action, **data)
    assert store.status()["session"] == before


def test_cli_unicode_separate_process_and_invalid_input(teaching, tmp_path, capsys):
    module, store, _ = teaching
    data = tmp_path / "request.json"
    data.write_text(
        json.dumps(
            {
                "workflow_id": "fatture-xml-check",
                "title": "Perché l’IVA?",
                "goal": "Capire",
            }
        )
    )
    base = ["--state-root", str(store.root)]
    assert module.main(["begin", *base, "--input", str(data)]) == 0
    state = json.loads(capsys.readouterr().out)["session"]
    args = [*base, "--session", state["session_id"]]
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "local_teaching.py"), "status", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["session"]["title"] == "Perché l’IVA?"
    assert module.main(["worker", *args]) == 2
    capsys.readouterr()
    assert (
        module.main(
            [
                "worker",
                *args,
                "--thread-id",
                "native-worker",
                "--workflow",
                "fatture-xml-check",
                "--token",
                state["worker_token"],
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert module.main(["pause", *args]) == 2
    capsys.readouterr()
    data.write_text(json.dumps({"next_step": "Riprendere da qui"}))
    assert module.main(["pause", *args, "--input", str(data)]) == 2
    capsys.readouterr()
    assert (
        module.main(
            ["pause", *args, "--revision", str(state["revision"]), "--input", str(data)]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["session"]["phase"] == "paused"


def test_openai_packages_include_teaching_and_cowork_omits_it():
    source = (SCRIPTS / "local_teaching.py").read_bytes()
    for name, prefix in [
        ("vera-plugin.zip", "vera-codex-plugin/plugins/vera/"),
        ("vera-chatgpt-upload.zip", ""),
    ]:
        with ZipFile(ROOT / "plugin_packages/vera" / name) as archive:
            assert archive.read(prefix + "scripts/local_teaching.py") == source
            assert prefix + "skills/learn-with-vera/SKILL.md" in archive.namelist()
    with ZipFile(ROOT / "plugin_packages/vera/vera-claude-plugin.zip") as archive:
        assert not any(
            "learn-with-vera" in name or "local_teaching" in name
            for name in archive.namelist()
        )
        router = archive.read("skills/vera/SKILL.md").decode()
        assert "learn-with-vera" not in router
        catalog = archive.read("skills/vera/references/workflow-catalog.md").decode()
        registry = archive.read(
            "skills/vera/references/workflow-registry.json"
        ).decode()
        assert "learn-with-vera" not in catalog
        assert "learn-with-vera" not in registry


def test_first_onboarding_pause_retains_progress_and_revokes_worker(teaching, tmp_path):
    _, _, _profile = teaching
    onboarding = sys.modules["local_onboarding"]
    profile = onboarding.Store(tmp_path / "onboarding-pause")
    prepare(profile)
    state = change(profile, "start", workflow_id="fatture-xml-check")
    token = state["lessons"][0]["worker_token"]
    paused = change(
        profile,
        "pause",
        workflow_id="fatture-xml-check",
        next_step="Spiegare il totale appena prodotto",
    )
    with pytest.raises(ValueError, match="current paired"):
        profile.worker("native-worker", "fatture-xml-check", token)
    with pytest.raises(ValueError, match="paused"):
        change(
            profile,
            "finish",
            workflow_id="fatture-xml-check",
            confirmed_by_user=True,
            understanding="Not completed",
        )
    change(
        profile,
        "checkpoint",
        workflow_id="fatture-xml-check",
        next_step="Rispondere alla domanda prima di continuare",
    )
    resumed = change(
        profile,
        "resume",
        workflow_id="fatture-xml-check",
        next_step="Continuare con il controllo dell'IVA",
    )
    assert (
        profile.worker(
            "native-worker", "fatture-xml-check", resumed["lessons"][0]["worker_token"]
        )["local_only"]
        is True
    )
    assert len(resumed["lessons"]) == 3
    assert resumed["lessons"][0]["worker_token"] != paused["lessons"][0]["worker_token"]
