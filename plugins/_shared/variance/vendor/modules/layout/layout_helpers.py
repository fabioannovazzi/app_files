import inspect
import logging

from PIL import Image

from modules.layout.core.ui_adapter import UIAdapter, ui
from modules.utilities.session_context import session_state

try:
    from modules.utilities.config import (
        get_config_params,
        get_naming_params,
    )
except Exception as e:  # fallback for tests stubbing this module
    logging.exception(e)
    ui.error("Something went wrong while importing configuration helpers.")

    def get_naming_params():
        return {}

    def get_config_params():
        return {}


try:
    from modules.utilities.error_messages import add_app_message_to_paramdict
except Exception as e:
    logging.exception(e)
    ui.error("Something went wrong while importing error-message helpers.")

    def add_app_message_to_paramdict(*_a, **_k):
        return {}


try:
    from modules.utilities.helpers import (
        get_chart_image_info,
        print_error_details,
    )
except Exception as e:  # pragma: no cover
    logging.exception(e)
    ui.error("Something went wrong while importing utility helpers.")

    def get_chart_image_info(*_a, **_k):
        return {}

    def print_error_details(*_a, **_k):
        return ""


def show_error_ui(message: str, details: Exception | str) -> None:
    """Render error details in the UI."""
    ui.error(message)
    ui.exception(details)


def show_warning_ui(message: str) -> None:
    """Display a warning message in the UI."""
    ui.warning(message)


def show_language_selector() -> None:
    """Render a language selector widget with a unique key."""
    session_state.setdefault("help_lang", "English")

    stack = inspect.stack()
    caller = stack[1].function if len(stack) > 1 else "root"
    if caller == "_display_help_text" and len(stack) > 2:
        caller = stack[2].function

    widget_key = f"help_lang_{caller}"
    if widget_key not in session_state:
        session_state[widget_key] = session_state["help_lang"]

    lang = ui.radio(
        "Help language",
        ["English", "Italiano"],
        key=widget_key,
        horizontal=True,
    )
    session_state["help_lang"] = lang


def _display_help_text(help_text: dict[str, str]) -> None:
    """Render localized help text with an inline selector."""
    show_language_selector()
    ui.markdown(help_text[session_state.get("help_lang", "English")])


def make_six_col_width_array():
    col_width_array = [1, 1, 1, 1, 1, 1]
    col1, col2, col3, col4, col5, col6 = ui.columns(col_width_array)
    return [col1, col2, col3, col4, col5, col6]


def make_five_col_width_array():
    col_width_array = [1, 1, 1, 1, 1]
    col1, col2, col3, col4, col5 = ui.columns(col_width_array)
    return [col1, col2, col3, col4, col5]


def make_four_col_width_array():
    col_width_array = [1, 1, 1, 1]
    col1, col2, col3, col4 = ui.columns(col_width_array)
    return [col1, col2, col3, col4]


def make_two_plus_one_col_width_array():
    col_width_array = [1, 1, 2]
    col1, col2, col3 = ui.columns(col_width_array)
    return [col1, col2, col3]


def make_two_col_width_array():
    col_width_array = [1, 1]
    col1, col2 = ui.columns(col_width_array)
    return [col1, col2]


def make_three_col_width_array():
    col_width_array = [1, 1, 1]
    col1, col2, col3 = ui.columns(col_width_array)
    return [col1, col2, col3]


def make_large_and_small_two_col_width_array():
    col_width_array = [3, 1]
    col1, col2 = ui.columns(col_width_array)
    return [col1, col2]


def make_small_and_large_two_col_width_array():
    col_width_array = [1, 3]
    col1, col2 = ui.columns(col_width_array)
    return [col1, col2]


def make_small_large_small_three_col_width_array():
    col_width_array = [4, 1, 12, 4]
    col1, col2, col3, col4 = ui.columns(col_width_array)
    return [col1, col2, col3, col4]


def show_chart_image(
    chart_name: str | None,
    col: UIAdapter,
    param_dict: dict,
) -> dict:
    """Display ``chart_name`` image in the provided column."""

    naming_params = get_naming_params()
    error_type = naming_params["errorMessageType"]
    info_type = naming_params["infoMessageType"]
    plot_charts_tab = naming_params["plotChartsTab"]
    show_examples_key = naming_params["showPlotExamples"]
    not_met = naming_params["notMetConditionValue"]
    met_condition = naming_params["metConditionValue"]
    col_number = 2

    show_examples = not_met
    if show_examples_key in param_dict and param_dict[show_examples_key]:
        show_examples = not_met

    if chart_name and show_examples:
        try:
            image_path, caption = get_chart_image_info(chart_name)
            with col:
                try:
                    with Image.open(image_path) as image:
                        ui.caption(caption + " plot")
                        ui.image(image, caption=None)
                except Exception as e:
                    logging.exception(e)
                    message = "image " + image_path + " file not found."
                    e = print_error_details(e)
                    param_dict = add_app_message_to_paramdict(
                        e,
                        error_type,
                        plot_charts_tab,
                        param_dict,
                        isMessage=True,
                        isToast=False,
                        colNumber=col_number,
                    )
                    param_dict = add_app_message_to_paramdict(
                        message,
                        info_type,
                        plot_charts_tab,
                        param_dict,
                        isMessage=True,
                        isToast=True,
                        colNumber=col_number,
                    )
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong while loading chart image.")
    return param_dict


def show_add_attribute_messages() -> None:
    """Display help text for the Add Attributes tab."""
    namingParams = get_naming_params()
    addAttributesTabLabel = namingParams["addAttributesTabLabel"]  # noqa: F841
    help_text = {
        "English": (
            """1️⃣ Context required for discovery
Provide your **industry** and/or **company** before running attribute enrichment. This
context is used to generate taxonomy branches for new categories when needed.

2️⃣ How classification handles unknown values
- Values like "no idea/unknown/na" are normalized to `N/A`.
- If an LLM returns a value not in the allowed list for an attribute,
  the app emits `other` in the output and records the observation for follow‑up.

3️⃣ Managing improvements
Use the Taxonomy page to manage synonyms and leaves manually as needed.
"""
        ),
        "Italiano": (
            """1️⃣ Contesto necessario per la discovery
Inserisci **settore** e/o **azienda** prima di eseguire l'arricchimento. Questo contesto
serve a generare rami di tassonomia per nuove categorie quando necessario.

2️⃣ Come vengono gestiti i valori sconosciuti
- Valori come "no idea/unknown/na" vengono normalizzati a `N/A`.
- Se l'LLM restituisce un valore non presente nella lista consentita, l'app emette `other`
  in output e registra l'osservazione per un controllo successivo.

3️⃣ Gestione miglioramenti
Usa la pagina Tassonomia per gestire manualmente sinonimi e foglie quando necessario.
"""
        ),
    }
    _display_help_text(help_text)
    return None


def show_check_statements_messages() -> None:
    """Display minimal help text for the Check Statements tab."""
    help_text: dict[str, str] = {
        "English": (
            """1. Upload
   - Bank statements (PDF/Excel/CSV)
   - Ledger files (entries of the bank account)

2. Select the bank account
   - Pick the account to reconcile; exclude other accounts if needed

3. Set tolerances (2 controls)
   - Amount tolerance (absolute)
   - Date window (days)

 Stages in order
   1) Amount and Date Window — assign when the amount/date match is unique within the window; ambiguous rows are deferred to later stages.
   2) Bank Fees and Charges — accept small bank fees/charges; creates synthetic fee entries; does not consume ledger rows
   3) Cash Withdrawals/Deposits — match ATM movemenrs on both sides within the amount/date tolerance.
   4) Card Payments — match card transactions when both sides share the same operation type within tolerance/window.
   5) Payroll and Taxes — requires the Amount and Date Window; accept when the bank description mentions payroll (synonyms: stipendio/salari/busta paga/cedolino/retribuzione) with a payroll‑labelled ledger account, OR tax payments (F24) against tax‑labelled ledger entries; nearest‑date within window.
   6) Beneficiary Name — accept on beneficiary similarity (no IBAN) when within the tolerance/window.
   7) IBAN — accept on exact IBAN equality within the tolerance/window.
   8) References (Invoice/CRO/TRN) — accept on shared references (invoice number, CRO/TRN, EndToEndId).
   Baseline: Stages 3–8 all start from the same Stage‑1 assigned pool; Stage 2 starts from the Stage‑1 not‑matched pool.
Behaviour
   - Non‑transaction lines (headers, numeric balance tables) are dropped automatically before matching.
   - Dense days (many same‑amount payments) are handled automatically.
   - F24 bank payments only match tax‑posted ledger lines.

Results
   - The funnel shows a Starting column; stages 3–8 start from Stage 1 (assigned), while Bank Fees and Charges starts from the Stage‑1 not‑matched pool.
   - Balanced amount/date clusters and value buckets help fast clearance.

Export
   - Excel includes: summary, matched, unmatched_bank, unmatched_ledger, settings, diagnostics. No "dropped_rows" sheet.
"""
        ),
        "Italiano": (
            """1. Carica
   - Estratti conto (PDF/Excel/CSV)
   - Prima nota del conto banca

2. Seleziona il conto
   - Scegli il conto da riconciliare; escludi gli altri se necessario

3. Imposta le tolleranze (2 controlli)
   - Tolleranza importo (assoluta)
   - Finestra date (giorni)

Stadi in sequenza
   1) Amount and Date Window — abbinamento per importo e finestra temporale; i duplicati si risolvono col più vicino per data.
   2) Spese e Commissioni Bancarie — accetta piccole spese/commissioni bancarie; crea righe sintetiche per le spese; non consuma scritture di prima nota.
   3) Prelievi e versamenti Bancomat — abbina i prelievi ATM su entrambi i lati entro tolleranza e finestra.
   4) Pagamenti con Carta — abbina i pagamenti con carta quando l'operazione coincide su entrambi i lati entro tolleranza/finestra.
   5) Payroll e Imposte — richiede finestra Importo/Data; accetta quando la descrizione banca cita la paga (sinonimi: stipendio/salari/busta paga/cedolino/retribuzione) con conto PN payroll, OPPURE F24 contro scritture fiscali; data più vicina entro finestra.
   6) Beneficiary — accetta su similarità del beneficiario (senza IBAN) quando dentro tolleranza e finestra.
   7) IBAN — accetta su IBAN identico entro tolleranza/finestra.
   8) Riferimenti (Fattura/CRO/TRN) — accetta su riferimenti condivisi (numero fattura, CRO/TRN, EndToEndId).
   Baseline: Gli stadi 3–8 partono tutti dagli assegnati dello Stadio 1; lo Stadio 2 parte dai non abbinati dello Stadio 1.

Comportamento
   - Le righe non transazionali (intestazioni, tabelle di saldo numeriche) vengono scartate automaticamente prima del matching.
   - Le giornate “dense” (molti pagamenti con stesso importo) sono gestite automaticamente.
   - I pagamenti F24 si abbinano solo a scritture fiscali.

Risultati
   - La funnel mostra la colonna Starting; gli stadi 3–8 partono dagli assegnati dello Stadio 1, mentre Spese e Commissioni Bancarie parte dai non abbinati dello Stadio 1.
   - I cluster bilanciati importo/data e i bucket per valore aiutano lo sfoltimento.

Esportazione
   - Excel include: summary, matched, unmatched_bank, unmatched_ledger, settings, diagnostics. Nessun foglio "dropped_rows".
"""
        ),
    }
    _display_help_text(help_text)


def show_check_report_messages() -> None:
    """Display help text for the Check Report tab."""
    namingParams = get_naming_params()
    checkResearchTabLabel = namingParams["checkResearchTabLabel"]  # noqa: F841
    help_text = {
        "English": (
            """1️⃣ **Paste Your Document**
Select All - Copy - Paste the OpenAI Deep Research report you want to verify or upload the PDF, then click **Run Checks**.

2️⃣ **System Identifies Key Claims**
The app scans your text to find the main statements or “claims” contained in the document.

3️⃣ **Verification Against Sources**
- If a claim has URL references, the system checks whether those sources actually support the claim.
- If no references are provided, it attempts to find reputable sources for confirmation.

4️⃣ **Reasoning Check**
The system also evaluates whether each claim is logically coherent—i.e., whether the argument or reasoning behind it makes sense.

5️⃣ **Review Flagged Claims**
Inspect each claim’s issues. For any issue, you can **keep**, **edit** or **ignore** it.

6️⃣ **Rebuild the Document**
After deciding which issues to keep, edit or ignore, click **Generate Updated Document**. You’ll get a new version of your research that omits or revises any discredited claims."""
        ),
        "Italiano": (
            """1️⃣ **Incolla il tuo documento**
Seleziona tutto - copia - incolla il report di OpenAI Deep Research da verificare oppure carica il PDF, quindi clicca **Run Checks**.

2️⃣ **Il sistema individua le affermazioni chiave**
L'app analizza il testo per trovare le principali affermazioni contenute nel documento.

3️⃣ **Verifica delle fonti**
- Se un'affermazione ha riferimenti URL, il sistema controlla che le fonti la supportino.
- Se non ci sono riferimenti, tenta di trovare fonti affidabili per confermarla.

4️⃣ **Controllo della logica**
Il sistema valuta anche la coerenza logica di ogni affermazione.

5️⃣ **Rivedi le affermazioni segnalate**
Esamina ogni affermazione e i relativi problemi. Per ciascuno puoi **tenere**, **modificare** o **ignorare**.

6️⃣ **Ricostruisci il documento**
Dopo aver scelto cosa tenere, modificare o ignorare, clicca **Generate Updated Document**. Otterrai una nuova versione del report senza le affermazioni smentite o con le revisioni."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_load_data_messages() -> None:
    """Display help text for the Load Data tab."""
    namingParams = get_naming_params()
    clearCacheLabel = namingParams["clearCacheLabel"]
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]  # noqa: F841
    allDimensionsStringLabel = namingParams["allDimensionsStringLabel"]  # noqa: F841
    fileChoiceLabel = namingParams["fileChoiceLabel"]  # noqa: F841
    submitPlotLabel = namingParams["submitPlotLabel"]  # noqa: F841
    help_text = {
        "English": (
            f"""1️⃣ Insert your activation token to enable the app.

2️⃣ Choose an example dataset or **upload a Excel / CSV** file. To upload a dataset, set the **Choose a test  dataset** widget to 'I will upload a file'.

3️⃣ Call your gross sales column **Amount** and your date column **Date**. If your dataset has a period/scenario column, call it **Period**. You can call your dimension columns as you wish.

4️⃣ Check that the metric columns of your dataset have been mapped correctly. If everything else fails , click on the **{clearCacheLabel}** button below to start over.

5️⃣ Set the currency, the color palette. If you add the name of the reporting entity this will be shown in the chart title. Choose if you want GPT to add a comment to the charts."""
        ),
        "Italiano": (
            f"""1️⃣ Inserisci il token di attivazione per abilitare l'app.

2️⃣ Scegli un dataset di esempio oppure **carica un file Excel/CSV**. Per caricare un dataset imposta il widget **Choose a test  dataset** su 'I will upload a file'.

3️⃣ Chiama la colonna delle vendite lorde **Amount** e quella della data **Date**. Se il tuo dataset ha una colonna periodo/scenario, chiamala **Period**. Le colonne di dimensione possono avere qualsiasi nome.

4️⃣ Verifica che le colonne metriche siano state mappate correttamente. Se tutto fallisce, clicca il pulsante **{clearCacheLabel}** qui sotto per ricominciare.

5️⃣ Imposta valuta e palette colori. Se aggiungi il nome dell'entità riportante sarà mostrato nel titolo del grafico. Decidi se GPT deve aggiungere un commento ai grafici."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_join_dataset_messages() -> None:
    """Display help text for joining datasets."""
    namingParams = get_naming_params()
    clearCacheLabel = namingParams["clearCacheLabel"]  # noqa: F841
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]  # noqa: F841
    loadDataTabLabel = namingParams["loadDataTabLabel"]
    allDimensionsStringLabel = namingParams["allDimensionsStringLabel"]
    fileChoiceLabel = namingParams["fileChoiceLabel"]  # noqa: F841
    submitPlotLabel = namingParams["submitPlotLabel"]  # noqa: F841
    help_text = {
        "English": (
            f"""1️⃣ You can choose whether to keep zero and negative values, and whether to automatically drop duplicate rows from the dataset.

2️⃣ You can join dimension tables to your main dataset. Make sure the columns are named the same in both datasets and the keys are unique. Upload the dimension tables using the widget below.

3️⃣ If the join keys are numeric columns (aka codes) make sure the **{allDimensionsStringLabel}** widget in the **{loadDataTabLabel}** tab is set to False.

4️⃣ You can download the joined table to avoid performing the join each time you use the app.

5️⃣ Summary ℹ️ info on the loaded dataset is given below."""
        ),
        "Italiano": (
            f"""1️⃣ Puoi decidere se mantenere valori zero e negativi e se eliminare automaticamente le righe duplicate dal dataset.

2️⃣ Puoi unire tabelle di dimensioni al dataset principale. Assicurati che le colonne abbiano lo stesso nome in entrambe le tabelle e che le chiavi siano uniche. Carica le tabelle usando il widget sottostante.

3️⃣ Se le chiavi di join sono colonne numeriche (cioè codici) assicurati che il widget **{allDimensionsStringLabel}** nella scheda **{loadDataTabLabel}** sia impostato su False.

4️⃣ Puoi scaricare la tabella unita per evitare di ripetere il join ogni volta che usi l'app.

5️⃣ Di seguito trovi un riepilogo ℹ️ delle informazioni sul dataset caricato."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_plan_data_messages() -> None:
    """Display help text for the Plan Data tab."""
    namingParams = get_naming_params()
    configParams = get_config_params()
    clearCacheLabel = namingParams["clearCacheLabel"]  # noqa: F841
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]  # noqa: F841
    fileChoiceLabel = namingParams["fileChoiceLabel"]  # noqa: F841
    planDataTabLabel = namingParams["planDataTabLabel"]
    setTimePeriodTabLabel = namingParams["setTimePeriodTabLabel"]
    numberOfItems = configParams[namingParams["numberOfItems"]]
    numberOfDimensions = configParams[namingParams["numberOfDimensions"]]
    help_text = {
        "English": (
            f"""1️⃣ Generates a {planDataTabLabel} from a dataset with 12 rolling or calendar months of Actual data.

2️⃣ In the {setTimePeriodTabLabel} tab, set the Compare period to date widget to False.

3️⃣ Choose the approach to apply when a dataset row meets more than one condition: use first modifier or multiply modifiers.

4️⃣ Choose to separately forecast other metrics (discounts, cogs) or set their forecast proportionally to the Amount forecaui.

5️⃣ Set default forecast values.

6️⃣ Select a dimension or a set of dimensions.

7️⃣ For each dimension/set of dimensions, select the condition value items and the default forecast modifiers.

8️⃣ Click on New Item to add a condition item to a dimension, on New Dimension to add dimensions. Up to {numberOfDimensions} sets of dimensions and {numberOfItems} items for each dimension.

9️⃣ You can save your planning scenario as a playback JSON file and reload the file to re-run or modify the scenario."""
        ),
        "Italiano": (
            f"""1️⃣ Genera un {planDataTabLabel} da un dataset con 12 mesi consecutivi o di calendario di dati Actual.

2️⃣ Nella scheda {setTimePeriodTabLabel} imposta il widget Compare period to date su False.

3️⃣ Scegli l'approccio da applicare quando una riga del dataset soddisfa più condizioni: usa il primo modificatore oppure moltiplica i modificatori.

4️⃣ Decidi se prevedere separatamente altre metriche (sconti, cogs) o impostarle in proporzione all'Amount previsto.

5️⃣ Imposta i valori di forecast predefiniti.

6️⃣ Seleziona una dimensione o un insieme di dimensioni.

7️⃣ Per ogni dimensione/insieme di dimensioni, scegli gli elementi di condizione e i modificatori di forecast predefiniti.

8️⃣ Clicca su New Item per aggiungere un elemento di condizione a una dimensione, su New Dimension per aggiungere dimensioni. Fino a {numberOfDimensions} insiemi di dimensioni e {numberOfItems} elementi per ciascuna.

9️⃣ Puoi salvare lo scenario di pianificazione in un file JSON di playback e ricaricarlo per rieseguirlo o modificarlo."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_open_ai_messages() -> None:
    """Display help text for the OpenAI tab."""
    namingParams = get_naming_params()
    configParams = get_config_params()
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]
    openAITabLabel = namingParams["openAITabLabel"]  # noqa: F841
    submitPromptLabel = namingParams["submitPromptLabel"]
    loadDataTabLabel = namingParams["loadDataTabLabel"]
    numberOfItems = configParams[namingParams["numberOfItems"]]  # noqa: F841
    numberOfDimensions = configParams[namingParams["numberOfDimensions"]]  # noqa: F841
    help_text = {
        "English": (
            f"""1️⃣ To enable this tab and generate reports automatically, enter your activation token in the {loadDataTabLabel} tab.

2️⃣ Load a dataset and hit the **{submitPromptLabel}** button below. GPT will generate a list of charts to plot that you can download below.

3️⃣ Upload GPT's response in the {plotChartsTabLabel} tab and plot your charts or refine GPT's suggestions. Don't forget to download each chart.

4️⃣ Ask GPT to comment each plot. Add each comment to the comment file. You can edit GPT's comments.

5️⃣ Review the chart files and comment file before using them in a report package."""
        ),
        "Italiano": (
            f"""1️⃣ Per abilitare questa scheda e generare report automaticamente inserisci il token di attivazione nella scheda {loadDataTabLabel}.

2️⃣ Carica un dataset e premi il pulsante **{submitPromptLabel}** qui sotto. GPT genererà un elenco di grafici da tracciare che potrai scaricare.

3️⃣ Carica la risposta di GPT nella scheda {plotChartsTabLabel} e traccia i grafici o affina i suggerimenti. Ricorda di scaricare ogni grafico.

4️⃣ Chiedi a GPT di commentare ogni grafico. Aggiungi ogni commento al file dei commenti. Puoi modificare i commenti di GPT.

5️⃣ Rivedi i file dei grafici e il file dei commenti prima di usarli in un report."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_set_time_period_messages() -> None:
    """Display help text for setting the time period."""
    namingParams = get_naming_params()
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]
    periodToDateLabel = namingParams["periodToDateLabel"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    help_text = {
        "English": (
            f"""1️⃣ Set the time (to date, rolling or calendar) and the period (year, quarter, month or week) horizon for the comparison.

2️⃣ You can also compare scenarios, for instance Actual vs Plan.

3️⃣ Periods and scenarios are notated according to the IBCS standard abbreviations.

4️⃣ Period to date: underscore + period (e.g., _Feb-2020). Rolling 12 months: tilde + period (e.g., ~Feb-2020). Calendar: period (e.g., 2020).

5️⃣ Actual: AC (black), Plan: PL (outlined white), Forecast: FC (hatched), Previous year: PY (grey), Year before previous year: PPY (light grey).

6️⃣ YTD: set the **{periodToDateLabel}** widget to True.

7️⃣ Rolling 12 months: set the **{periodToDateLabel}** widget to False and the Compare with rolling period widget to True.

8️⃣ Calendar: set the **{periodToDateLabel}** widget to False and the Compare with rolling period widget to False.

9️⃣ To plot, wait until the program has finished running, then hit the **{submitPlotLabel}** button in the {plotChartsTabLabel} tab."""
        ),
        "Italiano": (
            f"""1️⃣ Imposta l'orizzonte temporale (to date, rolling o calendar) e il periodo (anno, trimestre, mese o settimana) per il confronto.

2️⃣ Puoi anche confrontare scenari, ad esempio Actual vs Plan.

3️⃣ Periodi e scenari sono indicati secondo le abbreviazioni standard IBCS.

4️⃣ Period to date: underscore + periodo (es. _Feb-2020). Rolling 12 mesi: tilde + periodo (es. ~Feb-2020). Calendar: periodo (es. 2020).

5️⃣ Actual: AC (nero), Plan: PL (bianco contornato), Forecast: FC (tratteggiato), Previous year: PY (grigio), Year before previous year: PPY (grigio chiaro).

6️⃣ YTD: imposta il widget **{periodToDateLabel}** su True.

7️⃣ Rolling 12 mesi: imposta il widget **{periodToDateLabel}** su False e attiva il widget Compare with rolling period.

8️⃣ Calendar: imposta il widget **{periodToDateLabel}** su False e disattiva il widget Compare with rolling period.

9️⃣ Per tracciare, attendi il completamento dell'elaborazione e premi il pulsante **{submitPlotLabel}** nella scheda {plotChartsTabLabel}."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_filter_data_messages() -> None:
    """Display help text for the Filter Data tab."""
    namingParams = get_naming_params()
    clearCacheLabel = namingParams["clearCacheLabel"]  # noqa: F841
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    help_text = {
        "English": (
            f"""1️⃣ You can filter your dataset data to exclude certain elements or to include only certain elements.

2️⃣ You can apply up to four filters.

3️⃣ The applied filters will be automatically shown in the chart title.

4️⃣ If you specify the reporting entity name, this will be shown in the chart title if no filter is applied.

5️⃣ To plot, wait until the program has finished running, then hit the **{submitPlotLabel}** button in the {plotChartsTabLabel} tab."""
        ),
        "Italiano": (
            f"""1️⃣ Puoi filtrare il dataset per escludere o includere solo determinati elementi.

2️⃣ Puoi applicare fino a quattro filtri.

3️⃣ I filtri applicati verranno mostrati automaticamente nel titolo del grafico.

4️⃣ Se specifichi il nome dell'entità riportante, sarà mostrato nel titolo quando non ci sono filtri.

5️⃣ Per tracciare, attendi il completamento dell'elaborazione poi premi il pulsante **{submitPlotLabel}** nella scheda {plotChartsTabLabel}."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_variance_calculation_messages() -> None:
    """Display help text for the Variance Calculation tab."""
    namingParams = get_naming_params()
    clearCacheLabel = namingParams["clearCacheLabel"]  # noqa: F841
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    help_text = {
        "English": (
            f"""1️⃣ If you are analysing costs rather than revenues, set the 'color choice widget' to '🟢-🔴+' (positive variance = bad).

2️⃣ Select a calculation option if you want the app to perform it. Otherwise leave the default choice.

3️⃣ Choose if you want the system to perform the variance calculation along one dimension or run root cause bridge analysis across different dimensions.

4️⃣ Choose how you want to show variance among those that can be computed with your dataset.

5️⃣ For example, total variance can be shown aggregated together, or price and volume variance can be shown separately.

6️⃣ To plot, wait until the program has finished running, then hit the **{submitPlotLabel}** button in the {plotChartsTabLabel} tab."""
        ),
        "Italiano": (
            f"""1️⃣ Se analizzi i costi e non i ricavi, imposta il 'color choice widget' su '🟢-🔴+' (varianza positiva = negativa).

2️⃣ Se vuoi che l'app esegua un calcolo specifico, seleziona l'opzione desiderata; altrimenti lascia quella predefinita.

3️⃣ Scegli se calcolare la varianza su una sola dimensione o effettuare un'analisi bridge delle cause lungo diverse dimensioni.

4️⃣ Decidi come mostrare la varianza tra le opzioni calcolabili con il tuo dataset.

5️⃣ Ad esempio, la varianza totale può essere aggregata oppure suddivisa tra prezzo e volume.

6️⃣ Per tracciare, attendi il termine dell'elaborazione e premi il pulsante **{submitPlotLabel}** nella scheda {plotChartsTabLabel}."""
        ),
    }
    _display_help_text(help_text)
    return None


def show_plot_chart_messages() -> None:
    """Display help text for the Plot Chart tab."""
    namingParams = get_naming_params()
    clearCacheLabel = namingParams["clearCacheLabel"]  # noqa: F841
    plotChartsTabLabel = namingParams["plotChartsTabLabel"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    help_text = {
        "English": (
            f"""1️⃣ Select the chart type you want to plot.

2️⃣ Click on ➕ **Plot options** to see the available options of the selected chart.

3️⃣ You can annotate the chart, add a message, edit the title and the labels.

4️⃣ To plot, wait until the program has finished running, then hit the **{submitPlotLabel}** button below.

5️⃣ To download the chart image click on the symbol on the upper right of the plot.

6️⃣ You can save your plot parameters in a playback JSON file and reload the file to rerun or modify all your plots.

7️⃣ You can select columns in which you want to analyse cohorts, lost items, unique items and like for like.

8️⃣ If you select the Customer column, the app creates a set of new dimensions (Customer Since, Customer Lost) and metrics (Number of Customers, Sales by Customers, ...)."""
        ),
        "Italiano": (
            f"""1️⃣ Seleziona il tipo di grafico da generare.

2️⃣ Clicca su ➕ **Plot options** per vedere le opzioni disponibili per il grafico scelto.

3️⃣ Puoi annotare il grafico, aggiungere un messaggio, modificare titolo e etichette.

4️⃣ Per tracciare, attendi il completamento dell'elaborazione e premi il pulsante **{submitPlotLabel}** qui sotto.

5️⃣ Per scaricare l'immagine del grafico clicca sull'icona in alto a destra.

6️⃣ Puoi salvare i parametri del grafico in un file JSON di playback e ricaricarlo per rieseguire o modificare i grafici.

7️⃣ Puoi selezionare le colonne su cui analizzare cohorti, elementi persi, unici e like for like.

8️⃣ Se selezioni la colonna Customer l'app crea nuove dimensioni (Customer Since, Customer Lost) e metriche (Number of Customers, Sales by Customers, ...)."""
        ),
    }
    _display_help_text(help_text)
    return None
