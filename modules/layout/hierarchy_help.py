from __future__ import annotations

from modules.utilities.ui_notifier import ui

from modules.utilities.config import get_naming_params

__all__ = ["show_hierarchy_messages", "show_product_parent_messages"]


def show_hierarchy_messages(language: str = "en") -> None:
    """Explain how to use the hierarchy tab.

    Args:
        language: Output language, ``"en"`` or ``"it"``.
    """

    naming_params = get_naming_params()
    _ = naming_params["hierarchyTabLabel"]
    if language == "it":
        ui.markdown(
            "1️⃣ **Esegui il controllo della gerarchia** per rilevare potenziali coppie figlio → genitore."
        )
        ui.markdown(
            "2️⃣ **Rivedi l'anteprima** e analizza le righe ambigue quando presenti."
        )
        ui.markdown(
            "3️⃣ **Applica le correzioni** per imporre un singolo genitore per ogni figlio e scarica il dataset pulito."
        )
    else:
        ui.markdown(
            "1️⃣ **Run hierarchy check** to detect potential child → parent pairs."
        )
        ui.markdown("2️⃣ **Review the preview** and inspect ambiguous rows when shown.")
        ui.markdown(
            "3️⃣ **Apply Fixes** to enforce a single parent per child and download the cleaned dataset."
        )





def show_product_parent_messages(language: str = "en") -> None:
    """Describe how to use the Get PDPs tab."""

    naming_params = get_naming_params()
    _ = naming_params["getLinesTabLabel"]
    if language == "it":
        ui.markdown(
            "1️⃣ **Esegui Add Attributes** per arricchire il dataset con le classificazioni."
        )
        ui.markdown(
            "2️⃣ **Apri Get PDPs** per vedere come i prodotti vengono raggruppati automaticamente in base al brand e alla categoria."
        )
        ui.markdown(
            "3️⃣ **Scarica o filtra** i PDP suggeriti per validarli o riutilizzarli in altri strumenti."
        )
    else:
        ui.markdown(
            "1️⃣ **Run Add Attributes** to enrich the dataset with classifications."
        )
        ui.markdown(
            "2️⃣ **Open Get PDPs** to review automatically inferred PDPs within each brand and category."
        )
        ui.markdown(
            "3️⃣ **Download or filter** the suggestions to validate or reuse the detected PDPs elsewhere."
        )
