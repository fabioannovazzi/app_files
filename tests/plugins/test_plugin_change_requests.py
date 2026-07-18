from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_CLIENT = ROOT / "plugins" / "clara" / "scripts" / "change_requests.py"
VERA_CLIENT = ROOT / "plugins" / "vera" / "scripts" / "change_requests.py"


def load_client() -> Any:
    spec = importlib.util.spec_from_file_location(
        "mparanza_plugin_change_requests", CLARA_CLIENT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return self.body if amount < 0 else self.body[:amount]


def _concurrent_submit_worker(
    plugin_root: str,
    request_path: str,
    stable_root: str,
    change_request_id: str,
    posted_event: Any,
    release_event: Any,
) -> None:
    os.environ["MPARANZA_CHANGE_REQUEST_DATA"] = stable_root
    client = load_client()

    def opener(*_args: object, **_kwargs: object) -> FakeResponse:
        posted_event.set()
        if release_event is not None:
            assert release_event.wait(5)
        return FakeResponse(
            {
                "change_request_id": change_request_id,
                "status_token": f"token-{change_request_id}",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        )

    client.submit_problem(
        Path(plugin_root),
        Path(request_path),
        base_url="http://localhost:8080",
        opener=opener,
    )


def write_plugin(root: Path, name: str, version: str = "1.2.3") -> Path:
    plugin_root = root / name
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"name": name, "version": version}), encoding="utf-8"
    )
    return plugin_root


def read_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_clara_and_vera_change_request_clients_stay_identical() -> None:
    assert CLARA_CLIENT.read_bytes() == VERA_CLIENT.read_bytes()


def test_submit_problem_persists_before_post_and_syncs_both_state_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "clara")
    request_path = tmp_path / "request.json"
    request_payload = {
        "title": "Workbook export failed",
        "expected": "A workbook",
        "actual": "No file was produced",
    }
    request_path.write_text(json.dumps(request_payload), encoding="utf-8")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    posted: list[dict[str, Any]] = []

    def opener(request: Any, **_kwargs: object) -> FakeResponse:
        stable_state = read_state(stable_root / "clara" / "state.json")
        explicit_state = read_state(plugin_data / "change-requests" / "state.json")
        assert stable_state == explicit_state
        assert stable_state["requests"][0]["status"] == "pending"
        assert "pending_payload" in stable_state["requests"][0]
        assert request.full_url == "http://localhost:8080/api/change-requests"
        posted.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(
            {
                "change_request_id": "CR-123",
                "status_token": "status-secret",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        )

    receipt = client.submit_problem(
        plugin_root,
        request_path,
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=opener,
        now=100.0,
    )

    assert receipt["change_request_id"] == "CR-123"
    assert posted == [
        {
            "schema_version": 1,
            "submission_id": receipt["submission_id"],
            "kind": "problem",
            "plugin": "clara",
            "plugin_version": "1.2.3",
            "request": request_payload,
        }
    ]
    stable_state = read_state(stable_root / "clara" / "state.json")
    explicit_state = read_state(plugin_data / "change-requests" / "state.json")
    assert stable_state == explicit_state
    assert stable_state["requests"][0]["change_request_id"] == "CR-123"
    assert "pending_payload" not in stable_state["requests"][0]
    assert (stable_root / "clara" / "state.json").stat().st_mode & 0o777 == 0o600


def test_submit_problem_retries_with_same_persisted_submission_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_root = write_plugin(tmp_path, "vera")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"actual": "Parser stopped"}), encoding="utf-8")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("offline")

    with pytest.raises(client.ChangeRequestError, match="Could not reach"):
        client.submit_problem(
            plugin_root,
            request_path,
            base_url="http://127.0.0.1:8000",
            opener=unavailable,
            now=200.0,
        )
    state_after_failure = read_state(stable_root / "vera" / "state.json")
    submission_id = state_after_failure["requests"][0]["submission_id"]

    def retry_opener(request: Any, **_kwargs: object) -> FakeResponse:
        assert (
            json.loads(request.data.decode("utf-8"))["submission_id"] == submission_id
        )
        return FakeResponse(
            {
                "change_request_id": "CR-7",
                "status_token": "retry-token",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        )

    receipt = client.submit_problem(
        plugin_root,
        request_path,
        base_url="http://127.0.0.1:8000",
        opener=retry_opener,
        now=201.0,
    )

    assert receipt["submission_id"] == submission_id
    assert len(read_state(stable_root / "vera" / "state.json")["requests"]) == 1

    def must_not_post(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A stored receipt should make a retry local")

    repeated = client.submit_problem(
        plugin_root,
        request_path,
        base_url="http://127.0.0.1:8000",
        opener=must_not_post,
        now=202.0,
    )
    assert repeated == receipt


def test_parallel_processes_preserve_both_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("This regression test requires fork-capable process locking.")
    context = multiprocessing.get_context("fork")
    stable_root = tmp_path / "stable"
    plugin_root = write_plugin(tmp_path, "clara")
    first_request = tmp_path / "first.json"
    second_request = tmp_path / "second.json"
    first_request.write_text(json.dumps({"actual": "First"}), encoding="utf-8")
    second_request.write_text(json.dumps({"actual": "Second"}), encoding="utf-8")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    first_posted = context.Event()
    second_posted = context.Event()
    release_first = context.Event()
    first_process = context.Process(
        target=_concurrent_submit_worker,
        args=(
            str(plugin_root),
            str(first_request),
            str(stable_root),
            "CR-1",
            first_posted,
            release_first,
        ),
    )
    second_process = context.Process(
        target=_concurrent_submit_worker,
        args=(
            str(plugin_root),
            str(second_request),
            str(stable_root),
            "CR-2",
            second_posted,
            None,
        ),
    )

    first_process.start()
    assert first_posted.wait(5)
    second_process.start()
    second_process.join(5)
    release_first.set()
    first_process.join(5)

    assert first_process.exitcode == 0
    assert second_process.exitcode == 0
    state = read_state(stable_root / "clara" / "state.json")
    assert {entry["change_request_id"] for entry in state["requests"]} == {
        "CR-1",
        "CR-2",
    }


def test_start_interview_persists_receipt_before_opening_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    posted: list[dict[str, Any]] = []
    opened: list[str] = []

    def opener(request: Any, **_kwargs: object) -> FakeResponse:
        assert request.full_url.endswith("/api/change-requests/interviews")
        posted.append(json.loads(request.data.decode("utf-8")))
        assert (
            read_state(stable_root / "vera" / "state.json")["requests"][0]["status"]
            == "pending"
        )
        return FakeResponse(
            {
                "schema_version": 1,
                "change_request_id": "CR-88",
                "status": "open",
                "status_token": "interview-token",
                "interview_url": "http://localhost:8080/change-requests/interviews/session-1",
            }
        )

    def open_browser(url: str) -> None:
        stored = read_state(stable_root / "vera" / "state.json")["requests"][0]
        assert stored["change_request_id"] == "CR-88"
        assert "pending_payload" not in stored
        opened.append(url)

    receipt = client.start_interview(
        plugin_root,
        "Add a consolidated client deadline view",
        language="it",
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=opener,
        browser_opener=open_browser,
        now=300.0,
    )

    assert posted == [
        {
            "schema_version": 1,
            "submission_id": receipt["submission_id"],
            "plugin": "vera",
            "plugin_version": "2.0.0",
            "opportunity": "Add a consolidated client deadline view",
            "language": "it",
        }
    ]
    assert opened == ["http://localhost:8080/change-requests/interviews/session-1"]
    assert read_state(stable_root / "vera" / "state.json") == read_state(
        plugin_data / "change-requests" / "state.json"
    )


def test_check_fixed_requests_emits_exact_message_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "clara")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"actual": "Wrong total"}), encoding="utf-8")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))

    receipt = client.submit_problem(
        plugin_root,
        request_path,
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=lambda *_args, **_kwargs: FakeResponse(
            {
                "change_request_id": "CR-123",
                "status_token": "fixed-token",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        ),
        now=400.0,
    )

    def status_opener(request: Any, **_kwargs: object) -> FakeResponse:
        assert json.loads(request.data.decode("utf-8")) == {
            "requests": [
                {
                    "change_request_id": receipt["change_request_id"],
                    "status_token": receipt["status_token"],
                }
            ]
        }
        return FakeResponse(
            {
                "requests": [
                    {
                        "change_request_id": "CR-123",
                        "found": True,
                        "status": "fixed",
                        "fixed": True,
                        "fixed_version": "1.3.0",
                        "install_url": "https://chatgpt.com/plugins/clara",
                    }
                ]
            }
        )

    message = client.check_fixed_requests(
        plugin_root,
        plugin_data,
        opener=status_opener,
        now=500.0,
        base_url="http://localhost:8080",
    )

    assert message == "The problem you reported as CR-123 is fixed. Update now?"
    stable_state = read_state(stable_root / "clara" / "state.json")
    explicit_state = read_state(plugin_data / "change-requests" / "state.json")
    assert stable_state == explicit_state
    assert stable_state["requests"][0]["fixed_notified_at"] == 500.0

    def must_not_poll(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A fixed request must be notified only once")

    assert (
        client.check_fixed_requests(
            plugin_root,
            plugin_data,
            opener=must_not_poll,
            now=501.0,
            base_url="http://localhost:8080",
        )
        is None
    )


def test_hook_visible_state_merges_request_created_without_plugin_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "hook-plugin-data"
    plugin_root = write_plugin(tmp_path, "vera")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"actual": "Missing row"}), encoding="utf-8")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))

    client.submit_problem(
        plugin_root,
        request_path,
        base_url="http://localhost:8080",
        opener=lambda *_args, **_kwargs: FakeResponse(
            {
                "change_request_id": "CR-45",
                "status_token": "bridge-token",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        ),
        now=600.0,
    )
    assert not (plugin_data / "change-requests" / "state.json").exists()

    message = client.check_fixed_requests(
        plugin_root,
        plugin_data,
        base_url="http://localhost:8080",
        opener=lambda *_args, **_kwargs: FakeResponse(
            {
                "requests": [
                    {
                        "change_request_id": "CR-45",
                        "found": True,
                        "status": "open",
                        "fixed": False,
                        "fixed_version": None,
                        "install_url": None,
                    }
                ]
            }
        ),
        now=601.0,
    )

    assert message is None
    assert read_state(stable_root / "vera" / "state.json") == read_state(
        plugin_data / "change-requests" / "state.json"
    )


def test_start_interview_rejects_non_mparanza_interview_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "clara")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    opened: list[str] = []

    with pytest.raises(client.ChangeRequestError, match="not hosted by Mparanza"):
        client.start_interview(
            plugin_root,
            "Add one more export format",
            base_url="http://localhost:8080",
            opener=lambda *_args, **_kwargs: FakeResponse(
                {
                    "schema_version": 1,
                    "change_request_id": "CR-90",
                    "status": "open",
                    "status_token": "interview-token",
                    "interview_url": "https://example.com/interview/session-1",
                }
            ),
            browser_opener=opened.append,
        )

    assert opened == []


def test_client_rejects_unapproved_remote_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "clara")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"actual": "Failure"}), encoding="utf-8")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))

    with pytest.raises(client.ChangeRequestError, match="must be https://mparanza.com"):
        client.submit_problem(
            plugin_root,
            request_path,
            base_url="https://example.com",
            opener=lambda *_args, **_kwargs: None,
        )
