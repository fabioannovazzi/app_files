import json
from pathlib import Path

import pytest

import src.category_lookup as category_lookup


@pytest.fixture(autouse=True)
def _category_market_context():
    """Provide industry context for category website lookups."""

    category_lookup.set_category_market_context(industry="cosmetics")
    yield
    category_lookup.set_category_market_context()


def test_load_mapping_normalizes_and_caches(tmp_path, monkeypatch):
    # Arrange
    mapping_file = tmp_path / "category_websites.json"
    mapping_file.write_text(
        json.dumps(
            {
                "Books": "https://books.example",
                "Toys": ["https://toys.example", 123],
            }
        )
    )
    monkeypatch.setattr(category_lookup, "FILE_PATH", mapping_file, raising=False)
    monkeypatch.setattr(category_lookup, "_WEBSITE_CACHE", None, raising=False)

    # Act
    first = category_lookup.load_mapping()

    # Assert
    assert first["Books"] == ["https://books.example"]
    # Lists are preserved as-is by load; inner non-strings are not filtered here
    assert first["Toys"] == ["https://toys.example", 123]

    # Mutate the file to ensure the cached result is reused on subsequent calls
    mapping_file.write_text(
        json.dumps({"Books": "changed", "New": "https://new.example"})
    )
    second = category_lookup.load_mapping()
    assert second is first  # served from cache
    assert second["Books"] == ["https://books.example"]
    assert "New" not in second


def test_load_mapping_invalid_json_returns_empty(tmp_path, monkeypatch):
    # Arrange
    mapping_file = tmp_path / "category_websites.json"
    mapping_file.write_text("{not json")
    monkeypatch.setattr(category_lookup, "FILE_PATH", mapping_file, raising=False)
    monkeypatch.setattr(category_lookup, "_WEBSITE_CACHE", None, raising=False)

    # Act
    mapping = category_lookup.load_mapping()

    # Assert
    assert mapping == {}


def test_lookup_category_websites_populates_and_persists_and_ignores_bad(
    tmp_path, monkeypatch
):
    # Arrange existing mapping file
    mapping_file = tmp_path / "category_websites.json"
    mapping_file.write_text(json.dumps({"Books": ["https://books.example"]}))
    monkeypatch.setattr(category_lookup, "FILE_PATH", mapping_file, raising=False)
    monkeypatch.setattr(category_lookup, "_WEBSITE_CACHE", None, raising=False)

    # Stub LLM batch runner to return deterministic results derived from prompts
    def fake_run_step_json(
        llm_wrapper,
        step,
        system,
        prompts,
        *,
        tools=None,
        tool_choice="auto",
        service_tier=None,
    ):  # noqa: D401
        if isinstance(prompts, str):
            prompts = [prompts]
        results = []
        for p in prompts:
            # Extract category between "product category '" and the next "'"
            try:
                cat = p.split("product category '", 1)[1].split("'", 1)[0]
            except Exception:
                cat = ""
            if cat == "Toys":
                results.append(
                    {"websites": ["https://toys.example", 42]}
                )  # non-string filtered later
            elif cat == "Garden":
                results.append(
                    {"website": "https://garden.example"}
                )  # singular accepted
            elif cat == "Broken":
                results.append({"unexpected": True})  # ignored
            else:
                results.append({})
        return results

    monkeypatch.setattr(
        category_lookup, "run_step_json", fake_run_step_json, raising=False
    )

    # Act
    categories = ["", "Books", "Toys", "Garden", "Toys", "Broken"]
    mapping = category_lookup.lookup_category_websites(None, categories)

    # Assert mapping content
    assert mapping["Books"] == ["https://books.example"]  # unchanged
    assert mapping["Toys"] == ["https://toys.example"]  # only strings kept
    assert mapping["Garden"] == ["https://garden.example"]  # normalized from singular
    assert "Broken" not in mapping  # ignored due to malformed response

    # Assert persisted file matches the in-memory mapping
    on_disk = json.loads(mapping_file.read_text())
    assert on_disk == mapping


def test_load_mapping_missing_dir_does_not_create(tmp_path, monkeypatch):
    mapping_file = tmp_path / "missing" / "category_websites.json"
    monkeypatch.setattr(category_lookup, "FILE_PATH", mapping_file, raising=False)
    monkeypatch.setattr(category_lookup, "_WEBSITE_CACHE", None, raising=False)
    category_lookup.load_mapping()
    assert not mapping_file.parent.exists()


def test_save_mapping_creates_parent_dir(tmp_path, monkeypatch):
    mapping_file = tmp_path / "missing" / "category_websites.json"
    monkeypatch.setattr(category_lookup, "FILE_PATH", mapping_file, raising=False)
    monkeypatch.setattr(category_lookup, "_WEBSITE_CACHE", None, raising=False)
    category_lookup._save_mapping({"Books": ["https://books.example"]})
    assert mapping_file.exists()
