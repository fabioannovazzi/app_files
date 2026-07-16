from __future__ import annotations

import pytest

import modules.layout.hierarchy_help as hh


def _capture_markdown(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def _md(msg: str, *args, **kwargs) -> None:  # pragma: no cover - trivial wrapper
        calls.append(msg)

    monkeypatch.setattr(hh.ui, "markdown", _md)
    return calls


@pytest.mark.parametrize(
    "language,expected",
    [
        (
            "en",
            [
                "1️⃣ **Run hierarchy check** to detect potential child → parent pairs.",
                "2️⃣ **Review the preview** and inspect ambiguous rows when shown.",
                "3️⃣ **Apply Fixes** to enforce a single parent per child and download the cleaned dataset.",
            ],
        ),
        (
            "it",
            [
                "1️⃣ **Esegui il controllo della gerarchia** per rilevare potenziali coppie figlio → genitore.",
                "2️⃣ **Rivedi l'anteprima** e analizza le righe ambigue quando presenti.",
                "3️⃣ **Applica le correzioni** per imporre un singolo genitore per ogni figlio e scarica il dataset pulito.",
            ],
        ),
    ],
)
def test_show_hierarchy_messages_outputs_expected(language: str, expected: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    calls = _capture_markdown(monkeypatch)
    monkeypatch.setattr(hh, "get_naming_params", lambda: {"hierarchyTabLabel": "Hierarchy"})

    # Act
    hh.show_hierarchy_messages(language=language)

    # Assert
    assert calls == expected



def test_show_product_parent_messages_fallbacks_to_english_for_unknown_language(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_markdown(monkeypatch)
    monkeypatch.setattr(hh, "get_naming_params", lambda: {"getLinesTabLabel": "Get PDPs"})

    hh.show_product_parent_messages(language="fr")

    assert calls == [
        "1️⃣ **Run Add Attributes** to enrich the dataset with classifications.",
        "2️⃣ **Open Get PDPs** to review automatically inferred PDPs within each brand and category.",
        "3️⃣ **Download or filter** the suggestions to validate or reuse the detected PDPs elsewhere.",
    ]


@pytest.mark.parametrize(
    "func,missing_key",
    [
        (hh.show_hierarchy_messages, "hierarchyTabLabel"),
        (hh.show_product_parent_messages, "getLinesTabLabel"),
    ],
)
def test_messages_raise_keyerror_when_required_naming_param_missing(
    func, missing_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _capture_markdown(monkeypatch)
    monkeypatch.setattr(hh, "get_naming_params", lambda: {})

    with pytest.raises(KeyError):
        func("en")

    assert calls == []
