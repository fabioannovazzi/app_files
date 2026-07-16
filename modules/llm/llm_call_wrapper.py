import copy
import hashlib
import json
import logging
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, MutableMapping

from modules.llm.wrapper_config import get_llm_wrapper_template
from modules.utilities.cache import get_cache_dir
from modules.utilities.notifier import Notifier, get_notifier
from modules.utilities.session_context import SessionContext, resolve_session_state

try:
    _CACHE_DIR = get_cache_dir("llm")
except PermissionError:  # pragma: no cover - fallback when cache unwritable
    _CACHE_DIR = Path.cwd()


def init_llm_wrapper(
    user_text: str,
    session: SessionContext | MutableMapping[str, Any],
    notifier: Notifier | None = None,
) -> None:
    """Initialize LLM wrapper defaults inside the provided session mapping."""
    state = resolve_session_state(session)
    template = get_llm_wrapper_template()

    if "correction_prompt_llm" not in state:
        state["correction_prompt_llm"] = None
    if "user_issue_edits" not in state:
        state["user_issue_edits"] = {}
    if "original_markdown_text" not in state:
        state["original_markdown_text"] = user_text
    if "llm_wrapper" not in state:
        state["llm_wrapper"] = LLMCallWrapper(
            mode=template["mode"],
            record_file=template["record_file"],
            step_config=template["step_config"],
            notifier=notifier,
        )
    elif notifier is not None and hasattr(state["llm_wrapper"], "set_notifier"):
        state["llm_wrapper"].set_notifier(notifier)


class LLMCallWrapper:
    def __init__(
        self,
        mode="live",
        record_file: str = str(_CACHE_DIR / "record.json"),
        step_config=None,
        notifier: Notifier | None = None,
    ):
        """
        A flexible LLM call wrapper.

        :param mode: str, one of ("live", "write", "replay"), the global/default mode
        :param record_file: str, path to the JSON file for storing or loading calls
        :param step_config: dict, optional mapping of step_name -> mode
               e.g. { "attributeClassificationQuery": "write" }
               If a step_name is found in step_config, it overrides the global mode.
        """
        self.mode = mode
        self.record_file = record_file
        self.step_config = step_config or {}
        self._record_data = {"llm_calls": []}
        self._notifier = get_notifier(notifier)

        record_path = Path(self.record_file)
        if record_path.exists():
            try:
                with record_path.open("r", encoding="utf-8") as f:
                    self._record_data = json.load(f)
            except json.JSONDecodeError:
                self._notifier.warning(
                    f"Could not decode JSON from {self.record_file}. Starting with empty record."
                )
                self._record_data = {"llm_calls": []}

        # Build a cache of hash_key -> response_text
        self._cache = {}
        for entry in self._record_data["llm_calls"]:
            key = entry.get("hash_key")
            resp = entry.get("response_text")
            if key is not None and resp is not None:
                self._cache[key] = resp

    def _make_json_safe(self, obj: Any) -> Any:
        """Return a JSON serializable representation of ``obj``."""

        if is_dataclass(obj):
            return {k: self._make_json_safe(v) for k, v in asdict(obj).items()}

        if isinstance(obj, dict):
            return {k: self._make_json_safe(v) for k, v in obj.items()}

        if isinstance(obj, (list, tuple, set)):
            return [self._make_json_safe(v) for v in obj]

        if hasattr(obj, "model_dump"):
            try:
                try:
                    dumped = obj.model_dump(warnings="none")
                except TypeError:
                    dumped = obj.model_dump()
                return self._make_json_safe(dumped)
            except Exception as e:
                logging.exception(e)
                self._notifier.error(
                    "Something went wrong while sanitizing JSON for LLM calls."
                )

        if hasattr(obj, "model_dump_json"):
            try:
                try:
                    dumped = obj.model_dump_json(warnings="none")
                except TypeError:
                    dumped = obj.model_dump_json()
                return json.loads(dumped)
            except Exception as e:
                logging.exception(e)
                self._notifier.error(
                    "Something went wrong while sanitizing JSON for LLM calls."
                )

        if hasattr(obj, "to_dict"):
            try:
                return self._make_json_safe(obj.to_dict())
            except Exception as e:
                logging.exception(e)
                self._notifier.error(
                    "Something went wrong while sanitizing JSON for LLM calls."
                )

        if hasattr(obj, "__dict__"):
            try:
                return self._make_json_safe(vars(obj))
            except Exception as e:
                logging.exception(e)
                self._notifier.error(
                    "Something went wrong while sanitizing JSON for LLM calls."
                )

        return obj

    def _hash_key(self, query_step, prompt_system, prompt_user, *args, **kwargs):
        """
        Generate a stable hash from input parameters to identify repeated calls.
        Here we use query_step (and not a derived Query name) as the unique key.
        """
        raw = {
            "query_step": query_step,
            "prompt_system": prompt_system,
            "prompt_user": prompt_user,
            "args": args,
            "kwargs": kwargs,
        }
        return hashlib.md5(json.dumps(raw, sort_keys=True).encode("utf-8")).hexdigest()

    def _call_llm(
        self, query_step, prompt_system, prompt_user, real_llm_func, *args, **kwargs
    ):
        """
        :param query_step: unique label (e.g. "attributeClassificationQuery")
        :param prompt_system: system prompt text (str)
        :param prompt_user: user prompt text (str)
        :param real_llm_func: a function that actually invokes your LLM
        :param args/kwargs: additional parameters for real_llm_func
        :return: the final response text (str or JSON) from the LLM
        """
        # 1) Determine the effective mode for this step
        #    If there's a step-level config, override global mode
        step_mode = self.step_config.get(query_step, self.mode)

        hash_key = self._hash_key(
            query_step, prompt_system, prompt_user, *args, **kwargs
        )

        # 3) If mode is "replay" => attempt to retrieve from cache
        if step_mode == "replay":
            showMessage = False
            if hash_key in self._cache:
                return self._cache[hash_key]
            else:
                step_mode = "write"  # fallback to write if not found
                if showMessage:
                    msg = f"No replay data found for hash_key={hash_key}. Switching step '{query_step}' to 'write'."
                    self._notifier.warning(msg)
        # If "live", just return the response immediately
        if step_mode == "live":
            response_data = real_llm_func(
                query_step=query_step,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                *args,
                **kwargs,
            )
            return response_data

        if step_mode == "write":
            # if hash_key in self._cache:
            # If you want to skip re-calling the LLM if we have a match:
            # (comment out this block if you always want fresh calls for "write")
            # return self._cache[hash_key]
            # else we proceed with a live call below

            # 5) If we get here, we are either "live" or "write" (or fallback from replay -> write),
            #    so we do a fresh call to real_llm_func
            response_data = real_llm_func(
                query_step=query_step,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                *args,
                **kwargs,
            )

            safe_response = self._make_json_safe(response_data)

            new_entry = {
                "query_step": query_step,
                "hash_key": hash_key,
                "timestamp": time.time(),
                "prompt_system": prompt_system,
                "prompt_user": prompt_user,
                "response_text": safe_response,
                "args": args,
                "kwargs": kwargs,
            }

            updated = copy.deepcopy(self._record_data)
            updated["llm_calls"].append(new_entry)

            try:
                json_str = json.dumps(updated, indent=2)
            except TypeError:
                self._notifier.warning(
                    "Failed to serialize LLM response; record.json not updated"
                )
                return response_data

            record_path = Path(self.record_file)
            try:
                record_path.parent.mkdir(parents=True, exist_ok=True)
                with record_path.open("w", encoding="utf-8") as f:
                    f.write(json_str)
            except OSError as exc:
                logging.warning("Failed to write LLM cache to %s: %s", record_path, exc)
                return response_data

            self._record_data = updated
            self._cache[hash_key] = safe_response

            # 8) Return final
            return response_data

        self._notifier.warning(
            f"Unrecognized mode {step_mode}, defaulting to 'live'."
        )
        response_data = real_llm_func(
            query_step=query_step,
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            *args,
            **kwargs,
        )
        return response_data

    def set_notifier(self, notifier: Notifier | None) -> None:
        """Update the notifier used for warnings and errors."""
        self._notifier = get_notifier(notifier)
