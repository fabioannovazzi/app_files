from __future__ import annotations

import json
from typing import Any, Iterable, List, Mapping

from modules.llm.model_router import (
    query_llm_return_json,
    query_llm_return_text,
    should_use_batch,
    should_use_flex,
)
from modules.llm.openai_batch import create_batch_file, submit_batch, wait_for_batch
from modules.utilities.config import get_naming_params, select_provider

__all__ = [
    "run_step_json",
    "run_step_text",
]

import logging

logger = logging.getLogger(__name__)

BATCH_FILE_MAX_BYTES = 200 * 1024 * 1024
BATCH_FILE_SAFE_MARGIN = 1 * 1024 * 1024
BATCH_FILE_TARGET_BYTES = BATCH_FILE_MAX_BYTES - BATCH_FILE_SAFE_MARGIN


def _content_has_json(content: object) -> bool:
    if isinstance(content, str):
        return "json" in content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                text_val = part.get("text")
                if isinstance(text_val, str) and "json" in text_val:
                    return True
            elif isinstance(part, str) and "json" in part:
                return True
    return False


def _normalize_prompt_item(
    item: object,
    system_prompt: str,
) -> tuple[object, str, dict | None]:
    if not isinstance(item, dict):
        return item, system_prompt, None
    user_content = item.get("user_content")
    if user_content is None:
        user_content = item.get("content")
    if user_content is None:
        user_content = item.get("prompt", item)
    system_override = item.get("system_prompt") or item.get("system")
    sys_text = system_override if isinstance(system_override, str) else system_prompt
    extra = item.get("extra_body")
    extra_body = extra if isinstance(extra, dict) else None
    return user_content, sys_text, extra_body


def _build_lines(
    step: str,
    system_prompt: str,
    prompts: Iterable[object],
    *,
    extra_body: dict | None = None,
    reasoning_effort: str | None = None,
) -> List[dict]:

    naming_params = get_naming_params()
    model_key = naming_params["modelName"]
    model = select_provider(step)[model_key]

    lines: List[dict] = []
    for i, p in enumerate(prompts):
        user_content, sys_text, per_extra = _normalize_prompt_item(p, system_prompt)
        sys_msg = {"role": "system", "content": sys_text or ""}
        if isinstance(user_content, list):
            content_value: object = user_content
        elif user_content is None:
            content_value = ""
        else:
            content_value = str(user_content)
        user_msg = {"role": "user", "content": content_value}

        inputs = [sys_msg, user_msg]
        # Safety net: ensure the literal lowercase word 'json' is present
        # in at least one input message when using text.format=json_object.
        # Some prompts include "JSON" in uppercase, which does not satisfy
        # the provider requirement. Append a small system hint if needed.
        sys_has_json = _content_has_json(sys_msg["content"])
        user_has_json = _content_has_json(user_msg["content"])
        if not (sys_has_json or user_has_json):
            inputs.append({"role": "system", "content": "Respond in json."})

        body = {
            "model": model,
            "input": inputs,
            # Default JSON-mode output for parity across steps
            "text": {"format": {"type": "json_object"}},
        }
        if extra_body:
            body = {**body, **extra_body}
        if per_extra:
            body = {**body, **per_extra}
        if reasoning_effort is not None:
            body["reasoning"] = {"summary": "auto", "effort": reasoning_effort}
        lines.append({"custom_id": str(i), "body": body})
    return lines


def _estimate_jsonl_bytes(lines: Iterable[dict]) -> int:
    total = 0
    for line in lines:
        total += len(json.dumps(line, ensure_ascii=False).encode("utf-8")) + 1
    return total


def _parse_batch_item(raw: str) -> str:
    try:
        data = json.loads(raw)
        if "response" in data:
            payload = data["response"]
            if isinstance(payload, dict) and "body" in payload:
                payload = payload.get("body", payload)

            def _extract_text(output):
                if not isinstance(output, list):
                    return ""
                for entry in output:
                    if not isinstance(entry, dict):
                        continue
                    content = entry.get("content")
                    if isinstance(content, list):
                        for part in content:
                            if not isinstance(part, dict):
                                continue
                            for key in ("text", "output_text"):
                                text_val = part.get(key)
                                if isinstance(text_val, str) and text_val.strip():
                                    return text_val
                            if "json" in part and part["json"]:
                                json_val = part["json"]
                                if isinstance(json_val, str) and json_val.strip():
                                    return json_val
                                if isinstance(json_val, dict):
                                    return json.dumps(json_val)
                    text_val = entry.get("text")
                    if isinstance(text_val, str) and text_val.strip():
                        return text_val
                return ""

            output = payload.get("output", []) if isinstance(payload, dict) else []
            text = _extract_text(output)
        else:
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception:
        text = raw
    return str(text)


def _parse_batch_map(raw_map: Mapping[str, str]) -> List[str]:
    # Preserve order by numeric custom_id
    results: List[str] = []
    for _, raw in sorted(raw_map.items(), key=lambda kv: int(kv[0])):
        results.append(_parse_batch_item(raw))
    return results


def _parse_batch_map_with_missing(
    raw_map: Mapping[str, str],
    expected_count: int,
) -> tuple[list[str | None], list[int]]:
    results: list[str | None] = [None] * expected_count
    seen: set[int] = set()
    for key, raw in raw_map.items():
        try:
            idx = int(key)
        except Exception:
            continue
        if 0 <= idx < expected_count:
            results[idx] = _parse_batch_item(raw)
            seen.add(idx)
    missing = [i for i in range(expected_count) if i not in seen]
    return results, missing


def _normalize_retry_missing(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except Exception:
        return 0


def run_step_json(
    llm_wrapper,
    step: str,
    system_prompt: str,
    prompts: Iterable[object] | str,
    *,
    tools: list | None = None,
    tool_choice: str | dict = "auto",
    service_tier: str | None = None,
    reasoning_effort: str | None = None,
    extra_body: dict | None = None,
    retry_missing: int | bool = False,
) -> List[dict]:
    """Run a step returning JSON, batching when appropriate.

    If ``prompts`` is a single string, returns a list with one dict.
    If it is an iterable of strings, preserves input order in the results.
    """
    # Clamp explicit Flex if step is not eligible for Flex.
    if service_tier == "flex" and not should_use_flex(step):
        service_tier = None

    if isinstance(prompts, str):
        items = [prompts]
    else:
        items = list(prompts)

    def _run_batch(
        batch_lines: List[dict],
        batch_prompts: list[object],
    ) -> List[dict]:
        fid = create_batch_file(batch_lines)
        bid = submit_batch(fid)
        raw_map = wait_for_batch(llm_wrapper, bid)
        texts, missing = _parse_batch_map_with_missing(raw_map, len(batch_prompts))
        max_retries = _normalize_retry_missing(retry_missing)
        attempt = 1
        missing_indices = missing
        while missing_indices and attempt <= max_retries:
            logger.warning(
                "run_step_json(step=%s) missing %s batch responses; retry %s/%s",
                step,
                len(missing_indices),
                attempt,
                max_retries,
            )
            retry_prompts = [batch_prompts[i] for i in missing_indices]
            retry_lines = _build_lines(
                step,
                system_prompt,
                retry_prompts,
                extra_body=extra_body,
                reasoning_effort=reasoning_effort,
            )
            retry_fid = create_batch_file(retry_lines)
            retry_bid = submit_batch(retry_fid)
            retry_map = wait_for_batch(llm_wrapper, retry_bid)
            retry_texts, retry_missing_idx = _parse_batch_map_with_missing(
                retry_map, len(retry_prompts)
            )
            for offset, original_idx in enumerate(missing_indices):
                if retry_texts[offset] is not None:
                    texts[original_idx] = retry_texts[offset]
            missing_indices = [missing_indices[i] for i in retry_missing_idx]
            attempt += 1
        if missing_indices:
            logger.warning(
                "run_step_json(step=%s) still missing %s responses after retries",
                step,
                len(missing_indices),
            )

        out: List[dict] = []
        for t in texts:
            if t is None:
                out.append({"error": "batch_missing"})
                continue
            try:
                out.append(json.loads(t) if isinstance(t, str) else t)
            except Exception:
                out.append({"raw": t})
        return out

    # If tools are requested, avoid batch (Responses batch does not support tools)
    if len(items) > 1 and not tools and should_use_batch(step):
        try:
            lines = _build_lines(
                step,
                system_prompt,
                items,
                extra_body=extra_body,
                reasoning_effort=reasoning_effort,
            )
            sizes = [
                len(json.dumps(line, ensure_ascii=False).encode("utf-8")) + 1
                for line in lines
            ]
            if sizes and max(sizes) > BATCH_FILE_TARGET_BYTES:
                raise ValueError("single batch line exceeds size limit")
            total_bytes = sum(sizes)
            if total_bytes <= BATCH_FILE_TARGET_BYTES:
                return _run_batch(lines, items)

            results: List[dict] = []
            batch_start = 0
            while batch_start < len(items):
                running_bytes = 0
                batch_end = batch_start
                while batch_end < len(items):
                    line_bytes = sizes[batch_end]
                    if (
                        running_bytes
                        and running_bytes + line_bytes > BATCH_FILE_TARGET_BYTES
                    ):
                        break
                    running_bytes += line_bytes
                    batch_end += 1
                chunk_items = items[batch_start:batch_end]
                chunk_lines = _build_lines(
                    step,
                    system_prompt,
                    chunk_items,
                    extra_body=extra_body,
                    reasoning_effort=reasoning_effort,
                )
                results.extend(_run_batch(chunk_lines, chunk_items))
                batch_start = batch_end
            return results
        except Exception as exc:
            logger.warning(
                "run_step_json(step=%s) batch path failed; falling back to sequential: %s",
                step,
                exc,
            )

    # Sequential fallback (or when batch disabled/tools provided). Prefer Flex
    # only when the step is configured for batch ("batchFlex"). Tools alone do
    # not trigger Flex.
    if not service_tier and should_use_flex(step):
        service_tier = "flex"
    if tools is not None:
        logger.debug(
            "run_step_json(step=%s) tools=%s extra_body=%s", step, tools, extra_body
        )
    results: List[dict] = []
    for p in items:
        if isinstance(p, dict):
            user_content, sys_text, per_extra = _normalize_prompt_item(p, system_prompt)
            merged_extra: dict | None
            if extra_body or per_extra:
                merged_extra = {}
                if extra_body:
                    merged_extra.update(extra_body)
                if per_extra:
                    merged_extra.update(per_extra)
            else:
                merged_extra = None
            if isinstance(user_content, list):
                prompt_user = ""
            elif user_content is None:
                prompt_user = ""
            else:
                prompt_user = str(user_content)
            prompt_system = sys_text or system_prompt
            if isinstance(user_content, list):
                inputs = [
                    {"role": "system", "content": prompt_system or ""},
                    {"role": "user", "content": user_content},
                ]
                if not (
                    _content_has_json(prompt_system) or _content_has_json(user_content)
                ):
                    inputs.append({"role": "system", "content": "Respond in json."})
                merged_extra = {**(merged_extra or {}), "input": inputs}
            results.append(
                query_llm_return_json(
                    llm_wrapper,
                    step,
                    prompt_system,
                    str(prompt_user),
                    tools=tools,
                    tool_choice=tool_choice,
                    service_tier=service_tier,
                    reasoning_effort=reasoning_effort,
                    extra_body=merged_extra,
                )
            )
        else:
            results.append(
                query_llm_return_json(
                    llm_wrapper,
                    step,
                    system_prompt,
                    p,
                    tools=tools,
                    tool_choice=tool_choice,
                    service_tier=service_tier,
                    reasoning_effort=reasoning_effort,
                    extra_body=extra_body,
                )
            )
    return results


def run_step_text(
    llm_wrapper,
    step: str,
    system_prompt: str,
    prompts: Iterable[str] | str,
    *,
    tools: list | None = None,
    tool_choice: str | dict = "auto",
) -> List[str]:
    """Run a step returning plain text, batching when appropriate.

    If ``prompts`` is a single string, returns a list with one string.
    If it is an iterable of strings, preserves input order in the results.
    """
    if isinstance(prompts, str):
        items = [prompts]
    else:
        items = list(prompts)

    if len(items) > 1 and not tools and should_use_batch(step):
        lines = _build_lines(step, system_prompt, items)
        fid = create_batch_file(lines)
        bid = submit_batch(fid)
        raw_map = wait_for_batch(llm_wrapper, bid)
        return _parse_batch_map(raw_map)

    return [
        query_llm_return_text(
            llm_wrapper,
            step,
            system_prompt,
            p,
            tools=tools,
            tool_choice=tool_choice,
        )
        for p in items
    ]
