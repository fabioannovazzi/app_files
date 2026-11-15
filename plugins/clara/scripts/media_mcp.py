"""Local media selection and durable operator handoffs; hosted processing is explicit."""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request

from jsonschema import Draft202012Validator, ValidationError

__all__ = ["MediaApp", "main"]
ROOT = Path(__file__).resolve().parents[1]
URI = "ui://clara/media-v1.html"
MIME = "text/html;profile=mcp-app"
MAX_CHUNK = 262144
MAX_FILE = 256 * 1024 * 1024
AUDIO = {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def video_module() -> Any:
    path = ROOT / "skills/research-video/scripts/research_video.py"
    spec = importlib.util.spec_from_file_location("clara_media_video", path)
    if spec is None or spec.loader is None:
        raise ValueError("Narration workflow is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def narration_payload(work: Path) -> dict[str, Any]:
    """Verify the existing exact narration approval before any transmission."""
    video = video_module()
    intake = video._read_json(work / "run_intake.json")
    video._verify_visual_inventory(work, intake)
    video._verify_approval(work, intake)
    return video._read_json(work / "mparanza_voice_request.json")


class MediaApp:
    """Persist selection separately from consent, execution and delivered output."""

    def __init__(self, state_root: Path | None = None) -> None:
        self.state_root = state_root or Path(
            os.environ.get(
                "CLARA_MEDIA_STATE_DIR",
                str(Path.home() / ".local/share/mparanza/clara/media"),
            )
        )
        string = {"type": "string", "minLength": 1, "maxLength": 4000}
        session = {"type": "string", "pattern": "^[a-f0-9]{32}$"}
        definitions = [
            (
                "open",
                {
                    "operation": {"enum": ["transcribe", "deck_feedback", "narration"]},
                    "work_dir": string,
                    "source": string,
                    "language": {"enum": ["it", "en", "fr", "de", "es"]},
                },
                ["operation", "work_dir"],
                "model",
            ),
            ("status", {"session": session}, ["session"], "both"),
            (
                "save",
                {
                    "session": session,
                    "filename": string,
                    "index": {"type": "integer", "minimum": 0},
                    "data": {"type": "string", "maxLength": 350000},
                    "final": {"type": "boolean"},
                },
                ["session", "filename", "index", "data", "final"],
                "app",
            ),
            ("confirm", {"session": session}, ["session"], "app"),
            (
                "run",
                {"session": session, "credential_file": string},
                ["session", "credential_file"],
                "model",
            ),
        ]
        descriptions = {
            "open": "Open the local Clara media panel for one explicit work folder. Optionally bind a selected audio source. Narration uses the already-approved run in work_dir. No external request.",
            "status": "Resume a saved media handoff and inspect its actual state. Does not retry processing.",
            "save": "Save user-selected audio bytes locally in ordered bounded chunks. No upload to any external service.",
            "confirm": "Record the panel user's request to process the selected file with Mparanza/OpenAI. Returns a continuation prompt; does not send audio.",
            "run": "Process the confirmed selection using an explicitly supplied private Mparanza session-cookie file. Never request cookie contents in chat or extract browser credentials. Saves and imports the returned bundle locally. Does not launch a browser. Repeated completed calls return saved output; uncertain calls are not retried.",
        }
        self.tools = []
        for operation, properties, required, visibility in definitions:
            ui: dict[str, Any] = {
                "visibility": ["app", "model"] if visibility == "both" else [visibility]
            }
            if operation in {"open", "status"}:
                ui["resourceUri"] = URI
            self.tools.append(
                {
                    "name": "clara_media_" + operation,
                    "description": descriptions[operation],
                    "inputSchema": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                    "annotations": {
                        "readOnlyHint": operation == "status",
                        "destructiveHint": False,
                        "openWorldHint": operation == "run",
                    },
                    "_meta": {"ui": ui},
                }
            )

    def _path(self, session: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", session):
            raise ValueError("Unknown media session")
        return self.state_root / (session + ".json")

    def _read(self, session: str) -> dict[str, Any]:
        return json.loads(self._path(session).read_text(encoding="utf-8"))

    def _write(self, state: dict[str, Any]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self._path(state["session"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.chmod(0o600)
        temporary.replace(path)

    @staticmethod
    def result(state: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: state[key] for key in ("session", "operation", "language", "status")
        }
        public["filename"] = Path(state["source"]).name if state.get("source") else ""
        public["output"] = state.get("output", "")
        return {
            "content": [{"type": "text", "text": "Clara media: " + state["status"]}],
            "structuredContent": public,
            "_meta": {"media": public},
        }

    def open(
        self, operation: str, work_dir: str, source: str = "", language: str = "en"
    ) -> dict[str, Any]:
        work = Path(work_dir)
        if not work.is_absolute() or not work.is_dir():
            raise ValueError("Select an existing absolute work folder")
        work = work.resolve()
        if operation not in {"transcribe", "deck_feedback", "narration"}:
            raise ValueError("Unsupported media operation")
        state: dict[str, Any] = {
            "session": secrets.token_hex(16),
            "operation": operation,
            "work_dir": str(work),
            "language": language,
            "status": "select_file",
            "chunks": [],
            "size": 0,
        }
        if operation == "narration":
            narration_payload(work)
            source = str(work / "mparanza_voice_request.json")
        if source:
            path = Path(source)
            if not path.is_absolute() or not path.is_file():
                raise ValueError("Select an existing absolute source file")
            if operation != "narration" and path.suffix.lower() not in AUDIO:
                raise ValueError("Select a supported audio or recording file")
            state.update(
                source=str(path.resolve()), sha256=digest(path), status="ready"
            )
        self._write(state)
        return self.result(state)

    def status(self, session: str) -> dict[str, Any]:
        return self.result(self._read(session))

    def save(
        self, session: str, filename: str, index: int, data: str, final: bool
    ) -> dict[str, Any]:
        state = self._read(session)
        if state["operation"] == "narration" or state["status"] not in {
            "select_file",
            "receiving",
            "ready",
        }:
            raise ValueError("This session cannot receive another file")
        name = Path(filename).name
        if name != filename or "\\" in name or Path(name).suffix.lower() not in AUDIO:
            raise ValueError("Select a supported recording filename")
        try:
            chunk = base64.b64decode(data, validate=True)
        except binascii.Error as exc:
            raise ValueError("Invalid file chunk") from exc
        if not chunk or len(chunk) > MAX_CHUNK:
            raise ValueError("File chunk is empty or too large")
        signature = hashlib.sha256(chunk).hexdigest()
        # A lost acknowledgment must not duplicate bytes in a retained upload.
        if index < len(state["chunks"]):
            if state.get("filename") == name and state["chunks"][index] == {
                "sha256": signature,
                "final": final,
            }:
                return self.result(state)
            raise ValueError("Chunk differs from the saved selection")
        if (
            state["status"] == "ready"
            or index != len(state["chunks"])
            or (state.get("filename") and state["filename"] != name)
        ):
            raise ValueError("Resume the same file in order or open a new selection")
        if state["size"] + len(chunk) > MAX_FILE:
            raise ValueError(
                "File exceeds 256 MB; select it from its local path in chat"
            )
        folder = Path(state["work_dir"]) / ".clara-media" / session
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        part = folder / "recording.part"
        # Truncate a write whose receipt was interrupted before acknowledging it.
        with part.open("r+b" if part.exists() else "w+b") as stream:
            stream.truncate(state["size"])
            stream.seek(state["size"])
            stream.write(chunk)
        state["chunks"].append({"sha256": signature, "final": final})
        state.update(filename=name, size=state["size"] + len(chunk), status="receiving")
        if final:
            state.update(source=str(part), sha256=digest(part), status="ready")
            # Keep a stable path through receipt persistence, then use original extension for processing.
            target = folder / ("recording" + Path(name).suffix.lower())
            target.write_bytes(part.read_bytes())
            state["source"] = str(target)
        self._write(state)
        return self.result(state)

    def confirm(self, session: str) -> dict[str, Any]:
        state = self._read(session)
        if state["status"] not in {"ready", "confirmed", "authentication_required"}:
            raise ValueError("Select a complete file before continuing")
        if digest(Path(state["source"])) != state["sha256"]:
            raise ValueError("The selected file changed; reopen it for review")
        state["status"] = "confirmed"
        self._write(state)
        return self.result(state)

    def run(self, session: str, credential_file: str) -> dict[str, Any]:
        lock = self._path(session).with_suffix(".lock")
        try:
            handle = lock.open("x")
        except FileExistsError as exc:
            raise ValueError(
                "This session is already running; inspect its saved state"
            ) from exc
        try:
            with handle:
                return self._run(session, credential_file)
        finally:
            lock.unlink()

    def _run(self, session: str, credential_file: str) -> dict[str, Any]:
        state = self._read(session)
        if state["status"] == "complete":
            if (
                not Path(state["output"]).is_file()
                or digest(Path(state["output"])) != state["output_sha256"]
            ):
                raise ValueError("Saved output changed; inspect it before continuing")
            return self.result(state)
        if state["status"] not in {"confirmed", "authentication_required"}:
            raise ValueError(
                "Processing is not confirmed or its previous outcome needs review"
            )
        from launch_hosted_voice import read_private_text_file

        try:
            cookie = read_private_text_file(
                Path(credential_file), label="Mparanza session"
            )
        except (OSError, ValueError):
            state["status"] = "authentication_required"
            self._write(state)
            return self.result(state)
        source = Path(state["source"])
        if digest(source) != state["sha256"]:
            raise ValueError("Selected source changed; reopen it before processing")
        if state["operation"] == "narration":
            narration_payload(Path(state["work_dir"]))
        if state["operation"] != "narration":
            state["audio_source"] = str(self.prepare_audio(state))
        state["status"] = "processing"
        self._write(state)
        try:
            output = self.process(state, cookie)
        except (OSError, ValueError, RuntimeError):
            state["status"] = "needs_review"
            self._write(state)
            raise ValueError(
                "Processing was not confirmed. Retained files and state need review before retrying."
            ) from None
        state.update(
            status="complete", output=str(output), output_sha256=digest(output)
        )
        self._write(state)
        return self.result(state)

    @staticmethod
    def prepare_audio(state: dict[str, Any]) -> Path:
        """Strip screen/video tracks locally before any hosted transcription."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ValueError(
                "Local audio extraction needs ffmpeg; the recording has not been sent"
            )
        folder = Path(state["work_dir"]) / ".clara-media" / state["session"]
        folder.mkdir(parents=True, exist_ok=True)
        audio = folder / "transcription-audio.wav"
        result = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                state["source"],
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "pcm_s16le",
                str(audio),
            ],
            capture_output=True,
            timeout=300,
            check=False,
        )
        if result.returncode or not audio.is_file() or audio.stat().st_size <= 44:
            raise ValueError(
                "No usable audio track; the original recording remains local"
            )
        return audio

    @staticmethod
    def process(state: dict[str, Any], cookie: str) -> Path:
        """Use the existing authenticated engines; no manual downloads or browser launcher."""
        from upload_hosted_audio import (
            _new_opener,
            bind_session_cookie,
            upload_hosted_audio,
        )

        work = Path(state["work_dir"])
        output = work / ".clara-media" / state["session"]
        output.mkdir(parents=True, exist_ok=True)
        if state["operation"] == "narration":
            payload = narration_payload(work)
            opener = _new_opener()
            bind_session_cookie(
                opener, base_url="https://mparanza.com", cookie_header=cookie
            )
            request = Request(
                "https://mparanza.com/case-notes/api/research-video/voice",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Mparanza-Action": "research-video-voice-v1",
                },
                method="POST",
            )
            with opener.open(request, timeout=300) as response:
                data = response.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise ValueError("Narration response exceeds the supported size")
            bundle = output / "narration.zip"
            bundle.write_bytes(data)
            video_module().attach_hosted_voice(work, bundle)
            return work / "hosted_voice_manifest.json"
        is_case = (work / "case_manifest.json").is_file()
        result = upload_hosted_audio(
            case_dir=work,
            audio_path=Path(state["audio_source"]),
            cookie_header=cookie,
            output_dir=output,
            language=state["language"],
            include_case_context=False,
            import_bundle=is_case,
            source_metadata={"title": Path(state["source"]).stem},
        )
        if not is_case:
            from import_hosted_voice_bundle_to_folder import (
                import_hosted_voice_bundle_to_folder,
            )

            import_hosted_voice_bundle_to_folder(work, result.bundle_path)
        return result.bundle_path

    @staticmethod
    def resource() -> dict[str, Any]:
        html = (ROOT / "ui/media.html").read_text(encoding="utf-8")
        font = ROOT / "vendor/modules/courseware/assets/InstrumentSans-Regular.ttf"
        if not font.is_file():
            font = (
                ROOT.parent
                / "_shared/vendor/modules/courseware/assets/InstrumentSans-Regular.ttf"
            )
        html = html.replace("__FONT__", base64.b64encode(font.read_bytes()).decode())
        return {
            "contents": [
                {
                    "uri": URI,
                    "mimeType": MIME,
                    "text": html,
                    "_meta": {
                        "ui": {
                            "csp": {"connectDomains": [], "resourceDomains": []},
                            "permissions": {"microphone": {}},
                        },
                        "openai/ui": {
                            "preferredDisplayMode": "fullscreen",
                            "availableDisplayModes": ["inline", "fullscreen"],
                        },
                    },
                }
            ]
        }

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        method, params = request["method"], request.get("params", {})
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "serverInfo": {"name": "clara-media", "version": "1.0.0"},
                "capabilities": {"tools": {}, "resources": {}},
            }
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "resources/list":
            return {
                "resources": [{"uri": URI, "name": "Clara media", "mimeType": MIME}]
            }
        if method in {"resources/templates/list", "prompts/list"}:
            return {
                "resourceTemplates" if method.startswith("resources") else "prompts": []
            }
        if method == "resources/read" and params.get("uri") == URI:
            return self.resource()
        if method == "tools/call":
            tool = next(
                (t for t in self.tools if t["name"] == params.get("name")), None
            )
            if tool:
                args = params.get("arguments", {})
                Draft202012Validator(tool["inputSchema"]).validate(args)
                return getattr(self, tool["name"].removeprefix("clara_media_"))(**args)
        if method == "ping":
            return {}
        raise ValueError("Unknown media method")


def main() -> None:
    app = MediaApp()
    for line in sys.stdin:
        request: dict[str, Any] = {}
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            if "id" not in request:
                continue
            result = app.dispatch(request)
            reply = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except (ValueError, OSError, ValidationError) as exc:
            reply = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32602,
                    "message": (
                        "Invalid media request"
                        if isinstance(exc, ValidationError)
                        else str(exc)
                    ),
                },
            }
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
