from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import ssl
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

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


def _concurrent_prompt_reservation_worker(
    plugin_root: str,
    stable_root: str,
    plugin_data: str,
    checked_at: float,
    ready_event: Any,
    start_event: Any,
    result_queue: Any,
) -> None:
    os.environ["MPARANZA_CHANGE_REQUEST_DATA"] = stable_root
    client = load_client()
    ready_event.set()
    assert start_event.wait(5)
    result = client.reserve_suggestion_prompt(
        Path(plugin_root),
        plugin_data=Path(plugin_data),
        now=checked_at,
    )
    result_queue.put(result["ask"])


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


def certificate_verification_error(verify_code: int) -> ssl.SSLCertVerificationError:
    error = ssl.SSLCertVerificationError(1, "certificate verify failed")
    error.verify_code = verify_code
    error.verify_message = "Basic Constraints of CA cert not marked critical"
    return error


def _write_noncritical_ca_tls_material(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Write a valid leaf and its deliberately malformed test CA."""

    valid_from = datetime(2020, 1, 1, tzinfo=timezone.utc)
    valid_until = datetime(2100, 1, 1, tzinfo=timezone.utc)
    ca_key = ec.derive_private_key(1, ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca_certificate = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(valid_from)
        .not_valid_after(valid_until)
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=1),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf_key = ec.derive_private_key(2, ec.SECP256R1())
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mparanza.com")])
    leaf_certificate = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(2)
        .not_valid_before(valid_from)
        .not_valid_after(valid_until)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("mparanza.com")]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = tmp_path / "noncritical-ca.pem"
    certificate_path = tmp_path / "mparanza.pem"
    key_path = tmp_path / "mparanza-key.pem"
    ca_path.write_bytes(ca_certificate.public_bytes(serialization.Encoding.PEM))
    certificate_path.write_bytes(
        leaf_certificate.public_bytes(serialization.Encoding.PEM)
    )
    key_path.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ca_path, certificate_path, key_path


def _complete_memory_bio_handshake(
    client_context: ssl.SSLContext, server_context: ssl.SSLContext
) -> None:
    """Complete one client/server TLS handshake without opening a socket."""

    client_in = ssl.MemoryBIO()
    client_out = ssl.MemoryBIO()
    server_in = ssl.MemoryBIO()
    server_out = ssl.MemoryBIO()
    client = client_context.wrap_bio(
        client_in,
        client_out,
        server_side=False,
        server_hostname="mparanza.com",
    )
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    client_done = False
    server_done = False
    for _attempt in range(20):
        if not client_done:
            try:
                client.do_handshake()
                client_done = True
            except ssl.SSLWantReadError:
                pass
        client_bytes = client_out.read()
        if client_bytes:
            server_in.write(client_bytes)
        if not server_done:
            try:
                server.do_handshake()
                server_done = True
            except ssl.SSLWantReadError:
                pass
        server_bytes = server_out.read()
        if server_bytes:
            client_in.write(server_bytes)
        if client_done and server_done:
            return
    raise AssertionError("In-memory TLS handshake did not complete.")


class _MemoryBioUrlopen:
    """Exercise urlopen calls against one in-memory malformed-CA TLS peer."""

    def __init__(
        self,
        ca_path: Path,
        certificate_path: Path,
        key_path: Path,
        create_default_context: Any,
    ) -> None:
        self.ca_path = ca_path
        self.create_default_context = create_default_context
        self.server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server_context.load_cert_chain(certificate_path, key_path)
        self.verify_flags: list[ssl.VerifyFlags] = []
        self.verify_codes: list[int] = []

    def __call__(self, _request: Any, **kwargs: Any) -> FakeResponse:
        context = kwargs.get("context")
        if context is None:
            context = self.create_default_context(cafile=self.ca_path)
            context.verify_flags |= ssl.VERIFY_X509_STRICT
        assert isinstance(context, ssl.SSLContext)
        self.verify_flags.append(context.verify_flags)
        try:
            _complete_memory_bio_handshake(context, self.server_context)
        except ssl.SSLCertVerificationError as exc:
            self.verify_codes.append(exc.verify_code)
            raise urllib.error.URLError(exc) from exc
        return FakeResponse(
            {
                "schema_version": 1,
                "change_request_id": "CR-89",
                "status": "open",
                "status_token": "interview-token",
                "interview_url": "https://mparanza.com/interviews/session-89",
            }
        )


def test_clara_and_vera_change_request_clients_stay_identical() -> None:
    assert CLARA_CLIENT.read_bytes() == VERA_CLIENT.read_bytes()


def test_reserve_suggestion_prompt_cli_returns_machine_readable_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "clara")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    monkeypatch.setenv("PLUGIN_DATA", str(plugin_data))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "change_requests.py",
            "--plugin-root",
            str(plugin_root),
            "reserve-suggestion-prompt",
        ],
    )

    exit_code = client.main()

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ask"] is True
    assert output["cooldown_seconds"] == 14 * 24 * 60 * 60
    assert read_state(stable_root / "clara" / "state.json") == read_state(
        plugin_data / "change-requests" / "state.json"
    )


def test_submit_suggestion_cli_dispatches_capability_request_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera")
    request_path = tmp_path / "suggestion.json"
    request_path.write_text(
        json.dumps({"desired": "A deadline view"}), encoding="utf-8"
    )
    calls: list[tuple[Path, Path]] = []

    def submit_suggestion(
        plugin: Path, request: Path, **_kwargs: object
    ) -> dict[str, Any]:
        calls.append((plugin, request))
        return {
            "change_request_id": "CR-9",
            "status": "open",
        }

    monkeypatch.setattr(client, "submit_suggestion", submit_suggestion)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "change_requests.py",
            "--plugin-root",
            str(plugin_root),
            "submit-suggestion",
            "--request",
            str(request_path),
        ],
    )

    exit_code = client.main()

    assert exit_code == 0
    assert calls == [(plugin_root, request_path)]
    assert json.loads(capsys.readouterr().out)["change_request_id"] == "CR-9"


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


def test_submit_suggestion_posts_capability_and_reuses_durable_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "clara")
    request_path = tmp_path / "suggestion.json"
    request_payload = {
        "title": "Add a consolidated deadline view",
        "desired": "Show every client deadline in one reviewed table",
    }
    request_path.write_text(json.dumps(request_payload), encoding="utf-8")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    posted: list[dict[str, Any]] = []

    def opener(request: Any, **_kwargs: object) -> FakeResponse:
        stable_state = read_state(stable_root / "clara" / "state.json")
        explicit_state = read_state(plugin_data / "change-requests" / "state.json")
        assert stable_state == explicit_state
        assert stable_state["requests"][0]["kind"] == "capability"
        posted.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(
            {
                "change_request_id": "CR-124",
                "status_token": "suggestion-secret",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        )

    receipt = client.submit_suggestion(
        plugin_root,
        request_path,
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=opener,
        now=250.0,
    )

    assert posted == [
        {
            "schema_version": 1,
            "submission_id": receipt["submission_id"],
            "kind": "capability",
            "plugin": "clara",
            "plugin_version": "1.2.3",
            "request": request_payload,
        }
    ]

    def must_not_post(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A stored suggestion receipt should make a retry local")

    repeated = client.submit_suggestion(
        plugin_root,
        request_path,
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=must_not_post,
        now=251.0,
    )
    assert repeated == receipt


def test_first_suggestion_prompt_reservation_persists_to_both_state_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "vera")
    first_at = 1_000.0
    cooldown = 14 * 24 * 60 * 60
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))

    result = client.reserve_suggestion_prompt(
        plugin_root,
        plugin_data=plugin_data,
        now=first_at,
    )

    assert result == {
        "ask": True,
        "cooldown_seconds": cooldown,
        "reserved_at": first_at,
        "next_eligible_at": first_at + cooldown,
    }
    stable_state = read_state(stable_root / "vera" / "state.json")
    explicit_state = read_state(plugin_data / "change-requests" / "state.json")
    assert stable_state == explicit_state
    assert stable_state["suggestion_prompt_reserved_at"] == first_at
    assert (stable_root / "vera" / "state.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("failed_store", ["stable", "plugin_data"])
def test_suggestion_prompt_reservation_succeeds_with_one_writable_state_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_store: str,
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "clara")
    first_at = 2_000.0
    stable_path = stable_root / "clara" / "state.json"
    plugin_data_path = plugin_data / "change-requests" / "state.json"
    failed_path = stable_path if failed_store == "stable" else plugin_data_path
    successful_path = plugin_data_path if failed_store == "stable" else stable_path
    original_write = client._write_one_state
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))

    def fail_one_replica(path: Path, state: dict[str, Any]) -> None:
        if path == failed_path:
            raise OSError("replica unavailable")
        original_write(path, state)

    monkeypatch.setattr(client, "_write_one_state", fail_one_replica)

    result = client.reserve_suggestion_prompt(
        plugin_root,
        plugin_data=plugin_data,
        now=first_at,
    )

    assert result["ask"] is True
    assert read_state(successful_path)["suggestion_prompt_reserved_at"] == first_at
    assert not failed_path.exists()


def test_suggestion_prompt_reservation_skips_when_state_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera")
    cooldown = 14 * 24 * 60 * 60

    def fail_to_open_state_lock(_state_dir: Path) -> tuple[Any, Any]:
        raise OSError("read-only runtime")

    monkeypatch.setattr(client, "_open_state_lock", fail_to_open_state_lock)

    result = client.reserve_suggestion_prompt(plugin_root, now=2_000.0)

    assert result == {
        "ask": False,
        "cooldown_seconds": cooldown,
        "reason": "state_unavailable",
    }


@pytest.mark.parametrize(
    ("elapsed_seconds", "expected_ask", "expected_reserved_at"),
    [
        (14 * 24 * 60 * 60 - 1, False, 1_000.0),
        (14 * 24 * 60 * 60, True, 1_000.0 + 14 * 24 * 60 * 60),
    ],
)
def test_suggestion_prompt_reservation_enforces_exact_fourteen_day_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    elapsed_seconds: int,
    expected_ask: bool,
    expected_reserved_at: float,
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "clara")
    first_at = 1_000.0
    cooldown = 14 * 24 * 60 * 60
    stable_path = stable_root / "clara" / "state.json"
    stable_path.parent.mkdir(parents=True)
    stable_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plugin": "clara",
                "requests": [],
                "suggestion_prompt_reserved_at": first_at,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))

    result = client.reserve_suggestion_prompt(
        plugin_root,
        plugin_data=plugin_data,
        now=first_at + elapsed_seconds,
    )

    assert result == {
        "ask": expected_ask,
        "cooldown_seconds": cooldown,
        "reserved_at": expected_reserved_at,
        "next_eligible_at": expected_reserved_at + cooldown,
    }
    assert read_state(stable_path) == read_state(
        plugin_data / "change-requests" / "state.json"
    )


def test_parallel_prompt_reservations_admit_exactly_one_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("This regression test requires fork-capable process locking.")
    context = multiprocessing.get_context("fork")
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    plugin_root = write_plugin(tmp_path, "clara")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    first_ready = context.Event()
    second_ready = context.Event()
    start_event = context.Event()
    result_queue = context.Queue()
    args = (
        str(plugin_root),
        str(stable_root),
        str(plugin_data),
        5_000.0,
    )
    first_process = context.Process(
        target=_concurrent_prompt_reservation_worker,
        args=(*args, first_ready, start_event, result_queue),
    )
    second_process = context.Process(
        target=_concurrent_prompt_reservation_worker,
        args=(*args, second_ready, start_event, result_queue),
    )

    first_process.start()
    second_process.start()
    assert first_ready.wait(5)
    assert second_ready.wait(5)
    start_event.set()
    first_process.join(5)
    second_process.join(5)

    assert first_process.exitcode == 0
    assert second_process.exitcode == 0
    assert sorted([result_queue.get(timeout=5), result_queue.get(timeout=5)]) == [
        False,
        True,
    ]
    assert read_state(stable_root / "clara" / "state.json") == read_state(
        plugin_data / "change-requests" / "state.json"
    )


def test_prompt_reservation_deduplicates_plugin_data_alias_of_stable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("This regression test requires fork-capable process locking.")
    context = multiprocessing.get_context("fork")
    stable_root = tmp_path / "stable"
    stable_state_dir = stable_root / "clara"
    stable_state_dir.mkdir(parents=True)
    plugin_data = tmp_path / "plugin-data"
    plugin_data.mkdir()
    (plugin_data / "change-requests").symlink_to(
        stable_state_dir, target_is_directory=True
    )
    plugin_root = write_plugin(tmp_path, "clara")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    ready_event = context.Event()
    start_event = context.Event()
    result_queue = context.Queue()
    process = context.Process(
        target=_concurrent_prompt_reservation_worker,
        args=(
            str(plugin_root),
            str(stable_root),
            str(plugin_data),
            5_000.0,
            ready_event,
            start_event,
            result_queue,
        ),
    )

    process.start()
    assert ready_event.wait(5)
    start_event.set()
    process.join(5)
    if process.is_alive():
        process.terminate()
        process.join(5)

    assert process.exitcode == 0
    assert result_queue.get(timeout=5) is True


def test_prompt_reservation_stops_when_a_shared_lock_is_contended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    plugin_root = write_plugin(tmp_path, "clara")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    monkeypatch.setattr(client.tempfile, "gettempdir", lambda: str(temporary_root))
    attempts = 0
    released: list[int] = []

    class FakeLockFile:
        closed = False

        def close(self) -> None:
            self.closed = True

        def fileno(self) -> int:
            return 42

        def seek(self, _offset: int) -> None:
            return None

    class FakeLockModule:
        LOCK_UN = 8
        LK_UNLCK = 0

        def flock(self, descriptor: int, operation: int) -> None:
            assert operation == self.LOCK_UN
            released.append(descriptor)

        def locking(self, descriptor: int, operation: int, amount: int) -> None:
            assert operation == self.LK_UNLCK
            assert amount == 1
            released.append(descriptor)

    first_lock_file = FakeLockFile()

    def contend_on_second_lock(_state_dir: Path) -> tuple[Any, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return first_lock_file, FakeLockModule()
        raise client._StateLockContentionError("synthetic contention")

    monkeypatch.setattr(client, "_open_state_lock", contend_on_second_lock)

    with pytest.raises(client.ChangeRequestError, match="state is busy"):
        client.reserve_suggestion_prompt(plugin_root, now=5_000.0)

    assert attempts == 2
    assert released == [42]
    assert first_lock_file.closed is True


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


def test_start_interview_falls_back_when_primary_state_is_unwritable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = load_client()
    blocked_root = tmp_path / "blocked-state-root"
    blocked_root.write_text("not a directory", encoding="utf-8")
    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    opened: list[str] = []
    observed_state_paths: list[Path] = []
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(blocked_root))
    monkeypatch.setattr(client.tempfile, "gettempdir", lambda: str(temporary_root))

    def opener(_request: Any, **_kwargs: object) -> FakeResponse:
        state_paths = list(
            temporary_root.glob("mparanza-change-requests-*/vera/state.json")
        )
        assert len(state_paths) == 1
        observed_state_paths.extend(state_paths)
        pending = read_state(state_paths[0])["requests"][0]
        assert pending["status"] == "pending"
        assert "pending_payload" in pending
        return FakeResponse(
            {
                "schema_version": 1,
                "change_request_id": "CR-90",
                "status": "open",
                "status_token": "interview-token",
                "interview_url": "http://localhost:8080/change-requests/interviews/session-90",
            }
        )

    receipt = client.start_interview(
        plugin_root,
        "General Vera improvement suggestion",
        base_url="http://localhost:8080",
        opener=opener,
        browser_opener=opened.append,
        now=300.0,
    )

    assert receipt["change_request_id"] == "CR-90"
    assert opened == ["http://localhost:8080/change-requests/interviews/session-90"]
    assert len(observed_state_paths) == 1
    state_path = observed_state_paths[0]
    stored = read_state(state_path)["requests"][0]
    assert stored["change_request_id"] == "CR-90"
    assert "pending_payload" not in stored
    assert state_path.parent.parent.stat().st_mode & 0o777 == 0o700
    assert state_path.parent.stat().st_mode & 0o777 == 0o700
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert state_path.with_name(".state.lock").stat().st_mode & 0o777 == 0o600


def test_submit_problem_falls_back_when_primary_state_is_unwritable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = load_client()
    blocked_root = tmp_path / "blocked-state-root"
    blocked_root.write_text("not a directory", encoding="utf-8")
    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    request_path = tmp_path / "problem.json"
    request_path.write_text(
        json.dumps({"actual": "Synthetic read-only state failure"}),
        encoding="utf-8",
    )
    posted: list[dict[str, Any]] = []
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(blocked_root))
    monkeypatch.setattr(client.tempfile, "gettempdir", lambda: str(temporary_root))

    def opener(request: Any, **_kwargs: object) -> FakeResponse:
        posted.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(
            {
                "change_request_id": "CR-91",
                "status_token": "problem-token",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        )

    receipt = client.submit_problem(
        plugin_root,
        request_path,
        base_url="http://localhost:8080",
        opener=opener,
        now=400.0,
    )

    assert receipt["change_request_id"] == "CR-91"
    assert len(posted) == 1
    assert posted[0]["submission_id"] == receipt["submission_id"]
    state_paths = list(
        temporary_root.glob("mparanza-change-requests-*/vera/state.json")
    )
    assert len(state_paths) == 1
    stored = read_state(state_paths[0])["requests"][0]
    assert stored["change_request_id"] == "CR-91"
    assert "pending_payload" not in stored


def test_start_interview_preserves_fallback_receipt_when_stable_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable-root"
    stable_root.write_text("temporarily read only", encoding="utf-8")
    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    posted: list[dict[str, Any]] = []
    opened: list[str] = []
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    monkeypatch.setattr(client.tempfile, "gettempdir", lambda: str(temporary_root))

    def opener(request: Any, **_kwargs: object) -> FakeResponse:
        posted.append(json.loads(request.data.decode("utf-8")))
        stable_root.unlink()
        stable_root.mkdir()
        return FakeResponse(
            {
                "schema_version": 1,
                "change_request_id": "CR-92",
                "status": "open",
                "status_token": "interview-token",
                "interview_url": "http://localhost:8080/change-requests/interviews/session-92",
            }
        )

    first_receipt = client.start_interview(
        plugin_root,
        "General Vera improvement suggestion",
        base_url="http://localhost:8080",
        opener=opener,
        browser_opener=opened.append,
        now=500.0,
    )

    def must_not_post(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A recovered receipt must prevent a duplicate POST")

    second_receipt = client.start_interview(
        plugin_root,
        "General Vera improvement suggestion",
        base_url="http://localhost:8080",
        opener=must_not_post,
        browser_opener=opened.append,
        now=501.0,
    )

    temporary_paths = list(
        temporary_root.glob("mparanza-change-requests-*/vera/state.json")
    )
    assert len(posted) == 1
    assert first_receipt == second_receipt
    assert first_receipt["change_request_id"] == "CR-92"
    assert len(temporary_paths) == 1
    assert read_state(stable_root / "vera" / "state.json") == read_state(
        temporary_paths[0]
    )
    assert opened == [
        "http://localhost:8080/change-requests/interviews/session-92",
        "http://localhost:8080/change-requests/interviews/session-92",
    ]


def test_completed_receipt_dominates_equal_timestamp_pending_replica(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = load_client()
    stable_root = tmp_path / "stable"
    plugin_data = tmp_path / "plugin-data"
    blocked_temporary_root = tmp_path / "blocked-temporary"
    blocked_temporary_root.write_text("not a directory", encoding="utf-8")
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    posted: list[dict[str, Any]] = []
    opened: list[str] = []
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(stable_root))
    monkeypatch.setattr(
        client.tempfile, "gettempdir", lambda: str(blocked_temporary_root)
    )

    def opener(request: Any, **_kwargs: object) -> FakeResponse:
        posted.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(
            {
                "schema_version": 1,
                "change_request_id": "CR-94",
                "status": "open",
                "status_token": "interview-token",
                "interview_url": "http://localhost:8080/change-requests/interviews/session-94",
            }
        )

    client.start_interview(
        plugin_root,
        "General Vera improvement suggestion",
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=opener,
        browser_opener=opened.append,
        now=700.0,
    )
    completed_state = read_state(stable_root / "vera" / "state.json")
    pending_entry = dict(completed_state["requests"][0])
    for field in (
        "change_request_id",
        "status_token",
        "interview_url",
        "fixed",
        "fixed_version",
        "install_url",
    ):
        pending_entry.pop(field, None)
    pending_entry["status"] = "pending"
    pending_entry["pending_payload"] = posted[0]
    (plugin_data / "change-requests" / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plugin": "vera",
                "requests": [pending_entry],
            }
        ),
        encoding="utf-8",
    )

    def must_not_post(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A completed receipt must prevent a duplicate POST")

    receipt = client.start_interview(
        plugin_root,
        "General Vera improvement suggestion",
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=must_not_post,
        browser_opener=opened.append,
        now=701.0,
    )

    repaired_stable = read_state(stable_root / "vera" / "state.json")["requests"][0]
    repaired_plugin = read_state(plugin_data / "change-requests" / "state.json")[
        "requests"
    ][0]
    assert len(posted) == 1
    assert receipt["change_request_id"] == "CR-94"
    assert receipt["status"] == "open"
    assert repaired_stable == repaired_plugin
    assert "pending_payload" not in repaired_stable
    assert opened == [
        "http://localhost:8080/change-requests/interviews/session-94",
        "http://localhost:8080/change-requests/interviews/session-94",
    ]


def test_submit_problem_uses_plugin_data_when_home_and_temp_are_unwritable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = load_client()
    blocked_stable_root = tmp_path / "blocked-stable"
    blocked_stable_root.write_text("not a directory", encoding="utf-8")
    blocked_temporary_root = tmp_path / "blocked-temporary"
    blocked_temporary_root.write_text("not a directory", encoding="utf-8")
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    plugin_data = tmp_path / "plugin-data"
    request_path = tmp_path / "problem.json"
    request_path.write_text(
        json.dumps({"actual": "Synthetic read-only state failure"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(blocked_stable_root))
    monkeypatch.setattr(
        client.tempfile, "gettempdir", lambda: str(blocked_temporary_root)
    )

    receipt = client.submit_problem(
        plugin_root,
        request_path,
        plugin_data=plugin_data,
        base_url="http://localhost:8080",
        opener=lambda *_args, **_kwargs: FakeResponse(
            {
                "change_request_id": "CR-93",
                "status_token": "problem-token",
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        ),
        now=600.0,
    )

    state_path = plugin_data / "change-requests" / "state.json"
    assert receipt["change_request_id"] == "CR-93"
    assert read_state(state_path)["requests"][0]["change_request_id"] == "CR-93"
    assert state_path.with_name(".state.lock").stat().st_mode & 0o777 == 0o600


def test_fallback_rejects_symlink_without_touching_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = load_client()
    blocked_stable_root = tmp_path / "blocked-stable"
    blocked_stable_root.write_text("not a directory", encoding="utf-8")
    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o755)
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    request_path = tmp_path / "problem.json"
    request_path.write_text(
        json.dumps({"actual": "Synthetic read-only state failure"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(blocked_stable_root))
    monkeypatch.setattr(client.tempfile, "gettempdir", lambda: str(temporary_root))
    fallback_state_dir = client._temporary_state_dir("vera")
    fallback_state_dir.parent.mkdir(mode=0o700)
    fallback_state_dir.symlink_to(victim, target_is_directory=True)

    with pytest.raises(
        client.ChangeRequestError,
        match="Could not access a writable change-request state directory",
    ):
        client.submit_problem(
            plugin_root,
            request_path,
            base_url="http://localhost:8080",
            opener=lambda *_args, **_kwargs: FakeResponse({}),
        )

    assert victim.stat().st_mode & 0o777 == 0o755
    assert list(victim.iterdir()) == []


def test_start_interview_retries_default_https_once_for_noncritical_ca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    default_context = ssl.create_default_context()
    calls: list[dict[str, Any]] = []
    opened: list[str] = []

    def urlopen(_request: Any, **kwargs: Any) -> FakeResponse:
        calls.append(kwargs)
        if len(calls) == 1:
            raise urllib.error.URLError(certificate_verification_error(89))
        return FakeResponse(
            {
                "schema_version": 1,
                "change_request_id": "CR-89",
                "status": "open",
                "status_token": "interview-token",
                "interview_url": "https://mparanza.com/case-notes/interview/session-89",
            }
        )

    monkeypatch.setattr(client.urllib.request, "urlopen", urlopen)

    receipt = client.start_interview(
        plugin_root,
        "General Vera improvement suggestion",
        browser_opener=opened.append,
        now=300.0,
    )

    compatibility_context = calls[1]["context"]
    assert receipt["change_request_id"] == "CR-89"
    assert opened == ["https://mparanza.com/case-notes/interview/session-89"]
    assert calls[0] == {"timeout": client.DEFAULT_TIMEOUT_SECONDS}
    assert calls[1]["timeout"] == client.DEFAULT_TIMEOUT_SECONDS
    assert isinstance(compatibility_context, ssl.SSLContext)
    assert compatibility_context.verify_flags == (
        default_context.verify_flags & ~ssl.VERIFY_X509_STRICT
    )
    assert compatibility_context.verify_mode == ssl.CERT_REQUIRED
    assert compatibility_context.check_hostname is True


@pytest.mark.skipif(
    ssl.OPENSSL_VERSION_INFO < (3, 0, 0),
    reason="OpenSSL 3 is required for verification error code 89.",
)
def test_start_interview_retries_real_strict_noncritical_ca_handshake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera", "2.0.0")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    ca_path, certificate_path, key_path = _write_noncritical_ca_tls_material(tmp_path)
    create_default_context = ssl.create_default_context
    opener = _MemoryBioUrlopen(
        ca_path,
        certificate_path,
        key_path,
        create_default_context,
    )
    opened: list[str] = []

    def create_trusted_strict_context(*_args: Any, **_kwargs: Any) -> ssl.SSLContext:
        context = create_default_context(cafile=ca_path)
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        return context

    monkeypatch.setattr(
        client.ssl, "create_default_context", create_trusted_strict_context
    )
    monkeypatch.setattr(client.urllib.request, "urlopen", opener)

    receipt = client.start_interview(
        plugin_root,
        "General Vera improvement suggestion",
        browser_opener=opened.append,
        now=300.0,
    )

    assert receipt["change_request_id"] == "CR-89"
    assert opened == ["https://mparanza.com/interviews/session-89"]
    assert opener.verify_codes == [89]
    assert len(opener.verify_flags) == 2
    assert opener.verify_flags[0] & ssl.VERIFY_X509_STRICT
    assert opener.verify_flags[1] == (opener.verify_flags[0] & ~ssl.VERIFY_X509_STRICT)


def test_start_interview_retries_noncritical_ca_at_most_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    calls = 0

    def unavailable(_request: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise urllib.error.URLError(certificate_verification_error(89))

    monkeypatch.setattr(client.urllib.request, "urlopen", unavailable)

    with pytest.raises(client.ChangeRequestError, match="Could not reach"):
        client.start_interview(
            plugin_root,
            "General Vera improvement suggestion",
            browser_opener=lambda _url: None,
        )

    assert calls == 2


def test_start_interview_does_not_retry_other_certificate_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    calls = 0

    def unavailable(_request: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise urllib.error.URLError(certificate_verification_error(62))

    monkeypatch.setattr(client.urllib.request, "urlopen", unavailable)

    with pytest.raises(client.ChangeRequestError, match="Could not reach"):
        client.start_interview(
            plugin_root,
            "General Vera improvement suggestion",
            browser_opener=lambda _url: None,
        )

    assert calls == 1


def test_start_interview_does_not_relax_tls_for_non_mparanza_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    calls = 0

    def unavailable(_request: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise urllib.error.URLError(certificate_verification_error(89))

    monkeypatch.setattr(client.urllib.request, "urlopen", unavailable)

    with pytest.raises(client.ChangeRequestError, match="Could not reach"):
        client.start_interview(
            plugin_root,
            "General Vera improvement suggestion",
            base_url="https://localhost:8443",
            browser_opener=lambda _url: None,
        )

    assert calls == 1


def test_start_interview_does_not_retry_an_injected_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    plugin_root = write_plugin(tmp_path, "vera")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    calls = 0

    def unavailable(_request: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise urllib.error.URLError(certificate_verification_error(89))

    with pytest.raises(client.ChangeRequestError, match="Could not reach"):
        client.start_interview(
            plugin_root,
            "General Vera improvement suggestion",
            opener=unavailable,
            browser_opener=lambda _url: None,
        )

    assert calls == 1


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
