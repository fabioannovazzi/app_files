import pytest

from modules.check_entries.constants import BeneficiaryCheckMode
from modules.check_entries.logic import (
    _pre_llm_check,  # test behaviour that depends on line_has_keyword
)
from modules.check_entries.logic import (
    LANGUAGE_ALIASES,
    LANGUAGE_NAMES,
    LOCALIZED_STRINGS,
    get_severity_label,
    query_llm_return_json,
)


def test_query_llm_return_json_forwards_all_args(monkeypatch):
    # Arrange
    calls = []

    def fake_router_call(llm_wrapper, query_step, system_prompt, user_prompt, **kwargs):
        calls.append(
            (
                llm_wrapper,
                query_step,
                system_prompt,
                user_prompt,
                kwargs,
            )
        )
        return {"ok": True, "kwargs": kwargs}

    # Patch the router used inside logic.query_llm_return_json
    import modules.check_entries.logic as logic_mod

    monkeypatch.setattr(
        logic_mod.model_router,
        "query_llm_return_json",
        fake_router_call,
        raising=True,
    )

    llm_wrapper = object()
    kwargs = {"tools": ["t"], "tool_choice": "required", "service_tier": "flex"}

    # Act
    res = query_llm_return_json(
        llm_wrapper,
        "checkEntriesQuery",
        "system",
        "user",
        **kwargs,
    )

    # Assert
    assert res["ok"] is True
    assert len(calls) == 1
    _, step, sys_p, usr_p, forwarded = calls[0]
    assert step == "checkEntriesQuery" and sys_p == "system" and usr_p == "user"
    assert forwarded == kwargs


@pytest.mark.parametrize(
    "lang, expected",
    [
        ("en", "Critical"),
        ("ita", "Critico"),
        ("spa", "Crítico"),
        ("xx", "Critical"),  # unknown language -> fallback to English labels
    ],
)
def test_get_severity_label_localization_and_fallback(lang, expected):
    # Arrange/Act
    label = get_severity_label("amount_mismatch", lang)

    # Assert
    assert label == expected


def test_get_severity_label_unknown_mismatch_defaults_to_minor_label():
    # Arrange/Act: unknown key -> MINOR severity -> German labels
    label = get_severity_label("not_a_key", "deu")

    # Assert
    assert label == "Gering"


@pytest.mark.parametrize("language", ("es", "spa", "spanish", "español", "espanol"))
def test_spanish_language_aliases_resolve_to_localized_runtime_copy(
    language: str,
) -> None:
    canonical = LANGUAGE_ALIASES[language]

    assert canonical == "spa"
    assert LANGUAGE_NAMES[canonical] == "Spanish"
    assert LOCALIZED_STRINGS[canonical]["manual_review"].startswith("El texto extraído")


def test_amount_match_on_keyword_line_no_mismatch():
    # Arrange
    entry = {"amount": "100.00", "date": ""}
    pdf_text = """
    Description line
    Total amount: 100.00 EUR
    Footer
    """.strip()

    # Act
    mismatches = _pre_llm_check(
        entry,
        pdf_text,
        lang_code="eng",
        amount_tolerance=0.0,
        date_window=0,
        timing_difference_window=None,
        beneficiary_similarity=100.0,
        beneficiary_check_mode=BeneficiaryCheckMode.OFF,
    )

    # Assert
    assert mismatches is None


def test_no_keyword_falls_back_to_all_amounts_no_mismatch():
    # Arrange: number present but no 'total'/'amount' or beneficiary keywords
    entry = {"amount": "100.0", "date": ""}
    pdf_text = "Paid to vendor: 100.00 on invoice 123"

    # Act
    mismatches = _pre_llm_check(
        entry,
        pdf_text,
        lang_code="eng",
        amount_tolerance=0.0,
        date_window=0,
        timing_difference_window=None,
        beneficiary_similarity=100.0,
        beneficiary_check_mode=BeneficiaryCheckMode.OFF,
    )

    # Assert
    assert mismatches is None


def test_keyword_line_mismatch_overrides_non_keyword_match():
    # Arrange: correct value exists but only on non-keyword line
    entry = {"amount": "100.0", "date": ""}
    pdf_text = """
    Value elsewhere 100.00
    Total due: 99.00
    """.strip()

    # Act
    mismatches = _pre_llm_check(
        entry,
        pdf_text,
        lang_code="eng",
        amount_tolerance=0.0,
        date_window=0,
        timing_difference_window=None,
        beneficiary_similarity=100.0,
        beneficiary_check_mode=BeneficiaryCheckMode.OFF,
    )

    # Assert
    assert mismatches is not None and len(mismatches) == 1
    mm = mismatches[0]
    assert mm["mismatch_type"] == "amount_mismatch"
    # Both amounts were extracted; line numbers should include both lines
    assert set(mm.get("line_numbers", [])) == {1, 2}


def test_beneficiary_keyword_enables_match_without_total_or_amount():
    # Arrange: beneficiary name appears on the line with the amount
    entry = {"amount": "100.0", "beneficiary": "ACME", "date": ""}
    pdf_text = "Payment to ACME: 100\nThanks"

    # Act
    mismatches = _pre_llm_check(
        entry,
        pdf_text,
        lang_code="eng",
        amount_tolerance=0.0,
        date_window=0,
        timing_difference_window=None,
        beneficiary_similarity=100.0,
        beneficiary_check_mode=BeneficiaryCheckMode.OFF,
    )

    # Assert
    assert mismatches is None
