from __future__ import annotations

import io
import json
import logging
import time
import uuid
from typing import Dict, List, Tuple

# Unified LLM call interface (used for fallback-only execution)
from modules.llm import llm_client, model_router
from modules.utilities.config import (
    get_naming_params,
    get_run_params,
    select_provider,
)

logger = logging.getLogger(__name__)

__all__ = ["create_batch_file", "submit_batch", "wait_for_batch"]


# Registry of submitted provider batch jobs (batch_id -> file_id).
_BATCH_JOBS: Dict[str, str] = {}


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _ensure_line(prompt: dict) -> dict:
    body = dict(prompt.get("body", {}))
    if "model" not in body:
        naming = get_naming_params()
        batch_key = naming["llmFallbackQuery"]
        selection = select_provider(batch_key)
        if selection.get("provider") != naming["openai"]:
            raise RuntimeError("OpenAI batch fallback must resolve to OpenAI.")
        body["model"] = selection["model"]
    line_body = {**body, "text": {"format": {"type": "json_object"}}}
    if "schema" in prompt:
        line_body["text"] = {
            "format": {"type": "json_schema"},
            "schema": prompt["schema"],
        }
    return {
        "custom_id": prompt["custom_id"],
        "method": prompt.get("method", "POST"),
        "url": prompt.get("url", "/v1/responses"),
        "body": line_body,
    }


def _lines_to_jsonl(lines: List[dict]) -> bytes:
    return ("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n").encode(
        "utf-8"
    )


def _provider_enabled() -> bool:
    try:
        rp = get_run_params()
        return bool(rp.get("llmBatchMode", False))
    except Exception:  # pragma: no cover - defensive
        return False


def create_batch_file(prompts: list[dict]) -> str:
    """Create an OpenAI batch input file and return its file ID.

    Provider batch mode (``llmBatchMode``) must be enabled.
    """
    if not _provider_enabled():
        raise RuntimeError("Provider batch mode is disabled.")

    lines: List[dict] = [_ensure_line(p) for p in prompts]
    client = llm_client.get_openai_client()
    content = _lines_to_jsonl(lines)
    file_obj = ("batch.jsonl", io.BytesIO(content), "application/jsonl")
    created = client.files.create(file=file_obj, purpose="batch")
    return created.id


def submit_batch(
    file_id: str,
    *,
    completion_window: str = "24h",
    endpoint: str = "/v1/responses",
    **_params,
) -> str:
    """Submit a batch job and return a batch ID (provider when enabled)."""
    if not _provider_enabled():
        raise RuntimeError("Provider batch mode is disabled.")

    client = llm_client.get_openai_client()
    job = client.batches.create(
        input_file_id=file_id,
        completion_window=completion_window,
        endpoint=endpoint,
    )
    _BATCH_JOBS[str(job.id)] = file_id
    return job.id


def _extract_prompts(line: dict) -> tuple[str, str]:
    msgs = list(line.get("body", {}).get("input", []))
    system_parts: List[str] = []
    user_parts: List[str] = []
    for m in msgs:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(str(content))
        elif role == "user":
            user_parts.append(str(content))
    return "\n".join(system_parts).strip(), "\n".join(user_parts).strip()


def _should_return_json(line: dict) -> bool:
    text = line.get("body", {}).get("text", {}) or {}
    fmt = (text.get("format") or {}).get("type")
    return fmt in {"json_object", "json_schema"}


def _parse_provider_output(content: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for ln in content.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            custom_id = str(obj.get("custom_id", ""))
            mapping[custom_id] = ln
        except Exception:
            # keep robustness: capture raw line under a synthetic key
            mapping[_gen_id("line")] = ln
    return mapping


def wait_for_batch(
    llm_wrapper,
    batch_id: str,
    *,
    timeout: float | None = None,
) -> dict[str, str]:
    """Wait for provider batch completion and return mapping ``custom_id -> raw_json_line``."""
    if str(batch_id).startswith("membatch_"):
        raise RuntimeError(f"Unknown batch job: {batch_id}")

    try:
        client = llm_client.get_openai_client()
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError("Unable to initialize OpenAI batch client") from exc

    file_id = _BATCH_JOBS.get(batch_id)
    start = time.time()
    while True:
        job = client.batches.retrieve(batch_id)
        status = getattr(job, "status", "in_progress")
        if status == "completed":
            out_id = getattr(job, "output_file_id", None)
            if not out_id:
                raise RuntimeError("Batch completed without output_file_id")
            data = client.files.retrieve_content(out_id)
            data_text = data if isinstance(data, str) else data.decode()
            mapping = _parse_provider_output(data_text)
            err_file = getattr(job, "error_file_id", None)
            if err_file:
                error_data = client.files.retrieve_content(err_file)
                error_text = (
                    error_data if isinstance(error_data, str) else error_data.decode()
                )
                mapping.update(_parse_provider_output(error_text))
            return mapping
        if status == "failed":
            err_file = getattr(job, "error_file_id", None)
            if err_file:
                data = client.files.retrieve_content(err_file)
                msg = data if isinstance(data, str) else data.decode()
                raise RuntimeError(msg)
            last_error = getattr(job, "last_error", None)
            if last_error:
                raise RuntimeError(str(last_error))
            errors = getattr(job, "errors", None) or []
            if errors:
                first = getattr(errors[0], "message", None) or str(errors[0])
                raise RuntimeError(str(first))
            raise RuntimeError("Batch failed without error details")
        if timeout is not None and time.time() - start > timeout:
            raise RuntimeError("Batch polling timed out")
        time.sleep(1.0)
