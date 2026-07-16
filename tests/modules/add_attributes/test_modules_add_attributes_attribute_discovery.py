import types

import pytest

from modules.add_attributes import attribute_discovery as ad


def test_deduplicate_attributes_filters_similar_and_substrings_without_llm():
    # Arrange
    attributes = ["Color", "Weight", "price"]
    existing = ["color", "price_eur"]

    # Act
    result = ad.deduplicate_attributes(attributes, existing, llm_wrapper=None)

    # Assert
    assert result == ["Weight"]


def test_deduplicate_attributes_llm_keep_filters_results(monkeypatch):
    # Arrange
    attributes = ["Battery Life", "Durability", "Color"]
    existing = ["color", "size"]  # "Color" should be dropped before LLM step

    # Minimal naming params to satisfy access pattern
    monkeypatch.setattr(
        ad, "get_naming_params", lambda: {"attributeDiscoveryQuery": "attributeDiscoveryQuery"}
    )

    # Stub LLM JSON runner to return a keep list filtering to only "Durability"
    def fake_run_step_json(llm_wrapper, step, system_prompt, user_prompt, **kwargs):
        return [{"keep": ["Durability"]}]

    monkeypatch.setattr(ad, "run_step_json", fake_run_step_json)

    # Act
    result = ad.deduplicate_attributes(attributes, existing, llm_wrapper=object())

    # Assert
    assert result == ["Durability"]


def test_deduplicate_attributes_llm_ignores_bad_response(monkeypatch):
    # Arrange
    attributes = ["Battery", "Durability"]
    existing = []

    monkeypatch.setattr(
        ad, "get_naming_params", lambda: {"attributeDiscoveryQuery": "attributeDiscoveryQuery"}
    )

    # Return a malformed response (no "keep" list); function should keep original uniques
    def fake_run_step_json(llm_wrapper, step, system_prompt, user_prompt, **kwargs):
        return [{"not_keep": ["Battery"]}]

    monkeypatch.setattr(ad, "run_step_json", fake_run_step_json)

    # Act
    result = ad.deduplicate_attributes(attributes, existing, llm_wrapper=object())

    # Assert
    assert result == attributes


def test_discover_attributes_for_category_end_to_end_with_throttle(monkeypatch):
    # Arrange
    existing = ["color", "price_usd"]

    # Provide only what's needed by the code path
    monkeypatch.setattr(
        ad, "get_naming_params", lambda: {"attributeDiscoveryQuery": "attributeDiscoveryQuery"}
    )

    # Capture sleep calls to assert throttling without delaying the test
    sleep_calls: list[float] = []

    def fake_sleep(x: float) -> None:
        sleep_calls.append(x)

    monkeypatch.setattr(ad.time, "sleep", fake_sleep)

    # One stub covers both LLM calls by checking the system prompt
    def fake_run_step_json(llm_wrapper, step, system_prompt, user_prompt, **kwargs):
        if "expert product analyst" in system_prompt:
            # First call: suggest attributes (includes duplicates w.r.t. existing)
            return [{"attributes": ["Color", "Weight", "price"]}]
        # Second call from deduplicate_attributes: filter via keep list
        return [{"keep": ["Weight"]}]

    monkeypatch.setattr(ad, "run_step_json", fake_run_step_json)

    # Act
    result = ad.discover_attributes_for_category(object(), "Laptops", existing)

    # Assert
    assert result == ["Weight"]
    assert sleep_calls == [pytest.approx(1.0)]
