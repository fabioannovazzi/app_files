from __future__ import annotations

import hashlib
import logging
import os
from collections import Counter
from contextlib import nullcontext
from importlib.util import find_spec
from io import BytesIO

import polars as pl

from modules.llm.function_calls import function_specs, mapping_examples
from modules.llm.random_entries_queries import infer_column_mapping
from modules.process_excel.logic import (
    _as_dict,
    _merge_header_rows,
    _suggest_header_row,
    _unique_column_names,
)
from modules.process_pdf_journal.logic import parse_journal_any
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import Notifier, NullNotifier, get_ui_notifier
from modules.utilities.utils import get_schema_and_column_names

if find_spec("src.check_statements"):
    from src.check_statements import (  # pragma: no cover - optional dependency
        _detect_excel_header_polars as detect_excel_header_polars,
    )
    from src.check_statements import (  # pragma: no cover - optional dependency
        _rebuild_df_with_header as rebuild_df_with_header,
    )
else:  # pragma: no cover - optional dependency missing
    detect_excel_header_polars = None
    rebuild_df_with_header = None

NONE_TOKENS = {" ", "<none>", "<select>", ""}


def _resolve_notifier(notifier: Notifier | None) -> Notifier:
    return notifier or get_ui_notifier() or NullNotifier()


def _is_filled(val: object) -> bool:
    """Return ``True`` for non-empty strings or non-null ``pl.Series``."""

    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, pl.Series):
        return val.drop_nulls().len() > 0
    return False


def show_mapping_panel(
    mapping: dict,
    key: str,
    *,
    key_prefix: str = "",
    notifier: Notifier | None = None,
) -> None:
    """
    Display a tidy mapping table.
    • Shows ⚠️ warning if the same column appears in >1 field.
    • Provides an “Edit mappings” button to reopen the form.
    """
    notify = _resolve_notifier(notifier)

    # ---------- detect duplicates ----------
    # Ignore blanks/placeholders (e.g., " ", "", None)
    # Use _is_filled so strings like " " are treated as empty.
    values = [v for v in mapping.values() if _is_filled(v)]
    dupes = {col for col, cnt in Counter(values).items() if cnt > 1}

    # ---------- build dataframe ----------
    rows = []
    for field, col in mapping.items():
        display_col = col if _is_filled(col) else "—"
        if _is_filled(col) and col in dupes:
            display_col = f"❌  {display_col}"  # mark duplicates
        rows.append((field, display_col))

    try:
        df_map = pl.DataFrame(rows, schema=["Field", "Column"], orient="row")
    except TypeError as exc:  # pragma: no cover - for older Polars or test stubs
        notify.write("show_mapping_panel DataFrame error:", exc)
        df_map = pl.DataFrame(rows, schema=["Field", "Column"])

    # UI can display Polars frames directly; the original code converted
    # to pandas only to set an index. Showing the Polars table preserves the
    # functionality without conversion.
    table_fn = getattr(notify, "table", None)
    if callable(table_fn):
        table_fn(df_map)
    else:
        dataframe_fn = getattr(notify, "dataframe", None)
        if callable(dataframe_fn):
            dataframe_fn(df_map)

    # ---------- duplicate warning ----------
    if dupes:
        notify.warning(
            "⚠️  Each column should be used **once**. "
            "Duplicates detected: " + ", ".join(sorted(dupes))
        )

    # ---------- edit button ----------
    button_fn = getattr(notify, "button", None)
    if callable(button_fn) and button_fn("✏️  Edit mapping", key=key):
        # restore widget defaults so dropdowns reopen pre-selected
        if f"{key_prefix}amount_col" not in session_state:
            session_state[f"{key_prefix}amount_col"] = (
                mapping["amount"] or "<select>"
            )
        if f"{key_prefix}debit_col" not in session_state:
            session_state[f"{key_prefix}debit_col"] = (
                mapping["debit_amount"] or "<select>"
            )
        if f"{key_prefix}credit_col" not in session_state:
            session_state[f"{key_prefix}credit_col"] = (
                mapping["credit_amount"] or "<select>"
            )
        if f"{key_prefix}date_col" not in session_state:
            session_state[f"{key_prefix}date_col"] = mapping["date"] or "<select>"
        if f"{key_prefix}account_col" not in session_state:
            session_state[f"{key_prefix}account_col"] = (
                mapping["account"] or "<select>"
            )
        if f"{key_prefix}account_desc_col" not in session_state:
            session_state[f"{key_prefix}account_desc_col"] = (
                mapping["account_desc"] or "<none>"
            )
        if f"{key_prefix}line_desc_col" not in session_state:
            session_state[f"{key_prefix}line_desc_col"] = (
                mapping["line_desc"] or "<none>"
            )
        if f"{key_prefix}beneficiary_col" not in session_state:
            session_state[f"{key_prefix}beneficiary_col"] = (
                mapping.get("beneficiary") or "<none>"
            )
        if f"{key_prefix}movement_number_col" not in session_state:
            session_state[f"{key_prefix}movement_number_col"] = (
                mapping["movement_number"] or "<none>"
            )

        session_state[f"{key_prefix}mapping_done"] = False
        rerun_fn = getattr(notify, "rerun", None)
        if callable(rerun_fn):
            rerun_fn()


def load_data(
    llm_wrapper: object,
    key: str,
    *,
    notifier: Notifier | None = None,
) -> tuple[pl.LazyFrame | None, bool]:
    """Upload a journal file and return a lazy frame and mode flag."""
    notify = _resolve_notifier(notifier)

    # -------------------------------
    # 1. Upload
    # -------------------------------
    if key == "random_entries":
        typeArray = ["xlsx", "csv", "pdf"]
    else:
        typeArray = [
            "xlsx",
            "csv",
        ]
    columns_fn = getattr(notify, "columns", None)
    if callable(columns_fn):
        cols = columns_fn([1, 1])
        if isinstance(cols, (list, tuple)) and len(cols) >= 2:
            upload_col, _ = cols
        else:  # pragma: no cover - unusual stub behaviour
            upload_col, _ = nullcontext(), nullcontext()
    else:  # pragma: no cover - for minimal stubs
        upload_col, _ = nullcontext(), nullcontext()
    with upload_col:
        file_uploader_fn = getattr(notify, "file_uploader", None)
        if callable(file_uploader_fn):
            uploaded_file = file_uploader_fn(
                "Choose an Excel, CSV, or PDF file",
                type=typeArray,
                key="journal_upload" + key,  # ← keep this
                help="Upload the journal file (max 200 MB).",
            )
        else:  # pragma: no cover - for minimal stubs
            uploaded_file = None
    if uploaded_file is None:
        notify.info("⬆️  Upload a file first")
        return None, False

    # -------------------------------
    # 2. Preview & header‑row choice
    # -------------------------------

    content = uploaded_file.getvalue()

    from modules.process_excel.print_friendly_parser import parse_print_friendly_journal

    use_pf = False
    parsed_df: pl.DataFrame | None = None
    force_pf = os.getenv("FORCE_PRINT_FRIENDLY") == "1"
    force_raw = os.getenv("FORCE_RAW") == "1"

    if force_pf:
        try:
            parsed_df = parse_print_friendly_journal(content, language="auto")
        except Exception as exc:  # noqa: BLE001 - best effort
            logging.exception(exc)
            parsed_df = None

    width = height = 0
    if parsed_df is not None:
        try:
            height = parsed_df.height
            width = parsed_df.width
        except Exception as exc:
            logging.exception(exc)
            height = width = 0
        if width > 0 and height > 0:
            use_pf = True

    if force_pf:
        use_pf = True
    if force_raw:
        use_pf = False

    if use_pf and parsed_df is not None and width > 0 and height > 0:
        notify.dataframe(parsed_df.head(10))
        notify.success(
            f"Auto-parsed print-friendly journal → {height:,} rows × {width} columns"
        )
        return parsed_df.lazy(), True

    if uploaded_file.name.lower().endswith(".pdf"):
        try:
            raw_df = parse_journal_any(content)
        except Exception as exc:  # noqa: BLE001
            logging.exception(exc)
            notify.error("Something went wrong while parsing the uploaded journal file.")
            return None, False
        df = raw_df
        inferred = 0
    else:
        if uploaded_file.name.lower().endswith((".xlsx", "xls")):
            raw_df = pl.read_excel(
                BytesIO(content),
                has_header=False,
                drop_empty_rows=False,
                drop_empty_cols=False,
            )
            inferred = None
            if callable(detect_excel_header_polars):
                try:
                    inferred = detect_excel_header_polars(content)
                except Exception:
                    inferred = None
            if inferred is None:
                inferred = _suggest_header_row(raw_df)
            df = raw_df
        else:
            raw_df = pl.read_csv(BytesIO(content), has_header=False)
            inferred = _suggest_header_row(raw_df)
            df = raw_df
    file_id = hashlib.sha1(content, usedforsecurity=False).hexdigest()
    if session_state.get("current_file_id") != file_id:
        for state_key in list(session_state.keys()):
            # When a new file is uploaded, drop cached mapping/inference state
            if (
                "map_" in state_key
                or state_key.endswith(("layout", "mapping_done"))
                or state_key.endswith("column_inference")
            ):
                session_state.pop(state_key)
        session_state["current_file_id"] = file_id
    # UI's dataframe widget understands Polars frames directly.
    notify.dataframe(raw_df.head(10))

    default_header = str(inferred if inferred is not None else 0)
    header_input = notify.text_input(
        "Which row contains the column titles? (0‑indexed; e.g. '3' or '3,4')",
        value=default_header,
        key=f"header_row_{key}",
    )
    if not header_input:
        header_input = default_header
    header_row: int | tuple[int, int]
    try:
        if "," in header_input:
            parts = [int(p.strip()) for p in header_input.split(",") if p.strip()]
            if len(parts) != 2:
                raise ValueError("Provide two comma-separated numbers")
            header_row = (parts[0], parts[1])
        else:
            header_row = int(header_input)
        if uploaded_file.name.lower().endswith(".pdf"):
            if isinstance(header_row, tuple):
                df = parse_journal_any(content, header_row=header_row)
            else:
                df = (
                    raw_df
                    if header_row == 0
                    else parse_journal_any(content, header_row=header_row)
                )
        elif uploaded_file.name.lower().endswith((".xlsx", "xls")):
            if isinstance(header_row, tuple):
                row1 = [str(x) for x in raw_df.row(header_row[0])]
                row2 = [str(x) for x in raw_df.row(header_row[1])]
                header_vals = _merge_header_rows(row1, row2)
                header_vals = _unique_column_names(header_vals)
                df = raw_df.slice(offset=max(header_row) + 1)
                df.columns = header_vals
            else:
                if rebuild_df_with_header is not None:
                    df = rebuild_df_with_header(content, header_row)
                else:
                    header_vals = [str(x) for x in raw_df.row(header_row)]
                    header_vals = _unique_column_names(header_vals)
                    df = raw_df.slice(offset=header_row + 1)
                    df.columns = header_vals
        else:
            if isinstance(header_row, tuple):
                row1 = [str(x) for x in raw_df.row(header_row[0])]
                row2 = [str(x) for x in raw_df.row(header_row[1])]
                header_vals = _merge_header_rows(row1, row2)
                header_vals = _unique_column_names(header_vals)
                df = raw_df.slice(offset=max(header_row) + 1)
                df.columns = header_vals
            else:
                header_vals = [str(x) for x in raw_df.row(header_row)]
                header_vals = _unique_column_names(header_vals)
                df = raw_df.slice(offset=header_row + 1)
                df.columns = header_vals
    except Exception as exc:  # pragma: no cover - UI path
        logging.exception(exc)
        notify.error("Something went wrong while parsing the uploaded journal file.")
        stop_fn = getattr(notify, "stop", None)
        if callable(stop_fn):
            stop_fn()
        return None, False

    notify.success(f"Loaded file → {df.height:,} rows × {df.width} columns")
    return df.lazy(), False


def _persist_key(widget_key: str) -> str:
    """Return the session_state key we use to persist the user's choice."""
    return f"{widget_key}__persist"


def pick_column(
    label: str,
    *,
    all_cols: list[str],
    chosen: set[str],
    key: str,
    placeholder: str = " ",
    allow_none: bool = False,
    notifier: Notifier | None = None,
) -> str:
    """
    Alphabetical dropdown that hides columns already in *chosen*.
    Uses a *separate* persisted key so user choices survive reruns and
    we can enforce uniqueness without mutating the widget key.
    """
    from modules.layout import widgets as layout_widgets

    # Available options exclude columns already taken by previous fields
    base = sorted([c for c in all_cols if c not in chosen])
    options = (["<none>"] + base) if allow_none else ([placeholder] + base)

    # Load last persisted choice (NOT the widget key).
    pkey = _persist_key(key)
    prev = session_state.get(pkey, session_state.get(key, options[0]))

    # If prev is already taken by another field, don't re-add it.
    # Otherwise ensure it's present so the selectbox can display it.
    if prev not in options and prev not in chosen:
        options.append(prev)

    # Make the widget default follow the persisted choice (before rendering).
    if key not in session_state or session_state[key] not in options:
        session_state[key] = prev if prev in options else options[0]
    index = options.index(session_state[key])

    choice_ui = layout_widgets.searchable_selectbox_with_state(
        label, options, key=key, index=index, notifier=notifier
    )

    # Persist selection and update 'chosen' (ignore placeholders)
    session_state[pkey] = choice_ui
    if choice_ui not in {placeholder, "<none>"}:
        chosen.add(choice_ui)

    # Normalise return value: convert "<none>" to " " to match the pipeline
    return " " if (allow_none and choice_ui == "<none>") else choice_ui


def map_columns(
    llm_wrapper,
    df: pl.DataFrame,
    *,
    key_prefix: str = "",
    notifier: Notifier | None = None,
) -> tuple[dict, str | None]:
    """Return column mapping after user confirmation.

    ``key_prefix`` isolates UI widget keys so multiple tabs can use the
    column-mapping UI without collisions.
    """

    notify = _resolve_notifier(notifier)
    # ---------- fast-path ----------
    if session_state.get(f"{key_prefix}mapping_done", False):
        return (
            {
                "amount": session_state[f"{key_prefix}map_amount"],
                "debit_amount": session_state[f"{key_prefix}map_debit"],
                "credit_amount": session_state[f"{key_prefix}map_credit"],
                "date": session_state[f"{key_prefix}map_date"],
                "account": session_state[f"{key_prefix}map_account"],
                "account_desc": session_state[f"{key_prefix}map_account_desc"],
                "line_desc": session_state[f"{key_prefix}map_line_desc"],
                "beneficiary": session_state.get(
                    f"{key_prefix}map_beneficiary", None
                ),
                "movement_number": session_state[
                    f"{key_prefix}map_movement_number"
                ],
            },
            session_state[f"{key_prefix}layout"],
        )

    # ---------- infer defaults ----------
    notify.info("Mapping columns automatically, please be patient")
    examples = mapping_examples()
    specs = function_specs()
    inference_key = f"{key_prefix}column_inference"
    # Only call the LLM once per file; cache the inference result in session_state
    if inference_key not in session_state:
        inferred = infer_column_mapping(llm_wrapper, df, examples, specs)
        if not isinstance(inferred, dict):
            inferred = {}
        session_state[inference_key] = inferred
    else:
        inferred = session_state[inference_key]

    # Store layout (may be None if inference failed)
    layout = inferred.get("layout")
    session_state[f"{key_prefix}layout"] = layout

    # Extract and normalize the fields payload for UI defaults
    mapping = _as_dict(inferred.get("fields", {}))

    # Show the banner only if we actually have suggested fields
    if mapping:
        notify.info("Column mapping suggested automatically. Please review.")

    # Continue as before
    columns, _schema = get_schema_and_column_names(df)
    cols = list(columns)
    chosen = set()
    placeholder = "<select>"

    # ---------- pre-fill persisted defaults & enforce uniqueness ----------
    allow_none_keys = {
        f"{key_prefix}account_desc_col",
        f"{key_prefix}line_desc_col",
        f"{key_prefix}beneficiary_col",
    }
    default_map = {
        f"{key_prefix}amount_col": mapping.get("amount", ""),
        f"{key_prefix}debit_col": mapping.get("debit_amount", ""),
        f"{key_prefix}credit_col": mapping.get("credit_amount", ""),
        f"{key_prefix}date_col": mapping.get("date", ""),
        f"{key_prefix}account_col": mapping.get("account", ""),
        f"{key_prefix}account_desc_col": mapping.get("account_desc", ""),
        f"{key_prefix}line_desc_col": mapping.get("line_desc", ""),
        f"{key_prefix}beneficiary_col": mapping.get("beneficiary", ""),
        f"{key_prefix}movement_number_col": mapping.get("movement_number", ""),
    }

    # Build initial persisted defaults (prefer the user's latest widget value)
    persisted: dict[str, str] = {}
    for wkey, suggested in default_map.items():
        pkey = _persist_key(wkey)

        # 1) Latest widget value (set by UI before script runs)
        val = session_state.get(wkey)

        # 2) Previously persisted choice (from prior reruns)
        if val is None:
            val = session_state.get(pkey)

        # 3) LLM suggestion (only if we have nothing else)
        if val is None:
            if suggested and suggested in cols:
                val = suggested
            else:
                val = " " if wkey in allow_none_keys else placeholder

        persisted[wkey] = val

    # Enforce uniqueness *before* rendering: earlier fields win, later dups cleared
    order = [
        f"{key_prefix}amount_col",
        f"{key_prefix}debit_col",
        f"{key_prefix}credit_col",
        f"{key_prefix}date_col",
        f"{key_prefix}account_col",
        f"{key_prefix}account_desc_col",
        f"{key_prefix}line_desc_col",
        f"{key_prefix}beneficiary_col",
        f"{key_prefix}movement_number_col",
    ]
    taken: set[str] = set()
    for wkey in order:
        v = persisted[wkey]
        if v not in NONE_TOKENS and v in taken:
            # clear the duplicate to <none>/placeholder
            persisted[wkey] = " " if wkey in allow_none_keys else placeholder
        elif v not in NONE_TOKENS:
            taken.add(v)
        # Prime widget defaults & persist for next rerun
        session_state[wkey] = persisted[wkey]
        session_state[_persist_key(wkey)] = persisted[wkey]

    form_fn = getattr(notify, "form", None)
    form_ctx = form_fn(f"{key_prefix}map_form") if callable(form_fn) else nullcontext()
    with form_ctx:
        w_amount = pick_column(
            "Amount",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}amount_col",
            placeholder=placeholder,
            notifier=notify,
        )
        w_debit = pick_column(
            "Debit Amount",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}debit_col",
            placeholder=placeholder,
            notifier=notify,
        )

        w_credit = pick_column(
            "Credit Amount",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}credit_col",
            placeholder=placeholder,
            notifier=notify,
        )
        w_date = pick_column(
            "Date",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}date_col",
            placeholder=placeholder,
            notifier=notify,
        )

        w_account = pick_column(
            "Account NUMBER",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}account_col",
            placeholder=placeholder,
            notifier=notify,
        )

        w_account_desc = pick_column(
            "Account DESCRIPTION",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}account_desc_col",
            allow_none=True,
            notifier=notify,
        )

        w_line_desc = pick_column(
            "Line / memo",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}line_desc_col",
            allow_none=True,
            notifier=notify,
        )

        w_beneficiary = pick_column(
            "Beneficiary",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}beneficiary_col",
            allow_none=True,
            notifier=notify,
        )

        w_movement_number = pick_column(
            "Movement number",
            all_cols=cols,
            chosen=chosen,
            key=f"{key_prefix}movement_number_col",
            placeholder=placeholder,
            notifier=notify,
        )

        # --- earlier field choice overrides later fields immediately ---
        # Build current selections in the same order used for de-duping
        current_choices = {
            f"{key_prefix}amount_col": w_amount,
            f"{key_prefix}debit_col": w_debit,
            f"{key_prefix}credit_col": w_credit,
            f"{key_prefix}date_col": w_date,
            f"{key_prefix}account_col": w_account,
            f"{key_prefix}account_desc_col": w_account_desc,
            f"{key_prefix}line_desc_col": w_line_desc,
            f"{key_prefix}beneficiary_col": w_beneficiary,
            f"{key_prefix}movement_number_col": w_movement_number,
        }

        # Earlier fields keep their selection; later duplicates are cleared immediately.
        seen_cols = set()
        for wkey in order:  # 'order' is already defined above
            val = current_choices[wkey]
            if val in NONE_TOKENS:
                continue
            if val in seen_cols:
                cleared = " " if wkey in allow_none_keys else placeholder
                # Clear both the visible widget and the persisted choice
                session_state[wkey] = cleared
                session_state[_persist_key(wkey)] = cleared
            else:
                seen_cols.add(val)

        submit_fn = getattr(notify, "form_submit_button", None)
        apply_clicked = submit_fn("Apply mapping") if callable(submit_fn) else False

    # ---------- wait until user clicks ----------
    if not apply_clicked:
        return {}, None

    monetary = [c for c in (w_amount, w_debit, w_credit) if c != placeholder]
    if len(monetary) != len(set(monetary)):
        notify.error("Monetary columns must be distinct.")
        stop_fn = getattr(notify, "stop", None)
        if callable(stop_fn):
            stop_fn()
        return {}, None
    # NEW: no column may be selected in two different roles
    chosen_cols = [
        x
        for x in (
            w_amount,
            w_debit,
            w_credit,
            w_date,
            w_account,
            w_account_desc,
            w_line_desc,
            w_beneficiary,
            w_movement_number,
        )
        if x not in NONE_TOKENS
    ]
    if len(chosen_cols) != len(set(chosen_cols)):
        notify.error("Each field must be mapped to a *different* column.")
        stop_fn = getattr(notify, "stop", None)
        if callable(stop_fn):
            stop_fn()
        return {}, None
    # ---------- persist selections ----------
    # Normalize selections: convert placeholders/blanks to None
    def _norm_choice(v: str | None) -> str | None:
        if v in NONE_TOKENS or v == placeholder or not _is_filled(v):
            return None
        return str(v)

    mapping = {
        "amount": _norm_choice(w_amount),
        "debit_amount": _norm_choice(w_debit),
        "credit_amount": _norm_choice(w_credit),
        "date": _norm_choice(w_date),
        "account": _norm_choice(w_account),
        "account_desc": _norm_choice(w_account_desc),
        "line_desc": _norm_choice(w_line_desc),
        "beneficiary": _norm_choice(w_beneficiary),
        "movement_number": _norm_choice(w_movement_number),
    }

    # ---------- simple completeness check ----------
    has_amount_account = _is_filled(mapping.get("amount")) and _is_filled(
        mapping.get("account")
    )
    has_debit_credit_account = (
        _is_filled(mapping.get("debit_amount"))
        and _is_filled(mapping.get("credit_amount"))
        and _is_filled(mapping.get("account"))
    )
    if not (has_amount_account or has_debit_credit_account):
        notify.error("Map at least Account, plus Amount *or* both Debit & Credit.")
        stop_fn = getattr(notify, "stop", None)
        if callable(stop_fn):
            stop_fn()
        return {}, None

    session_state.update(
        {
            # individual keys for next fast-path
            f"{key_prefix}map_amount": mapping["amount"],
            f"{key_prefix}map_debit": mapping["debit_amount"],
            f"{key_prefix}map_credit": mapping["credit_amount"],
            f"{key_prefix}map_date": mapping["date"],
            f"{key_prefix}map_account": mapping["account"],
            f"{key_prefix}map_account_desc": mapping["account_desc"],
            f"{key_prefix}map_line_desc": mapping["line_desc"],
            f"{key_prefix}map_beneficiary": mapping["beneficiary"],
            f"{key_prefix}map_movement_number": mapping["movement_number"],
            f"{key_prefix}mapping_done": True,
        }
    )

    return mapping, layout


__all__ = [
    "load_data",
    "map_columns",
    "pick_column",
    "show_mapping_panel",
    "NONE_TOKENS",
]
