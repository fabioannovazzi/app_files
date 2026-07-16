import copy
import hashlib
import json
import logging
import pickle
from typing import Any, Callable, MutableMapping

import polars as pl

try:
    from deepdiff import DeepDiff
except ImportError:  # pragma: no cover - variance plugin does not need diff logging
    DeepDiff = None

from modules.layout.session_manager import SessionManager
from modules.utilities.logging_utils import report_error
from modules.utilities.session_context import SessionContext
from modules.utilities.ui_notifier import ui

LOGGER = logging.getLogger(__name__)

try:  # UI tests may stub config with limited API
    from modules.utilities.config import get_naming_params, get_run_params
except Exception as e:  # pragma: no cover - provide safe defaults for tests
    logging.exception(e)
    report_error("memoization config import error", e)
    from modules.utilities.config import get_naming_params

    def get_run_params() -> dict:  # type: ignore[override]
        """Return minimal run parameters when real config is unavailable."""

        return {"checkCollect": False}


def get_hashed_key(key, columnHash):
    if columnHash:
        key = key + "_" + str(columnHash)
    return key


def ensure_session_state_initialized(
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
):
    session_manager = SessionManager(state=session_context)
    namingParams = get_naming_params()
    collectedHashesKey = namingParams["collectedHashes"]
    if not session_manager.contains(collectedHashesKey):
        # We'll store a dict: { signature_str: step_str }
        session_manager.set(collectedHashesKey, {})


def hash_polars_df(df: pl.DataFrame) -> str:
    # Polars built-in row hashing gives a Series of UInt64
    row_hashes = df.hash_rows()
    # Convert the Series to a Python list of Python ints
    row_hashes_list = row_hashes.to_list()

    # Turn that list of unsigned 64-bit integers into bytes
    combined_bytes = b"".join(
        h.to_bytes(8, "little", signed=False) for h in row_hashes_list
    )

    # Finally, compute MD5
    return hashlib.md5(combined_bytes, usedforsecurity=False).hexdigest()


def hash_polars_lf(lf: pl.LazyFrame) -> str:
    """Return an MD5 digest for the entire lazy frame."""

    # Compute row-wise hashes in a version-neutral way and aggregate them
    # to a single integer so that large frames are not materialised.
    plan = lf.select(pl.struct(pl.all()).hash().sum().alias("all_hash"))

    # Collect the aggregated value
    df = plan.collect()
    hash_val = int(df["all_hash"][0])

    # Convert to bytes using as many bytes as required to represent ``hash_val``.
    # Polars may produce values outside the 64‑bit range, so a fixed eight‑byte
    # buffer can raise ``OverflowError``. By dynamically sizing the byte array we
    # avoid that issue while keeping the hash stable across platforms.
    signed = hash_val < 0
    byte_len = max(1, (hash_val.bit_length() + (1 if signed else 0) + 7) // 8)
    hash_bytes = hash_val.to_bytes(byte_len, "little", signed=signed)
    return hashlib.md5(hash_bytes, usedforsecurity=False).hexdigest()


def get_signature(collectedVariable):
    """
    Return a string signature that identifies the data only
    (not the step/label).
    """
    if isinstance(collectedVariable, (int, float)):
        # Simple numeric => just convert to string
        return str(collectedVariable)
    elif hasattr(collectedVariable, "hash_rows"):
        if isinstance(collectedVariable, pl.DataFrame):
            # DataFrame => use the hashing function above
            return hash_polars_df(collectedVariable)
        elif isinstance(collectedVariable, pl.LazyFrame):
            # DataFrame => use the hashing function above
            return hash_polars_lf(collectedVariable)
    elif collectedVariable is not None and "naive plan" in str(collectedVariable):
        # Fallback => use str(...) as naive approach
        return str(collectedVariable[:30])
    else:
        return None


def check_collect(
    step,
    label,
    data,
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
):
    """
    1) Hash the data (signature).
    2) If signature already in session_state, we skip and
       say "collect {step}, value {data} already collected in step {old_step}".
    3) Otherwise, we print "collect {step}, label={label}, value={data}"
       and store the signature -> step in session_state.
    """
    session_manager = SessionManager(state=session_context)
    namingParams = get_naming_params()
    runParams = get_run_params()
    checkCollect = runParams["checkCollect"]
    collectedHashesKey = namingParams["collectedHashes"]
    printHit = False
    if checkCollect:
        ensure_session_state_initialized(session_manager._state)

        signature = get_signature(data)

        # We keep a mapping { signature: step_where_it_was_first_collected }
        collected_hashes = session_manager.get(collectedHashesKey)

        if signature and "naive plan" in str(signature):
            pass

        elif signature in collected_hashes:
            # This data was already collected under a different step
            old_step = collected_hashes[signature]
            if printHit:
                if step != old_step:
                    message = f"**Already collected**: "
                    message2 = f" {step}, value={data} in step {old_step}"
                    ui.write(f":red[" + message + "]" + message2)
        else:
            # New data signature => store it
            collected_hashes[signature] = step
            message = "**New**:"
            message2 = f" collect {step}, label={label}, value={data}"
            if printHit:
                if isinstance(data, pl.DataFrame):
                    ui.write(f":green[" + message + "]" + message2)
                else:
                    ui.write(f":green[" + message + "]" + message2)
    return None


def file_signature(uploaded_file):
    """
    Create a 'signature' (hash) for the uploaded file.
    Combines the file's name + an MD5 of its raw bytes.
    If the file is large, you might do something more efficient
    (like partial hashing or file size + modification date).
    """
    if not uploaded_file:
        return "NO_FILE"
    name_part = uploaded_file.name
    content_bytes = uploaded_file.getvalue()  # watch out if it's huge
    content_hash = hashlib.md5(content_bytes, usedforsecurity=False).hexdigest()
    return f"{name_part}:{content_hash}"


def _normalize_value(value):
    """
    Recursively:
    - Replaces polars objects with a placeholder.
    - Sorts dictionary keys.
    - Sorts list items by a stable JSON representation.
    """
    # Replace Polars objects
    if isinstance(value, (pl.DataFrame, pl.LazyFrame)):
        return "<POLARS_OBJECT>"

    # Sort dictionaries by keys, recurse on values
    if isinstance(value, dict):
        return {
            k: _normalize_value(v)
            for k, v in sorted(value.items(), key=lambda item: item[0])
        }

    # Sort lists by the stable JSON representation of each item
    if isinstance(value, list):
        normalized_items = [_normalize_value(v) for v in value]
        return sorted(normalized_items, key=lambda x: json.dumps(x, sort_keys=True))

    # Tuples: process the contents but keep them as tuples
    if isinstance(value, tuple):
        return tuple(_normalize_value(v) for v in value)

    # All other scalar values
    return value


def filter_polars_objects(*args, **kwargs):
    """
    Return a version of (args, kwargs) in which:
    1) Any polars DataFrame/LazyFrame is replaced with "<POLARS_OBJECT>"
    2) Dictionaries and lists are recursively sorted.
    """
    # Normalize each arg
    filtered_args = tuple(_normalize_value(a) for a in args)
    # Normalize each kwarg value
    filtered_kwargs = {k: _normalize_value(v) for k, v in kwargs.items()}

    return filtered_args, filtered_kwargs


def session_memoize_check_params(
    check_diff=False, *, session_manager: SessionManager | None = None
):
    """
    A decorator that does NOT do file checks.
    It only hashes non-Polars arguments (post-normalization)
    and caches the result in the session state store.

    :param check_diff: If True, use DeepDiff to compare the previous
                       vs. current arguments on a cache miss.
    """

    session_manager = session_manager or SessionManager()

    def real_decorator(func):
        def wrapper(*args, **kwargs):
            printHit = False
            # 1. Filter & normalize polars objects, dicts, lists, etc.
            filtered_args, filtered_kwargs = filter_polars_objects(*args, **kwargs)

            # 2. Prepare data for hashing
            pickled_args = pickle.dumps(
                (filtered_args, sorted(filtered_kwargs.items()))
            )
            args_hash = hashlib.md5(pickled_args, usedforsecurity=False).hexdigest()

            # 3. Create keys
            function_key = f"{func.__name__}"
            cache_key = f"{func.__module__}.{func.__name__}-{args_hash}"

            # Also track the *previous* normalized arguments for this function
            # if we're going to do a diff. Each function gets its own 'LAST_ARGS' key.
            last_args_key = f"{func.__module__}.{func.__name__}-LAST_ARGS"

            # 4. Check the session state for a cache hit
            if session_manager.contains(cache_key):
                if printHit:
                    ui.write(":green[Cache hit:] ", function_key)
                return session_manager.get(cache_key)
            else:
                if printHit:
                    ui.write(":red[Cache miss:] ", function_key)

                # 5. Compare to previous arguments (if they exist) using DeepDiff
                if (
                    check_diff
                    and DeepDiff is not None
                    and session_manager.contains(last_args_key)
                ):
                    previous_args, previous_kwargs = session_manager.get(last_args_key)

                    diff = DeepDiff(
                        {"args": previous_args, "kwargs": previous_kwargs},
                        {"args": filtered_args, "kwargs": filtered_kwargs},
                        # ignore_order=True  # Optional, might not be needed since we do canonical sorting
                    )
                    if printHit:
                        if diff:
                            ui.write(
                                "**Differences in function arguments (DeepDiff):**"
                            )
                            ui.write(diff)
                        else:
                            ui.write("No differences found (but hash changed?).")

                # 6. Store the *new* normalized arguments for future comparisons
                if check_diff:
                    session_manager.set(last_args_key, (filtered_args, filtered_kwargs))

                # 7. Compute the real result
                result = func(*args, **kwargs)

                # 8. Cache and return
                session_manager.set(cache_key, result)
                return result

        return wrapper

    return real_decorator


def session_memoize_check_upload(
    func: Callable | None = None, *, session_manager: SessionManager | None = None
):
    """
    Decorator that:
      1) Computes a file signature (name+hash) of the uploaded_file argument.
      2) Filters out polars objects from other args so they're not hashed.
      3) Builds a unique key from (file_sig + hashed non-polars args).
      4) Checks the session state store for an existing cached result under that key.
      5) If found, returns it. Otherwise, calls func, caches its result, returns it.

    => Perfect for storing and retrieving lazy polars data across UI reruns,
       invalidating only when file or relevant parameters change.
    => We do NOT attempt to hash any polars DataFrame/LazyFrame arguments
       (they're replaced by "<POLARS_OBJECT>") to avoid serialization errors.
    """
    if func is None:
        return lambda f: session_memoize_check_upload(
            f, session_manager=session_manager
        )

    session_manager = session_manager or SessionManager()

    def wrapper(uploaded_file, *args, **kwargs):
        # 1. Make a signature for the uploaded file
        file_sig = file_signature(uploaded_file)

        # 2. Filter out polars from the rest of args so we don't hash them
        filtered_args, filtered_kwargs = filter_polars_objects(*args, **kwargs)

        # 3. Hash just the 'filtered' arguments
        pickled_args = pickle.dumps((filtered_args, sorted(filtered_kwargs.items())))
        param_hash = hashlib.md5(pickled_args, usedforsecurity=False).hexdigest()

        # 4. Combine file + param hash => unique cache key
        cache_key = f"{func.__module__}.{func.__name__}-{file_sig}-{param_hash}"

        # 5. Check if we already have a cached result
        if session_manager.contains(cache_key):
            ui.write(":green[Cache hit:] ", cache_key)
            return session_manager.get(cache_key)

        # 6. If not, run the function => cache miss
        ui.write(":red[Cache miss:] ", cache_key)
        result = func(uploaded_file, *args, **kwargs)

        # 7. Store the result (including lazy frames) in session_state
        session_manager.set(cache_key, result)
        return result

    return wrapper
