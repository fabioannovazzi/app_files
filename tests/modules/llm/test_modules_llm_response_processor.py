from modules.llm import response_processor as rp
from modules.llm.response_processor import check_if_image_in_source_dictionary
from modules.utilities.ui_notifier import NullNotifier, use_ui_notifier


class DummyCol:
    """Minimal context manager simulating a UI column."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _use_notifier():
    notifier = NullNotifier()
    return notifier, use_ui_notifier(notifier)


def test_check_if_image_in_source_dictionary_returns_same_when_keys_valid():
    col = DummyCol()
    llm_output = {"1": "imgA", "2": "imgB"}
    original = {"1": "srcA", "2": "srcB"}

    _notifier, ctx = _use_notifier()
    with ctx:
        result = check_if_image_in_source_dictionary(llm_output, original, col)

    assert result is llm_output


def test_check_if_image_in_source_dictionary_calls_synchronize_when_missing_keys(
    monkeypatch,
):
    col = DummyCol()
    llm_output = {"1": "imgA", "3": "imgC"}
    original = {"1": "srcA", "2": "srcB"}
    called = {}

    def fake_sync(orig, llm, _col):
        called["args"] = (orig, llm, _col)
        return {"1": llm["1"], "2": "imgB"}

    monkeypatch.setattr(rp, "synchronize_keys", fake_sync)

    _notifier, ctx = _use_notifier()
    with ctx:
        result = check_if_image_in_source_dictionary(llm_output, original, col)

    assert called["args"] == (original, llm_output, col)
    assert result == {"1": "imgA", "2": "imgB"}
