import importlib
import json
import sys
import types
from io import BytesIO
from pathlib import Path

import pytest


class NamedBytesIO(BytesIO):
    """BytesIO with a .name attribute to mimic uploaded files."""

    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def _import_lrl_with_stubs(monkeypatch):
    """Import src.load_report_logic with stubs to avoid circular dependencies."""
    fake_manage = types.ModuleType("modules.layout.manage_session")
    fake_manage.cleanup_session_folder = lambda p: None
    fake_manage.initialize_session_folder = lambda: Path("/tmp/fake_session")
    monkeypatch.setitem(sys.modules, "modules.layout.manage_session", fake_manage)

    fake_llm_pkg = types.ModuleType("modules.llm")
    fake_llm_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "modules.llm", fake_llm_pkg)

    fake_prompts = types.ModuleType("modules.llm.prompt_helpers")
    fake_prompts.extract_industry_and_company_from_dict = lambda d: d or {}
    monkeypatch.setitem(sys.modules, "modules.llm.prompt_helpers", fake_prompts)

    fake_ui = types.ModuleType("modules.llm.ui_helpers")
    fake_ui.convert_image_for_GPT = lambda f, *a, **k: b"img"
    monkeypatch.setitem(sys.modules, "modules.llm.ui_helpers", fake_ui)

    sys.modules.pop("src.load_report_logic", None)
    return importlib.import_module("src.load_report_logic")


@pytest.mark.parametrize(
    "gate,expected",
    [
        (False, ("exec_passthrough", {"img": 1}, {"desc": 1})),
        (True, ({"ok": True}, {"png": "x"}, {"d": 1})),
    ],
)
def test_get_json_and_plots_from_disk_gates_loading(monkeypatch, gate, expected):
    # Arrange
    lrl = _import_lrl_with_stubs(monkeypatch)
    naming = {
        "fileCodeName": "fileCode",
        "isDataUploaded": "isUploaded",
        "notMetConditionValue": 0,
    }
    monkeypatch.setattr(lrl, "get_naming_params", lambda: naming)

    # When the gate is open, delegate to loader and return its values
    monkeypatch.setattr(
        lrl,
        "load_json_and_plots_from_disk",
        lambda pd: ({"ok": True}, {"png": "x"}, {"d": 1}),
    )

    param = {"fileCode": "code", "isUploaded": 0} if gate else {"isUploaded": 1}
    passthrough = ("exec_passthrough", {"img": 1}, {"desc": 1})

    # Act
    result = lrl.get_json_and_plots_from_disk(param, *passthrough)

    # Assert
    assert result == expected


def test_load_json_and_plots_from_disk_reads_json_and_images(tmp_path, monkeypatch):
    # Arrange minimal config and helpers
    lrl = _import_lrl_with_stubs(monkeypatch)
    reports_root = tmp_path / "reports"
    chosen_folder = "folder1"
    (reports_root / chosen_folder / "json").mkdir(parents=True)
    (reports_root / chosen_folder / "images").mkdir(parents=True)

    # Create JSON files
    exec_json = reports_root / chosen_folder / "json" / "executive.json"
    desc_json = reports_root / chosen_folder / "json" / "descriptions.json"
    exec_json.write_text(json.dumps({"raw": "data"}))
    desc_json.write_text(json.dumps({"desc": 123}))

    # Create PNG filenames (contents don't matter; we stub Image.open)
    (reports_root / chosen_folder / "images" / "A.png").write_bytes(b"")
    (reports_root / chosen_folder / "images" / "Z.png").write_bytes(b"")

    # Config stubs
    monkeypatch.setattr(
        lrl,
        "get_naming_params",
        lambda: {"fileCodeName": "fileCode", "chosenReportFolderName": "chosen"},
    )
    monkeypatch.setattr(
        lrl,
        "get_file_params",
        lambda: {
            "jsonExecutiveSummaryName": "executive",
            "jsonDescriptionsName": "descriptions",
            "reportsFolderName": str(reports_root),
            "jsonFolderName": "json",
            "imagesFolderName": "images",
        },
    )
    monkeypatch.setattr(
        lrl,
        "get_report_params",
        lambda: {"code1": {"chosen": chosen_folder}},
    )
    # Avoid UI/session side effects; return keys we expect to validate
    monkeypatch.setattr(
        lrl,
        "extract_industry_and_company_from_dict",
        lambda d: {"A": {"v": 1}, "B": {"v": 2}},
    )

    # Stub PIL.Image.open to avoid decoding empty files
    class _Img:
        @staticmethod
        def open(p: Path):
            return f"opened:{Path(p).name}"

    monkeypatch.setattr(lrl, "Image", _Img)

    param = {"fileCode": "code1"}

    # Act
    validated, image_dict, descriptions = lrl.load_json_and_plots_from_disk(param)

    # Assert
    assert validated == {"A": {"v": 1}}  # only keys with matching PNGs
    assert set(image_dict.keys()) == {"A.png", "Z.png"}
    assert descriptions == {"desc": 123}


def test_process_uploaded_files_missing_exec_json_adds_error(monkeypatch):
    # Arrange config
    lrl = _import_lrl_with_stubs(monkeypatch)
    monkeypatch.setattr(
        lrl,
        "get_naming_params",
        lambda: {
            "metConditionValue": "MET",
            "reportUploaded": "reportUploaded",
        },
    )
    monkeypatch.setattr(
        lrl,
        "get_file_params",
        lambda: {"jsonExecutiveSummaryName": "executive", "jsonDescriptionsName": "descriptions"},
    )

    # Capture error messages
    errors: list[str] = []

    def _add_err(pd, msg):
        errors.append(msg)
        pd.setdefault("__errors__", []).append(msg)
        return pd

    monkeypatch.setattr(lrl, "add_error_message_in_load_data_tab", _add_err)

    # Prepare uploaded files: a PNG and a descriptions JSON, but no executive JSON
    png = NamedBytesIO(b"fake", name="A.png")
    desc = NamedBytesIO(json.dumps({"d": 1}).encode(), name="descriptions.json")
    param = {}

    # Act
    validated, image_dict, descriptions, new_param = lrl.process_uploaded_files(
        [png, desc], param
    )

    # Assert
    assert validated == {}
    assert image_dict == {}
    assert errors  # error was recorded
    assert "__errors__" in new_param
