import ast
import json
import logging

from json_repair import repair_json

from modules.llm.llm_api import (
    clean_response_from_triple_quotes,
    extract_response,
    get_completion_chart_message_openai,
)
from modules.utilities.config import (
    get_naming_params,
    get_run_params,
    select_provider,
)
from modules.utilities.notifier import Notifier, get_notifier


def fallback_openai(sys_msg, user_msg, model):
    r = get_completion_chart_message_openai(sys_msg, user_msg, model, temperature=0)
    return extract_response(r).strip()


def query_llm_return_text(
    llm_wrapper,
    query_step,
    prompt_system,
    prompt_user,
    tools: list | None = None,
    tool_choice: str | dict = "auto",
    notifier: Notifier | None = None,
):
    """Call an LLM for a plain text response."""
    if llm_wrapper is None:
        raise ValueError("llm_wrapper cannot be None; call init_llm_wrapper() first.")
    naming_params = get_naming_params()
    provider_key = naming_params["providerName"]
    model_key = naming_params["modelName"]
    query_dict = select_provider(query_step)
    provider = query_dict[provider_key]
    model = query_dict[model_key]

    def _real_llm_call_text(**kwargs):
        if provider == naming_params["openai"]:
            resp = get_completion_chart_message_openai(
                prompt_system, prompt_user, model, tools, tool_choice, temperature=0
            )
            return extract_response(resp).strip()
        else:
            fallback_model = select_provider("llmFallbackQuery")[model_key]
            return fallback_openai(prompt_system, prompt_user, fallback_model)

    response_text = llm_wrapper._call_llm(
        real_llm_func=_real_llm_call_text,
        query_step=query_step,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        model=model,
        provider=provider,
    )

    return response_text


def model_supports_batch(model: str) -> bool:
    """Return True if the model's family is listed in ``batchModels``.

    Model families are defined in :func:`get_naming_params`; editing those
    lists adjusts behaviour globally without touching call sites.
    """
    if not model:
        return False
    name = str(model).lower()
    families = [m.lower() for m in get_naming_params()["batchModels"]]
    return any(name.startswith(fam) for fam in families)


def model_supports_flex(model: str) -> bool:
    """Return True if the model's family is listed in ``flexModels``."""
    if not model:
        return False
    name = str(model).lower()
    families = [m.lower() for m in get_naming_params()["flexModels"]]
    return any(name.startswith(fam) for fam in families)


def should_use_flex(query_step: str) -> bool:
    """Decide whether to prefer Flex tier for this step.

    Rules:
    - Global run param ``llmBatchMode`` is True (opt-in per run).
    - Step config has ``batchMode`` True (treat as "batchFlex" when not batching).
    - Provider is OpenAI.
    - Model family listed in ``flexModels``.
    """
    naming = get_naming_params()
    provider_key = naming["providerName"]
    model_key = naming["modelName"]
    openai_name = naming["openai"]
    run_params = get_run_params()
    if not run_params["llmBatchMode"]:
        return False
    q = select_provider(query_step)
    if not q or not q["batchMode"]:
        return False
    if str(q[provider_key]).lower() != str(openai_name).lower():
        return False
    model = str(q[model_key])
    return model_supports_flex(model)


def should_use_batch(query_step: str) -> bool:
    """Central gate to decide whether a step prefers batch execution.

    Conditions:
    - Global run param ``llmBatchMode`` is True.
    - Step config has ``batchMode`` True.
    - Provider is OpenAI and the selected model's family is in ``batchModels``.
    """
    naming = get_naming_params()
    provider_key = naming["providerName"]
    model_key = naming["modelName"]
    openai_name = naming["openai"]
    run_params = get_run_params()
    if not run_params["llmBatchMode"]:
        return False
    q = select_provider(query_step)
    if not q or not q["batchMode"]:
        return False
    if str(q[provider_key]).lower() != str(openai_name).lower():
        return False
    model = str(q[model_key])
    return model_supports_batch(model)


def replace_inner_quotes(obj):
    """
    Walk an arbitrarily nested structure (dicts / lists / scalars) and
    replace every double quote inside **string values** with a single quote.

    • Keys are *never* modified.
    • Non-string scalars (int, float, bool, None) are returned unchanged.
    • Works depth-first: dict  → list  → str.
    """

    # --- Case 1: dictionary ------------------------------------------
    if isinstance(obj, dict):
        new_dict = {}
        for key, item in obj.items():  # key stays intact
            # recurse into the value
            new_dict[key] = replace_inner_quotes(item)
        return new_dict

    # --- Case 2: list / tuple ----------------------------------------
    if isinstance(obj, list):
        return [replace_inner_quotes(elem) for elem in obj]

    # --- Case 3: string ----------------------------------------------
    if isinstance(obj, str):
        return obj.replace('"', "'")

    # --- Case 4: anything else ---------------------------------------
    return obj


def parse_or_fallback_to_dict(
    extracted: str,
    notifier: Notifier | None = None,
) -> dict:
    """Safely parse a raw LLM response into a dictionary."""
    notify = get_notifier(notifier)
    raw = extract_response(extracted)
    if isinstance(raw, dict):
        return raw
    if not raw.strip():
        return {"error": "LLM response was empty", "raw_response": raw}

    try:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            try:
                repaired = repair_json(raw)
                parsed = json.loads(repaired)
            except Exception as e:
                logging.exception(e)
                notify.error("Something went wrong while repairing JSON.")
                parsed = ast.literal_eval(raw)

        parsed = replace_inner_quotes(parsed)
        return parsed
    except Exception as e:
        logging.exception(e)
        notify.error("Something went wrong while parsing the LLM response as JSON.")
        return {
            "error": "JSON parsing failed",
            "exception": str(e),
            "raw_response": raw,
        }


def query_llm_return_json(
    llm_wrapper,
    query_step,
    prompt_system,
    prompt_user,
    tools: list | None = None,
    tool_choice: str | dict = "auto",
    service_tier: str | None = None,
    reasoning_effort: str | None = None,
    extra_body: dict | None = None,
    notifier: Notifier | None = None,
):
    """Call an LLM and parse the JSON response.

    ``reasoning_effort`` is forwarded to providers that support reasoning
    controls (currently OpenAI).
    """
    if llm_wrapper is None:
        raise ValueError("llm_wrapper cannot be None; call init_llm_wrapper() first.")
    naming_params = get_naming_params()
    provider_key = naming_params["providerName"]
    model_key = naming_params["modelName"]
    query_dict = select_provider(query_step)
    provider = query_dict[provider_key]
    model = query_dict[model_key]

    def _real_llm_call_json(
        *,
        service_tier: str | None = None,
        reasoning_effort: str | None = None,
        **kwargs,
    ):
        if provider == naming_params["openai"]:
            use_json_mode = True
            if tools and any("web_search" in (t.get("type", "")) for t in tools):
                use_json_mode = False
            prompt_user_local = prompt_user
            if use_json_mode and "json" not in prompt_user.lower():
                prompt_user_local = f"{prompt_user}\nRespond with a valid json object."
            fallback_resp = get_completion_chart_message_openai(
                prompt_system,
                prompt_user_local,
                model,
                tools,
                tool_choice,
                temperature=0,
                service_tier=service_tier,
                json_mode=use_json_mode,
                reasoning_effort=reasoning_effort,
                extra_body=extra_body,
            )
            return parse_or_fallback_to_dict(fallback_resp, notifier=notifier)

        else:
            fallback_model = select_provider("llmFallbackQuery")[model_key]
            fallback_resp = fallback_openai(prompt_system, prompt_user, fallback_model)
            return parse_or_fallback_to_dict(fallback_resp, notifier=notifier)

    response_dict = llm_wrapper._call_llm(
        real_llm_func=_real_llm_call_json,
        query_step=query_step,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        model=model,
        provider=provider,
        service_tier=service_tier,
        reasoning_effort=reasoning_effort,
        extra_body=extra_body,
    )

    return response_dict
