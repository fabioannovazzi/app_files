from modules.process_excel.ui_helpers import load_data, show_mapping_panel
from modules.utilities.ui_notifier import FastAPINotifier


def test_show_mapping_panel_emits_warning_for_duplicates():
    notifier = FastAPINotifier()
    mapping = {
        "amount": "Amount",
        "debit_amount": "Amount",
        "credit_amount": "Credit",
    }

    show_mapping_panel(mapping, "map", notifier=notifier)

    assert any(event["level"] == "warning" for event in notifier.events)


def test_load_data_without_upload_emits_info():
    notifier = FastAPINotifier()

    df, used_pf = load_data(object(), "random_entries", notifier=notifier)

    assert df is None
    assert used_pf is False
    assert any(
        event["level"] == "info" and "Upload a file first" in event["message"]
        for event in notifier.events
    )
