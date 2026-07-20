from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import BackgroundTasks, HTTPException

from modules.auth.session import AuthenticatedUser
from modules.case_notes_voice import api
from modules.openai_realtime import RealtimeCallResult

ROOT = Path(__file__).resolve().parents[3]


def _patch_voice_retention_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    """Keep every Hosted Voice storage class isolated in one test directory."""

    roots = {
        "jobs": tmp_path / "voice-jobs",
        "sources": tmp_path / "voice-sources",
        "chunks": tmp_path / "voice-chunks",
        "work": tmp_path / "voice-work",
        "locks": tmp_path / "voice-locks",
    }
    for root in roots.values():
        root.mkdir(parents=True)
    monkeypatch.setattr(api, "_upload_job_root", lambda: roots["jobs"])
    monkeypatch.setattr(
        api,
        "_uploaded_audio_source_root",
        lambda: roots["sources"],
    )
    monkeypatch.setattr(api, "_chunked_upload_root", lambda: roots["chunks"])
    monkeypatch.setattr(api, "_voice_work_root", lambda: roots["work"])
    monkeypatch.setattr(api, "_voice_lock_root", lambda: roots["locks"])
    return roots


def test_write_upload_job_removes_sensitive_temp_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    job_id = "replace-failure"
    job_path = api._upload_job_path(job_id)
    temp_path = job_path.with_suffix(".tmp")
    original_replace = Path.replace

    def fail_job_replace(path: Path, target: Path) -> Path:
        if path == temp_path:
            raise OSError("Atomic replace failed.")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_job_replace)

    with pytest.raises(OSError):
        api._write_upload_job(
            job_id,
            {
                "status": "done",
                "bundle": {"user_transcript": "Sensitive transcript."},
            },
        )

    assert not temp_path.exists()
    assert not job_path.exists()


def test_voice_capture_api_is_transcription_only() -> None:
    assert not hasattr(api, "build_session_config")
    assert not hasattr(api, "PartnerWhisperRequest")
    assert not hasattr(api, "create_partner_whisper")


def test_browser_assets_do_not_expose_api_key() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert "gpt-realtime-2" not in script
    assert "OPENAI_API_KEY" not in page
    assert "OPENAI_API_KEY" not in script
    assert "Authorization" not in page
    assert "Authorization" not in script


def test_audio_upload_controls_are_inactive_without_plugin_launch() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert 'class="upload{% if not session_ready %} is-disabled{% endif %}"' in page
    assert "aria-disabled=\"{{ 'false' if session_ready else 'true' }}\"" in page
    assert page.count("{% if not session_ready %}disabled{% endif %}") == 1
    assert '<button id="uploadAudio" disabled>Transcribe file</button>' in page
    assert 'aria-label="Capture input"' in page
    assert 'aria-label="Audio file transcription"' in page
    assert "audioFileInput.disabled = true;" in script
    assert "uploadKindSelect" not in script
    assert "languageSelect.disabled = true;" in script
    assert "function updateUploadButtonState()" in script
    assert "function updateConnectButtonState()" in script
    assert (
        "!sessionReady || !file || uploadInProgress || !hasRequiredSourceMetadata()"
        in (script)
    )


def test_voice_source_identity_metadata_resets_between_captures() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert "Source details" not in page
    assert 'aria-label="Call metadata"' in page
    assert 'id="sourceTitle" autocomplete="off" required' in page
    assert 'id="sourceParticipants"' in page
    assert 'id="sourceType"' not in page
    assert 'source_type: document.getElementById("sourceType")' in script
    assert "function resetSourceIdentityFields()" in script
    assert script.count("resetSourceIdentityFields();") == 3
    assert (
        "downloadZipBundle(`case-notes-voice-${compactTimestamp}.zip`, zipEntries)"
        in (script)
    )
    assert (
        "downloadZipBundle(`case-notes-audio-${compactTimestamp}.zip`, zipEntries)"
        in script
    )


def test_voice_capture_requires_title_and_participant_metadata() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert 'id="sourceTitle" autocomplete="off" required' in page
    assert (
        "required"
        in page.split('id="sourceParticipants"', maxsplit=1)[1].split(
            "</label>",
            maxsplit=1,
        )[0]
    )
    assert "function validateRequiredSourceMetadata()" in script
    assert (
        "Add a short title and at least one participant before recording or uploading."
        in script
    )
    assert script.count("if (!validateRequiredSourceMetadata())") == 2
    assert "liveCaptureSourceMetadata = collectSourceMetadata();" in script
    assert "sourceMetadata: collectSourceMetadata()" in script
    assert "sourceMetadata: liveCaptureSourceMetadata || collectSourceMetadata()" in (
        script
    )
    assert "function hasRequiredSourceMetadata()" in script
    assert 'field?.addEventListener("input", updateSourceMetadataState)' in script
    assert "updateConnectButtonState();" in script
    assert "updateUploadButtonState();" in script


def test_browser_capture_page_does_not_expose_debrief_or_kickoff_modes() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert 'data-mode="guided_debrief"' not in page
    assert 'data-mode="kickoff_briefing"' not in page
    assert "listen_only" not in page
    assert 'id="mode"' not in page
    assert "Live mode" not in page
    assert "Clara kickoff" not in page
    assert "Debrief or voice note" not in page
    assert "Challenge session" not in page
    assert "Start the private Clara voice interview now" not in script
    assert "Speak first." not in script
    assert "listen_only" not in script
    assert "Transcribe file" in page


def test_capture_surface_uses_capture_and_upload_without_mode_controls() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert 'id="mode"' not in page
    assert "Live mode" not in page
    assert 'id="uploadKind"' not in page
    assert "listen_only" not in page
    assert "syncRecordingTypeFromMode()" not in script
    assert "modeForRecordingType" not in script
    assert "replaceModeInUrl" not in script
    assert "listen_only" not in script
    assert 'id="screenPreviewPanel"' in page
    assert 'id="screenPreview"' in page
    assert "attachScreenPreview(screenStream)" in script
    assert "screenVisualEvidenceMetadata()" in script
    assert "visual_evidence: screenVisualEvidenceMetadata()" in script
    assert "startLiveVideoRecording(screenStream, {" in script
    assert "video_file_name: videoFileName" in script
    assert "video_content_type: videoContentType" in script
    assert "screen_capture_metadata" in script
    assert "screen_video_bytes" in script
    assert "shouldCommitRealtimeAudioForTiming()" not in script
    assert "input_audio_buffer.commit" in script
    assert "input_audio_buffer.committed" in script
    assert "conversation.item.input_audio_transcription.segment" not in script
    assert "transcript_video_sync" in script


def test_live_capture_records_screen_video_and_automatic_audio() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert 'id="audioSource"' not in page
    assert "function openLiveCaptureStreams()" in script
    assert "function createMixedAudioStream(displayStream, micStream)" in script
    assert "function audioStatusText(metadata = captureAudioMetadata)" in script
    assert "function shouldShowScreenPreview()" in script
    assert "navigator.mediaDevices.getDisplayMedia({" in script
    assert "navigator.mediaDevices.getUserMedia({" in script
    assert "audio: true" in script
    assert "video: true" in script
    assert "live_screen_context" in script
    assert "provenance_only: !required" in script
    assert 'screenCaptureReason = "live_screen_context";' in script
    assert 'audio_source: "automatic"' in script
    assert "audio_sources: { ...captureAudioMetadata }" in script
    assert "startLiveVideoRecording(screenStream, {" in script
    assert "required: true" in script
    assert "downloadAudioBundle(bundle, file, companionVideoBlob)" in script
    assert "companionVideoBlob: liveVideoBlob" in script
    assert "video_provenance_note" in script
    assert (
        "zipEntries.push({ name: videoFileName, data: companionVideoBlob })" in script
    )


def test_launch_token_is_short_lived_metadata_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    user = AuthenticatedUser(email="advisor@example.com")
    now = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    token = api.issue_voice_launch_token(user=user, now=now)
    metadata = api.verify_voice_launch_token(token=token, user=user, now=now)
    token_files = list(tmp_path.glob("*.json"))

    assert metadata["email"] == user.email
    assert api.TOKEN_TTL_SECONDS == 8 * 60 * 60
    assert "." in token
    assert len(token_files) == 0


def test_launch_token_can_store_case_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    user = AuthenticatedUser(email="advisor@example.com")
    now = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    token = api.issue_voice_launch_token(
        user=user,
        case_context="Client: ExampleCo\nProject: succession",
        now=now,
    )
    metadata = api.verify_voice_launch_token(token=token, user=user, now=now)

    assert metadata["case_context"] == "Client: ExampleCo\nProject: succession"
    assert list(tmp_path.glob("*.json")) == []


def test_source_metadata_drops_confidentiality() -> None:
    metadata = api._parse_source_metadata_json(
        json.dumps(
            {
                "source_type": "interview",
                "title": "ExampleCo",
                "confidentiality": "sensitive",
                "ignored": "not stored",
            }
        )
    )

    assert metadata == {"source_type": "interview", "title": "ExampleCo"}


def test_launch_route_decodes_compressed_case_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    user = AuthenticatedUser(email="advisor@example.com")
    encoded = base64.urlsafe_b64encode(
        zlib.compress("Client: ExampleCo".encode("utf-8"), level=9)
    ).decode("ascii")

    response = api.launch_voice_page(
        case_context_z=encoded,
        user=user,
    )
    query = parse_qs(urlsplit(response.headers["location"]).query)
    session = query["session"][0]
    metadata = api.verify_voice_launch_token(token=session, user=user)

    assert metadata["case_context"] == "Client: ExampleCo"
    assert "mode" not in query


def test_realtime_transcription_session_uses_transcription_only_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    user = AuthenticatedUser(email="advisor@example.com")
    token = api.issue_voice_launch_token(user=user)
    captured: dict[str, object] = {}

    def fake_realtime_call(**kwargs):
        captured.update(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="call_live_asr")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "sk-test")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)

    response = api.create_realtime_transcription_session(
        api.RealtimeTranscriptionSessionRequest(
            launch_token=token,
            sdp="offer-sdp",
            language="it",
        ),
        user=user,
    )
    body = json.loads(response.body)

    assert body["status"] == "ready"
    assert body["sdp"] == "answer-sdp"
    assert body["call_id"] == "call_live_asr"
    assert body["transcription_model"] == "gpt-realtime-whisper"
    assert captured["sdp"] == "offer-sdp"
    assert captured["safety_identifier"].startswith("case-notes-voice-")
    session_config = captured["session_config"]
    assert isinstance(session_config, dict)
    assert session_config["type"] == "transcription"
    assert "model" not in session_config
    assert "tracing" not in session_config
    assert session_config["audio"]["input"]["turn_detection"] is None
    assert session_config["audio"]["input"]["transcription"] == {
        "model": "gpt-realtime-whisper",
        "language": "it",
        "delay": "low",
    }


def test_realtime_transcription_session_rejects_invalid_launch_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    user = AuthenticatedUser(email="advisor@example.com")

    with pytest.raises(HTTPException) as error:
        api.create_realtime_transcription_session(
            api.RealtimeTranscriptionSessionRequest(
                launch_token="missing",
                sdp="offer-sdp",
                language="it",
            ),
            user=user,
        )

    assert error.value.status_code == 400
    assert "Invalid or expired Clara voice launch token" in str(error.value.detail)


def test_create_audio_transcription_posts_small_audio_multipart(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    captured: list[dict[str, str | bytes]] = []

    def fake_urlopen(request, timeout):
        body = request.data
        captured.append(
            {
                "content_type": request.headers.get("Content-type", ""),
                "body": body,
                "timeout": str(timeout),
            }
        )
        return FakeResponse(
            {"text": "Facilitator apre davvero la riunione. Reviewer risponde bene."}
        )

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 12.0)

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_bytes=b"fake-audio",
        filename="note.mp3",
        content_type="audio/mpeg",
        language="es",
        case_context="Cliente: ExampleCo",
    )
    upload_body = captured[0]["body"]

    assert (
        result.text == "Facilitator apre davvero la riunione. Reviewer risponde bene."
    )
    assert (
        result.raw_transcription_text
        == "Facilitator apre davvero la riunione. Reviewer risponde bene."
    )
    assert result.metadata["status"] == "complete"
    assert result.metadata["mode"] == "single"
    assert result.metadata["transcription_strategy"] == "clean_text_only"
    assert result.metadata["transcription_model"] == "gpt-4o-transcribe"
    assert result.metadata["source_duration_seconds"] == 12.0
    assert len(captured) == 1
    assert "multipart/form-data" in str(captured[0]["content_type"])
    assert b'name="model"' in upload_body
    assert b"gpt-4o-transcribe" in upload_body
    assert b"gpt-4o-transcribe-diarize" not in upload_body
    assert b"diarized_json" not in upload_body
    assert b'name="chunking_strategy"' not in upload_body
    assert b'name="temperature"' in upload_body
    assert b"\r\n0\r\n" in upload_body
    assert b'name="language"' in upload_body
    assert b"\r\nes\r\n" in upload_body
    assert b'name="prompt"' in upload_body
    assert b"Preferred spellings / case glossary" in upload_body
    assert b"- ExampleCo" in upload_body
    assert b"Useful case vocabulary and context follows" in upload_body
    assert b"Cliente: ExampleCo" in upload_body
    expected_timeout = str(api.OPENAI_UPLOAD_TRANSCRIPTION_TIMEOUT_SECONDS)
    assert captured[0]["timeout"] == expected_timeout


def test_create_single_audio_transcription_rejects_openai_oversized_payload(
    monkeypatch,
) -> None:
    oversized_audio = b"audio-at-request-limit"
    monkeypatch.setattr(
        api,
        "MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES",
        len(oversized_audio),
    )

    with pytest.raises(api.VoiceSessionError, match="25 MB"):
        api._create_single_audio_transcription(
            api_key="sk-test",
            audio_bytes=oversized_audio,
            filename="note.wav",
            content_type="audio/wav",
            language="it",
            case_context="Cliente: ExampleCo",
        )


def test_create_single_audio_transcription_wraps_socket_timeout(monkeypatch) -> None:
    def fake_urlopen(_request, timeout):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(api.VoiceSessionError, match="Audio transcription timed out"):
        api._create_single_audio_transcription(
            api_key="sk-test",
            audio_bytes=b"small-audio",
            filename="note.wav",
            content_type="audio/wav",
            language="it",
            case_context="Cliente: ExampleCo",
        )


def test_parse_ffmpeg_duration_output() -> None:
    output = "Input #0, mov,mp4,m4a: Duration: 00:59:12.19, start: 0.000000"

    assert api._parse_ffmpeg_duration(output) == pytest.approx(3552.19)


def test_chunk_time_windows_overlap_without_gaps() -> None:
    windows = api._chunk_time_windows(1850, chunk_seconds=900, overlap_seconds=30)

    assert windows == [
        (0.0, 900.0, 0.0),
        (870.0, 1770.0, 30.0),
        (1740.0, 1850, 30.0),
    ]


def test_join_chunk_transcripts_removes_exact_boundary_duplicate() -> None:
    overlap = (
        "Pensavi di provare tutti e tre nel ruolo di amministratore delegato "
        "Alex e Jordan con stili diversi potremmo entrare a parlare"
    )

    transcript = api._join_chunk_transcripts(
        [
            f"Prima parte. {overlap}",
            f"{overlap} e poi continuiamo con la parte nuova.",
        ]
    )

    assert transcript == (
        "Prima parte."
        "\n\n"
        "Pensavi di provare tutti e tre nel ruolo di amministratore delegato "
        "Alex e Jordan con stili diversi potremmo entrare a parlare e poi "
        "continuiamo con la parte nuova."
    )


def test_join_chunk_transcripts_removes_fuzzy_boundary_duplicate() -> None:
    first = (
        "Prima parte. Alex e Jordan con stili diversi potremmo entrare a "
        "parlare e nella mia testa c'era più Alex che Jordan ma devo "
        "ammettere che Alex sta dimostrando di avere trattenuto complici al "
        "bambino."
    )
    second = (
        "Alex e Jordan con stili diversi potrebbero aiutare a parlare e "
        "nella mia testa c'era più Alex che Jordan ma devo ammettere che "
        "Alex non sta dimostrando di avere attenuta complice al bambino. "
        "Questo è testo nuovo."
    )

    transcript = api._join_chunk_transcripts([first, second])

    assert transcript.endswith("Questo è testo nuovo.")
    assert transcript.count("Questo è testo nuovo.") == 1
    assert transcript.count("Alex e Jordan") == 1
    assert (
        "potrebbero aiutare a parlare e nella mia testa c'era più Alex che Jordan"
        in transcript
    )


def test_join_chunk_transcripts_prefers_later_overlap_wording() -> None:
    first = (
        "Prima parte. Per la famiglia ExampleCo l'azienda è l'unico asset o avete "
        "altri asset? Cioè abbiamo un patrimonio immobiliare di 5-6 mila."
    )
    second = (
        "Per la famiglia ExampleCo l'azienda è l'unico asset o avete altri asset? "
        "Cioè abbiamo un patrimonio immobiliare di 5-6 miliardi. Ma quindi "
        "il patrimonio è largo."
    )

    transcript = api._join_chunk_transcripts([first, second])

    assert "5-6 mila" not in transcript
    assert "5-6 miliardi" in transcript
    assert transcript.count("patrimonio immobiliare") == 1


def test_chunk_transcription_note_does_not_delegate_overlap_deduplication() -> None:
    chunk = api.AudioTranscriptionChunk(
        index=2,
        filename="chunk-0001.m4a",
        content_type="audio/mp4",
        content=b"audio",
        start_seconds=570,
        duration_seconds=600,
        overlap_seconds=30,
    )

    note = api._chunk_transcription_note(chunk, 7)

    assert "Transcribe the entire chunk verbatim" in note
    assert "including the overlapping opening speech" in note
    assert "removed later by the application" in note
    assert "avoid duplicating" not in note


def test_transcription_stream_copy_windows_use_duration_and_api_byte_limits() -> None:
    audio_bytes = 59_385_733

    windows = api._transcription_stream_copy_windows(
        duration_seconds=3552.23,
        audio_bytes=audio_bytes,
    )

    assert api._transcription_stream_copy_target_bytes() == (
        api.MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES
    )
    assert api._transcription_stream_copy_chunk_count(audio_bytes) == 3
    assert (
        api._transcription_stream_copy_min_chunk_count(
            duration_seconds=3552.23,
            audio_bytes=audio_bytes,
        )
        == 7
    )
    assert len(windows) == 7
    assert windows[0] == (0.0, 600.0, 0.0)
    assert windows[1] == (570.0, 1170.0, 30.0)
    assert windows[-1] == (3420.0, 3552.23, 30.0)


def test_audio_splitters_keep_generated_chunks_on_disk(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.m4a"
    source_path.write_bytes(b"source-audio")

    def fake_run_ffmpeg(command):
        output_path = Path(command[-1])
        output_path.write_bytes(f"audio:{output_path.name}".encode("utf-8"))

    monkeypatch.setattr(api, "_ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(api, "_run_ffmpeg_audio_preparation", fake_run_ffmpeg)
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 10.0)

    transcription_chunks = api._split_audio_for_transcription_stream_copy(
        input_path=source_path,
        output_dir=tmp_path / "transcription",
        input_duration_seconds=20.0,
        input_audio_bytes=20_000,
        filename="source.m4a",
        content_type="audio/mp4",
    )

    assert transcription_chunks
    assert all(chunk.content == b"" for chunk in transcription_chunks)
    assert all(
        chunk.path is not None and chunk.path.exists() for chunk in transcription_chunks
    )
    assert (
        api._audio_transcription_chunk_content(transcription_chunks[0])
        == b"audio:chunk-0000.m4a"
    )


def test_create_audio_transcription_stream_splits_oversized_audio_by_bytes(
    monkeypatch,
) -> None:
    source_audio = b"long-audio"
    monkeypatch.setattr(api, "MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES", len(source_audio))
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 120.0)

    split_inputs: list[tuple[bytes, int, bool]] = []

    def fake_split_audio_for_transcription_stream_copy(**kwargs):
        split_inputs.append(
            (
                kwargs["input_path"].read_bytes(),
                kwargs["input_audio_bytes"],
                "chunk_seconds" in kwargs,
            )
        )
        return [
            api.AudioTranscriptionChunk(
                index=1,
                filename="chunk-0000.m4a",
                content_type="audio/mp4",
                content=b"chunk-one",
                start_seconds=0,
                duration_seconds=60,
                overlap_seconds=0,
            ),
            api.AudioTranscriptionChunk(
                index=2,
                filename="chunk-0001.m4a",
                content_type="audio/mp4",
                content=b"chunk-two",
                start_seconds=60,
                duration_seconds=60,
                overlap_seconds=0,
            ),
        ]

    captured: list[tuple[str, str, bytes]] = []

    def fake_single_transcription(**kwargs):
        captured.append(
            (
                kwargs["filename"],
                kwargs["safety_identifier"],
                kwargs["audio_bytes"],
            )
        )
        return api.AudioTranscriptionResponse(
            text=f"Trascrizione completa del segmento numero {len(captured)}."
        )

    monkeypatch.setattr(
        api,
        "_split_audio_for_transcription_stream_copy",
        fake_split_audio_for_transcription_stream_copy,
    )
    monkeypatch.setattr(
        api, "_create_single_audio_transcription", fake_single_transcription
    )

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_bytes=source_audio,
        filename="meeting.m4a",
        content_type="audio/mp4",
        language="it",
        case_context="Cliente: ExampleCo",
        model="gpt-4o-transcribe",
        safety_identifier="case-notes-test",
    )

    assert (
        result.text
        == "Trascrizione completa del segmento numero 1.\n\nTrascrizione completa del segmento numero 2."
    )
    assert split_inputs == [(source_audio, len(source_audio), False)]
    assert result.metadata["mode"] == "chunked"
    assert result.metadata["chunk_count"] == 2
    assert result.metadata["chunk_overlap_seconds"] == 0.0
    assert result.metadata["status"] == "complete"
    assert captured == [
        ("chunk-0000.m4a", "case-notes-test-chunk-1-attempt-1", b"chunk-one"),
        ("chunk-0001.m4a", "case-notes-test-chunk-2-attempt-1", b"chunk-two"),
    ]


def test_create_audio_transcription_splits_decimal_limit_live_recording(
    monkeypatch,
    tmp_path: Path,
) -> None:
    recorded_audio_bytes = 25_271_670
    source_path = tmp_path / "case-notes-live-20260703.webm"
    source_path.write_bytes(b"local-webm-placeholder")
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 204.25)

    split_inputs: list[tuple[int, str, str]] = []

    def fake_split_audio_for_transcription_stream_copy(**kwargs):
        split_inputs.append(
            (
                kwargs["input_audio_bytes"],
                kwargs["filename"],
                kwargs["content_type"],
            )
        )
        return [
            api.AudioTranscriptionChunk(
                index=1,
                filename="chunk-0000.webm",
                content_type="audio/webm",
                content=b"chunk-one",
                start_seconds=0,
                duration_seconds=102.0,
                overlap_seconds=0,
            ),
            api.AudioTranscriptionChunk(
                index=2,
                filename="chunk-0001.webm",
                content_type="audio/webm",
                content=b"chunk-two",
                start_seconds=72.0,
                duration_seconds=132.25,
                overlap_seconds=30.0,
            ),
        ]

    captured: list[tuple[str, bytes]] = []

    def fake_single_transcription(**kwargs):
        captured.append((kwargs["filename"], kwargs["audio_bytes"]))
        return api.AudioTranscriptionResponse(
            text=f"Trascrizione segmento {len(captured)}."
        )

    monkeypatch.setattr(
        api,
        "_split_audio_for_transcription_stream_copy",
        fake_split_audio_for_transcription_stream_copy,
    )
    monkeypatch.setattr(
        api, "_create_single_audio_transcription", fake_single_transcription
    )

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_path=source_path,
        audio_size_bytes=recorded_audio_bytes,
        filename=source_path.name,
        content_type="audio/webm",
        language="it",
        case_context="Cliente: ExampleCo",
        model="gpt-4o-transcribe",
        safety_identifier="case-notes-test",
    )

    assert recorded_audio_bytes > 25_000_000
    assert recorded_audio_bytes < 25 * 1024 * 1024
    assert recorded_audio_bytes >= api.MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES
    assert split_inputs == [(recorded_audio_bytes, source_path.name, "audio/webm")]
    assert captured == [
        ("chunk-0000.webm", b"chunk-one"),
        ("chunk-0001.webm", b"chunk-two"),
    ]
    assert result.metadata["mode"] == "chunked"
    assert result.metadata["chunk_count"] == 2
    assert result.text == "Trascrizione segmento 1.\n\nTrascrizione segmento 2."


def test_create_audio_transcription_retries_implausibly_short_chunk(
    monkeypatch,
) -> None:
    source_audio = b"long-audio"
    monkeypatch.setattr(api, "MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES", len(source_audio))
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 600.0)

    def fake_split_audio_for_transcription_stream_copy(**_kwargs):
        return [
            api.AudioTranscriptionChunk(
                index=1,
                filename="chunk-0000.m4a",
                content_type="audio/mp4",
                content=b"chunk-one",
                start_seconds=0,
                duration_seconds=600,
                overlap_seconds=0,
            ),
        ]

    captured_identifiers: list[str] = []
    long_transcript = " ".join(f"parola{index}" for index in range(180)) + "."

    def fake_single_transcription(**kwargs):
        captured_identifiers.append(kwargs["safety_identifier"])
        if len(captured_identifiers) == 1:
            return api.AudioTranscriptionResponse(text="troppo breve")
        return api.AudioTranscriptionResponse(text=long_transcript)

    monkeypatch.setattr(
        api,
        "_split_audio_for_transcription_stream_copy",
        fake_split_audio_for_transcription_stream_copy,
    )
    monkeypatch.setattr(
        api, "_create_single_audio_transcription", fake_single_transcription
    )

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_bytes=source_audio,
        filename="meeting.m4a",
        content_type="audio/mp4",
        language="it",
        case_context="Cliente: ExampleCo",
        model="gpt-4o-transcribe",
        safety_identifier="case-notes-test",
    )

    assert captured_identifiers == [
        "case-notes-test-chunk-1-attempt-1",
        "case-notes-test-chunk-1-attempt-2",
    ]
    assert result.text == long_transcript
    assert result.metadata["status"] == "complete"
    assert result.metadata["chunks"][0]["warnings"] == []


def test_create_audio_transcription_repairs_after_invalid_chunk_retries(
    monkeypatch,
) -> None:
    source_audio = b"long-audio"
    monkeypatch.setattr(api, "MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES", len(source_audio))
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 600.0)

    def fake_split_audio_for_transcription_stream_copy(**kwargs):
        if kwargs.get("chunk_seconds") == api.UPLOAD_TRANSCRIPTION_REPAIR_CHUNK_SECONDS:
            return [
                api.AudioTranscriptionChunk(
                    index=1,
                    filename="repair-0000.m4a",
                    content_type="audio/mp4",
                    content=b"repair-one",
                    start_seconds=0,
                    duration_seconds=120,
                    overlap_seconds=0,
                ),
                api.AudioTranscriptionChunk(
                    index=2,
                    filename="repair-0001.m4a",
                    content_type="audio/mp4",
                    content=b"repair-two",
                    start_seconds=110,
                    duration_seconds=120,
                    overlap_seconds=10,
                ),
            ]
        return [
            api.AudioTranscriptionChunk(
                index=1,
                filename="chunk-0000.m4a",
                content_type="audio/mp4",
                content=b"chunk-one",
                start_seconds=0,
                duration_seconds=600,
                overlap_seconds=0,
            ),
        ]

    captured_identifiers: list[str] = []
    repair_one = " ".join(f"riparazionea{index}" for index in range(95)) + "."
    repair_two = " ".join(f"riparazioneb{index}" for index in range(95)) + "."
    repeated_phrase_loop = " ".join(
        ["alfa beta gamma delta epsilon zeta eta theta"] * 20
    )

    def fake_single_transcription(**kwargs):
        captured_identifiers.append(kwargs["safety_identifier"])
        if "-repair-1-" in kwargs["safety_identifier"]:
            return api.AudioTranscriptionResponse(text=repair_one)
        if "-repair-2-" in kwargs["safety_identifier"]:
            return api.AudioTranscriptionResponse(text=repair_two)
        return api.AudioTranscriptionResponse(text=repeated_phrase_loop)

    monkeypatch.setattr(
        api,
        "_split_audio_for_transcription_stream_copy",
        fake_split_audio_for_transcription_stream_copy,
    )
    monkeypatch.setattr(
        api, "_create_single_audio_transcription", fake_single_transcription
    )

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_bytes=source_audio,
        filename="meeting.m4a",
        content_type="audio/mp4",
        language="it",
        case_context="Cliente: ExampleCo",
        model="gpt-4o-transcribe",
        safety_identifier="case-notes-test",
    )

    assert captured_identifiers == [
        "case-notes-test-chunk-1-attempt-1",
        "case-notes-test-chunk-1-attempt-2",
        "case-notes-test-chunk-1-attempt-3",
        "case-notes-test-chunk-1-attempt-4",
        "case-notes-test-chunk-1-attempt-5",
        "case-notes-test-chunk-1-repair-1-attempt-1",
        "case-notes-test-chunk-1-repair-2-attempt-1",
    ]
    assert result.text == f"{repair_one}\n\n{repair_two}"
    assert result.metadata["status"] == "complete"
    assert result.metadata["chunks"][0]["warnings"] == []
    assert result.metadata["chunks"][0]["repair"]["strategy"] == (
        "smaller_audio_subchunks"
    )
    assert result.metadata["chunks"][0]["repair"]["trigger"] == (
        "Chunk transcript contains a repeated phrase loop."
    )
    assert result.metadata["chunks"][0]["repair"]["subchunk_count"] == 2


def test_create_audio_transcription_stream_splits_long_audio_below_api_limit(
    monkeypatch,
) -> None:
    source_audio = b"long-but-small-audio"
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 601.0)

    split_inputs: list[int] = []

    def fake_split_audio_for_transcription_stream_copy(**kwargs):
        split_inputs.append(kwargs["input_audio_bytes"])
        return [
            api.AudioTranscriptionChunk(
                index=1,
                filename="chunk-0000.m4a",
                content_type="audio/mp4",
                content=b"chunk-one",
                start_seconds=0,
                duration_seconds=600,
                overlap_seconds=0,
            ),
            api.AudioTranscriptionChunk(
                index=2,
                filename="chunk-0001.m4a",
                content_type="audio/mp4",
                content=b"chunk-two",
                start_seconds=570,
                duration_seconds=31,
                overlap_seconds=30,
            ),
        ]

    def fake_single_transcription(**kwargs):
        if kwargs["filename"] == "chunk-0000.m4a":
            return api.AudioTranscriptionResponse(
                text=" ".join(f"prima{index}" for index in range(160)) + "."
            )
        return api.AudioTranscriptionResponse(text=f"Testo {kwargs['filename']}.")

    monkeypatch.setattr(
        api,
        "_split_audio_for_transcription_stream_copy",
        fake_split_audio_for_transcription_stream_copy,
    )
    monkeypatch.setattr(
        api, "_create_single_audio_transcription", fake_single_transcription
    )

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_bytes=source_audio,
        filename="meeting.m4a",
        content_type="audio/mp4",
        language="it",
        case_context="Cliente: ExampleCo",
        model="gpt-4o-transcribe",
    )

    assert split_inputs == [len(source_audio)]
    assert result.text == (
        " ".join(f"prima{index}" for index in range(160)) + ".\n\nTesto chunk-0001.m4a."
    )
    assert result.metadata["chunk_count"] == 2
    assert result.metadata["chunk_overlap_seconds"] == 30.0


def test_create_audio_transcription_rejects_when_stream_split_cannot_fit_api_limit(
    monkeypatch,
) -> None:
    source_audio = b"high-bitrate-wav-audio"
    monkeypatch.setattr(api, "MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES", len(source_audio))
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 12.0)

    def fake_split_audio_for_transcription_stream_copy(**_kwargs):
        raise api.VoiceSessionError(
            "Uploaded audio cannot be split into API-safe transcription chunks "
            "without re-encoding."
        )

    monkeypatch.setattr(
        api,
        "_split_audio_for_transcription_stream_copy",
        fake_split_audio_for_transcription_stream_copy,
    )

    with pytest.raises(api.VoiceSessionError, match="without re-encoding"):
        api.create_audio_transcription(
            api_key="sk-test",
            audio_bytes=source_audio,
            filename="meeting.wav",
            content_type="audio/wav",
            language="it",
            case_context="Cliente: ExampleCo",
        )


def test_create_audio_transcription_needs_ffmpeg_for_oversized_short_audio(
    monkeypatch,
) -> None:
    source_audio = b"high-bitrate-wav-audio"
    monkeypatch.setattr(api, "MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES", len(source_audio))
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 12.0)
    monkeypatch.setattr(api, "_ffmpeg_binary", lambda: None)

    with pytest.raises(api.VoiceSessionError, match="ffmpeg"):
        api.create_audio_transcription(
            api_key="sk-test",
            audio_bytes=source_audio,
            filename="meeting.wav",
            content_type="audio/wav",
            language="it",
            case_context="Cliente: ExampleCo",
        )


def test_create_audio_transcription_normalizes_unknown_duration_audio(
    monkeypatch,
) -> None:
    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    captured: list[dict[str, str | bytes]] = []

    def fake_urlopen(request, timeout):
        captured.append(
            {
                "content_type": request.headers.get("Content-type", ""),
                "body": request.data,
                "timeout": str(timeout),
            }
        )
        return FakeResponse({"text": "Trascrizione recuperata dal webm."})

    def fake_audio_duration(path: Path) -> float | None:
        if path.name == "meeting.duration-normalized.wav":
            return 44.0
        return None

    def fake_run_ffmpeg(command: list[str]) -> None:
        Path(command[-1]).write_bytes(b"duration-bearing-wav")

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(api, "_audio_duration_seconds", fake_audio_duration)
    monkeypatch.setattr(api, "_ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(api, "_run_ffmpeg_audio_preparation", fake_run_ffmpeg)

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_bytes=b"durationless-webm",
        filename="meeting.webm",
        content_type="audio/webm",
        language="it",
        case_context="Cliente: ExampleCo",
    )

    upload_body = captured[0]["body"]

    assert result.text == "Trascrizione recuperata dal webm."
    assert result.metadata["source_duration_seconds"] == 44.0
    assert result.metadata["audio_preparation"] == "duration_normalized_wav"
    assert result.metadata["uploaded_audio_filename"] == "meeting.webm"
    assert result.metadata["transcribed_audio_filename"] == (
        "meeting.duration-normalized.wav"
    )
    assert b"meeting.duration-normalized.wav" in upload_body
    assert b"Content-Type: audio/wav" in upload_body
    assert b"duration-bearing-wav" in upload_body
    assert b"durationless-webm" not in upload_body


def test_create_audio_transcription_requires_ffmpeg_when_duration_is_unknown(
    monkeypatch,
) -> None:
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: None)
    monkeypatch.setattr(api, "_ffmpeg_binary", lambda: None)

    with pytest.raises(api.VoiceSessionError, match="normalization requires ffmpeg"):
        api.create_audio_transcription(
            api_key="sk-test",
            audio_bytes=b"long-audio",
            filename="meeting.m4a",
            content_type="audio/mp4",
            language="it",
            case_context="Cliente: ExampleCo",
        )


def test_create_audio_transcription_warns_on_suspicious_final_chunk(
    monkeypatch,
) -> None:
    source_audio = b"long-audio"
    monkeypatch.setattr(api, "MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES", len(source_audio))
    monkeypatch.setattr(api, "_audio_duration_seconds", lambda _path: 3552.23)

    def fake_split_audio_for_transcription_stream_copy(**_kwargs):
        return [
            api.AudioTranscriptionChunk(
                index=1,
                filename="chunk-0000.m4a",
                content_type="audio/mp4",
                content=b"chunk-one",
                start_seconds=0,
                duration_seconds=900,
                overlap_seconds=0,
            ),
            api.AudioTranscriptionChunk(
                index=2,
                filename="chunk-0001.m4a",
                content_type="audio/mp4",
                content=b"chunk-two",
                start_seconds=870,
                duration_seconds=540,
                overlap_seconds=0,
            ),
        ]

    def fake_single_transcription(**kwargs):
        if kwargs["filename"] == "chunk-0000.m4a":
            return api.AudioTranscriptionResponse(
                text=" ".join(f"prima{index}" for index in range(240)) + "."
            )
        return api.AudioTranscriptionResponse(
            text=" ".join(f"ultima{index}" for index in range(150))
        )

    monkeypatch.setattr(
        api,
        "_split_audio_for_transcription_stream_copy",
        fake_split_audio_for_transcription_stream_copy,
    )
    monkeypatch.setattr(
        api, "_create_single_audio_transcription", fake_single_transcription
    )

    result = api.create_audio_transcription(
        api_key="sk-test",
        audio_bytes=source_audio,
        filename="meeting.m4a",
        content_type="audio/mp4",
        language="it",
        case_context="Cliente: ExampleCo",
        model="gpt-4o-transcribe",
    )

    assert result.metadata["status"] == "warning"
    assert any(
        "Final chunk transcript ends" in warning
        for warning in result.metadata["warnings"]
    )


def test_audio_upload_metadata_rejects_oversized_file(monkeypatch) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_MAX_AUDIO_UPLOAD_BYTES", "10")
    api._validate_audio_upload_metadata("meeting.wav", 10)
    with pytest.raises(api.VoiceSessionError, match="too large"):
        api._validate_audio_upload_metadata("meeting.wav", 11)
    with pytest.raises(api.VoiceSessionError, match="empty"):
        api._validate_audio_upload_metadata("meeting.wav", 0)


def test_write_upload_file_to_path_rejects_oversized_stream(tmp_path: Path) -> None:
    class FakeUpload:
        def __init__(self) -> None:
            self.chunks = [b"12345", b"67890", b"!"]

        async def read(self, _size: int = -1):
            if not self.chunks:
                return b""
            return self.chunks.pop(0)

    output_path = tmp_path / "meeting.wav"

    with pytest.raises(api.VoiceSessionError, match="too large"):
        asyncio.run(
            api._write_upload_file_to_path(
                FakeUpload(),
                output_path,
                max_bytes=10,
            )
        )

    assert not output_path.exists()
    assert list(tmp_path.glob("*.uploading")) == []


def test_upload_audio_route_accepts_spanish_source_language(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    token = api.issue_voice_launch_token(
        user=user,
        case_context="Client: ExampleCo\nRisk: governance remains informal.",
    )

    class FakeUpload:
        filename = "meeting.wav"
        content_type = "audio/wav"

        def __init__(self) -> None:
            self.content = b"fake-audio"

        async def read(self, _size: int = -1):
            content = self.content
            self.content = b""
            return content

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "sk-test")
    background_tasks = BackgroundTasks()

    response = asyncio.run(
        api.upload_audio(
            background_tasks=background_tasks,
            launch_token=token,
            language="es",
            source_metadata_json=json.dumps(
                {
                    "source_type": "interview",
                    "title": "ExampleCo - CFO interview",
                    "participants": "CFO",
                    "role": "Finance",
                    "interviewer": "Reviewer",
                    "confidentiality": "sensitive",
                    "ignored": "not stored",
                }
            ),
            audio_file=FakeUpload(),
            user=user,
        )
    )
    body = json.loads(response.body)

    assert response.status_code == 202
    assert body["status"] == "queued"
    assert body["job_id"]
    job_payload = api._read_upload_job(body["job_id"], user)
    assert job_payload["status"] == "queued"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].kwargs["language"] == "es"


def test_upload_audio_route_rejects_unsupported_source_language() -> None:
    class FakeUpload:
        filename = "meeting.wav"
        content_type = "audio/wav"

        async def read(self, _size: int = -1):
            return b"fake-audio"

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            api.upload_audio(
                background_tasks=BackgroundTasks(),
                launch_token="unused",
                language="xx",
                source_metadata_json="{}",
                audio_file=FakeUpload(),
                user=None,
            )
        )

    assert error.value.status_code == 400
    assert error.value.detail == "Unsupported language: xx"


def test_chunked_audio_upload_route_returns_background_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES", 5)
    user = AuthenticatedUser(email="advisor@example.com")
    token = api.issue_voice_launch_token(
        user=user,
        case_context="Client: ExampleCo\nRisk: governance remains informal.",
    )
    audio_bytes = b"fake-audio"

    class FakeChunk:
        def __init__(self, content: bytes) -> None:
            self.content = content

        async def read(self, _size: int = -1):
            content = self.content
            self.content = b""
            return content

    start_response = asyncio.run(
        api.start_chunked_audio_upload(
            launch_token=token,
            language="it",
            source_metadata_json=json.dumps(
                {
                    "source_type": "interview",
                    "title": "ExampleCo - CFO interview",
                    "participants": "CFO",
                    "interviewer": "Reviewer",
                }
            ),
            filename="meeting.wav",
            content_type="audio/wav",
            total_bytes=len(audio_bytes),
            total_chunks=2,
            user=user,
        )
    )
    start_body = json.loads(start_response.body)

    assert start_response.status_code == 201
    assert start_body["status"] == "ready"
    assert start_body["chunk_size"] == api.CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES

    upload_id = start_body["upload_id"]
    upload_metadata = api._read_chunked_upload_metadata(upload_id, user)
    assert upload_metadata["expected_chunk_bytes"] == [5, 5]
    first_chunk_response = asyncio.run(
        api.upload_audio_chunk(
            upload_id=upload_id,
            chunk_index=0,
            audio_chunk=FakeChunk(audio_bytes[:5]),
            user=user,
        )
    )
    with pytest.raises(HTTPException) as duplicate_error:
        asyncio.run(
            api.upload_audio_chunk(
                upload_id=upload_id,
                chunk_index=0,
                audio_chunk=FakeChunk(b"xxxxx"),
                user=user,
            )
        )
    assert duplicate_error.value.status_code == 400
    assert "already received" in str(duplicate_error.value.detail)
    second_chunk_response = asyncio.run(
        api.upload_audio_chunk(
            upload_id=upload_id,
            chunk_index=1,
            audio_chunk=FakeChunk(audio_bytes[5:]),
            user=user,
        )
    )

    assert json.loads(first_chunk_response.body)["received_chunks"] == 1
    assert json.loads(second_chunk_response.body)["received_chunks"] == 2

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "sk-test")
    background_tasks = BackgroundTasks()
    finish_response = asyncio.run(
        api.finish_chunked_audio_upload(
            upload_id=upload_id,
            background_tasks=background_tasks,
            user=user,
        )
    )
    finish_body = json.loads(finish_response.body)

    assert finish_response.status_code == 202
    assert finish_body["status"] == "queued"
    assert finish_body["job_id"]
    job_payload = api._read_upload_job(finish_body["job_id"], user)
    assert job_payload["status"] == "queued"
    assert len(background_tasks.tasks) == 1
    assert not api._chunked_upload_dir(upload_id).exists()


def test_finish_chunked_audio_upload_does_not_queue_when_chunk_removal_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    upload_id = "chunk-removal-failure"
    api._write_chunked_upload_metadata(
        upload_id,
        {
            "status": "uploading",
            "email": user.email,
            "filename": "meeting.wav",
            "content_type": "audio/wav",
            "language": "it",
            "source_metadata": {},
            "case_context": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    upload_dir = api._chunked_upload_dir(upload_id)
    (upload_dir / "chunk-000000.part").write_bytes(b"raw-chunk")
    assembled_paths: list[Path] = []

    def fake_assemble_chunked_audio_file(
        *,
        upload_id: str,
        metadata,
        output_path: Path,
    ) -> int:
        del upload_id, metadata
        output_path.parent.mkdir(parents=True)
        output_path.write_bytes(b"assembled-audio")
        assembled_paths.append(output_path)
        return output_path.stat().st_size

    original_remove_voice_directory = api._remove_voice_directory

    def fail_chunk_directory_removal(path: Path, *, strict: bool = False) -> bool:
        if path == upload_dir:
            raise api.VoiceSessionError("Chunk upload could not be deleted.")
        return original_remove_voice_directory(path, strict=strict)

    monkeypatch.setattr(
        api,
        "_assemble_chunked_audio_file",
        fake_assemble_chunked_audio_file,
    )
    monkeypatch.setattr(
        api,
        "_remove_voice_directory",
        fail_chunk_directory_removal,
    )
    background_tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as removal_error:
        asyncio.run(
            api.finish_chunked_audio_upload(
                upload_id=upload_id,
                background_tasks=background_tasks,
                user=user,
            )
        )

    assert removal_error.value.status_code == 400
    assert "could not be deleted" in str(removal_error.value.detail)
    assert len(assembled_paths) == 1
    assert not assembled_paths[0].parent.exists()
    assert upload_dir.exists()
    assert background_tasks.tasks == []


def test_chunked_audio_upload_rejects_wrong_chunk_size(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES", 5)
    user = AuthenticatedUser(email="advisor@example.com")
    token = api.issue_voice_launch_token(user=user)

    class FakeChunk:
        def __init__(self, content: bytes) -> None:
            self.content = content

        async def read(self, _size: int = -1):
            content = self.content
            self.content = b""
            return content

    start_response = asyncio.run(
        api.start_chunked_audio_upload(
            launch_token=token,
            language="it",
            source_metadata_json="{}",
            filename="meeting.wav",
            content_type="audio/wav",
            total_bytes=10,
            total_chunks=2,
            user=user,
        )
    )
    upload_id = json.loads(start_response.body)["upload_id"]

    with pytest.raises(HTTPException) as upload_error:
        asyncio.run(
            api.upload_audio_chunk(
                upload_id=upload_id,
                chunk_index=0,
                audio_chunk=FakeChunk(b"bad"),
                user=user,
            )
        )

    metadata = api._read_chunked_upload_metadata(upload_id, user)

    assert upload_error.value.status_code == 400
    assert "unexpected size" in str(upload_error.value.detail)
    assert metadata["received_chunks"] == []
    assert not api._chunked_upload_chunk_path(upload_id, 0).exists()


def test_upload_audio_chunk_removes_chunk_when_metadata_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    upload_id = "metadata-write-failure"
    api._write_chunked_upload_metadata(
        upload_id,
        {
            "status": "uploading",
            "email": user.email,
            "filename": "meeting.wav",
            "content_type": "audio/wav",
            "total_bytes": 5,
            "total_chunks": 1,
            "chunk_size": 5,
            "expected_chunk_bytes": [5],
            "received_chunks": [],
            "chunk_bytes": {},
            "chunk_sha256": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    class FakeChunk:
        def __init__(self) -> None:
            self.content = b"abcde"

        async def read(self, _size: int = -1):
            content = self.content
            self.content = b""
            return content

    def fail_metadata_write(_upload_id: str, _metadata) -> None:
        raise OSError("Metadata replace failed.")

    monkeypatch.setattr(api, "_write_chunked_upload_metadata", fail_metadata_write)

    with pytest.raises(HTTPException) as metadata_error:
        asyncio.run(
            api.upload_audio_chunk(
                upload_id=upload_id,
                chunk_index=0,
                audio_chunk=FakeChunk(),
                user=user,
            )
        )

    metadata = api._read_chunked_upload_metadata(upload_id, user)
    assert metadata_error.value.status_code == 400
    assert "temporary copy was deleted" in str(metadata_error.value.detail)
    assert metadata["received_chunks"] == []
    assert not api._chunked_upload_chunk_path(upload_id, 0).exists()


def test_uploaded_audio_job_writes_bundle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    roots = _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    captured: dict[str, str | Path] = {}

    def fake_transcribe(**kwargs):
        captured["transcription_context"] = kwargs["case_context"]
        captured["filename"] = kwargs["filename"]
        captured["temporary_root"] = kwargs["temporary_root"]
        return api.AudioTranscriptionResult(
            text="Il passaggio richiede un mandato AD scritto.",
            metadata={
                "schema_version": 1,
                "status": "complete",
                "mode": "single",
                "transcription_strategy": "clean_text_only",
                "transcription_model": "gpt-4o-transcribe",
                "source_duration_seconds": 12.0,
                "chunk_count": 1,
                "coverage_complete": True,
                "warnings": [],
                "chunks": [],
            },
            raw_transcription_text="Il passaggio richiede un mandato AD scritto.",
        )

    monkeypatch.setattr(api, "create_audio_transcription", fake_transcribe)
    job_id = "job-test"
    audio_path = tmp_path / "upload-source" / "meeting.wav"
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"fake-audio")
    api._process_uploaded_audio_job(
        job_id=job_id,
        email=user.email.lower(),
        api_key="sk-test",
        audio_path=audio_path,
        audio_size_bytes=audio_path.stat().st_size,
        filename="meeting.wav",
        content_type="audio/wav",
        language="it",
        source_metadata={
            "source_type": "interview",
            "title": "ExampleCo - CFO interview",
            "participants": "CFO",
            "interviewer": "Reviewer",
        },
        case_context="Client: ExampleCo\nRisk: governance remains informal.",
        safety_identifier="case-notes-voice-test",
    )
    payload = api._read_upload_job(job_id, user)
    body = payload["bundle"]

    assert payload["status"] == "done"
    assert body["source"] == "case_notes_hosted_voice"
    assert body["capture_source"] == "uploaded_audio"
    assert body["language"] == "it"
    assert "upload_kind" not in body
    assert body["source_metadata"] == {
        "source_type": "interview",
        "title": "ExampleCo - CFO interview",
        "participants": "CFO",
        "interviewer": "Reviewer",
    }
    assert "role" not in body["source_metadata"]
    assert "confidentiality" not in body["source_metadata"]
    assert body["audio_file_name"] == "meeting.wav"
    assert body["model"] == "gpt-4o-transcribe"
    assert body["transcription_model"] == "gpt-4o-transcribe"
    assert body["user_transcript"] == "Il passaggio richiede un mandato AD scritto."
    assert (
        body["transcript_text_prompted"]
        == "Il passaggio richiede un mandato AD scritto."
    )
    assert body["raw_transcription_text"] == (
        "Il passaggio richiede un mandato AD scritto."
    )
    assert "intentionally not generated" in body["speaker_label_note"]
    assert "assign speaker attribution" in body["transcript_processing_note"]
    assert "check transcript quality" in body["transcript_processing_note"]
    assert "obviously wrong transcription words" in body["transcript_processing_note"]
    assert body["transcription_metadata"]["status"] == "complete"
    assert body["transcription_metadata"]["language"] == "it"
    assert body["extraction_text"] == ""
    assert body["extraction_json"] == {
        "cleaned_notes_markdown": "",
        "entries": [],
        "open_questions": [],
    }
    assert "clara_review_markdown" not in body
    assert "Client: ExampleCo" in captured["transcription_context"]
    assert captured["temporary_root"] == roots["work"] / job_id
    assert not audio_path.parent.exists()
    assert not api._voice_work_dir(job_id).exists()

    response = api.get_upload_audio_job(job_id, user=user)
    retrieved = json.loads(response.body)

    assert retrieved["status"] == "done"
    assert retrieved["bundle"] == body
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert not api._upload_job_path(job_id).exists()
    assert list(roots["jobs"].iterdir()) == []
    assert list(roots["sources"].iterdir()) == []
    assert list(roots["chunks"].iterdir()) == []
    assert list(roots["work"].iterdir()) == []
    lock_path = roots["locks"] / f"{job_id}.lock"
    assert lock_path.read_bytes() == b""


def test_get_upload_audio_job_running_status_has_private_no_store_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    job_id = "running-job"
    api._write_upload_job(
        job_id,
        {
            "status": "running",
            "email": user.email,
            "message": "Transcribing uploaded audio.",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    response = api.get_upload_audio_job(job_id, user=user)

    assert json.loads(response.body)["status"] == "running"
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert api._upload_job_path(job_id).exists()


def test_uploaded_audio_job_writes_warning_metadata_bundle_when_coverage_complete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")

    def fake_transcribe(**_kwargs):
        return api.AudioTranscriptionResult(
            text="Ultima frase senza chiusura",
            metadata={
                "schema_version": 1,
                "status": "warning",
                "mode": "chunked",
                "source_duration_seconds": 1410.0,
                "chunk_count": 2,
                "coverage_complete": True,
                "warnings": [
                    "Final chunk transcript ends without sentence punctuation; verify recording end coverage."
                ],
                "chunks": [],
            },
        )

    monkeypatch.setattr(api, "create_audio_transcription", fake_transcribe)
    job_id = "job-warning"
    audio_path = tmp_path / "upload-warning" / "meeting.wav"
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"fake-audio")
    api._process_uploaded_audio_job(
        job_id=job_id,
        email=user.email.lower(),
        api_key="sk-test",
        audio_path=audio_path,
        audio_size_bytes=audio_path.stat().st_size,
        filename="meeting.wav",
        content_type="audio/wav",
        language="it",
        source_metadata={},
        case_context="Client: ExampleCo",
        safety_identifier="case-notes-voice-test",
    )

    payload = api._read_upload_job(job_id, user)

    assert payload["status"] == "done"
    assert payload["message"] == "Audio transcription complete."
    assert payload["bundle"]["user_transcript"] == "Ultima frase senza chiusura"
    assert payload["bundle"]["transcription_metadata"]["status"] == "warning"
    assert payload["bundle"]["transcription_metadata"]["coverage_complete"] is True


def test_uploaded_audio_job_does_not_write_bundle_when_coverage_is_incomplete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")

    def fake_transcribe(**_kwargs):
        return api.AudioTranscriptionResult(
            text="Trascrizione parziale.",
            metadata={
                "schema_version": 1,
                "status": "warning",
                "mode": "chunked",
                "source_duration_seconds": 1410.0,
                "chunk_count": 2,
                "coverage_complete": False,
                "warnings": [
                    "Chunk windows do not cover the full source audio duration."
                ],
                "chunks": [],
            },
        )

    monkeypatch.setattr(api, "create_audio_transcription", fake_transcribe)
    job_id = "job-incomplete"
    audio_path = tmp_path / "upload-incomplete" / "meeting.wav"
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"fake-audio")
    api._process_uploaded_audio_job(
        job_id=job_id,
        email=user.email.lower(),
        api_key="sk-test",
        audio_path=audio_path,
        audio_size_bytes=audio_path.stat().st_size,
        filename="meeting.wav",
        content_type="audio/wav",
        language="it",
        source_metadata={},
        case_context="Client: ExampleCo",
        safety_identifier="case-notes-voice-test",
    )

    payload = api._read_upload_job(job_id, user)

    assert payload["status"] == "error"
    assert "no bundle was downloaded" in payload["message"]
    assert "bundle" not in payload
    assert payload["transcription_metadata"]["coverage_complete"] is False


def test_uploaded_audio_job_blocks_bundle_when_initial_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    job_id = "cleanup-failure"
    audio_path = api._uploaded_audio_source_path(job_id, "meeting.wav")
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"sensitive-audio")

    def fake_transcribe(**_kwargs):
        return api.AudioTranscriptionResult(
            text="Sensitive transcript.",
            metadata={
                "status": "complete",
                "coverage_complete": True,
                "warnings": [],
            },
        )

    original_remove_voice_directory = api._remove_voice_directory
    cleanup_failed = False

    def fail_first_strict_cleanup(path: Path, *, strict: bool = False) -> bool:
        nonlocal cleanup_failed
        if path == audio_path.parent and strict and not cleanup_failed:
            cleanup_failed = True
            raise api.VoiceSessionError("Temporary audio could not be deleted.")
        return original_remove_voice_directory(path, strict=strict)

    monkeypatch.setattr(api, "create_audio_transcription", fake_transcribe)
    monkeypatch.setattr(
        api,
        "_remove_voice_directory",
        fail_first_strict_cleanup,
    )

    api._process_uploaded_audio_job(
        job_id=job_id,
        email=user.email,
        api_key="sk-test",
        audio_path=audio_path,
        audio_size_bytes=audio_path.stat().st_size,
        filename="meeting.wav",
        content_type="audio/wav",
        language="it",
        source_metadata={},
        case_context="",
        safety_identifier="case-notes-voice-test",
    )

    payload = api._read_upload_job(job_id, user)
    assert cleanup_failed is True
    assert payload["status"] == "error"
    assert "bundle" not in payload
    assert "Download remains blocked" in payload["message"]
    assert not audio_path.parent.exists()
    assert not api._voice_work_dir(job_id).exists()


def test_uploaded_audio_job_removes_raw_audio_when_lock_acquisition_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    job_id = "lock-failure"
    audio_path = api._uploaded_audio_source_path(job_id, "meeting.wav")
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"sensitive-audio")

    def fail_lock(_job_id: str, *, blocking: bool):
        del blocking
        raise OSError("Lock storage unavailable.")

    monkeypatch.setattr(api, "_acquire_voice_job_lock", fail_lock)

    with pytest.raises(OSError):
        api._process_uploaded_audio_job(
            job_id=job_id,
            email="advisor@example.com",
            api_key="sk-test",
            audio_path=audio_path,
            audio_size_bytes=audio_path.stat().st_size,
            filename="meeting.wav",
            content_type="audio/wav",
            language="it",
            source_metadata={},
            case_context="",
            safety_identifier="case-notes-voice-test",
        )

    assert not audio_path.parent.exists()


def test_get_upload_audio_job_marks_stale_running_job_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "UPLOAD_JOB_STALE_SECONDS", 1)
    user = AuthenticatedUser(email="advisor@example.com")
    job_id = "stale-job"
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir(parents=True)
    (source_dir / "upload.wav").write_bytes(b"stale-audio")
    api._write_upload_job(
        job_id,
        {
            "status": "running",
            "email": user.email.lower(),
            "message": "Still running.",
            "updated_at": (
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
        },
    )

    response = api.get_upload_audio_job(job_id, user=user)
    body = json.loads(response.body)

    assert body["status"] == "error"
    assert body["previous_status"] == "running"
    assert "stale-job timeout" in body["message"]
    assert not source_dir.exists()
    assert not api._upload_job_path(job_id).exists()


def test_mark_stale_upload_jobs_deletes_abandoned_terminal_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "UPLOAD_JOB_TERMINAL_STALE_SECONDS", 1)
    job_id = "done-job"
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir(parents=True)
    (source_dir / "upload.wav").write_bytes(b"leftover-audio")
    api._write_upload_job(
        job_id,
        {
            "status": "done",
            "email": "advisor@example.com",
            "bundle": {"user_transcript": "Sensitive transcript."},
            "updated_at": (
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
        },
    )

    api._mark_stale_upload_jobs()

    assert not api._upload_job_path(job_id).exists()
    assert not source_dir.exists()


def test_delete_upload_job_strict_removes_all_sensitive_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    job_id = "completed-job"
    job_path = api._upload_job_path(job_id)
    api._write_upload_job(
        job_id,
        {
            "status": "done",
            "email": "advisor@example.com",
            "bundle": {"user_transcript": "Sensitive transcript."},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    temporary_job_path = job_path.with_suffix(".tmp")
    temporary_job_path.write_text("Sensitive temporary transcript.", encoding="utf-8")
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir()
    (source_dir / "upload.wav").write_bytes(b"sensitive-audio")
    work_dir = api._voice_work_dir(job_id)
    work_dir.mkdir()
    (work_dir / "transcription.wav").write_bytes(b"working-audio")

    removed = api._delete_upload_job(job_id, strict=True)

    assert removed is True
    assert not job_path.exists()
    assert not temporary_job_path.exists()
    assert not source_dir.exists()
    assert not work_dir.exists()


def test_delete_upload_job_keeps_terminal_state_when_raw_audio_cannot_be_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    job_id = "retryable-cleanup"
    job_path = api._upload_job_path(job_id)
    api._write_upload_job(
        job_id,
        {
            "status": "done",
            "email": "advisor@example.com",
            "bundle": {"user_transcript": "Sensitive transcript."},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir()
    (source_dir / "upload.wav").write_bytes(b"sensitive-audio")
    original_remove_voice_directory = api._remove_voice_directory

    def fail_source_deletion(path: Path, *, strict: bool = False) -> bool:
        if path == source_dir:
            raise api.VoiceSessionError("Raw audio could not be deleted.")
        return original_remove_voice_directory(path, strict=strict)

    monkeypatch.setattr(api, "_remove_voice_directory", fail_source_deletion)

    with pytest.raises(api.VoiceSessionError, match="Raw audio"):
        api._delete_upload_job(job_id, strict=True)

    assert source_dir.exists()
    assert job_path.exists()


def test_get_upload_audio_job_fails_closed_when_terminal_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    job_id = "completed-job"
    api._write_upload_job(
        job_id,
        {
            "status": "done",
            "email": user.email,
            "bundle": {"user_transcript": "Sensitive transcript."},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    cleanup_calls: list[tuple[str, bool]] = []

    def fail_cleanup(cleanup_job_id: str, *, strict: bool = False) -> bool:
        cleanup_calls.append((cleanup_job_id, strict))
        raise api.VoiceSessionError("Hosted Voice temporary data could not be deleted.")

    monkeypatch.setattr(api, "_delete_upload_job", fail_cleanup)

    with pytest.raises(HTTPException) as cleanup_error:
        api.get_upload_audio_job(job_id, user=user)

    assert cleanup_error.value.status_code == 503
    assert "could not be deleted" in str(cleanup_error.value.detail)
    assert cleanup_calls == [(job_id, True)]
    assert api._upload_job_path(job_id).exists()


def test_get_upload_audio_job_hides_locked_terminal_bundle_until_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = _patch_voice_retention_roots(tmp_path, monkeypatch)
    user = AuthenticatedUser(email="advisor@example.com")
    job_id = "locked-terminal-job"
    bundle = {"user_transcript": "Sensitive transcript."}
    api._write_upload_job(
        job_id,
        {
            "status": "done",
            "email": user.email,
            "bundle": bundle,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    lock_handle = api._acquire_voice_job_lock(job_id, blocking=True)
    assert lock_handle is not None

    try:
        locked_response = api.get_upload_audio_job(job_id, user=user)
    finally:
        api._release_voice_job_lock(lock_handle)

    locked_payload = json.loads(locked_response.body)
    assert locked_payload["status"] == "running"
    assert locked_payload["phase"] == "finalizing"
    assert "bundle" not in locked_payload
    assert b"Sensitive transcript" not in locked_response.body
    assert locked_response.headers["cache-control"] == "no-store, private"
    assert locked_response.headers["pragma"] == "no-cache"
    assert api._upload_job_path(job_id).exists()

    completed_response = api.get_upload_audio_job(job_id, user=user)
    completed_payload = json.loads(completed_response.body)

    assert completed_payload["status"] == "done"
    assert completed_payload["bundle"] == bundle
    assert completed_response.headers["cache-control"] == "no-store, private"
    assert completed_response.headers["pragma"] == "no-cache"
    assert not api._upload_job_path(job_id).exists()
    assert list(roots["jobs"].iterdir()) == []


def test_cleanup_voice_retention_state_removes_only_stale_hosted_voice_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "UPLOAD_JOB_STALE_SECONDS", 1)
    monkeypatch.setattr(api, "UPLOAD_JOB_TERMINAL_STALE_SECONDS", 1)
    monkeypatch.setattr(api, "CHUNKED_UPLOAD_STALE_SECONDS", 1)
    now = datetime.now(timezone.utc)
    stale_timestamp = now - timedelta(days=2)
    stale_epoch = stale_timestamp.timestamp()

    completed_job_id = "completed-job"
    api._write_upload_job(
        completed_job_id,
        {
            "status": "done",
            "email": "advisor@example.com",
            "bundle": {"user_transcript": "Sensitive transcript."},
            "updated_at": stale_timestamp.isoformat(),
        },
    )
    completed_job_temp = api._upload_job_path(completed_job_id).with_suffix(".tmp")
    completed_job_temp.write_text("Sensitive temporary transcript.", encoding="utf-8")
    completed_source_dir = api._uploaded_audio_source_dir(completed_job_id)
    completed_source_dir.mkdir()
    (completed_source_dir / "upload.wav").write_bytes(b"sensitive-audio")
    completed_work_dir = api._voice_work_dir(completed_job_id)
    completed_work_dir.mkdir()
    (completed_work_dir / "working.wav").write_bytes(b"working-audio")

    corrupt_job_path = roots["jobs"] / "corrupt-job.json"
    corrupt_job_path.write_text("{not-json", encoding="utf-8")
    os.utime(corrupt_job_path, (stale_epoch, stale_epoch))
    abandoned_temp_path = roots["jobs"] / "abandoned.tmp"
    abandoned_temp_path.write_text("Sensitive transcript fragment.", encoding="utf-8")
    os.utime(abandoned_temp_path, (stale_epoch, stale_epoch))

    orphan_source_dir = roots["sources"] / "orphan-source"
    orphan_source_dir.mkdir()
    orphan_source_file = orphan_source_dir / "upload.webm"
    orphan_source_file.write_bytes(b"orphan-audio")
    os.utime(orphan_source_file, (stale_epoch, stale_epoch))
    os.utime(orphan_source_dir, (stale_epoch, stale_epoch))
    orphan_work_dir = roots["work"] / "orphan-work"
    orphan_work_dir.mkdir()
    orphan_work_file = orphan_work_dir / "transcription.wav"
    orphan_work_file.write_bytes(b"orphan-work")
    os.utime(orphan_work_file, (stale_epoch, stale_epoch))
    os.utime(orphan_work_dir, (stale_epoch, stale_epoch))

    stale_chunk_id = "stale-upload"
    api._write_chunked_upload_metadata(
        stale_chunk_id,
        {
            "status": "uploading",
            "email": "advisor@example.com",
            "created_at": stale_timestamp.isoformat(),
            "updated_at": stale_timestamp.isoformat(),
        },
    )
    (api._chunked_upload_dir(stale_chunk_id) / "chunk-000000.part").write_bytes(
        b"stale-chunk"
    )
    corrupt_chunk_dir = roots["chunks"] / "corrupt-upload"
    corrupt_chunk_dir.mkdir()
    corrupt_chunk_metadata = corrupt_chunk_dir / "metadata.json"
    corrupt_chunk_metadata.write_text("{not-json", encoding="utf-8")
    os.utime(corrupt_chunk_metadata, (stale_epoch, stale_epoch))
    os.utime(corrupt_chunk_dir, (stale_epoch, stale_epoch))
    metadata_free_chunk_dir = roots["chunks"] / "metadata-free-upload"
    metadata_free_chunk_dir.mkdir()
    metadata_free_chunk_file = metadata_free_chunk_dir / "chunk-000000.part"
    metadata_free_chunk_file.write_bytes(b"orphan-chunk")
    os.utime(metadata_free_chunk_file, (stale_epoch, stale_epoch))
    os.utime(metadata_free_chunk_dir, (stale_epoch, stale_epoch))

    fresh_chunk_id = "fresh-upload"
    api._write_chunked_upload_metadata(
        fresh_chunk_id,
        {
            "status": "uploading",
            "email": "advisor@example.com",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )
    fresh_chunk_dir = api._chunked_upload_dir(fresh_chunk_id)
    (fresh_chunk_dir / "chunk-000000.part").write_bytes(b"fresh-chunk")

    hosted_interview_root = tmp_path / "hosted-interviews"
    hosted_interview_root.mkdir()
    interview_audio = hosted_interview_root / "recording.webm"
    interview_transcript = hosted_interview_root / "transcript.json"
    interview_audio.write_bytes(b"retained-interview-audio")
    interview_transcript.write_text(
        json.dumps({"transcript": "Retained interview transcript."}),
        encoding="utf-8",
    )

    api.cleanup_voice_retention_state(now=now)

    assert not api._upload_job_path(completed_job_id).exists()
    assert not completed_job_temp.exists()
    assert not completed_source_dir.exists()
    assert not completed_work_dir.exists()
    assert not corrupt_job_path.exists()
    assert not abandoned_temp_path.exists()
    assert not orphan_source_dir.exists()
    assert not orphan_work_dir.exists()
    assert not api._chunked_upload_dir(stale_chunk_id).exists()
    assert not corrupt_chunk_dir.exists()
    assert not metadata_free_chunk_dir.exists()
    assert fresh_chunk_dir.exists()
    assert interview_audio.read_bytes() == b"retained-interview-audio"
    assert json.loads(interview_transcript.read_text(encoding="utf-8")) == {
        "transcript": "Retained interview transcript."
    }


def test_cleanup_voice_retention_state_removes_invalid_stale_job_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "VOICE_ORPHAN_STALE_SECONDS", 1)
    now = datetime.now(timezone.utc)
    stale_epoch = (now - timedelta(seconds=5)).timestamp()
    invalid_temp_path = roots["jobs"] / "bad!.tmp"
    invalid_temp_path.write_text("Sensitive transcript fragment.", encoding="utf-8")
    os.utime(invalid_temp_path, (stale_epoch, stale_epoch))

    removed = api.cleanup_voice_retention_state(now=now)

    assert removed["job_temp_files"] == 1
    assert not invalid_temp_path.exists()


def test_cleanup_voice_retention_state_preserves_active_upload_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "UPLOAD_JOB_STALE_SECONDS", 1)
    now = datetime.now(timezone.utc)
    job_id = "active-job"
    api._write_upload_job(
        job_id,
        {
            "status": "running",
            "email": "advisor@example.com",
            "owner_pid": os.getpid(),
            "updated_at": (now - timedelta(days=2)).isoformat(),
        },
    )
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir()
    (source_dir / "upload.wav").write_bytes(b"active-audio")
    work_dir = api._voice_work_dir(job_id)
    work_dir.mkdir()
    (work_dir / "transcription.wav").write_bytes(b"active-working-audio")
    api._set_upload_job_active(job_id, active=True)

    try:
        api.cleanup_voice_retention_state(now=now)
    finally:
        api._set_upload_job_active(job_id, active=False)

    assert api._upload_job_path(job_id).exists()
    assert source_dir.exists()
    assert work_dir.exists()


def test_cleanup_voice_retention_state_retires_stale_alive_owner_without_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "VOICE_ORPHAN_STALE_SECONDS", 1)
    now = datetime.now(timezone.utc)
    job_id = "abandoned-alive-owner"
    api._write_upload_job(
        job_id,
        {
            "status": "running",
            "email": "advisor@example.com",
            "owner_pid": os.getpid(),
            "retention_lock_version": api.VOICE_RETENTION_LOCK_VERSION,
            "bundle": {"user_transcript": "Sensitive partial transcript."},
            "transcription_metadata": {"raw": "Sensitive metadata."},
            "updated_at": (now - timedelta(seconds=5)).isoformat(),
        },
    )
    job_temp_path = api._upload_job_path(job_id).with_suffix(".tmp")
    job_temp_path.write_text("Sensitive temporary transcript.", encoding="utf-8")
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir()
    (source_dir / "upload.wav").write_bytes(b"abandoned-audio")
    work_dir = api._voice_work_dir(job_id)
    work_dir.mkdir()
    (work_dir / "transcription.wav").write_bytes(b"abandoned-working-audio")

    api.cleanup_voice_retention_state(now=now)

    payload = api._read_upload_job(
        job_id,
        AuthenticatedUser(email="advisor@example.com"),
    )
    assert payload["status"] == "error"
    assert payload["previous_status"] == "running"
    assert "bundle" not in payload
    assert "transcription_metadata" not in payload
    assert not job_temp_path.exists()
    assert not source_dir.exists()
    assert not work_dir.exists()


def test_cleanup_voice_retention_state_preserves_fresh_alive_owner_grace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "VOICE_ORPHAN_STALE_SECONDS", 60)
    now = datetime.now(timezone.utc)
    job_id = "fresh-owned-job"
    api._write_upload_job(
        job_id,
        {
            "status": "queued",
            "email": "advisor@example.com",
            "owner_pid": os.getpid(),
            "retention_lock_version": api.VOICE_RETENTION_LOCK_VERSION,
            "updated_at": now.isoformat(),
        },
    )
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir()
    (source_dir / "upload.wav").write_bytes(b"queued-audio")

    api.cleanup_voice_retention_state(now=now)

    assert api._upload_job_path(job_id).exists()
    assert source_dir.exists()


def test_cleanup_voice_retention_state_preserves_cross_process_locked_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "VOICE_ORPHAN_STALE_SECONDS", 1)
    now = datetime.now(timezone.utc)
    job_id = "locked-job"
    api._write_upload_job(
        job_id,
        {
            "status": "running",
            "email": "advisor@example.com",
            "owner_pid": -1,
            "retention_lock_version": api.VOICE_RETENTION_LOCK_VERSION,
            "updated_at": (now - timedelta(seconds=5)).isoformat(),
        },
    )
    source_dir = api._uploaded_audio_source_dir(job_id)
    source_dir.mkdir()
    (source_dir / "upload.wav").write_bytes(b"active-audio")
    work_dir = api._voice_work_dir(job_id)
    work_dir.mkdir()
    (work_dir / "transcription.wav").write_bytes(b"active-working-audio")
    lock_handle = api._acquire_voice_job_lock(job_id, blocking=True)
    assert lock_handle is not None

    try:
        api.cleanup_voice_retention_state(now=now)
    finally:
        api._release_voice_job_lock(lock_handle)

    assert api._upload_job_path(job_id).exists()
    assert source_dir.exists()
    assert work_dir.exists()


def test_start_chunked_audio_upload_cleans_stale_upload_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _patch_voice_retention_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "CHUNKED_UPLOAD_STALE_SECONDS", 1)
    monkeypatch.setattr(api, "CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES", 5)
    user = AuthenticatedUser(email="advisor@example.com")
    token = api.issue_voice_launch_token(user=user)
    stale_upload_id = "stale-upload"
    stale_dir = api._chunked_upload_dir(stale_upload_id)
    api._write_chunked_upload_metadata(
        stale_upload_id,
        {
            "status": "uploading",
            "email": user.email.lower(),
            "filename": "old.wav",
            "content_type": "audio/wav",
            "total_bytes": 10,
            "total_chunks": 2,
            "chunk_size": 5,
            "language": "it",
            "source_metadata": {},
            "case_context": "",
            "received_chunks": [],
            "created_at": (
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
            "updated_at": (
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
        },
    )
    (stale_dir / "chunk-000000.part").write_bytes(b"stale")

    response = asyncio.run(
        api.start_chunked_audio_upload(
            launch_token=token,
            language="it",
            source_metadata_json="{}",
            filename="meeting.wav",
            content_type="audio/wav",
            total_bytes=10,
            total_chunks=2,
            user=user,
        )
    )
    body = json.loads(response.body)

    assert response.status_code == 201
    assert body["status"] == "ready"
    assert not stale_dir.exists()


def test_launch_token_rejects_wrong_or_expired_user(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CASE_NOTES_VOICE_TOKEN_ROOT", str(tmp_path))
    user = AuthenticatedUser(email="owner@example.com")
    other_user = AuthenticatedUser(email="other@example.com")
    now = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    token = api.issue_voice_launch_token(user=user, now=now)

    with pytest.raises(api.VoiceSessionError):
        api.verify_voice_launch_token(token=token, user=other_user, now=now)
    with pytest.raises(api.VoiceSessionError):
        api.verify_voice_launch_token(
            token=token,
            user=user,
            now=now + timedelta(seconds=api.TOKEN_TTL_SECONDS + 1),
        )


def test_browser_downloads_local_bundle_instead_of_posting_content() -> None:
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert "createZipBlob" in script
    assert "downloadZipBundle" in script
    assert "crc32" in script
    assert "/case-notes/api/voice/save" not in script
    assert "/case-notes/api/voice/upload" in script
    assert "/case-notes/api/voice/live-chunk" not in script
    assert 'id="save"' not in (ROOT / "templates" / "case_notes_voice.html").read_text(
        encoding="utf-8"
    )
    assert "saveButton" not in script
    assert "case-notes-audio-" in script
    assert "case-notes-voice-${compactTimestamp}.${audioExtensionForMimeType" in script
    assert "case-notes-voice-${compactTimestamp}.zip" in script
    assert "case_notes_hosted_voice" in script
    assert "Transcription coverage checks passed" in script
    assert '["complete", "warning"].includes(status)' in script
    assert "Audio ZIP bundle downloaded with transcription warnings" in script
    assert "No ZIP was downloaded" in script


def test_browser_retries_large_uploads_with_chunked_fallback() -> None:
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert "audioUploadChunkBytes = 32 * 1024 * 1024" in script
    assert "shouldRetryUploadAsChunks" in script
    assert "submitChunkedAudioUpload" in script
    assert "payload = await submitSingleAudioUpload(file, uploadSourceMetadata)" in (
        script
    )
    assert "return error?.status === 413" in script
    assert "[408, 413, 429, 502, 503, 504]" not in script
    assert "Retrying in upload parts" in script
    assert "/case-notes/api/voice/upload/chunks/start" in script
    assert "/case-notes/api/voice/upload/chunks/${encodeURIComponent(uploadId)}" in (
        script
    )
    assert (
        "/case-notes/api/voice/upload/chunks/${encodeURIComponent(uploadId)}/finish"
        in script
    )
    assert "Upload complete. Preparing transcription..." in script


def test_browser_microphone_failure_keeps_screen_capture_flow() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert "getUserMedia" in script
    assert "getDisplayMedia" in script
    assert "openMicrophoneStream" in script
    assert "openOptionalMicrophoneStream" in script
    assert "openLiveCaptureStreams" in script
    assert "openTabAudioStream" not in script
    assert "openAudioInputStream" not in script
    assert "cleanupCaptureStreams" in script
    assert "Microphone blocked for this browser/site" in script
    assert "No audio was captured." in script
    assert "Live capture requires a shared screen or browser tab." in script
    assert "updateConnectButtonState();" in script
    assert "Text mode" not in page
    assert "manual" not in script.lower()


def test_transcription_capture_uses_capture_monitor_without_model_panel() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert 'aria-label="Capture status"' in page
    assert "Clara Voice Capture" in page
    assert "Registra una trascrizione live" not in page
    assert (
        "In modalita solo ascolto Clara cattura l'audio senza intervenire." not in page
    )
    assert "Parla del caso in modo naturale" not in page
    assert 'id="transcriptPanels" aria-hidden="true"' in page
    assert "<h2>Transcript</h2>" in page
    assert "Last capture" in page
    assert "Last transcript" not in page
    assert "Consultant transcript" not in page
    assert "<h2>Clara replies</h2>" not in page
    assert "Voice model transcript" not in page
    assert "<label>Model" not in page
    assert "Extract candidates" not in page
    assert "Analyze transcript" not in page
    assert 'id="extract"' not in page
    assert "Extraction JSON" not in page
    assert "Analysis JSON" not in page
    assert "<label>Audio source" not in page
    assert '<option value="tab_audio">Browser tab audio</option>' not in page
    assert "<span>Audio</span>" in page
    assert "<span>Microphone</span>" not in page
    assert 'id="monitorConnection"' in page
    assert 'id="monitorMicrophone"' in page
    assert 'id="monitorTranscript"' in page
    assert 'id="monitorCapturedLabel"' in page
    assert 'id="monitorCaptured"' in page
    assert 'id="assistantPanel"' not in page
    assert "Source details" not in page
    assert 'id="sourceType"' not in page
    assert 'id="language"' in page
    assert 'id="uploadKind"' not in page
    assert "Recording type" not in page
    assert "listen_only" not in page
    assert "Call metadata" in page
    assert 'id="sourceTitle"' in page
    assert 'id="sourceParticipants"' in page
    assert 'id="sourceNotes"' in page
    assert "Speakers / participants" in page
    assert 'id="sourceRole"' not in page
    assert "Role / function" not in page
    assert 'id="sourceInterviewer"' not in page
    assert 'id="sourceType"' not in page
    assert 'id="sourceDate"' not in page
    assert "Confidentiality" not in page
    assert "sourceConfidentiality" not in page
    capture_block = page.split('aria-label="Capture input"', 1)[1].split(
        'id="status"', 1
    )[0]
    assert 'id="uploadKind"' not in capture_block
    assert 'id="language"' not in capture_block
    assert 'id="mode"' not in capture_block
    assert "Live mode" not in capture_block
    assert 'id="audioSource"' not in capture_block
    assert "Start live capture" in capture_block
    assert "Transcribe file" in capture_block
    assert "case-notes-voice.js?v=voice-retention-20260715-v1" in page
    assert "listen_only" not in script
    assert 'transcriptPanels?.classList.add("is-hidden")' in script
    assert 'transcriptPanels?.setAttribute("aria-hidden", "true")' in script
    assert "restoreSelectPreference(audioSourceSelect" not in script
    assert "restoreSelectPreference(languageSelect" in script
    assert '"clara.voice.audioSource"' not in script
    assert '"clara.voice.language"' in script
    assert "selectedCaptureMode()" not in script
    assert 'new URLSearchParams(window.location.search).get("mode")' not in script
    assert "applyInitialModeFromQuery()" not in script
    assert "syncRecordingTypeFromMode()" not in script
    assert "replaceModeInUrl" not in script
    assert "data-realtime-transcription-model" in page
    assert (
        "Recording live session with live timing. Clara will clean-transcribe the audio after you stop."
        in script
    )
    assert (
        "Clara is transcribing the live audio stream and committing at pauses."
        not in script
    )
    assert "extractButton" not in script
    assert "requestExtraction" not in script
    assert "parseExtractionJson" not in script
    assert "response.output_text" not in script
    assert "startRealtimeCommitTimer" in script
    assert 'fetch("/case-notes/api/voice/realtime-transcription/session"' in script
    assert "RTCPeerConnection" in script
    assert "realtime_timing_plus_record_then_upload" in script
    assert "timed_transcript_segments" in script
    assert "realtime_transcription_events" in script
    assert "realtime_user_transcript" in script
    assert "transcript_video_sync" in script
    assert "function startActiveSlideTracking(stream)" in script
    assert 'track.addEventListener("capturehandlechange"' in script
    assert "track?.getCaptureHandle?.()" in script
    assert "active_slide_timeline" in script
    assert "active_slide_id" in script
    assert "active_slide_title" in script
    assert "timedTranscriptSegmentWithActiveSlide" in script
    assert 'commit_strategy: "webrtc_audio_periodic_commit"' in script
    assert 'type: "input_audio_buffer.commit"' in script
    assert "waitForRealtimeCommitToResolve(finalCommit)" in script
    assert "final_commit_wait_timeout" in script
    assert "750" not in script
    assert "maybeCommitOnSilence" not in script
    assert "audioActiveRmsThreshold = 0.006" in script
    assert "speechLikeRmsThreshold" not in script
    assert "silenceCommitMs" not in script
    assert "silenceAutoStopMs = 5 * 60 * 1000" in script
    assert "maybeAutoStopOnSilence" in script
    assert "lastMeaningfulActivityAt" in script
    assert "audioTelemetryIntervalMs = 250" in script
    assert "commit_strategy" in script
    assert "record_then_upload" in script
    assert "client_silence_vad" not in script
    assert "chooseCompletedTranscript" not in script
    assert "transcriptDeltaPreferredEvents" not in script
    assert "wordCount" in script
    assert "words / ${elapsed}s" in script
    assert "activeUploadJobStatus" in script
    assert "setUploadMonitor" in script
    assert "uploadProgressText" in script
    assert 'monitorCapturedLabel.textContent = "Progress"' in script
    assert 'monitorCapturedLabel.textContent = "Captured"' in script
    assert "0 words" in page
    assert "0 segments / 0 chars" not in page
    start_capture_block = script.split("function startCaptureStatus()", 1)[1].split(
        "async function start", 1
    )[0]
    assert "8000" not in start_capture_block
    assert "debriefFollowUpsEnabled" not in script
    assert "conversation.item.input_audio_transcription.delta" in script
    assert "conversation.item.input_audio_transcription.completed" in script
    assert "startListenOnlyRecorder" not in script
    assert "MediaRecorder" in script
    assert "startLiveAudioRecording" in script
    assert "stopLiveAudioRecording" in script
    assert "selectedAudioSource" not in script
    assert "Tab audio active" not in script
    assert "Screen audio + microphone active" in script
    assert "openLiveCaptureStreams" in script
    assert "createMixedAudioStream" in script
    assert "live_screen_context" in script
    assert "startCaptureStatus();" in script
    assert "/case-notes/api/voice/session" not in script
    assert "new RTCPeerConnection" in script
    assert "/case-notes/api/voice/live-chunk" not in script
    assert "liveChunkMs" not in script
    assert "transcribeLiveChunk" not in script
    assert "Stop & download" in page
    assert "Stopped. ZIP bundle downloaded." in script
    assert 'stopButton.textContent = "Download bundle"' in script
    assert "bundleDownloadReady" in script
    assert "URL.revokeObjectURL(url)" in script
    assert "60000" in script
    assert "waitForUploadJob" in script
    assert "downloadAudioBundle" in script
    assert "uploadLiveAudioRecording" in script
    assert "if (liveAudioBlob?.size)" in script
    assert "Uploading recorded audio for transcription..." in script
    assert "Stopped. Audio ZIP bundle downloaded." in script
    assert "zipEntries.push({ name: audioFileName, data: liveAudioBlob })" in script
    assert "/case-notes/api/voice/upload/${encodeURIComponent(jobId)}" in script
    assert "Audio uploaded. Transcription is running..." in script
    assert "progress_percent" in script
    assert "collectSourceMetadata" in script
    assert "recording_type: uploadKindSelect" not in script
    assert "uploadKindSelect" not in script
    assert "source_metadata" in script
    assert "source_metadata_json" in script
    assert "language: selectedLanguage()" in script
    assert 'document.getElementById("language").value' not in script
    assert "buildClaraReviewMarkdown" not in script
    assert "clara_review_markdown" not in script
    assert "Well-Supported Points" not in script


def test_voice_capture_saves_raw_transcript_on_stop_without_manual_button() -> None:
    page = (ROOT / "templates" / "case_notes_voice.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "case-notes-voice.js").read_text(
        encoding="utf-8"
    )

    assert "function save()" in script
    assert "await save()" in script
    assert "createLiveAudioFile" in script
    assert "submitAudioUpload" in script
    assert "Recorded audio transcription failed" in script
    assert "hasDownloadableBundle" in script
    assert "prepareBundleDownloadButton" in script
    assert "capture_started_at" in script
    assert "capture_stopped_at" in script
    assert "capture_elapsed_seconds" in script
    assert "source_metadata" in script
    assert "audio_file_name" in script
    assert "audio_content_type" in script
    assert "audio_recording_bytes" in script
    assert "original_audio_file_name" in script
    assert "clara_review_markdown" not in script
    assert "capture_telemetry" in script
    assert "raw_transcript_chunks" not in script
    assert "transcriptDeltaStartedAt" not in script
    assert "function markCaptureStarted(startedAt = new Date())" in script
    assert "markCaptureStarted(screenCaptureStartedAt || new Date())" in script
    assert "flushDraftTranscriptSegment" not in script
    assert "buildTranscriptTiming" not in script
    assert "transcript_processing_note" in script
    assert (
        "Hosted Voice Capture records live screen video and automatically captured audio mechanically"
        in script
    )
    assert "assigns speakers" in script
    assert "silence_auto_stop_ms" in script
    assert "auto_stop_triggered" in script
    assert "speech_like_rms_threshold" not in script
    assert "Stopped automatically after 5 minutes of silence" in script
    assert "Finalizing transcript before download" not in script
    assert "No captured session is available to download." in script
    assert 'id="save"' not in page
    assert "saveButton" not in script


def test_clara_permission_covers_server_workflows_but_not_downloads() -> None:
    structure = json.loads(
        (ROOT / "config" / "permission_structure.json").read_text(encoding="utf-8")
    )

    assert "/downloads/clara" not in structure["clara"]
    assert "/static/shared/clara/downloads" not in structure["clara"]
    assert "/case-notes/voice" in structure["clara"]
    assert "/case-notes/api/voice" in structure["clara"]
    assert "/case-notes/api/attribute-reporting" in structure["clara"]
