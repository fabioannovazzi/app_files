from __future__ import annotations


class DummyNotifier:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def info(self, msg):
        self.calls.append(("info", msg))


def import_theme(monkeypatch):
    import modules.layout.theme as theme

    return theme


def test_load_theme_is_noop_notifies(monkeypatch):
    # Arrange: stub notifier for the deprecated theme loader
    theme = import_theme(monkeypatch)
    notifier = DummyNotifier()
    monkeypatch.setattr(theme, "ui", notifier)

    # Act
    result = theme.load_theme()

    # Assert
    assert result is None
    assert notifier.calls == [("info", "UI theme assets have been removed.")]
