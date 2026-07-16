import importlib
import sys
from pathlib import Path


def _import_llm_module(monkeypatch):
    """Import and reload the module under test."""
    for module_name in (
        "modules.utilities.config",
        "modules.utilities.helpers",
        "modules.utilities.secrets_loader",
        "modules.utilities.utils",
    ):
        module = sys.modules.get(module_name)
        if module is not None and not getattr(module, "__file__", None):
            del sys.modules[module_name]
    import modules.llm.llm_call_wrapper as llm_mod

    return importlib.reload(llm_mod)


def _set_temp_wrapper_template(monkeypatch, llm_mod, tmp_path):
    record_file = tmp_path / "llm" / "record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)

    def _template():
        return {
            "mode": "replay",
            "record_file": str(record_file),
            "step_config": {
                "llmFallbackQuery": "live",
            },
        }

    monkeypatch.setattr(llm_mod, "get_llm_wrapper_template", _template)
    return record_file


def test_import_does_not_require_writable_cache(monkeypatch):
    def _fail_mkdir(self, *_, **__):
        raise PermissionError

    monkeypatch.setattr(Path, "mkdir", _fail_mkdir)
    llm_mod = _import_llm_module(monkeypatch)
    assert hasattr(llm_mod, "LLMCallWrapper")


def test_init_llm_wrapper_initializes_session_state(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.chdir(tmp_path)  # avoid reading any real record.json
    llm_mod = _import_llm_module(monkeypatch)
    record_file = _set_temp_wrapper_template(monkeypatch, llm_mod, tmp_path)
    session_state = {}

    # Act
    llm_mod.init_llm_wrapper("hello world", session_state)

    # Assert
    assert session_state["correction_prompt_llm"] is None
    assert session_state["user_issue_edits"] == {}
    assert session_state["original_markdown_text"] == "hello world"
    assert "llm_wrapper" in session_state
    wrapper = session_state["llm_wrapper"]
    assert isinstance(wrapper, llm_mod.LLMCallWrapper)
    assert wrapper.mode == "replay"
    assert wrapper.record_file == str(record_file)
    # Spot-check a configured step and removed legacy steps
    assert wrapper.step_config.get("llmFallbackQuery") == "live"
    assert "ocrFallbackQuery" not in wrapper.step_config


def test_init_llm_wrapper_idempotent_preserves_existing_values(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.chdir(tmp_path)
    sentinel = object()
    session_state = {
        "correction_prompt_llm": "foo",
        "user_issue_edits": {"x": 1},
        "original_markdown_text": "existing",
        "llm_wrapper": sentinel,
    }
    llm_mod = _import_llm_module(monkeypatch)
    _set_temp_wrapper_template(monkeypatch, llm_mod, tmp_path)

    # Act
    llm_mod.init_llm_wrapper("new value", session_state)

    # Assert: nothing overwritten
    assert session_state["correction_prompt_llm"] == "foo"
    assert session_state["user_issue_edits"] == {"x": 1}
    assert session_state["original_markdown_text"] == "existing"
    assert session_state["llm_wrapper"] is sentinel


def test_init_llm_wrapper_sets_missing_only(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.chdir(tmp_path)
    session_state = {
        "correction_prompt_llm": "bar",
        "original_markdown_text": "keep me",
    }
    llm_mod = _import_llm_module(monkeypatch)
    _set_temp_wrapper_template(monkeypatch, llm_mod, tmp_path)

    # Act
    llm_mod.init_llm_wrapper("ignored if present", session_state)

    # Assert: existing preserved, missing added
    assert session_state["correction_prompt_llm"] == "bar"
    assert session_state["original_markdown_text"] == "keep me"
    assert session_state["user_issue_edits"] == {}
    assert isinstance(session_state["llm_wrapper"], llm_mod.LLMCallWrapper)
