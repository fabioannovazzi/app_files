from __future__ import annotations

import json
import logging
import time
from typing import Any, List, MutableMapping

from modules.llm import model_router
from modules.llm.llm_call_wrapper import LLMCallWrapper
from modules.llm.model_router import (
    parse_or_fallback_to_dict,
    should_use_batch,
)
from modules.llm.openai_batch import create_batch_file, submit_batch, wait_for_batch
from modules.utilities.config import get_naming_params, select_provider
from modules.utilities.session_context import SessionContext, resolve_session_state
from modules.utilities.ui_notifier import ui

__all__ = ["run_parallel_deep_research"]


SUPPORTED_WEB_SEARCH_TOOLS = {"web_search_preview"}


def run_parallel_deep_research(
    promptUser: str,
    runs: int = 5,
    *,
    throttle: float = 1.0,
    code_interpreter: bool = False,
    session: SessionContext | MutableMapping[str, Any] | None = None,
    llm_wrapper: Any | None = None,
) -> List[Any]:
    """Run Deep Research queries and return parsed JSON results.

    Parameters
    ----------
    promptUser:
        The user question to send to the model.
    runs:
        Number of times to execute the query.
    throttle:
        Seconds to wait between consecutive flex requests to avoid rate limits.
    code_interpreter:
        When ``True`` include the code interpreter tool in the LLM requeui.
    """
    if runs < 1:
        raise ValueError("runs must be >= 1")
    # Centralized gate: global toggle + step prefs + provider/model capability
    if llm_wrapper is None and session is not None:
        state = resolve_session_state(session)
        llm_wrapper = state.get("llm_wrapper")
    if llm_wrapper is None:
        llm_wrapper = LLMCallWrapper()
    codeInterpreter = code_interpreter
    naming_params = get_naming_params()
    step = naming_params["deepResearchRun"]
    use_batch = should_use_batch(step)
    try:
        web_search_tool = naming_params["webSearchTool"]
    except KeyError:
        logging.warning("Web search tool not configured; skipping.")
        web_search_tool = None
    else:
        if web_search_tool not in SUPPORTED_WEB_SEARCH_TOOLS:
            logging.warning(
                "Web search tool %s not supported; skipping.", web_search_tool
            )
            web_search_tool = None

    tools = []
    if web_search_tool:
        tools.append({"type": web_search_tool})
    if codeInterpreter:
        tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
    toolChoice = "auto"
    promptSystem = ""

    # Batch does NOT support tools. For Deep Research, batch when enabled and no tools.
    if use_batch and not tools:
        try:
            prompts = []
            # Derive the configured model for the step so batch requests target it
            provider_key = naming_params["providerName"]
            model_key = naming_params["modelName"]
            query_dict = select_provider(step)
            model = query_dict[model_key]
            for i in range(runs):
                body = {
                    "model": model,
                    "input": [
                        {"role": "system", "content": promptSystem},
                        {"role": "user", "content": promptUser},
                    ],
                }
                prompts.append({"custom_id": str(i), "body": body})

            file_id = create_batch_file(prompts)
            batch_id = submit_batch(file_id)
            outputs = wait_for_batch(llm_wrapper, batch_id)

            results: List[Any] = []
            for _, line in sorted(outputs.items(), key=lambda kv: kv[0]):
                try:
                    data = json.loads(line)
                    if "response" in data:
                        content = (
                            data["response"]
                            .get("output", [{}])[0]
                            .get("content", [{}])[0]
                            .get("text", "")
                        )
                    else:
                        content = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                except Exception as e:
                    logging.exception(e)
                    ui.error("Something went wrong running batch.")
                    content = line
                results.append(parse_or_fallback_to_dict(content))
            return results
        except Exception as e:
            ui.caption(f"Batch mode failed: {e}. Falling back to sequential.")
            logging.exception(e)

    results: List[Any] = []
    for i in range(runs):
        if i > 0 and throttle > 0:
            time.sleep(throttle)
        from modules.llm.batch_runner import run_step_json

        result = run_step_json(
            llm_wrapper,
            step,
            promptSystem,
            promptUser,
            tools=tools,
            tool_choice=toolChoice,
        )[0]
        results.append(result)
    return results
