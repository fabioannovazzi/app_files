"""Prepare and retrieve Clara hosted interviews through the authenticated API."""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "ALLOWED_REMOTE_HOSTS",
    "DEFAULT_BASE_URL",
    "HostedInterviewClientError",
    "authenticate_opener",
    "export_interview_bundle",
    "export_interview_review",
    "get_interview_status",
    "list_interview_campaigns",
    "main",
    "prepare_campaign_interview",
    "prepare_custom_interview",
    "request_magic_link",
    "token_from_value",
]


DEFAULT_BASE_URL = "https://mparanza.com"
DEFAULT_TIMEOUT_SECONDS = 60.0
ALLOWED_REMOTE_HOSTS = frozenset({"mparanza.com", "www.mparanza.com"})
LOCAL_TEST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SUPPORTED_LANGUAGES = ("it", "en", "fr", "de", "es")
LOGGER = logging.getLogger(__name__)


class HostedInterviewClientError(RuntimeError):
    """Raised when the hosted-interview API cannot complete an operation."""


def _url_origin(url: str) -> tuple[str, str, int | None]:
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError as exc:
        raise HostedInterviewClientError("Invalid hosted-interview URL port.") from exc
    if port is None:
        port = (
            443 if parts.scheme == "https" else 80 if parts.scheme == "http" else None
        )
    return parts.scheme.lower(), (parts.hostname or "").lower(), port


class _OriginBoundCookieHeader(urllib.request.BaseHandler):
    """Add a supplied Cookie header only to one exact approved origin."""

    handler_order = 400

    def __init__(self, cookie_header: str, base_url: str) -> None:
        self.cookie_header = cookie_header
        self.origin = _url_origin(base_url)

    def _apply(self, request: urllib.request.Request) -> urllib.request.Request:
        request.remove_header("Cookie")
        if _url_origin(request.full_url) == self.origin:
            request.add_unredirected_header("Cookie", self.cookie_header)
        return request

    def http_request(self, request: urllib.request.Request) -> urllib.request.Request:
        return self._apply(request)

    def https_request(self, request: urllib.request.Request) -> urllib.request.Request:
        return self._apply(request)


def _normalize_base_url(base_url: str) -> str:
    clean = base_url.strip()
    parts = urllib.parse.urlsplit(clean)
    host = (parts.hostname or "").lower()
    if not clean or not parts.scheme or not host:
        raise HostedInterviewClientError("Invalid hosted-interview base URL.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise HostedInterviewClientError(
            "Hosted-interview base URL cannot contain credentials, query, or fragment."
        )
    if parts.path not in {"", "/"}:
        raise HostedInterviewClientError(
            "Hosted-interview base URL cannot contain a path."
        )
    try:
        port = parts.port
    except ValueError as exc:
        raise HostedInterviewClientError(
            "Invalid hosted-interview base URL port."
        ) from exc
    is_local_test = host in LOCAL_TEST_HOSTS
    if is_local_test and parts.scheme not in {"http", "https"}:
        raise HostedInterviewClientError(
            "Local hosted-interview base URL must use HTTP or HTTPS."
        )
    if not is_local_test and (
        parts.scheme != "https"
        or host not in ALLOWED_REMOTE_HOSTS
        or port not in {None, 443}
    ):
        raise HostedInterviewClientError(
            "Remote hosted-interview base URL must be https://mparanza.com."
        )
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")


def _new_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _extract_magic_link(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise HostedInterviewClientError("Missing Mparanza magic link.")
    match = re.search(r"https://[^)\s]+/auth/magic/consume\?token=[^)\s]+", clean)
    magic_link = match.group(0) if match else clean
    parts = urllib.parse.urlsplit(magic_link)
    _normalize_base_url(f"{parts.scheme}://{parts.netloc}")
    if parts.path != "/auth/magic/consume" or not parts.query:
        raise HostedInterviewClientError("Invalid Mparanza magic-link URL.")
    return magic_link


def _set_cookie_header(
    opener: urllib.request.OpenerDirector,
    cookie_header: str,
    *,
    base_url: str,
) -> None:
    clean = re.sub(r"^\s*cookie\s*:\s*", "", cookie_header, flags=re.IGNORECASE).strip()
    if not clean:
        raise HostedInterviewClientError("Missing Mparanza cookie header.")
    opener.addheaders = [
        (name, value) for name, value in opener.addheaders if name.lower() != "cookie"
    ]
    opener.add_handler(_OriginBoundCookieHeader(clean, _normalize_base_url(base_url)))


def _request_json(
    opener: urllib.request.OpenerDirector,
    *,
    url: str,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = _json_bytes(payload)
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            error_payload = {"detail": body[:1_000] or str(exc)}
        detail = (
            error_payload.get("detail")
            if isinstance(error_payload, Mapping)
            else error_payload
        )
        raise HostedInterviewClientError(
            f"Hosted-interview request failed ({exc.code}): {detail}"
        ) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise HostedInterviewClientError(
            f"Hosted-interview request failed: {exc}"
        ) from exc
    try:
        return json.loads(body) if body.strip() else {}
    except json.JSONDecodeError as exc:
        raise HostedInterviewClientError(
            "Hosted-interview response was not valid JSON."
        ) from exc


def request_magic_link(
    opener: urllib.request.OpenerDirector,
    *,
    email: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Ask Mparanza to email a one-time authentication link."""

    _request_json(
        opener,
        url=f"{_normalize_base_url(base_url)}/auth/magic/request",
        method="POST",
        payload={"email": email.strip(), "redirect_path": "/case-notes/voice/launch"},
        timeout_seconds=timeout_seconds,
    )


def authenticate_opener(
    opener: urllib.request.OpenerDirector,
    *,
    magic_link: str = "",
    cookie_header: str = "",
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Authenticate an opener using one consumed magic link or session cookie."""

    if cookie_header.strip():
        _set_cookie_header(opener, cookie_header, base_url=base_url)
        return
    if not magic_link.strip():
        raise HostedInterviewClientError(
            "Authentication required: provide a magic-link file or cookie-header file."
        )
    request = urllib.request.Request(_extract_magic_link(magic_link), method="GET")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise HostedInterviewClientError(f"Magic-link login failed: {exc}") from exc


def list_interview_campaigns(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Return registered, versioned hosted-interview campaign briefs."""

    payload = _request_json(
        opener,
        url=(
            f"{_normalize_base_url(base_url)}"
            "/case-notes/api/voice/interviews/campaigns"
        ),
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(payload, list):
        raise HostedInterviewClientError("Campaign response was not a JSON list.")
    return [dict(item) for item in payload if isinstance(item, Mapping)]


def prepare_campaign_interview(
    opener: urllib.request.OpenerDirector,
    *,
    interview_campaign_id: str,
    case_id: str,
    participant_name: str,
    language: str,
    interviewee_role: str = "",
    expires_in_hours: int = 7 * 24,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Create one participant link from an exact registered campaign brief."""

    campaign_id = urllib.parse.quote(interview_campaign_id.strip(), safe="")
    payload = _request_json(
        opener,
        url=(
            f"{_normalize_base_url(base_url)}"
            f"/case-notes/api/voice/interviews/campaigns/{campaign_id}/interviews"
        ),
        method="POST",
        payload={
            "case_id": case_id.strip(),
            "participant_name": participant_name.strip(),
            "language": language.strip(),
            "interviewee_role": interviewee_role.strip(),
            "expires_in_hours": expires_in_hours,
        },
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(payload, Mapping):
        raise HostedInterviewClientError(
            "Prepared interview response was not an object."
        )
    return dict(payload)


def prepare_custom_interview(
    opener: urllib.request.OpenerDirector,
    *,
    brief: Mapping[str, Any],
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Create one participant link from a caller-authored case or research brief."""

    payload = _request_json(
        opener,
        url=f"{_normalize_base_url(base_url)}/case-notes/api/voice/interviews",
        method="POST",
        payload=brief,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(payload, Mapping):
        raise HostedInterviewClientError(
            "Prepared interview response was not an object."
        )
    return dict(payload)


def token_from_value(value: str) -> str:
    """Return a hosted-interview token from either a token or participant URL."""

    clean = value.strip().rstrip("/")
    if not clean:
        raise HostedInterviewClientError("Missing hosted-interview token or URL.")
    if "://" not in clean:
        return clean
    path_parts = [part for part in urllib.parse.urlsplit(clean).path.split("/") if part]
    if path_parts and path_parts[-1] == "output":
        path_parts.pop()
    if not path_parts:
        raise HostedInterviewClientError("Could not read a token from the URL.")
    return path_parts[-1]


def get_interview_status(
    opener: urllib.request.OpenerDirector,
    *,
    token_or_url: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return the public minimal status for one known participant link."""

    token = urllib.parse.quote(token_from_value(token_or_url), safe="")
    payload = _request_json(
        opener,
        url=(
            f"{_normalize_base_url(base_url)}"
            f"/case-notes/api/interviews/{token}/status"
        ),
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(payload, Mapping):
        raise HostedInterviewClientError("Interview status response was not an object.")
    return dict(payload)


def _export_interview_artifact(
    opener: urllib.request.OpenerDirector,
    *,
    token_or_url: str,
    artifact: str,
    base_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    token = urllib.parse.quote(token_from_value(token_or_url), safe="")
    payload = _request_json(
        opener,
        url=(
            f"{_normalize_base_url(base_url)}"
            f"/case-notes/api/voice/interviews/{token}/{artifact}"
        ),
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(payload, Mapping):
        raise HostedInterviewClientError(
            f"Interview {artifact} response was not an object."
        )
    return dict(payload)


def export_interview_bundle(
    opener: urllib.request.OpenerDirector,
    *,
    token_or_url: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return record, completion, transcript events, media metadata, and review."""

    return _export_interview_artifact(
        opener,
        token_or_url=token_or_url,
        artifact="bundle",
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def export_interview_review(
    opener: urllib.request.OpenerDirector,
    *,
    token_or_url: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return the post-interview model quality review or its recorded error."""

    return _export_interview_artifact(
        opener,
        token_or_url=token_or_url,
        artifact="review",
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _make_private(path: Path, *, label: str) -> None:
    try:
        path.chmod(0o600)
    except OSError as exc:
        raise HostedInterviewClientError(
            f"Could not protect {label} file: {path}"
        ) from exc


def _load_json_object(path: Path, *, label: str = "JSON") -> dict[str, Any]:
    _make_private(path, label=label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostedInterviewClientError(
            f"Could not read {label} file: {path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise HostedInterviewClientError(f"{label} file must contain a JSON object.")
    return dict(payload)


def _write_private_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _read_optional_secret(path: Path | None, *, label: str) -> str:
    if path is None:
        return ""
    _make_private(path, label=label)
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HostedInterviewClientError(
            f"Could not read {label} file: {path}"
        ) from exc


def _add_output_argument(
    parser: argparse.ArgumentParser, *, required: bool = False
) -> None:
    parser.add_argument(
        "--output",
        type=Path,
        required=required,
        help=(
            "Private JSON receipt/output path outside the plugin source tree."
            if required
            else "Optional JSON output path outside the plugin source tree."
        ),
    )


def _add_interview_source(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--receipt",
        type=Path,
        help="Private JSON receipt written by prepare or prepare-campaign.",
    )
    group.add_argument(
        "--participant-link-file",
        type=Path,
        help="Private file containing only the participant URL or token.",
    )


def _interview_source_from_args(args: argparse.Namespace) -> str:
    if args.receipt is not None:
        receipt = _load_json_object(args.receipt, label="interview receipt")
        value = str(receipt.get("public_url") or receipt.get("token") or "").strip()
        if not value:
            raise HostedInterviewClientError(
                "Interview receipt has no public_url or token."
            )
        return value
    return _read_optional_secret(
        args.participant_link_file,
        label="participant link",
    )


def _log_or_write(
    payload: Any,
    output: Path | None,
    *,
    allow_stdout: bool = False,
) -> None:
    if output is not None:
        _write_private_json(output, payload)
        LOGGER.info("Hosted-interview artifact: %s", output)
        return
    if not allow_stdout:
        raise HostedInterviewClientError(
            "A private --output path is required for this operation."
        )
    LOGGER.info("%s", json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    """Run one authenticated hosted-interview management operation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--magic-link-file", type=Path)
    parser.add_argument("--cookie-header-file", type=Path)
    parser.add_argument(
        "--request-magic-link",
        metavar="EMAIL",
        help="Request a link, then prompt for the received link.",
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list-campaigns", help="List registered interview campaigns."
    )
    _add_output_argument(list_parser)

    campaign_parser = subparsers.add_parser(
        "prepare-campaign", help="Create a participant link from a campaign."
    )
    campaign_parser.add_argument("interview_campaign_id")
    campaign_parser.add_argument("--case-id", required=True)
    campaign_parser.add_argument("--participant-name", required=True)
    campaign_parser.add_argument(
        "--language", choices=SUPPORTED_LANGUAGES, default="it"
    )
    campaign_parser.add_argument("--interviewee-role", default="")
    campaign_parser.add_argument("--expires-in-hours", type=int, default=7 * 24)
    _add_output_argument(campaign_parser, required=True)

    prepare_parser = subparsers.add_parser(
        "prepare", help="Create a participant link from a custom brief JSON."
    )
    prepare_parser.add_argument("brief_json", type=Path)
    _add_output_argument(prepare_parser, required=True)

    status_parser = subparsers.add_parser(
        "status", help="Check a known participant link without authentication."
    )
    _add_interview_source(status_parser)
    _add_output_argument(status_parser, required=True)

    bundle_parser = subparsers.add_parser(
        "bundle", help="Retrieve a completed interview bundle."
    )
    _add_interview_source(bundle_parser)
    _add_output_argument(bundle_parser, required=True)

    review_parser = subparsers.add_parser(
        "review", help="Retrieve the post-interview quality review."
    )
    _add_interview_source(review_parser)
    _add_output_argument(review_parser, required=True)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        base_url = _normalize_base_url(args.base_url)
        opener = _new_opener()
        magic_link = _read_optional_secret(
            args.magic_link_file,
            label="magic link",
        )
        cookie_header = _read_optional_secret(
            args.cookie_header_file,
            label="cookie header",
        )
        if args.request_magic_link:
            request_magic_link(
                opener,
                email=args.request_magic_link,
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
            LOGGER.info("Magic link requested.")
            magic_link = getpass.getpass("Magic link: ").strip()
        if args.command != "status":
            authenticate_opener(
                opener,
                magic_link=magic_link,
                cookie_header=cookie_header,
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
        if args.command == "status":
            result = get_interview_status(
                opener,
                token_or_url=_interview_source_from_args(args),
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "list-campaigns":
            result = list_interview_campaigns(
                opener,
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "prepare-campaign":
            result = prepare_campaign_interview(
                opener,
                interview_campaign_id=args.interview_campaign_id,
                case_id=args.case_id,
                participant_name=args.participant_name,
                language=args.language,
                interviewee_role=args.interviewee_role,
                expires_in_hours=args.expires_in_hours,
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "prepare":
            result = prepare_custom_interview(
                opener,
                brief=_load_json_object(args.brief_json, label="interview brief"),
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "bundle":
            result = export_interview_bundle(
                opener,
                token_or_url=_interview_source_from_args(args),
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
        else:
            result = export_interview_review(
                opener,
                token_or_url=_interview_source_from_args(args),
                base_url=base_url,
                timeout_seconds=args.timeout_seconds,
            )
    except HostedInterviewClientError as exc:
        LOGGER.error("%s", exc)
        return 1
    try:
        _log_or_write(
            result,
            args.output,
            allow_stdout=args.command == "list-campaigns",
        )
    except HostedInterviewClientError as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
