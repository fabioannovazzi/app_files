from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "plugins" / "clara" / "scripts" / "manage_hosted_interview.py"


def load_client() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_hosted_interview_client_tests", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class FakeOpener:
    def __init__(self, response: FakeResponse | BaseException) -> None:
        self.response = response
        self.addheaders: list[tuple[str, str]] = []

    def open(self, *_args: object, **_kwargs: object) -> FakeResponse:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://mparanza.com/", "https://mparanza.com"),
        ("https://www.mparanza.com", "https://www.mparanza.com"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
        ("http://localhost:9000/", "http://localhost:9000"),
    ],
)
def test_normalize_base_url_accepts_only_expected_origins(
    value: str, expected: str
) -> None:
    client = load_client()

    result = client._normalize_base_url(value)

    assert result == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://mparanza.com",
        "https://attacker.example",
        "https://mparanza.com:444",
        "https://user:password@mparanza.com",
        "https://mparanza.com/path",
        "https://mparanza.com:not-a-port",
        "file:///tmp/server",
    ],
)
def test_normalize_base_url_rejects_cookie_exfiltration_origins(value: str) -> None:
    client = load_client()

    with pytest.raises(client.HostedInterviewClientError):
        client._normalize_base_url(value)


def test_extract_magic_link_rejects_non_mparanza_origin() -> None:
    client = load_client()

    with pytest.raises(client.HostedInterviewClientError):
        client._extract_magic_link(
            "https://attacker.example/auth/magic/consume?token=secret"
        )


def test_authenticate_opener_sets_cookie_without_logging_value(caplog) -> None:
    client = load_client()
    opener = client._new_opener()

    with caplog.at_level(logging.INFO):
        client.authenticate_opener(opener, cookie_header="session=secret")

    request = urllib.request.Request("https://mparanza.com/case-notes/api/voice")
    handler = next(
        item
        for item in opener.handlers
        if isinstance(item, client._OriginBoundCookieHeader)
    )
    handler.https_request(request)

    assert request.get_header("Cookie") == "session=secret"
    assert all(name.lower() != "cookie" for name, _value in opener.addheaders)
    assert "secret" not in caplog.text


def test_cookie_header_is_stripped_from_cross_origin_redirect() -> None:
    client = load_client()
    handler = client._OriginBoundCookieHeader("session=secret", "https://mparanza.com")
    original = urllib.request.Request(
        "https://mparanza.com/case-notes/api/voice/interviews"
    )
    handler.https_request(original)
    redirected = urllib.request.HTTPRedirectHandler().redirect_request(
        original,
        None,
        302,
        "Found",
        {},
        "https://attacker.example/collect",
    )
    assert redirected is not None

    handler.https_request(redirected)

    assert original.get_header("Cookie") == "session=secret"
    assert redirected.get_header("Cookie") is None


def test_prepare_custom_interview_uses_authenticated_admin_endpoint(
    monkeypatch,
) -> None:
    client = load_client()
    observed: dict[str, Any] = {}

    def fake_request_json(_opener, **kwargs):
        observed.update(kwargs)
        return {"public_url": "https://mparanza.com/case-notes/interview/token"}

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.prepare_custom_interview(
        object(),
        brief={"interview_campaign_id": "operations-interview-v1"},
    )

    assert result["public_url"].endswith("/token")
    assert observed["method"] == "POST"
    assert observed["url"].endswith("/case-notes/api/voice/interviews")


def test_list_interview_campaigns_uses_registered_campaign_endpoint(
    monkeypatch,
) -> None:
    client = load_client()
    observed: dict[str, Any] = {}

    def fake_request_json(_opener, **kwargs):
        observed.update(kwargs)
        return [{"interview_campaign_id": "operations-interview-v1"}]

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.list_interview_campaigns(object())

    assert result == [{"interview_campaign_id": "operations-interview-v1"}]
    assert observed["url"].endswith("/case-notes/api/voice/interviews/campaigns")


@pytest.mark.parametrize(
    ("function_name", "artifact"),
    [("export_interview_bundle", "bundle"), ("export_interview_review", "review")],
)
def test_export_interview_artifact_uses_private_admin_endpoint(
    monkeypatch, function_name: str, artifact: str
) -> None:
    client = load_client()
    observed: dict[str, Any] = {}

    def fake_request_json(_opener, **kwargs):
        observed.update(kwargs)
        return {artifact: {}}

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = getattr(client, function_name)(object(), token_or_url="token-123")

    assert result == {artifact: {}}
    assert observed["url"].endswith(
        f"/case-notes/api/voice/interviews/token-123/{artifact}"
    )


def test_request_json_surfaces_server_detail_without_secret_echo() -> None:
    client = load_client()
    error = urllib.error.HTTPError(
        "https://mparanza.com/case-notes/api/voice/interviews",
        403,
        "Forbidden",
        hdrs=None,
        fp=BytesIO(b'{"detail":"permission denied"}'),
    )

    with pytest.raises(client.HostedInterviewClientError, match="permission denied"):
        client._request_json(
            FakeOpener(error),
            url="https://mparanza.com/case-notes/api/voice/interviews",
        )


def test_request_json_rejects_non_json_response() -> None:
    client = load_client()

    with pytest.raises(client.HostedInterviewClientError, match="not valid JSON"):
        client._request_json(
            FakeOpener(FakeResponse(b"not-json")),
            url="https://mparanza.com/case-notes/api/voice/interviews/campaigns",
        )


def test_interview_source_receipt_is_restricted_and_returns_url(tmp_path: Path) -> None:
    client = load_client()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {"public_url": "https://mparanza.com/case-notes/interview/token-123"}
        ),
        encoding="utf-8",
    )
    receipt.chmod(0o644)
    args = argparse.Namespace(receipt=receipt, participant_link_file=None)

    result = client._interview_source_from_args(args)

    assert result.endswith("/token-123")
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


def test_private_json_output_is_mode_0600(tmp_path: Path) -> None:
    client = load_client()
    output = tmp_path / "private.json"

    client._write_private_json(output, {"token": "secret"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"token": "secret"}
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_sensitive_output_cannot_fall_back_to_logs() -> None:
    client = load_client()

    with pytest.raises(client.HostedInterviewClientError, match="--output"):
        client._log_or_write({"public_url": "secret"}, None)


def test_prepare_campaign_cli_requires_private_output() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "prepare-campaign",
            "operations-interview-v1",
            "--case-id",
            "participant-001",
            "--participant-name",
            "Participant",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--output" in result.stderr


def test_prepare_campaign_cli_writes_receipt_without_logging_url(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    client = load_client()
    output = tmp_path / "receipt.json"
    participant_url = "https://mparanza.com/case-notes/interview/secret-token"
    monkeypatch.setattr(client, "_new_opener", object)
    monkeypatch.setattr(client, "authenticate_opener", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        client,
        "prepare_campaign_interview",
        lambda *_args, **_kwargs: {"public_url": participant_url},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "prepare-campaign",
            "operations-interview-v1",
            "--case-id",
            "participant-001",
            "--participant-name",
            "Participant",
            "--output",
            str(output),
        ],
    )

    with caplog.at_level(logging.INFO):
        result = client.main()

    assert result == 0
    assert (
        json.loads(output.read_text(encoding="utf-8"))["public_url"] == participant_url
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert participant_url not in caplog.text
