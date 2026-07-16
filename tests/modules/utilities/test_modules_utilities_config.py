import pytest

from modules.utilities.config import (
    get_currency_params,
    get_naming_params,
    get_run_params,
    select_provider,
)


def test_get_naming_params_idempotent_and_core_labels():
    # Arrange & Act
    n1 = get_naming_params()
    n2 = get_naming_params()

    # Assert: returns plain dicts with stable core labels
    assert isinstance(n1, dict) and isinstance(n2, dict)
    assert n1 == n2 and n1 is not n2

    # Core API labels used across the codebase
    assert n1["providerName"] == "provider"
    assert n1["modelName"] == "model"
    assert n1["openai"] == "OpenAI"
    assert n1["currencyDict"] == "currencyDict"
    assert isinstance(n1["batchModels"], list)
    assert isinstance(n1["flexModels"], list)
    assert n1["batchModels"] and all(isinstance(m, str) for m in n1["batchModels"])
    assert n1["flexModels"] and all(isinstance(m, str) for m in n1["flexModels"])

    # Mutating one result must not affect a fresh call
    n1["providerName"] = "mutated"
    assert get_naming_params()["providerName"] == "provider"


def test_get_run_params_expected_defaults_and_types():
    # Act
    rp = get_run_params()

    # Assert: core booleans and strings are as documented
    assert rp["beneficiaryCheckMode"] == "compare"
    assert rp["runChecksAndBold"] is True
    assert rp["runOpenAI"] is True
    assert rp["llmBatchMode"] is True

    # Logging flags contract and sensible numeric thresholds
    assert rp["show_user_errors"] is False
    assert rp["log_to_console"] is True
    assert rp["log_to_file"] is True
    assert isinstance(rp["log_file_max_bytes"], int) and rp["log_file_max_bytes"] > 0
    assert (
        isinstance(rp["log_file_backup_count"], int)
        and rp["log_file_backup_count"] >= 1
    )

    # Independence across calls
    rp["runOpenAI"] = False
    assert get_run_params()["runOpenAI"] is True


@pytest.mark.parametrize(
    "label,code",
    [
        ("US Dollar-USD", "USD"),
        ("Euro-EUR", "EUR"),
        ("Yen-JPY", "JPY"),
        ("Pound Sterling-GBP", "GBP"),
    ],
)
def test_get_currency_params_structure_and_known_mappings(label: str, code: str):
    # Arrange
    naming = get_naming_params()
    currency_key = naming["currencyDict"]

    # Act
    currencies_wrapper = get_currency_params()

    # Assert: single, named top-level key and expected mappings inside
    assert set(currencies_wrapper.keys()) == {currency_key}
    currencies = currencies_wrapper[currency_key]
    assert isinstance(currencies, dict)
    assert currencies[label] == code


def test_select_provider_maps_read_image_table_query() -> None:
    naming = get_naming_params()
    query = naming["readImageTableQuery"]
    provider_key = naming["providerName"]
    model_key = naming["modelName"]
    batch_key = naming["batchMode"]

    cfg = select_provider(query)

    assert cfg[provider_key] == naming["openai"]
    assert cfg[model_key] == naming["gpt5ThinkingMini"]
    assert cfg[batch_key] is False


def test_select_provider_maps_reasoned_judgement_query_to_openai() -> None:
    naming = get_naming_params()
    query = naming["reasonedJudgementQuery"]
    provider_key = naming["providerName"]
    model_key = naming["modelName"]
    batch_key = naming["batchMode"]

    cfg = select_provider(query)

    assert cfg[provider_key] == naming["openai"]
    assert cfg[model_key] == naming["gpt54Mini"]
    assert cfg[batch_key] is False


def test_select_provider_maps_launch_validation_review_query_to_openai() -> None:
    naming = get_naming_params()
    query = naming["launchValidationReviewQuery"]
    provider_key = naming["providerName"]
    model_key = naming["modelName"]
    batch_key = naming["batchMode"]

    cfg = select_provider(query)

    assert cfg[provider_key] == naming["openai"]
    assert cfg[model_key] == naming["gpt54Mini"]
    assert cfg[batch_key] is False


def test_select_provider_maps_llm_fallback_query_to_openai() -> None:
    naming = get_naming_params()
    query = naming["llmFallbackQuery"]
    provider_key = naming["providerName"]
    model_key = naming["modelName"]
    batch_key = naming["batchMode"]

    cfg = select_provider(query)

    assert cfg[provider_key] == naming["openai"]
    assert cfg[model_key] == naming["gpt54Mini"]
    assert cfg[batch_key] is False
