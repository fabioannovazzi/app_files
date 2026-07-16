import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modules.layout.set_up_widgets as suw


def test_download_plot_file_ui_integration(monkeypatch):
    df = pl.DataFrame({"value": [1, 2]})
    captured = {}

    monkeypatch.setattr(suw.ui, "caption", lambda *a, **k: None)

    def fake_download_button(*, label, data, file_name, mime):
        captured.update(
            {"label": label, "data": data, "file_name": file_name, "mime": mime}
        )

    monkeypatch.setattr(suw.ui, "download_button", fake_download_button)

    suw.download_plot_file(df, "testfile")

    assert captured["file_name"] == "testfile.csv"
    content = captured["data"].decode("utf-8").splitlines()
    assert content[0].startswith("index")
    assert content[1].startswith("0")
