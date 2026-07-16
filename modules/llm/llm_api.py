import json
import logging
import time

import httpx
import openai
from openai import APIError, APITimeoutError, RateLimitError

from modules.llm.llm_client import get_openai_client
from modules.utilities.config import get_naming_params
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import print_error_details
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui

# NOTE: Do NOT import model_router at module top-level to avoid a circular import.
# model_router imports functions from this module; importing it here would break
# module initialization. Instead, import inside functions where needed.


def _safe_model_dump(obj):
    """Return a dict from a pydantic model without emitting serializer warnings."""
    if not hasattr(obj, "model_dump"):
        return None
    try:
        return obj.model_dump(warnings="none")
    except TypeError:
        return obj.model_dump()


def _safe_model_dump_json(obj):
    """Return JSON from a pydantic model without emitting serializer warnings."""
    if not hasattr(obj, "model_dump_json"):
        return None
    try:
        return obj.model_dump_json(warnings="none")
    except TypeError:
        return obj.model_dump_json()


def _ensure_llm_wrapper(llm_wrapper):
    """Return a usable `llm_wrapper` or raise a helpful error.

    If not provided, try `session_state["llm_wrapper"]` (assumes UI already
    called `init_llm_wrapper("")` and set a SessionContext).
    """
    if llm_wrapper is not None:
        return llm_wrapper
    try:
        return session_state["llm_wrapper"]
    except Exception as e:
        logging.exception(e)
        raise ValueError(
            "llm_wrapper is required. Initialise once with init_llm_wrapper("
            ") "
            "and pass the wrapper down through function calls."
        )


def remove_duplicate_charts_in_dictionary(originalDict):
    uniqueDict = {}
    renumberedDict = {}
    # Loop through the original dictionary
    for key, value in originalDict.items():
        # Check if the value has already been added to the unique dictionary
        if value not in uniqueDict.values():
            # If the value is unique, add it to the unique dictionary with its original key
            uniqueDict[key] = value
    if len(originalDict) != len(uniqueDict):
        count = 1
        for element in uniqueDict:
            renumberedDict[str(count)] = uniqueDict[element]
            count = count + 1
    else:
        renumberedDict = uniqueDict
    return renumberedDict


def clean_response_from_triple_quotes(responseDict):
    if isinstance(responseDict, str) and "```json" in responseDict:
        responseDict = responseDict.replace("json", "")
        responseDict = responseDict.replace("```", "")
    return responseDict


def if_str_make_list(responseDict):
    if isinstance(responseDict, str):
        responseDict = responseDict.replace("'", '"')
    return responseDict


def clean_bouleans(responseDict):
    responseDict = responseDict.replace("True", "true")
    responseDict = responseDict.replace("False", "false")
    return responseDict


def extract_response(response):
    namingParams = get_naming_params()
    if response:
        if isinstance(response, dict) and "choices" in response:
            responseIndex = 0
            response = response["choices"][responseIndex]["message"]["content"]
            response = response.replace("dataframe", "data")
        elif isinstance(response, str):
            response = response.strip()
    return response


def wait_for_task(client, task_id: str) -> dict:
    """Poll the Responses API until the task is completed.

    Returns the full task dictionary instead of just ``output_text`` so that
    callers can access additional fields like reasoning information.
    """

    while True:
        task = client.responses.retrieve(task_id)
        status = getattr(task, "status", None)
        if status == "completed":
            if hasattr(task, "model_dump"):
                try:
                    dumped = _safe_model_dump(task)
                    if dumped is not None:
                        return dumped
                except Exception as e:
                    logging.exception(e)
                    ui.error(
                        "Something went wrong while converting the LLM task results."
                    )
            if hasattr(task, "model_dump_json"):
                try:
                    dumped = _safe_model_dump_json(task)
                    if dumped is not None:
                        return json.loads(dumped)
                except Exception as e:
                    logging.exception(e)
                    ui.error(
                        "Something went wrong while converting the LLM task results."
                    )
            if hasattr(task, "to_dict"):
                try:
                    return task.to_dict()
                except Exception as e:
                    logging.exception(e)
                    ui.error(
                        "Something went wrong while converting the LLM task results."
                    )
            if isinstance(task, dict):
                return task
            return task.__dict__
        if status in {"failed", "cancelled"}:
            message = ""
            error = getattr(task, "last_error", None)
            if error:
                if isinstance(error, dict):
                    code = error.get("code")
                    msg = error.get("message")
                else:
                    code = getattr(error, "code", None)
                    msg = getattr(error, "message", None)
                message = f": {code} {msg}" if msg else ""
            raise RuntimeError(f"Task {task_id} {status}{message}")
        time.sleep(0.5)


def get_completion_images(
    imgBytes, promptSystem, promptUser, modelChoice, paramDict, client, temperature
):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    model = modelChoice
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": promptSystem,
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": promptUser},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{imgBytes}",
                                "resize": 2048,
                            },
                        },
                    ],
                },
            ],
            max_tokens=4096,
        )
        responseIndex = 0
        dumped = _safe_model_dump(response)
        response = dumped if dumped is not None else response
        response = response["choices"][responseIndex]["message"]["content"]
    except Exception as e:
        logging.exception(e)
        response = {}
        logging.exception(e)
        ui.error("Something went wrong while generating images.")
        e = print_error_details(e)
        paramDict = add_app_message_to_paramdict(
            e,
            errorMessageType,
            plotChartsTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )
        message = "Error in processing image. Try again later."
        paramDict = add_app_message_to_paramdict(
            message,
            errorMessageType,
            plotChartsTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )
    return response, paramDict


def get_completion_chart_message_openai(
    promptSystem: str,
    promptUser: str,
    modelChoice: str,
    tools: list | None = None,
    tool_choice: str | dict = "auto",
    temperature: float = 0.0,
    service_tier: str | None = None,
    reasoning_effort: str | None = None,
    max_retries: int = 5,
    json_mode: bool = False,
    extra_body: dict | None = None,
):
    """Return a response from OpenAI using the appropriate endpoint.

    ``reasoning_effort`` optionally sets the desired reasoning cost level on
    models that support it. Implements retry logic with exponential backoff on
    ``429`` responses (rate‑limit or resource‑unavailable). After
    ``max_retries`` attempts the call is retried once more with
    ``service_tier="auto"`` before the exception is re-raised.
    """
    namingParams = get_naming_params()
    deepResearchO3 = namingParams["deepResearchO3"]
    deepResearchO4Mini = namingParams["deepResearchO4Mini"]
    gpt5Thinking = namingParams["gpt5Thinking"]
    gpt54Mini = namingParams["gpt54Mini"]
    gpt5ThinkingMini = namingParams["gpt5ThinkingMini"]
    gpt5ThinkingNano = namingParams["gpt5ThinkingNano"]
    gpt5Main = namingParams["gpt5Main"]
    client = get_openai_client()

    def _tools_to_responses(tools):
        """Convert Chat-style tools -> Responses-style tools."""
        out = []
        for t in tools or []:
            if isinstance(t, dict) and t.get("type") == "function":
                if "function" in t:  # Chat style
                    fn = t.get("function") or {}
                    name = fn.get("name")
                    entry = {"type": "function", "name": name}
                    if "description" in fn and fn["description"] is not None:
                        entry["description"] = fn["description"]
                    if "parameters" in fn and fn["parameters"] is not None:
                        entry["parameters"] = fn["parameters"]
                    out.append(entry)
                else:
                    out.append(t)
            else:
                out.append(t)
        return out

    def _tool_choice_to_responses(tc):
        """Convert Chat-style tool_choice -> Responses-style tool_choice."""
        if not isinstance(tc, dict):
            return tc
        if tc.get("type") == "function" and "name" not in tc and "function" in tc:
            fn = tc.get("function") or {}
            name = fn.get("name")
            return {"type": "function", "name": name} if name else tc
        return tc

    def _tools_to_chat(tools):
        """Convert Responses-style tools -> Chat-style tools."""
        out = []
        for t in tools or []:
            if (
                isinstance(t, dict)
                and t.get("type") == "function"
                and "function" not in t
                and t.get("name")
            ):
                fn = {"name": t["name"]}
                if "description" in t and t["description"] is not None:
                    fn["description"] = t["description"]
                if "parameters" in t and t["parameters"] is not None:
                    fn["parameters"] = t["parameters"]
                out.append({"type": "function", "function": fn})
            else:
                out.append(t)
        return out

    def _tool_choice_to_chat(tc):
        """Convert Responses-style tool_choice -> Chat-style tool_choice."""
        if not isinstance(tc, dict):
            return tc
        if tc.get("type") == "function" and "function" not in tc and "name" in tc:
            return {"type": "function", "function": {"name": tc["name"]}}
        return tc

    def _invoke_call(
        tier: str | None,
        modelChoice: str,
        reasoning_effort: str | None,
    ):
        responses_models = {
            gpt5Thinking,
            gpt54Mini,
            gpt5ThinkingMini,
            gpt5ThinkingNano,
            gpt5Main,
            deepResearchO3,
            deepResearchO4Mini,
        }
        if modelChoice in responses_models:
            toolsOk = {gpt5Thinking, gpt54Mini, gpt5ThinkingMini, gpt5ThinkingNano}
            if tools and modelChoice not in toolsOk:
                modelChoice = gpt5Thinking

            # prepare kwargs for responses
            kwargs = {
                "model": modelChoice,
                "input": promptUser,
                "instructions": promptSystem,
                "tools": _tools_to_responses(tools),
                "tool_choice": _tool_choice_to_responses(tool_choice),
            }
            if extra_body:
                kwargs.update(extra_body)
            if reasoning_effort is not None:
                kwargs["reasoning"] = {
                    "summary": "auto",
                    "effort": reasoning_effort,
                }
            else:
                kwargs["reasoning"] = {"summary": "auto"}
            if json_mode:
                kwargs["text"] = {"format": {"type": "json_object"}}
            if tier:
                kwargs["service_tier"] = tier
            for attempt in range(max_retries):
                try:
                    task = client.with_options(timeout=900.0).responses.create(**kwargs)
                    break
                except openai.InternalServerError as err:
                    if attempt == max_retries - 1:
                        request_id = getattr(err, "request_id", "unknown")
                        logging.error(
                            "OpenAI InternalServerError on responses.create (request ID %s)",
                            request_id,
                        )
                        raise RuntimeError(
                            f"OpenAI internal server error after {max_retries} retries (request ID: {request_id})"
                        ) from err
                    time.sleep(2**attempt)

            # wait for completion if needed
            if getattr(task, "status", None) and task.status != "completed":
                task = wait_for_task(client, task.id)
            # The Responses SDK may or may not expose attributes like output_json and tool_calls.
            # Use model_dump() to get a dict regardless of SDK version.
            try:
                task_dict = _safe_model_dump(task)
                if task_dict is None:
                    task_dict = {}
            except Exception:
                try:
                    dumped = _safe_model_dump_json(task)
                    task_dict = json.loads(dumped) if dumped is not None else {}
                except Exception:
                    task_dict = {}

            # Extract web_search sources when included
            def _extract_sources(task: dict) -> list:
                try:
                    out = []
                    for entry in task.get("output") or []:
                        if (
                            isinstance(entry, dict)
                            and entry.get("type") == "web_search_call"
                        ):
                            action = entry.get("action") or {}
                            for s in action.get("sources") or []:
                                if not isinstance(s, dict):
                                    continue
                                out.append(
                                    {
                                        "url": s.get("url"),
                                        "title": s.get("title"),
                                        "snippet": s.get("snippet"),
                                    }
                                )
                    return out
                except Exception:
                    return []

            sources = _extract_sources(task_dict)
            # 1) JSON mode: output_json contains the result
            if json_mode and isinstance(task_dict.get("output_json"), dict):
                out = task_dict["output_json"]
                if sources and isinstance(out, dict):
                    try:
                        out = dict(out)
                        out["_sources"] = sources
                    except Exception:
                        pass
                return out
            # 2) New Responses format: result is in the `output` list
            outputs = task_dict.get("output") or []
            for entry in outputs:
                # look for an entry of type function_call
                if isinstance(entry, dict) and entry.get("type") == "function_call":
                    args = entry.get("arguments")
                    if isinstance(args, str):
                        try:
                            obj = json.loads(args)
                            if sources and isinstance(obj, dict):
                                obj["_sources"] = sources
                            return obj
                        except Exception:
                            return args  # fall back to raw string
                    if args is not None:
                        try:
                            if sources and isinstance(args, dict):
                                args["_sources"] = sources
                        except Exception:
                            pass
                        return args

            # 2b) Extract plain text from message outputs when present
            # Some SDK versions return text inside `output` entries of type "message"
            # with a `content` array containing objects like {"type": "output_text", "text": "..."}.
            texts: list[str] = []
            for entry in outputs:
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") == "message":
                    for part in entry.get("content", []) or []:
                        if isinstance(part, dict):
                            txt = part.get("text")
                            if isinstance(txt, str) and txt.strip():
                                texts.append(txt)
            if texts:
                return "\n".join(texts)
            # 3) Chat‑style tool_calls for backwards compatibility
            tool_calls = task_dict.get("tool_calls") or []
            if tool_calls:
                func = tool_calls[0].get("function", {})
                args = func.get("arguments")
                if isinstance(args, str):
                    try:
                        obj = json.loads(args)
                        if sources and isinstance(obj, dict):
                            obj["_sources"] = sources
                        return obj
                    except Exception:
                        return args
                if args is not None:
                    try:
                        if sources and isinstance(args, dict):
                            args["_sources"] = sources
                    except Exception:
                        pass
                    return args

            # 4) Fall back to any output_text present.
            if "output_text" in task_dict:
                return task_dict["output_text"]
            # Last resort: coerce the entire dict to a string so callers expecting
            # text do not fail on `.strip()`; upstream may still handle it.
            try:
                return json.dumps(task_dict, ensure_ascii=False)
            except Exception:
                return str(task_dict)

        else:
            message = [
                {"role": "system", "content": promptSystem},
                {"role": "user", "content": promptUser},
            ]
            kwargs = dict(
                model=modelChoice,
                messages=message,
                n=1,
                temperature=temperature,
                tools=_tools_to_chat(tools),  # <— convert here
            )
            if extra_body:
                kwargs.update(extra_body)
            if reasoning_effort is not None:
                kwargs["reasoning"] = {
                    "summary": "auto",
                    "effort": reasoning_effort,
                }
        if tier:
            kwargs["service_tier"] = tier
        responseKeyArray = ["message", "content"]
        if tools:
            kwargs["tools"] = tools
            functionName = tools[0]["function"]["name"]
            tool_choice_local = {
                "type": "function",
                "function": {"name": functionName},
            }
            kwargs["tool_choice"] = tool_choice_local
            responseKeyArray = [
                "message",
                "tool_calls",
                "function",
                "arguments",
            ]
        response = client.chat.completions.create(**kwargs)

        responseIndex = 0
        dumped = _safe_model_dump(response)
        response = dumped if dumped is not None else response
        if tools:
            response = response["choices"][responseIndex][responseKeyArray[0]][
                responseKeyArray[1]
            ][0][responseKeyArray[2]][responseKeyArray[3]]
            return json.loads(response)
        return response["choices"][responseIndex][responseKeyArray[0]][
            responseKeyArray[1]
        ]

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = _invoke_call(service_tier, modelChoice, reasoning_effort)
            response = clean_response_from_triple_quotes(response)
            return extract_response(response)
        except (
            RateLimitError,
            APIError,
            APITimeoutError,
            httpx.ReadTimeout,
        ) as e:
            if (
                isinstance(e, APIError)
                and not isinstance(e, APITimeoutError)
                and getattr(e, "status_code", None) != 429
            ):
                raise
            last_error = e
            if attempt == max_retries - 1:
                break
            time.sleep(2**attempt)

    if service_tier != "auto":
        try:
            response = _invoke_call("auto", modelChoice, reasoning_effort)
            response = clean_response_from_triple_quotes(response)
            return extract_response(response)
        except (
            RateLimitError,
            APIError,
            APITimeoutError,
            httpx.ReadTimeout,
        ) as e:
            if (
                isinstance(e, APIError)
                and not isinstance(e, APITimeoutError)
                and getattr(e, "status_code", None) != 429
            ):
                raise
            last_error = e

    if last_error:
        raise last_error

    return ""
