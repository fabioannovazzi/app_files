from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping

from modules.utilities.ui_notifier import Notifier, NullNotifier, get_ui_notifier

__all__ = [
    "normalize_research_result",
    "extract_trace_info",
    "extract_output_text",
    "dump_response",
]

def _resolve_notifier(notifier: Notifier | None) -> Notifier:
    return notifier or get_ui_notifier() or NullNotifier()


def normalize_research_result(res: Any, *, notifier: Notifier | None = None) -> Any:
    """Return a displayable value from a research run result."""
    notify = _resolve_notifier(notifier)
    if isinstance(res, dict):
        res = res.get("response", res)
        if "error" in res:
            return res
        return res.get("raw_response", res)
    if isinstance(res, str):
        try:
            return json.loads(res)
        except Exception as e:
            logging.exception(e)
            notify.error("Error normalizing the research result")
            return res
    return res


def extract_trace_info(res: Any, *, notifier: Notifier | None = None) -> Dict[str, Any]:
    """Extract reasoning summary texts and first web search details."""
    notify = _resolve_notifier(notifier)
    output: List[Any] = []
    if isinstance(res, dict):
        payload = res.get("raw_response", res)
        if isinstance(payload, dict):
            output = payload.get("output", [])

    reasoning_texts: List[str] = []
    search_query = ""
    search_status = ""

    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, Mapping):
            return obj.get(key, default)
        if hasattr(obj, key):
            return getattr(obj, key)
        if hasattr(obj, "model_dump"):
            try:
                return obj.model_dump().get(key, default)
            except Exception as e:
                logging.exception(e)
                notify.error("Error extracting trace information")
                return default
        return default

    for item in output:
        if _get(item, "type") == "reasoning":
            summaries = _get(item, "summary", [])
            reasoning_texts = [_get(s, "text", "") for s in summaries]
            break

    for item in output:
        if _get(item, "type") == "web_search_call":
            action = _get(item, "action", {})
            search_query = _get(action, "query", "")
            search_status = _get(item, "status", "")
            break

    return {
        "reasoning": reasoning_texts,
        "search": {"query": search_query, "status": search_status},
    }


def dump_response(
    res: Any,
    *,
    notifier: Notifier | None = None,
) -> None:
    """Display a raw Deep Research response via a UI notifier or logging."""
    notify = _resolve_notifier(notifier)
    try:
        text = json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.exception(e)
        notify.error("Error dumping the response")
        text = str(res)
    if isinstance(notify, NullNotifier):
        logging.info(text)
    else:
        notify.write(text)


def extract_output_text(res: Any, *, notifier: Notifier | None = None) -> str | None:
    """Return the main text from a Deep Research result if available."""
    notify = _resolve_notifier(notifier)
    obj = res

    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception as e:
            logging.exception(e)
            notify.error("Error extracting output text JSON")
            return obj
    if isinstance(obj, Mapping):
        payload = obj.get("raw_response") or obj.get("response") or obj
        if isinstance(payload, str):
            return payload
        if isinstance(payload, Mapping):
            for key in ("output_text", "text", "content", "analysis", "result"):
                text = payload.get(key)
                if isinstance(text, str):
                    return text
            output = payload.get("output")
            if isinstance(output, list):
                for item in reversed(output):
                    if not isinstance(item, Mapping):
                        continue
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        return text
                    if isinstance(text, list):
                        for part in text:
                            if not isinstance(part, Mapping):
                                continue
                            inner_text = part.get("text") or part.get("content")
                            if isinstance(inner_text, str):
                                return inner_text
                    message = item.get("message")
                    if isinstance(message, Mapping):
                        content = message.get("content")
                        if isinstance(content, str):
                            return content
                        if isinstance(content, list):
                            for part in content:
                                if isinstance(part, Mapping):
                                    inner_text = part.get("text") or part.get("content")
                                    if isinstance(inner_text, str):
                                        return inner_text
                                elif isinstance(part, str):
                                    return part
            return None
