from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from modules.hosted_interviews import api, job_state


def test_worker_death_cleans_assembled_audio_on_inspection_preserving_original(
    tmp_path: Path,
) -> None:
    original = tmp_path / "chunk-000000.webm"
    original.write_bytes(b"synthetic original audio")
    script = """
import os, sys
from pathlib import Path
from modules.hosted_interviews import api, job_state
directory = Path(sys.argv[1])
(directory / "completed.json").write_text("{}")
api._audio_files_for_session = lambda _: [{'file_name':'chunk-000000.webm', 'relative_path':'chunk-000000.webm', 'content_type':'audio/webm'}]
api._resolve_openai_api_key = lambda: 'synthetic-no-network'
api._hosted_interview_transcription_context = lambda _: 'synthetic'
def crash(**kwargs):
    assert kwargs['audio_path'].read_bytes() == b'synthetic original audio'
    os._exit(23)
api.create_audio_transcription = crash
job_state.queue_job(directory, attempt_id='synthetic', stage='transcription_then_review')
job_state.run_job(directory, lambda: api._transcribe_interviewee_audio_chunks(record={'token_hash':'synthetic'}, session_dir=directory), lock=api._try_post_completion_task_lock)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], check=False, timeout=20
    )
    workspace = tmp_path / job_state.AUDIO_WORK_DIRECTORY
    assert child.returncode == 23
    assert list(workspace.rglob("*.webm"))

    state = job_state.inspect_job(tmp_path, lock=api._try_post_completion_task_lock)

    assert state["status"] == "interrupted"
    assert not workspace.exists()
    assert original.read_bytes() == b"synthetic original audio"


def test_active_worker_inspection_preserves_assembly_then_completion_cleans_it(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / job_state.AUDIO_WORK_DIRECTORY
    observed = []

    def active_work() -> None:
        workspace.mkdir()
        audio = workspace / "assembled.webm"
        audio.write_bytes(b"active audio")
        state = job_state.inspect_job(tmp_path, lock=api._try_post_completion_task_lock)
        observed.append((state["status"], audio.read_bytes()))

    job_state.queue_job(tmp_path, attempt_id="synthetic", stage="transcription")
    job_state.run_job(tmp_path, active_work, lock=api._try_post_completion_task_lock)

    assert observed == [("running", b"active audio")]
    assert not workspace.exists()


def test_audio_cleanup_failure_does_not_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / job_state.AUDIO_WORK_DIRECTORY
    workspace.mkdir()
    (workspace / "assembled.webm").write_bytes(b"retained pending cleanup")
    job_state.queue_job(tmp_path, attempt_id="synthetic", stage="transcription")

    def denied(path: Path) -> None:
        raise PermissionError("synthetic cleanup denial")

    monkeypatch.setattr(job_state.shutil, "rmtree", denied)

    with pytest.raises(PermissionError, match="synthetic cleanup denial"):
        job_state.inspect_job(tmp_path, lock=api._try_post_completion_task_lock)

    assert (workspace / "assembled.webm").exists()


def test_audio_workspace_symlink_cannot_delete_another_directory(
    tmp_path: Path,
) -> None:
    session = tmp_path / "session"
    session.mkdir()
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    sentinel = unrelated / "keep.txt"
    sentinel.write_text("preserve")
    (session / job_state.AUDIO_WORK_DIRECTORY).symlink_to(
        unrelated, target_is_directory=True
    )

    with pytest.raises(OSError, match="symbolic link"):
        job_state.inspect_job(session, lock=api._try_post_completion_task_lock)

    assert sentinel.read_text() == "preserve"


def test_post_call_review_process_death_preserves_saved_transcript_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    token, record = api.create_prepared_interview(
        api.PreparedInterviewRequest(
            interview_campaign_id=api.PLUGIN_IMPROVEMENT_CAMPAIGN_ID
        )
    )
    record["interview_mode"] = api.INTERVIEW_MODE_CASE
    api._save_record_for_token(token, record)
    directory = api._session_dir(token)
    completion = {
        "completion_status": api.INTERVIEW_STATUS_COMPLETED,
        "user_transcript": "Synthetic saved interview evidence.",
        "audio_chunks": 0,
    }
    api._write_json(api._completion_path(directory), completion)
    saved_bytes = api._completion_path(directory).read_bytes()
    script = """
import os, sys
from pathlib import Path
from modules.hosted_interviews import api, job_state
token = sys.argv[1]
directory = api._session_dir(token)
def exit_during_review(**kwargs):
    assert kwargs['completion']['user_transcript'] == 'Synthetic saved interview evidence.'
    (directory / 'provider-calls.txt').write_text('one review call')
    os._exit(23)
api._resolve_openai_api_key = lambda: 'synthetic-no-network'
api._generate_interview_quality_review = exit_during_review
api._send_completion_notification = lambda *args: None
job_state.queue_job(directory, attempt_id='synthetic', stage='transcription_then_review')
api._run_interview_post_completion_task(token)
"""

    child = subprocess.run(
        [sys.executable, "-c", script, token], check=False, timeout=20
    )
    response = api.public_interview_status(token)

    # A repeated dispatch must honor the interrupted terminal state.
    def reject_replayed_review(**kwargs: object) -> None:
        pytest.fail("Interrupted review must not trigger another provider call")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "synthetic-no-network")
    monkeypatch.setattr(
        api, "_generate_interview_quality_review", reject_replayed_review
    )
    api._run_interview_post_completion_task(token)

    assert child.returncode == 23
    assert json.loads(response.body)["post_completion"]["status"] == "interrupted"
    assert api._completion_path(directory).read_bytes() == saved_bytes
    assert (directory / "provider-calls.txt").read_text() == "one review call"
    assert not api._review_path(directory).exists()


@pytest.mark.parametrize("stage", ["queued", "running"])
def test_public_status_reports_process_death_without_replaying_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    token, record = api.create_prepared_interview(
        api.PreparedInterviewRequest(
            interview_campaign_id=api.PLUGIN_IMPROVEMENT_CAMPAIGN_ID
        )
    )
    directory = api._session_dir(token)
    script = """
import os, sys
from pathlib import Path
from modules.hosted_interviews import api, job_state
path = Path(sys.argv[1])
job_state.queue_job(path, attempt_id='synthetic', stage='transcription_then_review')
if sys.argv[2] == 'running':
    job_state.run_job(path, lambda: os._exit(23), lock=api._try_post_completion_task_lock)
os._exit(23)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(directory), stage], check=False, timeout=20
    )
    assert child.returncode == 23

    response = api.public_interview_status(token)

    progress = json.loads(response.body)["post_completion"]
    assert progress["status"] == "interrupted"
    assert "no automatic retry" in progress["message"]
    assert "owner_pid" not in progress
    assert "owner_host" not in progress
    assert not (directory / "review.json").exists()


def test_completed_job_does_not_repeat_provider_work(tmp_path: Path) -> None:
    job_state.queue_job(tmp_path, attempt_id="synthetic", stage="quality_review")
    calls = []
    job_state.run_job(
        tmp_path,
        lambda: calls.append("provider"),
        lock=api._try_post_completion_task_lock,
    )

    repeated = job_state.run_job(
        tmp_path,
        lambda: calls.append("provider"),
        lock=api._try_post_completion_task_lock,
    )

    assert repeated is False
    assert calls == ["provider"]
    assert (
        job_state.inspect_job(tmp_path, lock=api._try_post_completion_task_lock)[
            "status"
        ]
        == "completed"
    )


def test_status_does_not_interrupt_a_worker_holding_the_lock(tmp_path: Path) -> None:
    job_state.queue_job(tmp_path, attempt_id="synthetic", stage="quality_review")
    observed = []

    job_state.run_job(
        tmp_path,
        lambda: observed.append(
            job_state.inspect_job(tmp_path, lock=api._try_post_completion_task_lock)[
                "status"
            ]
        ),
        lock=api._try_post_completion_task_lock,
    )

    assert observed == ["running"]


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(
    "job_status,copy_key",
    [
        ("interrupted", "post_processing_interrupted"),
        ("running", "post_processing_pending"),
    ],
)
def test_output_template_shows_processing_state_and_saved_transcript(
    language: str, job_status: str, copy_key: str
) -> None:
    template_path = (
        Path(__file__).resolve().parents[3] / "templates/hosted_interview_output.html"
    )
    copy = api.HOSTED_INTERVIEW_OUTPUT_COPY[language]

    context = dict(
        output_language=language,
        copy=copy,
        record={},
        completion={"user_transcript": "Saved interview evidence"},
        review={},
        review_error={},
        post_completion={"status": job_status},
        value_labels={},
        dialog_turns=[{"speaker": "interviewee", "text": "Saved interview evidence"}],
        event_count=0,
        audio_chunk_count=0,
        bundle_url="/bundle",
        review_url="/review",
        error_message="",
    )

    # The repository conftest stubs Jinja; use a clean interpreter for real rendering.
    script = "import json, sys; from pathlib import Path; from jinja2 import Environment; sys.stdout.write(Environment(autoescape=True).from_string(Path(sys.argv[1]).read_text()).render(**json.load(sys.stdin)))"
    rendered = subprocess.run(
        [sys.executable, "-c", script, str(template_path)],
        input=json.dumps(context),
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    html = rendered.stdout

    assert copy[copy_key] in html
    assert "Saved interview evidence" in html
